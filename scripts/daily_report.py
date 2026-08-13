"""Daily NC pipeline report.

Runs as the final step of the 6 PM daily build. Reads the day's outputs,
builds a plain-text report, writes it to output/daily_report_YYYY-MM-DD.txt,
and optionally emails it via Gmail/Workspace SMTP.

Configured via .env (already loaded by the pipeline):
  SMTP_USER       — sender Gmail/Workspace address (e.g. oren@remedihomesolutions.com)
  SMTP_PASS       — Google app password (NOT your regular password)
  REPORT_TO       — comma-separated recipient list
  SMTP_HOST       — defaults to smtp.gmail.com
  SMTP_PORT       — defaults to 587 (TLS)

To run by hand:
    .venv\\Scripts\\python.exe scripts\\daily_report.py
    .venv\\Scripts\\python.exe scripts\\daily_report.py --no-email
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import smtplib
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from openpyxl import load_workbook

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


OUTPUT = Path("output")
LOGS = Path("logs")
# Running deep-prospecting ledger (repo root, committed). Every DP run —
# whether it produced a research doc or just an address/phone fix — appends a
# row here; the report's DEEP PROSPECTING section reads it (Oren, 2026-08-12).
DP_LOG = Path("dp_log.csv")


def read_dp_log() -> list[dict]:
    if not DP_LOG.exists():
        return []
    try:
        with DP_LOG.open(newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.DictReader(f) if (r.get("Case No.") or "").strip()]
    except OSError:
        return []


# ── Discovery ────────────────────────────────────────────────────────


def find_latest_workbook() -> Path | None:
    candidates = sorted(OUTPUT.glob("FTM_*_NC_Estates_throughWeek*.xlsx"))
    return candidates[-1] if candidates else None


def find_latest_datasift(week_n: int) -> Path | None:
    files = sorted(OUTPUT.glob(f"nc_estates_ftm_*_week{week_n}_datasift.csv"))
    return files[-1] if files else None


def find_yesterdays_datasift(week_n: int, today_path: Path) -> Path | None:
    """Datasift from a prior run — used to compute 'new today'."""
    files = sorted(OUTPUT.glob(f"nc_estates_ftm_*_week{week_n}_datasift.csv"))
    older = [f for f in files if f != today_path]
    return older[-1] if older else None


def find_latest_heir_transfer(week_n: int) -> Path | None:
    files = sorted(OUTPUT.glob(f"heir_transfer_review_week{week_n}_*.xlsx"))
    return files[-1] if files else None


# ── Parse outputs ────────────────────────────────────────────────────


def read_workbook_cases(wb_path: Path) -> tuple[int, list[dict]]:
    wb = load_workbook(wb_path, read_only=True)
    rows: list[dict] = []
    week_n = 0
    for sn in wb.sheetnames:
        m = re.search(r"Week (\d+)", sn)
        if m:
            week_n = max(week_n, int(m.group(1)))
        ws = wb[sn]
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            continue
        header = [str(c or "").strip() for c in all_rows[0]]
        for r in all_rows[1:]:
            d = {header[i]: r[i] for i in range(min(len(header), len(r)))}
            if (d.get("Case No.") or "").strip():
                d["_tab"] = sn
                rows.append(d)
    return week_n, rows


def read_csv_cases(path: Path) -> list[dict]:
    if not path or not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if (r.get("Case No.") or "").strip()]


def read_heir_transfer(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(c or "").strip() for c in rows[0]]
    out = []
    for r in rows[1:]:
        d = {header[i]: r[i] for i in range(min(len(header), len(r)))}
        if d.get("Case No."):
            out.append(d)
    return out


_DROP_PATTERNS = {
    "no_parcel":     re.compile(r"Dropped \(no parcel\): (\d+)"),
    "over_500k":     re.compile(r"Dropped >\$500K: (\d+)"),
    "heir_occupied": re.compile(r"Dropped heir-occupied: (\d+)"),
    "commercial":    re.compile(r"Dropped commercial: (\d+)"),
    "archive_dupe":  re.compile(r"Dropped archive-duplicate rows: (\d+)"),
    "non_pending":   re.compile(r"Dropped non-Pending: (\d+)"),
    "repick":        re.compile(r"REPICK "),
    "refound":       re.compile(r"Re-found correct parcels: (\d+)"),
    "under_min_value": re.compile(r"Dropped under-min-value: (\d+)"),
}


def parse_polish_log(log_path: Path, since: datetime | None = None) -> dict:
    """Parse polish log for drop counts + matcher events. Robust to UTF-8/UTF-16."""
    out = {k: 0 for k in _DROP_PATTERNS}
    if not log_path.exists():
        return out
    # Try UTF-8 first, fall back to UTF-16
    text = ""
    for enc in ("utf-8", "utf-16-le", "utf-16"):
        try:
            text = log_path.read_text(encoding=enc, errors="ignore")
            if text:
                break
        except (OSError, UnicodeDecodeError):
            continue
    if since is not None:
        # Keep only lines from today's run boundary onward
        cutoff = since.strftime("%H:%M")
        marker = f"=== Daily run started"
        if marker in text:
            text = text[text.rindex(marker):]
    for key, pat in _DROP_PATTERNS.items():
        matches = pat.findall(text)
        if key == "repick":
            out[key] = len(matches)
            continue
        # Sum all matches — polish processes multiple weeks in one run, each
        # producing its own "Dropped X: N" line. Total across all weeks.
        total = 0
        for m in matches:
            try:
                total += int(m)
            except ValueError:
                total += 1
        out[key] = total
    return out


def pipeline_runtime_min(log_path: Path) -> float | None:
    """Extract today's daily run wall-clock from the log's start/end markers."""
    if not log_path.exists():
        return None
    text = ""
    for enc in ("utf-8", "utf-16-le", "utf-16"):
        try:
            text = log_path.read_text(encoding=enc, errors="ignore")
            if text:
                break
        except (OSError, UnicodeDecodeError):
            continue
    starts = re.findall(r"Daily run started.*?(\d{2}):(\d{2}):(\d{2})", text)
    ends = re.findall(r"Daily run done.*?(\d{2}):(\d{2}):(\d{2})", text)
    if not starts or not ends:
        return None
    h1, m1, s1 = map(int, starts[-1])
    h2, m2, s2 = map(int, ends[-1])
    return ((h2 * 3600 + m2 * 60 + s2) - (h1 * 3600 + m1 * 60 + s1)) / 60.0


# ── Render ───────────────────────────────────────────────────────────


def _row_key(r: dict) -> tuple[str, str]:
    return ((r.get("County") or "").strip(), (r.get("Case No.") or "").strip().upper())


def compute_diffs(today_rows: list[dict], yesterday_rows: list[dict]) -> dict:
    """Compare two polished CSVs (same week, different runs).

    Returns dict with: new, dropped, parcel_changed, reason_today.
    - new:            rows in today but not yesterday
    - dropped:        rows in yesterday but not today (regression signal —
                      polish dropped something it had before)
    - parcel_changed: rows present in both but with a different Parcel ID
    - reason_today:   Counter of Match Reason tags from today's run
    """
    by_yest = {_row_key(r): r for r in yesterday_rows}
    by_today = {_row_key(r): r for r in today_rows}

    new = [r for k, r in by_today.items() if k not in by_yest]
    dropped = [r for k, r in by_yest.items() if k not in by_today]

    parcel_changed: list[dict] = []
    for k, r_today in by_today.items():
        r_yest = by_yest.get(k)
        if r_yest is None:
            continue
        p_y = (r_yest.get("Parcel ID") or "").strip()
        p_t = (r_today.get("Parcel ID") or "").strip()
        if p_y and p_t and p_y != p_t:
            parcel_changed.append({
                "case_no": r_today.get("Case No.", ""),
                "county":  r_today.get("County", ""),
                "decedent": r_today.get("Deceased Owner", ""),
                "parcel_yesterday": p_y,
                "parcel_today":     p_t,
                "addr_yesterday":   (r_yest.get("Property Address") or "").strip(),
                "addr_today":       (r_today.get("Property Address") or "").strip(),
            })

    reason_today: Counter[str] = Counter()
    for r in today_rows:
        raw = (r.get("Match Reason") or "").strip()
        if not raw:
            reason_today["(scrape direct)"] += 1
            continue
        for tag in (t.strip() for t in raw.split("|") if t.strip()):
            reason_today[tag] += 1

    return {
        "new": new,
        "dropped": dropped,
        "parcel_changed": parcel_changed,
        "reason_today": reason_today,
    }


# One-line plain-English description per Match Reason tag, shown as a glossary
# under the distribution and appended inline to each line. Dynamic-suffix tags
# (lot-cluster-N, low-confidence-parcel(NN%)) are matched by prefix in
# _describe_reason(). Keep in sync with tag_reason() calls in fix_addresses_and_prep.py.
REASON_GLOSSARY: dict[str, str] = {
    "(scrape direct)": "Parcel + PR came straight from the court record — no guessing",
    "default-sfr": "Property type unknown — labeled Single-Family (safe default)",
    "addr-corrected": "Property street address fixed/standardized from county records",
    "centroid-geocode": "No exact street number — map pin placed at the parcel's center",
    "name-research": "Property found by searching county records for the deceased's name",
    "name-nearmiss-addr-corroborated": "Name wasn't exact but the address confirmed it — treated as solid",
    "decedent-address": "Property matched using the deceased's own address from the court file",
    "app-realestate-parcel": "Parcel read from the real-estate section of the court Application PDF",
    "collapsed-same-property": "Duplicate rows for the same property merged into one",
    "condo-overruled-by-zillow": "Zillow says it's a house, not a condo — kept",
    "lincoln-ahdesc-structure": "Lincoln County structure type read from the GIS description field",
    # --- flagged: the matcher made a call but isn't fully sure (eyeball) ---
    "verify-middle-initial": "Matched via middle initial to separate same-named people — double-check",
    "verify-name-nomiddle": "Name matched but deed had no middle name to confirm — eyeball",
    "verify-name-ambiguous": "Several people could fit the name — best guess, eyeball",
    "verify-swap-lowconf": "Parcel swapped in with low confidence — eyeball",
    "verify-swap-ambiguous": "Parcel swap was ambiguous — eyeball",
    "low-confidence-parcel": "Property match scored below the 'strong' bar — eyeball",
    "addr-uncorroborated": "Address applied but not independently confirmed — eyeball",
    "verify-occupied-confirmed": "Court-confirmed home the surviving spouse occupies — kept (locked)",
    # --- multi-parcel / land ---
    "lot-cluster": "Estate with adjacent lots on one street — mobile-home-on-land play",
    "swap-on-dq": "Main property disqualified (e.g. heir lives there) — mailed a different estate parcel",
    "swap-on-over-cap": "Main house over your $500K cap — points to an under-cap estate parcel",
    "subdivide-exempt": "SFR/MH on >2 acres — gets the $1M cap (land is the play)",
    "tiny-vacant-lot": "Small vacant lot (low standalone value)",
    # --- where the contact / PR came from ---
    "heirs-of-fallback": "No usable PR/beneficiary — contact defaults to 'Heirs of [Deceased]' (deep-prospecting)",
    "coowner-dm": "Contact taken from a co-owner on the deed",
    "coowner-address": "Mailing address taken from a co-owner on the deed",
    "dm-promoted-pr": "No court executor — the obituary-found living heir (a real person) was promoted to mail target",
    "beneficiary-promoted-pr": "No court executor + no obit heir — a named beneficiary (real person w/ address) was promoted to mail target",
    "beneficiary-address": "Mailing address taken from a named beneficiary",
    "pr-backfill-parties": "PR filled from the eCourts Parties list",
    "pr-from-app-over-obit": "PR taken from the court Application, overriding a weaker obituary guess",
    "pr-from-app-override": "PR taken from the court Application, overriding another source",
    "pr-people-search": "PR's address found via free people-search",
    "pr-tracerfy": "PR's contact found via Tracerfy skip trace",
    "tracerfy": "Contact found via Tracerfy skip trace",
    "mailing-from-property": "PR mailing filled from the property address (so mail still lands)",
    "mailing-addr-split": "Mailing address split out of a combined field",
    "second-pass-obit-full": "Heir/PR found on a second obituary pass (full-name match)",
    "second-pass-obit-name-only": "Heir/PR found on a second obituary pass (name-only match)",
    # --- case data / values ---
    "landportal-revalued": "Vacant lot's value filled from the LandPortal data source",
    "late-doc-apply": "A court document arrived late — its info was applied",
    "small-estate-disposed-recent": "Recently-filed small-estate/disposed case (you work these)",
    "small-estate-address": "Property address from a small-estate filing",
    "heir-transferred-deed": "Deed already moved to a next-gen heir — still a lead, flagged",
    "dq-recently-sold": "Flagged — the property sold recently",
    "rowan-condo": "Rowan County condo (flagged — condos are normally dropped)",
    "audit-repick": "Nightly audit re-picked a better parcel for this case",
    "audit-blanked": "Nightly audit removed a parcel that no longer passes the matcher",
    "pdf-phone": "Phone number pulled from the court PDF",
    "pdf-phone-verified": "Phone number pulled from the court PDF and cross-checked",
}

# Tags meaning "matched, but not fully sure" — summed into the 'Cases to eyeball'
# headline. Matched by prefix so dynamic-suffix variants are included.
_EYEBALL_PREFIXES = (
    "verify-middle-initial", "verify-name-nomiddle", "verify-name-ambiguous",
    "verify-swap-lowconf", "verify-swap-ambiguous",
    "low-confidence-parcel", "addr-uncorroborated",
)


def _describe_reason(tag: str) -> str:
    """Plain-English one-liner for a Match Reason tag (handles dynamic suffixes)."""
    if tag in REASON_GLOSSARY:
        return REASON_GLOSSARY[tag]
    for key, desc in REASON_GLOSSARY.items():
        if tag.startswith(key):
            return desc
    return ""


def _is_eyeball_reason(tag: str) -> bool:
    """True if the tag means the matcher made an uncertain call worth a glance."""
    return any(tag.startswith(p) for p in _EYEBALL_PREFIXES)


def render_report(
    workbook_path: Path | None,
    workbook_rows: list[dict],
    week_n: int,
    today_csv_rows: list[dict],
    yesterday_csv_rows: list[dict],
    heir_transfer_rows: list[dict],
    polish_stats: dict,
    runtime_min: float | None,
    include_heir_transfer: bool = False,
) -> str:
    today_str = date.today().strftime("%a %b %d, %Y")
    diffs = compute_diffs(today_csv_rows, yesterday_csv_rows)
    new_today = diffs["new"]

    # Headlines
    total = len(workbook_rows)

    counties = Counter((r.get("County") or "").strip() for r in workbook_rows)

    lines: list[str] = []
    lines.append(f"NC Probate Pipeline — Daily Report")
    lines.append(f"  {today_str}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("HEADLINES")
    lines.append(f"  Workbook:           {workbook_path.name if workbook_path else '(missing!)'}")
    lines.append(f"  Total cases:        {total}")
    lines.append(f"  New today:          {len(new_today)}")
    eyeball_n = sum(n for tag, n in diffs["reason_today"].items() if _is_eyeball_reason(tag))
    lines.append(f"  Cases to eyeball:   {eyeball_n}   (uncertain matches — see >> rows below)")
    if runtime_min is not None:
        lines.append(f"  Pipeline runtime:   {runtime_min:.0f} min")
    lines.append("")
    lines.append(f"  By county:")
    for c, n in counties.most_common():
        label = c if c else "(blank)"
        lines.append(f"    {label:14} {n}")
    lines.append("")

    # New cases
    lines.append("NEW CASES TODAY")
    if not new_today:
        lines.append("  (none — workbook unchanged)")
    else:
        for r in new_today[:50]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  {cn:18}  {cty:12}  {dec[:32]:32}  ->  {prop}")
        if len(new_today) > 50:
            lines.append(f"  ... and {len(new_today) - 50} more")
    lines.append("")

    # Dropped since yesterday — regression signal. A case that was here
    # yesterday and isn't now means a polish step removed it. Could be a
    # legitimate drop (newly-failed audit, newly-detected heir-occupied)
    # or a regression to investigate.
    dropped = diffs["dropped"]
    lines.append("DROPPED SINCE YESTERDAY")
    if not dropped:
        lines.append("  (none)")
    else:
        for r in dropped[:25]:
            cn = (r.get("Case No.") or "").strip()
            cty = (r.get("County") or "").strip()
            dec = (r.get("Deceased Owner") or "").strip()
            prop = (r.get("Property Address") or "(no parcel)").strip()
            lines.append(f"  {cn:18}  {cty:12}  {dec[:32]:32}  ->  {prop}")
        if len(dropped) > 25:
            lines.append(f"  ... and {len(dropped) - 25} more")
    lines.append("")

    # Parcel changed since yesterday — same case, different parcel now.
    # Usually a smart-picker repick or a new sibling found a better main.
    pc = diffs["parcel_changed"]
    lines.append("PARCEL CHANGED SINCE YESTERDAY")
    if not pc:
        lines.append("  (none)")
    else:
        for e in pc[:15]:
            lines.append(f"  {e['case_no']:18}  {e['county']:12}  {e['decedent'][:30]:30}")
            lines.append(f"    was: {e['parcel_yesterday']:18}  {e['addr_yesterday']}")
            lines.append(f"    now: {e['parcel_today']:18}  {e['addr_today']}")
        if len(pc) > 15:
            lines.append(f"  ... and {len(pc) - 15} more")
    lines.append("")

    # Deep prospecting — running ledger (dp_log.csv) + doc count. Requested by
    # Oren 2026-08-12: a running log of DP runs, included in the daily report.
    dp_rows = read_dp_log()
    lines.append("DEEP PROSPECTING")
    if not dp_rows:
        lines.append("  (no DP runs logged yet — dp_log.csv missing or empty)")
    else:
        n_docs = len(list((OUTPUT / "reports").glob("DP_*.md")))
        by_outcome = Counter((r.get("Outcome") or "?").strip() for r in dp_rows)
        outcome_str = ", ".join(f"{n} {k}" for k, n in by_outcome.most_common())
        lines.append(f"  Runs logged: {len(dp_rows)}   Research docs: {n_docs}   ({outcome_str})")
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent = [r for r in dp_rows if (r.get("Date") or "") >= cutoff]
        if recent:
            lines.append(f"  Last 7 days ({len(recent)}):")
            for r in recent[-12:]:
                note = (r.get("Notes") or "").strip().replace("\n", " ")
                lines.append(f"    {r.get('Date','')}  {r.get('Case No.',''):16}  "
                             f"{(r.get('Decedent') or '')[:26]:26}  {r.get('Outcome',''):8}  "
                             f"{note[:58]}")
        open_rows = [r for r in dp_rows if (r.get("Outcome") or "").strip() == "open"]
        if open_rows:
            lines.append(f"  Still open ({len(open_rows)}):")
            for r in open_rows:
                lines.append(f"    {r.get('Case No.',''):16}  {(r.get('Decedent') or '')[:30]:30}  "
                             f"{(r.get('Notes') or '')[:60]}")
    lines.append("")

    # Heir-transfer — off by default (Oren, 2026-07-18). The review XLSX still
    # generates in output/; it's just no longer summarized here or emailed.
    # Re-enable with `daily_report.py --include-heir-transfer`.
    if include_heir_transfer:
        lines.append("HEIR-TRANSFER FLAGS (review file)")
        if not heir_transfer_rows:
            lines.append("  (none flagged)")
        else:
            # Count unique decedents
            unique_decedents = {(r.get("County"), r.get("Case No.")) for r in heir_transfer_rows}
            lines.append(f"  {len(unique_decedents)} decedent(s) with {len(heir_transfer_rows)} candidate parcel(s) flagged")
            # Group by case; show first 5
            by_case: dict[tuple, list[dict]] = {}
            for r in heir_transfer_rows:
                key = (r.get("County"), r.get("Case No."), r.get("Deceased Owner"))
                by_case.setdefault(key, []).append(r)
            for (cty, cn, dec), cands in list(by_case.items())[:5]:
                lines.append(f"  {cn}  {cty}  {dec}  ({len(cands)} candidate parcels)")
            if len(by_case) > 5:
                lines.append(f"  ... and {len(by_case) - 5} more decedents")
        lines.append("")

    # Polish drops
    lines.append("POLISH DROPS")
    drop_labels = [
        ("over_500k",     "Over $500K (buy-box cap)"),
        ("under_min_value", "Under $10K (standalone scrap parcel)"),
        ("heir_occupied", "Heir-occupied (PR mailing = property)"),
        ("commercial",    "Commercial/industrial"),
        ("no_parcel",     "No parcel found in county GIS"),
        ("archive_dupe",  "Cross-week archive duplicate"),
        ("non_pending",   "Case status not Pending"),
    ]
    any_drops = False
    for key, label in drop_labels:
        n = polish_stats.get(key, 0)
        if n:
            lines.append(f"  {label:40} {n}")
            any_drops = True
    if not any_drops:
        lines.append("  (no drops recorded)")
    if polish_stats.get("repick"):
        lines.append(f"  Smart-picker REPICK events:               {polish_stats['repick']}")
    if polish_stats.get("refound"):
        lines.append(f"  Step 0.5 Re-found correct parcels:        {polish_stats['refound']}")
    lines.append("")

    # A county GIS that went down during the polish. Its rows lost their parcel
    # to a dead server (not to "owns nothing") and were dropped at Step 4 — so
    # tonight's sheet is short for that county. The next clean run restores them,
    # and auto_archive_weeks.py won't freeze the week until then; this is just so
    # a short county count doesn't read as a quiet week.
    try:
        import json as _json
        _o = _json.loads((Path("output") / ".gis_outage_last_run.json")
                         .read_text(encoding="utf-8"))
        if _o.get("counties"):
            lines.append("*** COUNTY GIS OUTAGE THIS RUN ***")
            lines.append(f"  Down: {', '.join(_o['counties'])}")
            lines.append(f"  Rows for these counties are INCOMPLETE in week(s) "
                         f"{_o.get('weeks', [])} — they will be recovered on the "
                         f"next clean run, and the week won't be archived until then.")
            lines.append("")
    except Exception:
        pass

    # Wills/Applications that landed for weeks already archived. apply_late_docs.py
    # writes the name onto the archived sheet, but an archived week is not in the
    # workbook — this report is the ONLY place Oren would ever learn a dead
    # "Heirs of" row turned into a real named contact. Nothing pushes these to
    # DataSift, so they need typing in by hand; keep the case no. front and centre.
    try:
        import json as _json
        _updates = Path("output") / ".late_doc_updates.json"
        _recent = _json.loads(_updates.read_text(encoding="utf-8")).get("entries", [])
        _cut = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
        _new = [e for e in _recent if e.get("found_iso", "") >= _cut]
        if _new:
            lines.append("LATE DOCS — ARCHIVED WEEKS JUST GOT A NAME (add to DataSift by hand)")
            for e in _new:
                _rel = f" ({e['relationship']})" if e.get("relationship") else ""
                lines.append(f"  {e.get('case_number',''):18} {e.get('county',''):12} "
                             f"wk{e.get('week','?')}  {e.get('was','')} -> {e.get('now','')}{_rel}")
            lines.append("")
    except Exception:
        pass

    # Documents the court still hasn't scanned for high-priority leads. We retry
    # nightly for months, but if the Application/Will never appears the only way
    # to the executor name is a manual courthouse pull — surface the oldest so
    # Oren can grab them by hand.
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        import case_doc_queue as _cdq  # noqa: E402
        from ecourts_scraper import cases_needing_docs as _cnd  # noqa: E402
        stale_docs = _cdq.long_pending_high_priority(set(_cnd()), min_age_days=21)
        if stale_docs:
            lines.append("DOCS NOT SCANNED — MANUAL COURTHOUSE PULL (high-priority, 21+ days)")
            for e in stale_docs[:15]:
                lines.append(f"  {e.get('case_number',''):18} {e.get('county',''):12} "
                             f"{e['age_days']:>3}d  needs {','.join(e.get('needs', []))}")
            if len(stale_docs) > 15:
                lines.append(f"  ... and {len(stale_docs) - 15} more")
            lines.append("")
    except Exception:
        pass

    # Tracerfy spend (when funded). One-line summary of this week's burn
    # vs cap — useful for catching runaway costs before they hit the cap.
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from tracerfy_budget import budget_summary  # noqa: E402
        ts_line = budget_summary()
        if ts_line:
            lines.append("TRACERFY BUDGET")
            lines.append(f"  {ts_line}")
            lines.append("")
    except Exception:
        pass

    # Match Reason distribution — how each kept row got to its current state.
    # (scrape direct) = parcel + PR from court directly (high confidence,
    # no polish-step fallback fired). Other tags name the fallback step.
    reason_today = diffs["reason_today"]
    lines.append("MATCH REASON DISTRIBUTION (today's polished output)")
    lines.append("  (how each kept case got its property + contact — '>>' = worth an eyeball)")
    if not reason_today:
        lines.append("  (no rows in today's CSV)")
    else:
        for tag, n in reason_today.most_common():
            flag = ">>" if _is_eyeball_reason(tag) else "  "
            desc = _describe_reason(tag)
            lines.append(f"  {flag} {tag:30} {n:>4}   {desc}")
    lines.append("")

    lines.append("=" * 60)
    lines.append(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


# ── HTML email rendering ─────────────────────────────────────────────
# The plain-text report above stays the single source of truth for content;
# the HTML email wraps it in a branded shell (header + stat tiles + county
# chips) and syntax-highlights the body (section headers, >> eyeball rows,
# *** alerts). Email-safe: inline styles only, table layout, system fonts.

_GREEN = "#1b5e20"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _highlight_body(text: str) -> str:
    """Turn the plain-text report body into styled, monospace HTML lines.
    Drops the top title block and the trailing divider/Generated footer
    (both are rendered elsewhere in the shell)."""
    lines = text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "HEADLINES")
    except StopIteration:
        start = 0
    end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if s and set(s) == {"="}:
            end = i
            break
    mono = ("font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;"
            "font-size:12.5px;line-height:1.55;white-space:pre;padding:1px 12px;margin:0;")
    out: list[str] = []
    for ln in lines[start:end]:
        stripped = ln.strip()
        if not stripped:
            out.append('<div style="height:9px;line-height:9px">&nbsp;</div>')
            continue
        esc = _esc(ln)
        if ln.startswith("***"):
            out.append(f'<div style="{mono}color:#b91c1c;font-weight:700;'
                       f'background:#fef2f2;">{esc}</div>')
        elif ln[0] != " " and not ln.startswith("="):
            out.append(f'<div style="color:{_GREEN};font-weight:700;font-size:11.5px;'
                       f'letter-spacing:.5px;text-transform:uppercase;margin:16px 0 4px;'
                       f'padding:0 12px 5px;border-bottom:1px solid #e4e8eb;">{esc}</div>')
        elif stripped.startswith(">>"):
            out.append(f'<div style="{mono}background:#fff8e1;color:#7a5300;">{esc}</div>')
        else:
            out.append(f'<div style="{mono}color:#3a3f45;">{esc}</div>')
    return "\n".join(out)


def _stat_tile(number, label, accent_bg, accent_fg) -> str:
    return (
        f'<td style="width:33.3%;padding:6px;" valign="top">'
        f'<div style="background:{accent_bg};border-radius:8px;padding:14px 12px;text-align:center;">'
        f'<div style="font-size:30px;font-weight:800;color:{accent_fg};line-height:1;">{number}</div>'
        f'<div style="font-size:10.5px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;'
        f'color:#6b7280;margin-top:6px;">{label}</div>'
        f'</div></td>'
    )


def render_html_email(text: str, *, total: int, new_count: int, eyeball_n: int,
                      counties, week_n: int) -> str:
    d = date.today()
    date_str = d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")
    gen = next((l for l in reversed(text.split("\n")) if l.startswith("Generated ")), "")

    # Stat tiles — eyeball tile turns amber only when there's something to check.
    eye_bg, eye_fg = (("#fff8e1", "#b45309") if eyeball_n else ("#eef1f4", "#374151"))
    tiles = (
        _stat_tile(total, "Total cases", "#eef1f4", "#111827")
        + _stat_tile(new_count, "New today", "#e7f4ea", _GREEN)
        + _stat_tile(eyeball_n, "To eyeball", eye_bg, eye_fg)
    )

    chips = ""
    for name, n in counties:
        label = name if name else "(blank)"
        chips += (f'<span style="display:inline-block;background:#eef1f4;color:#374151;'
                  f'border-radius:12px;padding:3px 10px;margin:0 6px 6px 0;font-size:12px;">'
                  f'{_esc(label)}&nbsp;<b>{n}</b></span>')

    body_html = _highlight_body(text)

    return f"""\
