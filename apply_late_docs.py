#!/usr/bin/env python
"""Apply late-arriving case documents to ARCHIVED weeks' sheets.

Why this exists
---------------
The clerk scans the Will / Application for Probate or Letters days-to-weeks
after the estate is filed. `drain_pending_case_docs()` (inside the nightly
scrape) keeps hunting those PDFs for 30 days regardless of archive state --
`cases_needing_docs()` deliberately walks archived weeks too -- and every hit
lands in output/fetched_case_docs.json permanently.

But the step that WRITES a fetched doc onto a row (`apply_fetched_case_docs`,
polish Step -1.5) only runs inside the full polish, and the polish skips
archived weeks. So a Will that arrives after its week is archived gets
fetched, parsed, cached... and then applied to nothing. The find is real; it
just never reaches a sheet.

This script is that one step, unbolted from the ~2h polish:
  * archived weeks only -- live weeks already get it from the nightly polish
  * pure: no GIS, no people-search, no LLM, no network. A case_id_hex lookup
    into a JSON file we already have on disk. Runs in seconds and cannot hang
    on a county server.
  * idempotent -- same fetched cache in, same rows out (inherited from
    apply_fetched_case_docs)
  * newsworthy changes (an inferred "Heirs of ..." becoming a court-confirmed
    executor) are recorded to output/.late_doc_updates.json, which
    scripts/daily_report.py renders. This matters: an archived week is NOT in
    the workbook, so a row updated here is invisible unless the report says so.

Usage:
    python apply_late_docs.py                 # apply + record
    python apply_late_docs.py --dry-run       # report only, write nothing
    python apply_late_docs.py --weeks 28,29   # limit to specific ISO weeks
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fix_addresses_and_prep import apply_fetched_case_docs  # noqa: E402
from iso_week_archive import get_archived_weeks  # noqa: E402

OUTPUT_DIR = Path("output")
UPDATES_PATH = OUTPUT_DIR / ".late_doc_updates.json"

# How long a recorded find stays in the report feed. Long enough that a find
# landing Friday night is still on Monday's report after a quiet weekend.
UPDATES_RETENTION_DAYS = 30

# Same precedence consolidate_weeks.py uses: the most-enriched file wins, and
# among equals the newest scrape timestamp. Keep in sync if that list grows.
_FILE_PRIORITY = [
    ("_dm_enriched.csv", 2),
    ("_ecourts_backfilled.csv", 1),
    ("_datasift.csv", 0),
]
_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{6})")


def _row_count(fp: Path) -> int:
    """Rows excluding header. csv.reader (not line count) because Notes and
    Beneficiaries carry embedded newlines."""
    try:
        with fp.open(newline="", encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except OSError:
        return 0


def _search_dirs(wk: int) -> list[Path]:
    """Where a given week's polished CSVs can legitimately live.

    Deliberately NOT a recursive walk. output/ also holds _superseded_*/,
    archive_pre_validation/ and friends, which contain older copies of the
    same weeks -- picking one of those would silently write to a sheet Oren
    never sees. Only two places count: output/ root (consolidate's own scope)
    and the week's archive folder, where archiving moves finalized files.
    """
    dirs = [OUTPUT_DIR]
    archived = OUTPUT_DIR / f"archive_week{wk}_done"
    if archived.is_dir():
        dirs.append(archived)
    return dirs


def _canonical_file_per_week(weeks: set[int]) -> dict[int, Path]:
    """The one CSV per week that represents Oren's sheet.

    Replicates consolidate_weeks.auto_pick_weekly_files' precedence exactly --
    most-enriched wins, newest breaks ties, but a strictly newer scrape with
    MORE rows overrides (real new cases beat a stale enriched file). If these
    two ever disagree, this script would update a file the workbook doesn't
    read, so keep them in sync.
    """
    out: dict[int, Path] = {}
    for wk in sorted(weeks):
        cands: list[tuple[int, int, str, Path]] = []
        for d in _search_dirs(wk):
            for suffix, prio in _FILE_PRIORITY:
                for fp in d.glob(f"nc_estates_ftm_*_week{wk}{suffix}"):
                    tsm = _TS_RE.search(fp.name)
                    cands.append((_row_count(fp), prio, tsm.group(1) if tsm else "", fp))
        if not cands:
            continue
        baseline = max(cands, key=lambda c: (c[1], c[2]))
        fuller = [c for c in cands if c[0] > baseline[0] and c[2] > baseline[2]]
        chosen = max(fuller, key=lambda c: (c[0], c[2])) if fuller else baseline
        out[wk] = chosen[3]
    return out


def _is_inferred_pr(pr: str, match_reason: str) -> bool:
    """True when the row's Personal Representative is a guess, not a name the
    court gave us -- i.e. exactly the rows a late document can rescue.

    Mirrors the inferred-PR test inside apply_fetched_case_docs so that what
    we REPORT matches what that function actually chose to overwrite.
    """
    p = (pr or "").strip().lower()
    if not p or p.startswith("heirs of") or p.startswith("estate of"):
        return True
    r = (match_reason or "").lower()
    return "dm-promoted-pr" in r or "beneficiary-promoted-pr" in r


def _load_updates() -> list[dict]:
    try:
        data = json.loads(UPDATES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    cutoff = datetime.now() - timedelta(days=UPDATES_RETENTION_DAYS)
    kept = []
    for e in entries:
        try:
            if datetime.fromisoformat(e.get("found_iso", "")) >= cutoff:
                kept.append(e)
        except (ValueError, TypeError):
            continue
    return kept


def _save_updates(entries: list[dict]) -> None:
    try:
        UPDATES_PATH.write_text(
            json.dumps({"entries": entries}, indent=1), encoding="utf-8")
    except OSError as e:
        print(f"  WARNING: could not write {UPDATES_PATH.name}: {e}")


def process_week(wk: int, path: Path, *, dry_run: bool) -> list[dict]:
    """Apply fetched docs to one archived week. Returns newsworthy changes."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    if not rows:
        return []

    # Snapshot the fields a late doc can rescue, so we can tell a real find
    # (nobody -> a court-confirmed name) from routine field churn.
    before = [{
        "pr": (r.get("Personal Representative") or "").strip(),
        "reason": (r.get("Match Reason") or "").strip(),
    } for r in rows]

    updated = apply_fetched_case_docs(rows)
    if not updated:
        return []

    finds: list[dict] = []
    for prev, r in zip(before, rows):
        now_pr = (r.get("Personal Representative") or "").strip()
        if not now_pr or now_pr == prev["pr"]:
            continue
        # Only report the transition that changes what Oren does: a row with
        # no real contact gaining one. A name merely being corrected is
        # already reflected on the sheet and needs no callout.
        if not _is_inferred_pr(prev["pr"], prev["reason"]):
            continue
        if _is_inferred_pr(now_pr, r.get("Match Reason") or ""):
            continue
        finds.append({
            "week": wk,
            "case_number": (r.get("Case No.") or "").strip(),
            "county": (r.get("County") or "").strip(),
            "decedent": (r.get("Deceased Owner") or "").strip(),
            "was": prev["pr"] or "(blank)",
            "now": now_pr,
            "relationship": (r.get("PR Relationship (App)")
                             or r.get("PR Relationship (Will)") or "").strip(),
            "found_iso": datetime.now().isoformat(timespec="seconds"),
            "file": path.name,
        })

    if not dry_run:
        # Rewrite in place, preserving this file's own column order -- these
        # are finalized sheets, not freshly generated ones, and a column
        # reshuffle would be a gratuitous diff against what Oren already saw.
        tmp = path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames,
                               quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        tmp.replace(path)
    return finds


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    ap.add_argument("--weeks", default="",
                    help="comma-separated ISO weeks (default: all archived weeks)")
    args = ap.parse_args()

    if args.weeks:
        weeks = {int(w) for w in args.weeks.split(",") if w.strip()}
    else:
        weeks = get_archived_weeks()
    if not weeks:
        print("No archived weeks — nothing to do. "
              "(Live weeks get late docs from the nightly polish.)")
        return

    targets = _canonical_file_per_week(weeks)
    missing = sorted(weeks - set(targets))
    if missing:
        print(f"  note: no polished CSV found for week(s) {missing} — skipped")
    if not targets:
        print("No polished CSVs found for the archived weeks.")
        return

    all_finds: list[dict] = []
    for wk in sorted(targets):
        finds = process_week(wk, targets[wk], dry_run=args.dry_run)
        status = f"{len(finds)} new executor name(s)" if finds else "no change"
        print(f"  week {wk}: {targets[wk].name} — {status}")
        all_finds.extend(finds)

    if not all_finds:
        print("Late-doc apply: nothing new landed for archived weeks.")
        return

    print()
    print("LATE DOCS LANDED (archived weeks — these are NOT in the workbook):")
    for f in all_finds:
        rel = f" ({f['relationship']})" if f["relationship"] else ""
        print(f"  wk{f['week']} {f['case_number']:18} {f['county']:12} "
              f"{f['was']} -> {f['now']}{rel}")

    if args.dry_run:
        print("\n(dry run — no files written)")
        return

    _save_updates(_load_updates() + all_finds)
    print(f"\nRecorded {len(all_finds)} find(s) to {UPDATES_PATH.name} "
          f"— daily report will surface them.")


if __name__ == "__main__":
    main()
