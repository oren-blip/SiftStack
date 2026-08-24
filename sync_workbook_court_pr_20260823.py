"""Sync the FTM workbook to the court PR names pushed to DataSift on 8/23.

DataSift was corrected in three passes today (fix_bad_renames /
push_court_pr_renames / fix_stale_dp_names, see [[project_court_pr_beats_dp_guess]]),
but the weekly CSVs behind the workbook still read "Heirs of <Decedent>" or the
older DP-guessed name. This makes the spreadsheet agree with the CRM.

Edits ONLY the file consolidate_weeks.auto_pick_weekly_files() actually picks for
each ISO week - for several weeks that is the *_dm_enriched.csv, NOT the
*_datasift.csv the probe read. Editing the wrong one would leave the workbook
unchanged and look like a no-op.

Per matched row: Personal Representative / First Name / Last Name -> court PR.
Mailing is NOT changed (DataSift's mailing was not changed either - keeping the
two in step). Every touched file is backed up alongside itself first.

    python sync_workbook_court_pr_20260823.py            # DRY RUN
    python sync_workbook_court_pr_20260823.py --apply    # live
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
from consolidate_weeks import auto_pick_weekly_files  # noqa: E402

APPLY = "--apply" in sys.argv
OUTDIR = REPO / "output"


def changed_cases() -> dict:
    """case -> court PR full name, for every record actually written today."""
    probe = {r["Case No."]: r for r in csv.DictReader(
        open(OUTDIR / "heirs_pr_probe.csv", encoding="utf-8-sig"))}
    cases = {}
    for fn, keep in (("fix_bad_renames_20260823.csv", {"CORRECTED"}),
                     ("court_pr_renames_20260823.csv", {"RENAMED"}),
                     # dryrun file holds all 15 stale targets; the live file was
                     # rewritten by the resume run and lists only that run's 5
                     ("stale_dp_names_20260823_dryrun.csv", {"DRY"})):
        for r in csv.DictReader(open(OUTDIR / fn, encoding="utf-8-sig")):
            if r["Result"] in keep:
                pr = (probe.get(r["Case No."], {}).get("Court PR") or "").strip()
                if pr:
                    cases[r["Case No."]] = pr
    return cases


def main() -> int:
    cases = changed_cases()
    print(f"court-PR names to sync: {len(cases)}")

    picks = auto_pick_weekly_files(include_archived=True)
    total = 0
    touched_files = []
    for key in sorted(picks):
        path = Path(picks[key])
        with open(path, encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            cols, rows = rdr.fieldnames, list(rdr)
        hits = []
        for r in rows:
            case = (r.get("Case No.") or "").strip()
            pr = cases.get(case)
            if not pr:
                continue
            was = (r.get("Personal Representative") or "").strip()
            if was.lower() == pr.lower():
                continue
            parts = pr.split()
            r["Personal Representative"] = pr
            if "First Name" in (cols or []):
                r["First Name"] = parts[0]
            if "Last Name" in (cols or []):
                r["Last Name"] = parts[-1]
            hits.append((case, was, pr))
        if not hits:
            continue
        print(f"\n{path.name}  (week {key[1]})  {len(hits)} row(s)")
        for case, was, pr in hits:
            print(f"    {case:<16} {was[:34]:<35} -> {pr}")
        total += len(hits)
        touched_files.append(path)
        if APPLY:
            bak = path.with_suffix(path.suffix + ".pre_court_pr_bak")
            if not bak.exists():
                shutil.copy2(path, bak)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)

    print(f"\n==== {'LIVE' if APPLY else 'DRY'} ====")
    print(f"  {total} row(s) across {len(touched_files)} file(s)")
    if APPLY and touched_files:
        print("  backups written alongside each file (*.pre_court_pr_bak)")
        print("  now run:  python consolidate_weeks.py")
    unmatched = set(cases) - {c for c in cases}
    if unmatched:
        print(f"  NOT FOUND in any weekly file: {sorted(unmatched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