<!doctype html><html><body style="margin:0;padding:0;background:#eef0f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f2;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="700" cellpadding="0" cellspacing="0" style="max-width:700px;width:100%;background:#ffffff;border:1px solid #e2e5e9;border-radius:12px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:{_GREEN};padding:22px 24px;">
    <div style="color:#ffffff;font-size:19px;font-weight:800;letter-spacing:.2px;">NC Probate Pipeline</div>
    <div style="color:#bfe3c5;font-size:13px;margin-top:3px;">Daily Report &middot; Week {week_n} &middot; {date_str}</div>
  </td></tr>
  <tr><td style="padding:14px 18px 4px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{tiles}</tr></table>
  </td></tr>
  <tr><td style="padding:6px 24px 2px;">
    <div style="font-size:11px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">By county</div>
    <div>{chips}</div>
  </td></tr>
  <tr><td style="padding:8px 12px 4px;">
    <div style="overflow-x:auto;border:1px solid #eceef1;border-radius:8px;padding:8px 0;background:#fbfbfc;">
      {body_html}
    </div>
  </td></tr>
  <tr><td style="padding:12px 24px 22px;color:#9aa1a9;font-size:11px;">
    {_esc(gen)} &middot; SiftStack
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


# ── Email ────────────────────────────────────────────────────────────


