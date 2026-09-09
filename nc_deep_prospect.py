"""nc_deep_prospect.py — pipeline-integrated deep prospecting for no-contact NC estate rows.

Activates the existing heir-research engine (obituary survivors -> heir ranking
-> Tracerfy skip trace -> DM mailing address) against ONLY the rows in the
current weekly FTM workbook that have no living contact yet:

    - blank Personal Representative, OR a "Heirs of <Decedent>" placeholder, AND
    - no DM Name already filled, AND
    - a valid decedent name.

Those are exactly the rows Oren works by hand today. Everything with a
court-named PR or an already-discovered decision maker is skipped, so paid
sources (Serper / Firecrawl / Tracerfy) only ever touch no-contact rows.

This is a thin pipeline wrapper around the proven helpers in
`heir_prospect_no_executor.py` (row_to_notice / apply_notice_dm_to_row) plus
`obituary_enricher.enrich_obituary_data` and `tracerfy_skip_tracer.batch_skip_trace`.
The difference vs. that standalone script is I/O reconciliation: it operates on
the SAME per-week files `consolidate_weeks.py` reads, and writes results back to
a per-week `*_dm_enriched.csv` (registered as the highest consolidate priority)
so the enriched DM columns flow into the final workbook automatically.

Cost control:
    --dry-run        Count target rows + estimate cost. ZERO paid calls.
    --max-rows N     Hard cap rows processed this run (also: env NC_DP_MAX_ROWS).
    Only no-contact rows ever reach paid sources; reuses the persistent
    GIS / obituary caches so re-polished in-progress weeks don't re-pay.

Modes:
    (default)     Heir research + trace ONLY no-contact rows.
    --all-cases   ALSO Tracerfy + Trestle every row's contact (PR for named
                  rows, discovered heir for the rest) so the whole sheet has
                  phones + dial-priority before the DataSift upload.

Usage:
    python nc_deep_prospect.py --dry-run               # count + cost, no calls
    python nc_deep_prospect.py --all-cases --dry-run   # all-cases cost preview
    python nc_deep_prospect.py --all-cases             # trace + score everyone
    python nc_deep_prospect.py                         # no-contact rows only
    python nc_deep_prospect.py --all-weeks
    python nc_deep_prospect.py --csv output/nc_estates_ftm_..._week26_datasift.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402
from notice_parser import NoticeData  # noqa: E402
from obituary_enricher import enrich_obituary_data  # noqa: E402
from tracerfy_skip_tracer import batch_skip_trace  # noqa: E402
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402
# Reuse the proven row<->NoticeData mapping from the standalone heir script
# so there's one source of truth for how an FTM row becomes a search target.
from heir_prospect_no_executor import row_to_notice, apply_notice_dm_to_row, parse_file_date  # noqa: E402
from phone_validator import score_record_phones, clean_phone  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nc_deep_prospect")

# ── Cost estimate (DRY-RUN ONLY) ──────────────────────────────────────────
# Rough per-row figures for the paid sources a single no-contact row can hit.
# These are ESTIMATES for budgeting, not billed amounts — actual cost depends
# on cache hits (free), how many heirs get traced, and Firecrawl page counts.
#   - Web research: Serper search + Firecrawl render + Claude Haiku extract.
#   - Skip trace:   Tracerfy ~$0.02/contact, up to 5 heir traces/row.
# Override via env if your real numbers drift.
#   - Phone score:  Trestle ~$0.015/phone, a few DM/heir phones/row.
EST_COST_RESEARCH_PER_ROW = float(os.getenv("NC_DP_COST_RESEARCH", "0.05"))
EST_COST_SKIPTRACE_PER_ROW = float(os.getenv("NC_DP_COST_SKIPTRACE", "0.10"))
EST_COST_PHONESCORE_PER_ROW = float(os.getenv("NC_DP_COST_PHONESCORE", "0.05"))

# Actuals used for the --all-cases estimate (one trace per row, a few phones each).
TRACERFY_PER_RECORD = 0.02        # tracerfy_skip_tracer batch endpoint
TRESTLE_PER_PHONE = 0.015         # phone_validator.COST_PER_PHONE
EST_PHONES_PER_RECORD = float(os.getenv("NC_DP_EST_PHONES", "3"))
ENFORMION_PER_MATCH = 0.35        # enformion_client — billed per MATCH, misses free

DEFAULT_MAX_ROWS = int(os.getenv("NC_DP_MAX_ROWS", "50"))

# How many weeks back a run revisits (1 = latest week only, the pre-2026-09-09
# behaviour). An obituary is rarely published, let alone indexed, in the days
# after the estate is filed -- which was the entire window a case used to get.
DEFAULT_WEEKS_BACK = int(os.getenv("NC_DP_WEEKS_BACK", "4"))
# Per-file cap for the CATCH-UP weeks (the newest week keeps DEFAULT_MAX_ROWS).
# Deliberately small: those weeks are re-read every night, so the work is spread
# out rather than done in one burst, and most rows answer free from the obituary
# disk cache until their 4-day miss entry expires.
DEFAULT_BACKFILL_MAX_ROWS = int(os.getenv("NC_DP_BACKFILL_MAX_ROWS", "20"))
# Share of researched no-contact rows that actually yield a person, used only
# to keep the catch-up weeks' DRY-RUN estimate honest (they pay for a trace
# only when research finds someone). ~1 in 4 across the 2026-07/08 nightlies.
_RESOLVE_RATE = float(os.getenv("NC_DP_RESOLVE_RATE", "0.25"))


def is_target_row(row: dict) -> bool:
    """True when a row has no living contact yet and is worth researching.

    Targets: blank Personal Representative OR a "Heirs of <Decedent>"
    placeholder, with no DM Name already filled and a real decedent name.
    """
    dm = (row.get("DM Name") or "").strip().lower()
    if dm and not dm.startswith(("estate of", "heirs of")):
        return False  # already has a discovered decision maker
    # ("Estate of"/"Heirs of" DMs are placeholders, not people — the
    # enricher's old estate fallback wrote a bare "Estate of" on no-PR rows,
    # which made exactly the rows that need research look already-done.)
    decedent = (row.get("Deceased Owner") or "").strip()
    if not decedent or "IN THE MATTER" in decedent.upper():
        return False
    pr = (row.get("Personal Representative") or "").strip()
    if not pr:
        return True
    if pr.lower().startswith("heirs of"):
        return True
    return False


def build_trace_notice(row: dict) -> tuple[NoticeData | None, str, str]:
    """Build a NoticeData to skip-trace this row's BEST existing contact.

    Returns (notice, phone_col, tier_col); (None, "", "") when there's no
    contact to trace (no PR, no DM — a no-contact row Phase 1 couldn't crack).

      - Named PR  -> trace the PR as a living owner at their mailing address
                     (their own home), phone lands in "Phone 1".
      - DM / heir -> trace the discovered decision maker, phone -> "DM Phone".

    Used only by --all-cases (Phase 2). The PR branch is the common case;
    the DM branch covers no-contact rows Phase 1 just resolved to an heir.
    """
    county = row.get("County", "")
    date_added = parse_file_date(row.get("File Date", ""))
    prop_addr = row.get("Property Address", "")
    prop_city = row.get("Property City", "")
    prop_zip = row.get("Property Zip", "")

    pr = (row.get("Personal Representative") or "").strip()
    if pr and not pr.lower().startswith("heirs of"):
        first = (row.get("First Name") or "").strip()
        last = (row.get("Last Name") or "").strip()
        owner = f"{first} {last}".strip() or pr
        n = NoticeData(
            notice_type="probate", county=county, state="NC", date_added=date_added,
            owner_name=owner, owner_deceased="no",
            # Trace the PR at their own mailing address (falls back to property).
            address=(row.get("Mailing Address") or prop_addr),
            city=(row.get("Mailing City") or prop_city),
            zip=(row.get("Mailing Zip") or prop_zip),
        )
        return n, "Phone 1", "Phone 1 Tier"

    dm = (row.get("DM Name") or "").strip()
    # Never pay to trace a placeholder — "Estate of"/"Heirs of" is not a
    # person, so Tracerfy/Trestle spend on it is guaranteed-empty.
    if dm.lower().startswith(("estate of", "heirs of")):
        dm = ""
    if dm:
        n = NoticeData(
            notice_type="probate", county=county, state="NC", date_added=date_added,
            decedent_name=row.get("Deceased Owner", ""), owner_deceased="yes",
            decision_maker_name=dm,
            address=prop_addr, city=prop_city, zip=prop_zip,
        )
        return n, "DM Phone", "DM Phone Tier"

    return None, "", ""


def trace_target(row: dict) -> tuple[NoticeData | None, str, str]:
    """build_trace_notice, but skips rows already traced on a prior run.

    The daily build re-runs on the same in-progress week each night, reading
    back its own `_dm_enriched.csv`. Tracerfy/Trestle calls aren't cached, so
    without this guard every row would be re-traced (and re-billed) nightly.
    A populated destination phone column means we already paid for it — skip.
    Returns (None, "", "") to skip; otherwise the trace notice + dest columns.
    """
    tn, phone_col, tier_col = build_trace_notice(row)
    if tn is None:
        return None, "", ""
    if (row.get(phone_col) or "").strip():
        return None, "", ""  # already has a phone from a prior run — don't re-pay
    return tn, phone_col, tier_col


def _mark_reason(row: dict, code: str) -> None:
    """Append an audit code to Match Reason (same convention as the polish
    pipeline's tag_reason: ' | '-joined kebab codes, idempotent)."""
    existing = (row.get("Match Reason") or "").strip()
    parts = [p.strip() for p in existing.split("|") if p.strip()]
    if code not in parts:
        parts.append(code)
        row["Match Reason"] = " | ".join(parts)


def _enformion_fallback_pr_phones(trace_notices: list, meta: dict,
                                  src_name: str) -> tuple[int, int]:
    """Enformion PersonSearch on named PRs that Tracerfy couldn't crack.

    Scope is deliberately the PR branch ONLY (phone_col == "Phone 1"): there
    the notice's address is the PR's OWN mailing address, which is the anchor
    Enformion needs ("City, ST ZIP" — name+city alone is rejected, and
    anchoring a DM to the PROPERTY address would risk matching the wrong
    same-named person). ~$0.35 per match, misses free, hits disk-cached 14d.

    Fills the notice's phone fields IN PLACE so the existing Trestle scoring
    and row-apply loop downstream pick the numbers up like any Tracerfy
    result. Rows getting an Enformion phone are marked "enformion-phone" in
    Match Reason (flows to a DataSift tag — honest phone-source labeling);
    a PR Enformion reports as deceased gets flagged for review instead,
    never called. Returns (rows_filled, deceased_flagged).
    """
    candidates = []
    for tn in trace_notices:
        row, phone_col, _tier = meta[id(tn)]
        if phone_col != "Phone 1":
            continue  # PR branch only — see docstring
        if tn.primary_phone or tn.mobile_1 or tn.landline_1:
            continue  # Tracerfy delivered; no fallback needed
        if not (row.get("Mailing Zip") or "").strip():
            continue  # no ZIP anchor -> search would be rejected/unsafe
        candidates.append(tn)
    if not candidates:
        return 0, 0

    import enformion_client
    if not enformion_client.enabled():
        logger.info("%s: Enformion fallback: %d PR row(s) still phone-less after "
                    "Tracerfy — skipped (%s)", src_name, len(candidates),
                    "NC_ENFORMION=0" if enformion_client.credentials_present()
                    else "ENFORMION_AP_NAME/ENFORMION_AP_PASSWORD not set")
        return 0, 0

    filled = flagged = 0
    logger.info("%s: Enformion fallback on %d phone-less PR row(s) "
                "(~$%.2f worst case)...", src_name, len(candidates),
                len(candidates) * ENFORMION_PER_MATCH)
    for tn in candidates:
        row = meta[id(tn)][0]
        res = enformion_client.person_search_phones(
            row.get("First Name", ""), row.get("Last Name", ""),
            row.get("Mailing City", ""), row.get("Mailing State", "") or "NC",
            row.get("Mailing Zip", ""))
        if res is None:
            continue  # miss — free
        if res.get("is_deceased"):
            # PR died during probate — a lead-changing fact, not a call target.
            _mark_reason(row, "enformion-pr-deceased")
            notes = (row.get("Notes") or "").strip()
            note = ("[ENFORMION: PR appears DECEASED in the death index — "
                    "verify; the estate may need a successor PR]")
            if note not in notes:
                row["Notes"] = (notes + "\n" + note).strip()
            logger.warning("  %s/%s: PR %s reported deceased by Enformion — "
                           "flagged, not called", row.get("County"),
                           row.get("Case No."), row.get("Last Name"))
            flagged += 1
            continue
        if not res.get("primary"):
            continue  # matched (billed) but no usable phone
        tn.primary_phone = res["primary"]
        for i, m in enumerate(res.get("mobiles", [])[:5], start=1):
            setattr(tn, f"mobile_{i}", m)
        for i, l in enumerate(res.get("landlines", [])[:3], start=1):
            setattr(tn, f"landline_{i}", l)
        _mark_reason(row, "enformion-phone")
        filled += 1
    logger.info("%s: Enformion filled phones for %d row(s), flagged %d "
                "deceased PR(s) - billed $%.2f this run%s", src_name, filled,
                flagged, enformion_client.spend_this_run(),
                " (SPEND CAP HIT)" if enformion_client.cap_reached() else "")
    return filled, flagged


def enriched_output_path(src: Path) -> Path:
    """Derive the `*_dm_enriched.csv` sibling for a per-week input file.

    Strips the trailing source-stage token (`_datasift` / `_ecourts_backfilled`)
    and appends `_dm_enriched`, preserving the `_YYYY-MM-DD_` date and `_weekN`
    tokens that consolidate_weeks.py greps for.

    `_dm_enriched` is stripped too, so re-enriching a week UPDATES that week's
    file instead of growing a chain. The source is very often already enriched:
    consolidate's auto-pick prefers the most-enriched file, so any night with no
    fresh scrape for a week hands us our own previous output. Before the
    2026-09-09 catch-up window that was rare enough to go unnoticed; with four
    weeks re-read nightly it would have produced
    `..._week36_dm_enriched_dm_enriched_dm_enriched.csv` and so on, one link per
    night. Those names DO still match consolidate's glob, so nothing was lost --
    it was clutter and an ever-lengthening filename, not data loss.
    """
    stem = src.stem  # filename without .csv
    for token in ("_ecourts_backfilled", "_datasift", "_dm_enriched"):
        if stem.endswith(token):
            stem = stem[: -len(token)]
            break
    return src.with_name(f"{stem}_dm_enriched.csv")


def _upload_output_path(src: Path) -> Path | None:
    """The `*_datasift_upload.csv` the polish wrote for this same week.

    Only returned for a `_datasift.csv` input -- that is the one whose upload
    sibling the polish pipeline produces. Returns None otherwise so an
    `_ecourts_backfilled` or ad-hoc `--csv` run never invents a new upload file.
    """
    if not src.stem.endswith("_datasift"):
        return None
    return src.with_name(f"{src.stem}_upload.csv")


def select_target_files(all_weeks: bool, explicit_csv: str | None,
                        weeks_back: int = DEFAULT_WEEKS_BACK) -> list[Path]:
    """Pick the per-week file(s) consolidate would use, newest week first.

    Mirrors consolidate's auto-pick so we enrich the exact file that ends up
    in the workbook.

    `weeks_back` is how many weeks of CATCH-UP the run covers (1 = the old
    behaviour, latest week only). Deep prospecting used to see exactly one
    week, which quietly capped every case at ~4-5 nightly research passes, all
    of them in the first days after filing -- before any obituary is published.
    Traced 2026-09-09: Week 36 got passes 8/31-9/4, then the run moved to Week
    37 and never looked back, leaving seven cases whose obituary (with named
    survivors) had since landed in the cache with nobody left to read it.

    Archived weeks are INCLUDED here on purpose. Archiving is only a marker
    directory (output/archive_week<N>_done) -- the weekly CSVs never move, stay
    writable, and a `*_dm_enriched.csv` written for an archived week is still
    the highest-priority pick for that week's workbook tab. What "frozen" means
    is that the polish pipeline stops re-walking them, not that they are
    read-only.
    """
    if explicit_csv:
        p = Path(explicit_csv)
        if not p.exists():
            logger.error("CSV not found: %s", p)
            sys.exit(1)
        return [p]

    # Reuse consolidate's selection logic verbatim.
    sys.path.insert(0, str(Path(__file__).parent))
    from consolidate_weeks import auto_pick_weekly_files

    by_week = auto_pick_weekly_files(include_archived=weeks_back > 1)
    if not by_week:
        logger.warning("No per-week consolidate-input files found in output/.")
        return []
    # Sort by (year, week) descending -> newest first.
    ordered = [by_week[k] for k in sorted(by_week, reverse=True)]
    if all_weeks:
        return ordered
    return ordered[:max(1, weeks_back)]


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def process_file(
    src: Path,
    *,
    dry_run: bool,
    all_cases: bool,
    max_rows: int,
    max_heir_depth: int,
    skip_heir_verification: bool,
    skip_dm_address: bool,
    skip_skip_trace: bool,
    skip_phone_score: bool,
    skip_enformion: bool = False,
    trace_only_found: bool = False,
) -> dict:
    """Enrich one per-week file. Returns a stats dict.

    Phase 1 (always): heir research on no-contact rows -> fills DM Name.
    Phase 2 (--all-cases): Tracerfy + Trestle EVERY row's contact (the PR for
    named rows, the discovered heir for the rest) so the whole sheet has phones
    + dial-priority before the DataSift upload. No double-charge: in all-cases
    mode Phase 1 does research only and Phase 2 does the single trace per row.

    trace_only_found: pay to trace ONLY the rows where research just produced a
    person. Set for the catch-up weeks, which are re-read every night: without
    it each pass would re-bill Tracerfy for the same still-nameless estates,
    and tracing a row with no decision maker traces the decedent, which is
    money spent on a dead end.
    """
    rows = _load_rows(src)
    research_targets = [r for r in rows if is_target_row(r)]
    stats = {
        "file": src.name,
        "total_rows": len(rows),
        "targets": len(research_targets),
        "capped_out": 0,
        "dm_filled": 0,
        "traced": 0,
        "tiers_scored": 0,
        "output": "",
    }

    # The cap bounds the EXPENSIVE heir-research subset (obituary/Firecrawl).
    if max_rows and len(research_targets) > max_rows:
        stats["capped_out"] = len(research_targets) - max_rows
        logger.warning("%s: %d research targets exceeds cap of %d — researching %d, "
                       "DEFERRING %d (raise --max-rows / NC_DP_MAX_ROWS to cover all)",
                       src.name, len(research_targets), max_rows, max_rows, stats["capped_out"])
        research_targets = research_targets[:max_rows]

    if dry_run:
        if all_cases:
            traceable = sum(1 for r in rows if trace_target(r)[0] is not None)
            research_cost = len(research_targets) * EST_COST_RESEARCH_PER_ROW
            trace_cost = 0.0 if skip_skip_trace else traceable * TRACERFY_PER_RECORD
            score_cost = (0.0 if (skip_phone_score or skip_skip_trace)
                          else traceable * EST_PHONES_PER_RECORD * TRESTLE_PER_PHONE)
            est = research_cost + trace_cost + score_cost
            logger.info("%s: %d rows | ALL-CASES: %d traceable, %d need heir research -> "
                        "est ~$%.2f (research ~$%.2f + tracerfy ~$%.2f + trestle ~$%.2f) (DRY RUN)",
                        src.name, len(rows), traceable, len(research_targets),
                        est, research_cost, trace_cost, score_cost)
            # Enformion fallback ceiling: PR-branch rows with a ZIP anchor and
            # no phone yet. Only rows Tracerfy ALSO misses get searched, and
            # only matches bill — so the real spend is well under this.
            enf_eligible = 0
            if not (skip_skip_trace or skip_enformion):
                for r in rows:
                    tn, phone_col, _t = trace_target(r)
                    if (tn is not None and phone_col == "Phone 1"
                            and (r.get("Mailing Zip") or "").strip()):
                        enf_eligible += 1
            if enf_eligible:
                import enformion_client
                gate = ("ACTIVE" if enformion_client.enabled() else
                        ("off: NC_ENFORMION=0" if enformion_client.credentials_present()
                         else "inert: no ENFORMION_AP_NAME/PASSWORD in .env"))
                logger.info("%s: Enformion fallback [%s]: up to %d PR lookups if "
                            "Tracerfy misses all -> ceiling ~$%.2f (billed per "
                            "match; misses free; 14-day cache)",
                            src.name, gate, enf_eligible,
                            enf_eligible * ENFORMION_PER_MATCH)
        else:
            # Under trace_only_found the trace + score are paid ONLY for rows
            # where research turns up a person, so charging every target for
            # them (as the plain estimate does) overstates a catch-up week
            # several-fold. Bill the research to everyone and the trace to the
            # share that historically resolves.
            trace_share = _RESOLVE_RATE if trace_only_found else 1.0
            est = len(research_targets) * (
                EST_COST_RESEARCH_PER_ROW
                + trace_share * (0.0 if skip_skip_trace else EST_COST_SKIPTRACE_PER_ROW)
                + trace_share * (0.0 if (skip_phone_score or skip_skip_trace)
                                 else EST_COST_PHONESCORE_PER_ROW)
            )
            logger.info("%s: %d rows, %d no-contact targets%s -> est ~$%.2f (DRY RUN, no calls%s)",
                        src.name, len(rows), len(research_targets),
                        f" (+{stats['capped_out']} deferred by cap)" if stats["capped_out"] else "",
                        est,
                        "; ceiling — obituary cache hits are free" if trace_only_found else "")
        stats["est_cost"] = est
        return stats

    # ── Phase 1: heir research on no-contact rows (fills DM Name) ───────────
    if research_targets:
        if not config.ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set — required for obituary LLM extraction. "
                         "Skipping heir research for this file.")
        else:
            notices = [row_to_notice(r) for r in research_targets]
            notice_to_row = {id(n): r for n, r in zip(notices, research_targets, strict=True)}
            logger.info("%s: Phase 1 — researching %d no-contact rows (heir depth=%d)...",
                        src.name, len(notices), max_heir_depth)
            enrich_obituary_data(
                notices, config.ANTHROPIC_API_KEY,
                skip_heir_verification=skip_heir_verification,
                max_heir_depth=max_heir_depth,
                skip_dm_address=skip_dm_address,
                tracerfy_tier1=False,
                skip_ancestry=True,  # Ancestry SSDI is Knox-tested only; off for NC
            )
            obit_hits = sum(1 for n in notices if (n.decision_maker_name or "").strip())
            logger.info("%s: Phase 1 found a DM for %d/%d rows", src.name, obit_hits, len(notices))

            # In all-cases mode, defer ALL tracing to Phase 2 (one trace/row).
            # In default mode, trace + score the freshly-found DMs here.
            phase1_scores: dict = {}
            if not all_cases and not skip_skip_trace and config.TRACERFY_API_KEY:
                to_trace = ([n for n in notices if (n.decision_maker_name or "").strip()]
                            if trace_only_found else notices)
                if not to_trace:
                    logger.info("%s: no new decision maker found — nothing to trace.",
                                src.name)
                else:
                    logger.info("%s: Tracerfy skip trace on %d row(s)%s "
                                "(up to 5 heir traces/row)...", src.name, len(to_trace),
                                " with a freshly-found DM" if trace_only_found else "")
                    batch_skip_trace(to_trace, max_signing_traces=5,
                                     lookup_heir_addresses=True,
                                     address_lookup_api_key=config.ANTHROPIC_API_KEY)
                    if not skip_phone_score and config.TRESTLE_API_KEY:
                        phase1_scores = score_record_phones(to_trace, config.TRESTLE_API_KEY)

            for n in notices:
                row = notice_to_row[id(n)]
                if apply_notice_dm_to_row(row, n):
                    stats["dm_filled"] += 1
                if phase1_scores:
                    tier = phase1_scores.get(clean_phone(row.get("DM Phone", "")), {}).get("tier", "")
                    if tier:
                        row["DM Phone Tier"] = tier
                        stats["tiers_scored"] += 1

    # ── Phase 2: all-cases trace + score (PR phones + any heir phones) ──────
    if all_cases and not skip_skip_trace:
        if not config.TRACERFY_API_KEY:
            logger.warning("%s: TRACERFY_API_KEY not set — skipping all-cases trace", src.name)
        else:
            trace_notices: list[NoticeData] = []
            meta: dict[int, tuple[dict, str, str]] = {}
            for r in rows:
                tn, phone_col, tier_col = trace_target(r)
                if tn is not None:
                    trace_notices.append(tn)
                    meta[id(tn)] = (r, phone_col, tier_col)
            logger.info("%s: Phase 2 — tracing %d contacts (PR + discovered heirs; "
                        "rows already traced are skipped)...", src.name, len(trace_notices))
            if trace_notices:
                batch_skip_trace(trace_notices, max_signing_traces=5, lookup_heir_addresses=True,
                                 address_lookup_api_key=config.ANTHROPIC_API_KEY)
                # Enformion fallback for named PRs Tracerfy couldn't crack —
                # runs BEFORE Trestle so its phones get dial-priority tiers
                # like any other number. Inert without creds; NC_ENFORMION=0.
                if not skip_enformion:
                    stats["enformion_filled"], stats["enformion_deceased"] = (
                        _enformion_fallback_pr_phones(trace_notices, meta, src.name))
                scores: dict = {}
                if not skip_phone_score and config.TRESTLE_API_KEY:
                    logger.info("%s: Trestle phone scoring (dial priority)...", src.name)
                    scores = score_record_phones(trace_notices, config.TRESTLE_API_KEY)
                for tn in trace_notices:
                    row, phone_col, tier_col = meta[id(tn)]
                    phone = (tn.primary_phone or getattr(tn, "mobile_1", "")
                             or getattr(tn, "landline_1", ""))
                    if phone:
                        row[phone_col] = phone
                        stats["traced"] += 1
                        tier = scores.get(clean_phone(phone), {}).get("tier", "")
                        if tier:
                            row[tier_col] = tier
                            stats["tiers_scored"] += 1
                    email = getattr(tn, "email_1", "")
                    if email and phone_col == "DM Phone" and not (row.get("DM Email") or "").strip():
                        row["DM Email"] = email

    out_csv = enriched_output_path(src)
    out_xlsx = out_csv.with_suffix(".xlsx")
    write_csv(rows, out_csv)
    write_xlsx(rows, out_xlsx)
    stats["output"] = out_csv.name

    # Refresh the DataSift upload CSV with what we just found. The polish wrote
    # it BEFORE this step ran, so it carries only the pipeline's own
    # people-search phones -- every Tracerfy number and Trestle tier found here
    # was landing in the workbook and never reaching the CRM (Week 30: upload
    # had 3/53 phones, this file 39/53). Same filename the polish used, so
    # upload_netnew_datasift.py picks up the refreshed one.
    upload_csv = _upload_output_path(src)
    if upload_csv is not None:
        try:
            from nc_datasift_export import write_datasift_upload_csv
            wk_m = re.search(r"week(\d+)", src.stem)
            write_datasift_upload_csv(rows, upload_csv,
                                      week=int(wk_m.group(1)) if wk_m else None)
            stats["upload_refreshed"] = upload_csv.name
            logger.info("refreshed DataSift upload CSV -> %s", upload_csv.name)
        except Exception as e:  # never let this sink an otherwise-good run
            logger.warning("could not refresh DataSift upload CSV: %s", e)
    logger.info("%s: DM filled %d | phones traced %d (%d via Enformion) | "
                "tier-scored %d -> %s",
                src.name, stats["dm_filled"], stats["traced"],
                stats.get("enformion_filled", 0), stats["tiers_scored"], out_csv.name)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Count target rows + estimate cost. Makes ZERO paid calls.")
    ap.add_argument("--all-weeks", action="store_true",
                    help="Process every non-archived week (default: latest week only).")
    ap.add_argument("--all-cases", action="store_true",
                    help="Tracerfy + Trestle EVERY row's contact (not just no-contact "
                         "rows): the PR for named rows, the discovered heir for the rest. "
                         "Phones land in Phone 1 / DM Phone with dial-priority tiers.")
    ap.add_argument("--csv", default=None,
                    help="Process one explicit per-week CSV (overrides auto-pick).")
    ap.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS,
                    help=f"Cap target rows per file (default {DEFAULT_MAX_ROWS}; "
                         "env NC_DP_MAX_ROWS). 0 = no cap.")
    ap.add_argument("--max-heir-depth", type=int, default=2,
                    help="Obituary heir-verification depth (default 2).")
    ap.add_argument("--skip-heir-verification", action="store_true",
                    help="Skip living-status verification (faster, less accurate).")
    ap.add_argument("--skip-dm-address", action="store_true",
                    help="Skip DM mailing-address lookup (saves Firecrawl calls).")
    ap.add_argument("--skip-skip-trace", action="store_true",
                    help="Skip Tracerfy phone stage (no phone cost).")
    ap.add_argument("--skip-phone-score", action="store_true",
                    help="Skip Trestle dial-priority scoring of the DM phone.")
    ap.add_argument("--weeks-back", type=int, default=DEFAULT_WEEKS_BACK,
                    help=f"How many weeks back to revisit (default {DEFAULT_WEEKS_BACK}; "
                         "env NC_DP_WEEKS_BACK). 1 = latest week only. Obituaries "
                         "are usually published AFTER the estate is filed, so a "
                         "one-week window misses most of them.")
    ap.add_argument("--backfill-max-rows", type=int, default=DEFAULT_BACKFILL_MAX_ROWS,
                    help=f"Per-file research cap for the catch-up weeks (default "
                         f"{DEFAULT_BACKFILL_MAX_ROWS}; env NC_DP_BACKFILL_MAX_ROWS). "
                         "The newest week uses --max-rows.")
    ap.add_argument("--skip-enformion", action="store_true",
                    help="Skip the Enformion PersonSearch fallback for phone-less "
                         "named PRs (~$0.35/match; also: env NC_ENFORMION=0; "
                         "inert anyway unless ENFORMION_AP_NAME/PASSWORD are set).")
    args = ap.parse_args()

    files = select_target_files(args.all_weeks, args.csv, args.weeks_back)
    if not files:
        logger.info("No files to process.")
        return

    logger.info("%s deep prospecting over %d file(s):%s",
                "DRY RUN" if args.dry_run else "Running", len(files),
                " (latest week)" if len(files) == 1 and not args.csv else
                f" (latest week + {len(files) - 1} catch-up week(s))"
                if not args.all_weeks and not args.csv else "")

    all_stats = []
    for i, fp in enumerate(files):
        # Only the newest week gets the full all-cases treatment. The catch-up
        # weeks are re-read every night, so they research and trace ONLY what
        # is still nameless -- re-running all-cases over them would re-bill
        # Tracerfy/Enformion/Trestle for rows that already have their phones.
        catch_up = i > 0 and not args.csv and not args.all_weeks
        if catch_up:
            logger.info("--- catch-up week: %s (research only, cap %d)",
                        fp.name, args.backfill_max_rows)
        all_stats.append(process_file(
            fp,
            dry_run=args.dry_run,
            all_cases=args.all_cases and not catch_up,
            max_rows=args.backfill_max_rows if catch_up else args.max_rows,
            max_heir_depth=args.max_heir_depth,
            skip_heir_verification=args.skip_heir_verification,
            skip_dm_address=args.skip_dm_address,
            skip_skip_trace=args.skip_skip_trace,
            skip_phone_score=args.skip_phone_score,
            skip_enformion=args.skip_enformion,
            trace_only_found=catch_up,
        ))

    # ── Summary ───────────────────────────────────────────────────────────
    total_targets = sum(s["targets"] for s in all_stats)
    total_capped = sum(s["capped_out"] for s in all_stats)
    logger.info("=" * 64)
    if args.dry_run:
        total_est = sum(s.get("est_cost", 0.0) for s in all_stats)
        logger.info("DRY RUN complete: %d no-contact target rows across %d file(s)",
                    total_targets, len(all_stats))
        if total_capped:
            logger.info("  (%d rows would be DEFERRED by the --max-rows cap)", total_capped)
        logger.info("  Estimated cost if run: ~$%.2f  (rough — see EST_COST_* constants)",
                    total_est)
        logger.info("  Re-run without --dry-run to enrich.")
    else:
        total_filled = sum(s["dm_filled"] for s in all_stats)
        total_traced = sum(s["traced"] for s in all_stats)
        total_scored = sum(s["tiers_scored"] for s in all_stats)
        total_enf = sum(s.get("enformion_filled", 0) for s in all_stats)
        total_enf_dec = sum(s.get("enformion_deceased", 0) for s in all_stats)
        logger.info("Deep prospecting complete: %d DM names found, %d phones traced "
                    "(%d via Enformion fallback), %d phones tier-scored",
                    total_filled, total_traced, total_enf, total_scored)
        if total_enf_dec:
            logger.warning("  %d PR(s) reported DECEASED by Enformion — see "
                           "'enformion-pr-deceased' in Match Reason", total_enf_dec)
        if total_capped:
            logger.info("  %d rows deferred by cap — raise --max-rows to cover them next run",
                        total_capped)
        for s in all_stats:
            if s["output"]:
                logger.info("  %s -> %s", s["file"], s["output"])


if __name__ == "__main__":
    main()
