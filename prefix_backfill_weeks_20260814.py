"""One-shot: backfill Oren's "0 <street>" vacant-lot prefix into the ARCHIVED
week CSVs (Weeks 21-32) so the consolidated workbook stops showing bare
numberless streets ("HEATHER LN", "Ike Lynch Rd", ...).

Why a backfill: the Step 3.66 prefix helper only shipped in Week 30 and was
gated on Property use containing "vacant" until 2026-08-14 (mistyped-SFR lots
slipped through — see the widened prefix_numberless_vacant_streets). Archived
weeks are never re-polished, so their CSVs keep the old form forever; the
workbook regenerates from the LATEST *_weekN_datasift.csv per week, so fixing
those files fixes every future consolidation.

Rule (same as the widened Step 3.66, but suffix-gated for ALL rows here so a
leaked "Maiden NC 28650" city string never gets prefixed by the one-shot):
numberless Property Address matching a street suffix -> "0 <street>". The
Zillow URL is cleared on prefixed rows (nc_ftm_writer never builds one for a
"0 " address — a numberless Zillow search is garbage anyway).

Week 33 is the CURRENT week — tonight's build re-polishes it with the widened
rule, so it is skipped here.
"""
from __future__ import annotations

import csv
import glob
import re
from pathlib import Path

OUT = Path(r"d:\SiftStack\output")
WEEKS = range(21, 33)   # archived weeks only; Wk33 self-heals tonight

_STREET_SUFFIX_RE = re.compile(
    r"\b(rd|road|st|street|ln|lane|dr|drive|ave|avenue|hwy|highway|ct|court|"
    r"blvd|way|cir|circle|pl|place|trl|trail|loop|pkwy|ter|terrace|run|path|"
    r"row|pike|xing|crossing)\b", re.I)


def picked_week_csvs() -> dict[int, Path]:
    """Use consolidate_weeks' own picker so we edit exactly the files the
    workbook is built from (it prefers dm_enriched > ecourts_backfilled >
    datasift, and searches output/archive_week<N>_done/ too — the first
    version of this backfill edited *_datasift.csv and Weeks 31-32 didn't
    change because their tabs come from dm_enriched files)."""
    import os
    import sys
    sys.path.insert(0, r"d:\SiftStack")
    sys.path.insert(0, r"d:\SiftStack\src")
    cwd = os.getcwd()
    os.chdir(r"d:\SiftStack")   # consolidate globs relative "output/"
    try:
        from consolidate_weeks import auto_pick_weekly_files
        picks = auto_pick_weekly_files(include_archived=True)
    finally:
        os.chdir(cwd)
    return {wk: Path(r"d:\SiftStack") / p for (yr, wk), p in picks.items()}


def main() -> int:
    total = 0
    picks = picked_week_csvs()
    for week in WEEKS:
        path = picks.get(week)
        if not path or not path.exists():
            print(f"week {week}: no CSV")
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            rdr = csv.DictReader(f)
            rows = list(rdr)
            fields = rdr.fieldnames or []
        changed = []
        for r in rows:
            pa = (r.get("Property Address") or "").strip()
            if (not pa or pa[0].isdigit() or pa.lower() == "no address"
                    or not _STREET_SUFFIX_RE.search(pa)):
                continue
            r["Property Address"] = f"0 {pa}"
            if r.get("Zillow URL"):
                r["Zillow URL"] = ""
            changed.append(f"{r.get('Case No.')} {pa!r}")
        if not changed:
            print(f"week {week}: {path.name} — no rows to prefix")
            continue
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        total += len(changed)
        print(f"week {week}: {path.name} — prefixed {len(changed)}:")
        for c in changed:
            print(f"    {c}")
    print(f"\nTotal rows prefixed: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