def _send_email_resend(
    subject: str, body: str, attachments: list[Path] | None = None,
    html: str | None = None,
) -> tuple[bool, str]:
    """Send via Resend HTTP API. Used when RESEND_API_KEY is in .env."""
    import base64
    import requests

    api_key = os.environ["RESEND_API_KEY"]
    sender = os.environ.get("REPORT_FROM", "reports@remedihomesolutions.com")
    recipients_raw = os.environ.get("REPORT_TO", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        return False, "REPORT_TO not set in .env"

    payload: dict = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": body,   # plain-text fallback for clients that don't render HTML
    }
    if html:
        payload["html"] = html

    if attachments:
        attached = []
        for att in attachments:
            if not att.exists():
                continue
            attached.append({
                "filename": att.name,
                "content": base64.b64encode(att.read_bytes()).decode("ascii"),
            })
        if attached:
            payload["attachments"] = attached

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
    except requests.RequestException as e:
        return False, f"Resend HTTP error: {type(e).__name__}: {e}"
    if r.status_code >= 300:
        return False, f"Resend rejected (HTTP {r.status_code}): {r.text[:300]}"
    return True, f"Sent via Resend to {', '.join(recipients)} (id={r.json().get('id', '?')})"


def _send_email_smtp(
    subject: str, body: str, attachments: list[Path] | None = None,
    html: str | None = None,
) -> tuple[bool, str]:
    """Fallback: send via Gmail/Workspace SMTP using app password."""
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    report_to = os.environ.get("REPORT_TO") or smtp_user
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    if not smtp_user or not smtp_pass:
        return False, "Neither RESEND_API_KEY nor SMTP_USER/SMTP_PASS set in .env — skipping email."

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = report_to
    msg["Subject"] = subject
    msg.set_content(body)   # plain-text part
    if html:
        # multipart/alternative — clients pick HTML, fall back to text
        msg.add_alternative(html, subtype="html")

    for att in attachments or []:
        if not att.exists():
            continue
        ctype = "application/octet-stream"
        if att.suffix.lower() == ".xlsx":
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        maintype, subtype = ctype.split("/", 1)
        with att.open("rb") as fp:
            msg.add_attachment(fp.read(), maintype=maintype, subtype=subtype, filename=att.name)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Gmail rejected the app password: {e}. Re-generate at https://myaccount.google.com/apppasswords"
    except Exception as e:
        return False, f"Email send failed: {type(e).__name__}: {e}"
    return True, f"Sent via SMTP to {report_to}"


