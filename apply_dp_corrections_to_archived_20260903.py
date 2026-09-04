"""Apply manual_corrections.csv to EVERY week the workbook shows — archived included.

Why this exists (2026-09-03, Oren: "workflow still contains many Heirs records"):
the nightly polish is the only thing that runs apply_manual_corrections(), and it
only walks LIVE weeks. A week is archived the Wednesday after it closes
(scripts/auto_archive_weeks.py), and from that moment its polished CSV is frozen.

So a case that was "Heirs of X" at archive time and was deep-prospected a week
later gets its real name pushed to DataSift — and the workbook keeps showing
"Heirs of X" forever. Measured on FTM_2026_NC_Estates_throughWeek36.xlsx:
163 "Heirs of" rows, but 111 of them are already resolved/partial in dp_log.csv,
and the live CRM holds only 5 deliberate Heirs records. The workbook is the
stale artifact, not the CRM.

apply_late_docs.py already does exactly this job for late-arriving court
documents. This is the same idea for hand-verified corrections.

Pure local: reads manual_corrections.csv + the picked weekly CSVs, writes those
CSVs. No network, no CRM writes, no DataSift calls.

    python apply_dp_corrections_to_archived_20260903.py             # dry run
    python apply_dp_corrections_to_archived_20260903.py --apply     # write
    python apply_dp_corrections_to_archived_20260903.py --apply --consolidate
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from consolidate_weeks import auto_pick_weekly_files  # noqa: E402
from fix_addresses_and_prep import apply_manual_corrections  # noqa: E402

# Columns worth calling out one-by-one in the report — these are the ones that
# change who gets contacted. Everything else is summarised as a count.
_LOUD = ("Personal Representative", "First Name", "Last Name",
         "Mailing Address", "Mailing City", "Mailing State", "Mailing Zip",
         "DM Name", "DM Phone", "Phone 1")


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def _write(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    """Write back preserving the file's OWN header (never FTM_COLUMNS — a
    _datasift.csv has a different shape and forcing columns would gut it)."""
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames,
                           quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the corrected CSVs (default: dry run)")
    ap.add_argument("--consolidate", action="store_true",
                    help="rebuild the workbook afterwards (implies --apply)")
    args = ap.parse_args()
    if args.consolidate:
        args.apply = True

    picked = auto_pick_weekly_files(include_archived=True)
    if not picked:
        print("No weekly CSVs found in output/ — nothing to do.")
        return 1
    print(f"Weeks the workbook is built from: {len(picked)}")
    print(f"Mode: {'APPLY (writes CSVs)' if args.apply else 'DRY RUN (writes nothing)'}\n")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tot_fields = tot_cases = tot_heirs_fixed = 0
    touched_files = 0

    for (year, week), path in sorted(picked.items()):
        fieldnames, rows = _read(path)
        if not rows:
            continue
        before = [dict(r) for r in rows]
        fields, cases = apply_manual_corrections(rows)
        if not fields:
            continue

        # Diff for the report
        changes: list[str] = []
        heirs_fixed = 0
        for old, new in zip(before, rows):
            diffs = {k: (old.get(k, ""), new.get(k, ""))
                     for k in new if (old.get(k) or "") != (new.get(k) or "")}
            if not diffs:
                continue
            was_heirs = (old.get("Personal Representative") or "").lower().startswith("heirs of")
            now_heirs = (new.get("Personal Representative") or "").lower().startswith("heirs of")
            if was_heirs and not now_heirs:
                heirs_fixed += 1
            loud = {k: v for k, v in diffs.items() if k in _LOUD}
            if loud:
                case = new.get("Case No.", "?")
                bits = "; ".join(f"{k}: {a or '(blank)'!s} -> {b}"
                                 for k, (a, b) in loud.items())
                changes.append(f"      {case:18} {bits}")
            else:
                changes.append(f"      {new.get('Case No.','?'):18} "
                               f"({len(diffs)} minor field(s): {', '.join(sorted(diffs))})")

        touched_files += 1
        tot_fields += fields
        tot_cases += cases
        tot_heirs_fixed += heirs_fixed
        flag = f"  *** {heirs_fixed} 'Heirs of' -> real name" if heirs_fixed else ""
        print(f"  Week {week} {year}  {path.name}")
        print(f"    {cases} case(s), {fields} field(s){flag}")
        for line in changes[:12]:
            print(line)
        if len(changes) > 12:
            print(f"      ... and {len(changes) - 12} more row(s)")

        if args.apply:
            bak = path.with_suffix(path.suffix + f".bak_{stamp}")
            shutil.copy2(path, bak)
            _write(path, fieldnames, rows)
        print()

    print("=" * 68)
    print(f"Files touched      : {touched_files}")
    print(f"Cases corrected    : {tot_cases}")
    print(f"Fields written     : {tot_fields}")
    print(f"'Heirs of' cleared : {tot_heirs_fixed}")
    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
        return 0

    print(f"\nBackups written alongside each CSV as *.bak_{stamp}")
    if args.consolidate:
        print("\nRebuilding workbook...")
        import subprocess
        r = subprocess.run([sys.executable, "consolidate_weeks.py"],
                           cwd=str(REPO), capture_output=True, text=True)
        print(r.stdout[-2500:] or r.stderr[-2500:])
        return r.returncode
    print("\nRun  python consolidate_weeks.py  to rebuild the workbook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