def send_email(subject: str, body: str, attachments: list[Path] | None = None,
               html: str | None = None) -> tuple[bool, str]:
    """Send via Resend if RESEND_API_KEY is set, else fall back to SMTP."""
    if os.environ.get("RESEND_API_KEY"):
        return _send_email_resend(subject, body, attachments=attachments, html=html)
    return _send_email_smtp(subject, body, attachments=attachments, html=html)


def _count_new_cases(today_rows: list[dict], yesterday_rows: list[dict]) -> int:
    """Cases in today's polished CSV that weren't in yesterday's."""
    def key(r):
        return ((r.get("County") or "").strip(), (r.get("Case No.") or "").strip().upper())
    yesterday = {key(r) for r in yesterday_rows}
    return sum(1 for r in today_rows if key(r) not in yesterday)


# ── Main ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-email", action="store_true", help="Skip the email send (file output only)")
    ap.add_argument("--attach-workbook", action="store_true", help="Attach the FTM workbook to the email")
    ap.add_argument("--include-heir-transfer", action="store_true",
                    help="Re-enable the heir-transfer review section + XLSX attachment "
                         "(off by default per Oren; the XLSX still generates in output/)")
    args = ap.parse_args(argv)

    wb_path = find_latest_workbook()
    if not wb_path:
        print("ERROR: no FTM workbook found in output/", file=sys.stderr)
        return 1
    week_n, workbook_rows = read_workbook_cases(wb_path)

    today_datasift = find_latest_datasift(week_n)
    today_rows = read_csv_cases(today_datasift) if today_datasift else []
    yesterday_datasift = find_yesterdays_datasift(week_n, today_datasift) if today_datasift else None
    yesterday_rows = read_csv_cases(yesterday_datasift) if yesterday_datasift else []

    heir_path = find_latest_heir_transfer(week_n)
    heir_rows = read_heir_transfer(heir_path)

    polish_log = LOGS / "nc_daily_run.log"
    polish_stats = parse_polish_log(polish_log)
    runtime = pipeline_runtime_min(polish_log)

    report = render_report(
        workbook_path=wb_path,
        workbook_rows=workbook_rows,
        week_n=week_n,
        today_csv_rows=today_rows,
        yesterday_csv_rows=yesterday_rows,
        heir_transfer_rows=heir_rows,
        polish_stats=polish_stats,
        runtime_min=runtime,
        include_heir_transfer=args.include_heir_transfer,
    )

    out_path = OUTPUT / f"daily_report_{date.today().strftime('%Y-%m-%d')}.txt"
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    print()
    print(report)

    if args.no_email:
        return 0

    attachments = [out_path]
    if heir_path and args.include_heir_transfer:
        attachments.append(heir_path)
    if args.attach_workbook:
        attachments.append(wb_path)

    new_count = _count_new_cases(today_rows, yesterday_rows)
    subject = f"NC Probate Daily — Week {week_n} — {new_count} new"

    # Build the HTML email from the same report text + headline stats.
    _diffs = compute_diffs(today_rows, yesterday_rows)
    _eyeball = sum(n for tag, n in _diffs["reason_today"].items() if _is_eyeball_reason(tag))
    _counties = Counter((r.get("County") or "").strip() for r in workbook_rows).most_common()
    html = render_html_email(
        report, total=len(workbook_rows), new_count=len(_diffs["new"]),
        eyeball_n=_eyeball, counties=_counties, week_n=week_n,
    )

    ok, msg = send_email(subject, report, attachments=attachments, html=html)
    print(f"\nEmail: {msg}")
    return 0 if ok else 0  # File was written; email is best-effort


if __name__ == "__main__":
    sys.exit(main())
