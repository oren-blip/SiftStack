"""Auto-upload tonight's NETNEW rows to DataSift (nightly step, build 8/19+).

Oren approved unprompted uploads 2026-08-19 ("start running the upload
without my prompting"). Runs at the end of the nightly build, AFTER
consolidate and BEFORE the daily report — so the email's "waiting for the
next upload" line reflects the post-upload state (normally 0).

For each of tonight's `*_week{N}_datasift_upload_NETNEW.csv` files (today's
run stamp only — stale files from prior runs are never re-uploaded):
  - skip if it has 0 data rows (nothing net-new)
  - otherwise run upload_netnew_datasift.py --csv <file> --week N --headless
    (defaults on: enrich, skip trace scoped by batch tag, tier step,
    text touches — the exact flow Oren ran by hand through Wk34)

Off-switch:  set NC_AUTO_UPLOAD=0
A failed upload logs the error and leaves the rows in the ledger-less state,
so tomorrow's NETNEW simply carries them again — nothing is lost.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "output"
PY = REPO / ".venv" / "Scripts" / "python.exe"
sys.path.insert(0, str(REPO / "src"))


def data_rows(p: Path) -> int:
    try:
        with p.open(encoding="utf-8-sig", newline="") as f:
            return sum(1 for r in csv.DictReader(f)
                       if any((v or "").strip() for v in r.values()))
    except OSError:
        return -1


def unuploaded_cases(netnew_csv: Path) -> list[str] | None:
    """Case numbers in the NETNEW's .cases.json sidecar that the upload ledger
    does NOT already have. None = sidecar missing (can't tell -> be safe, skip).

    The NETNEW file on disk is written at polish time and NOT rewritten after
    an upload commits — only the ledger records the commit. Judging by file
    rows alone re-uploads (and re-skip-traces, pay-per-record) rows that were
    already committed earlier the same evening. Learned 2026-08-19 the hard way.
    """
    sidecar = netnew_csv.with_suffix(".cases.json")
    try:
        cases = json.loads(sidecar.read_text(encoding="utf-8")).get("cases", [])
    except (OSError, ValueError):
        return None
    from nc_datasift_export import load_upload_ledger
    ledger = load_upload_ledger()
    return [c for c in cases if c.strip().upper() not in ledger]


def main() -> int:
    if os.environ.get("NC_AUTO_UPLOAD", "1") == "0":
        print("auto-upload: skipped -- NC_AUTO_UPLOAD=0")
        return 0
    today = date.today().strftime("%Y-%m-%d")
    # newest stamp per week, today's run only
    per_week: dict[int, Path] = {}
    for p in sorted(OUTPUT.glob(f"nc_estates_ftm_{today}_*_week*_datasift_upload_NETNEW.csv")):
        m = re.search(r"_week(\d+)_", p.name)
        if m:
            per_week[int(m.group(1))] = p  # sorted() => later stamp wins
    if not per_week:
        print(f"auto-upload: no NETNEW files stamped {today} -- nothing to do "
              "(scrape/polish may not have produced output tonight)")
        return 0

    rc_all = 0
    for week, path in sorted(per_week.items()):
        n = data_rows(path)
        if n <= 0:
            print(f"auto-upload: week {week}: {path.name} has {n} rows -- skip")
            continue
        pending = unuploaded_cases(path)
        if pending is None:
            print(f"auto-upload: week {week}: no .cases.json sidecar for "
                  f"{path.name} -- can't verify against ledger, SKIPPING "
                  "(upload by hand if needed)")
            continue
        if not pending:
            print(f"auto-upload: week {week}: all {n} row(s) already in the "
                  "upload ledger -- nothing to do")
            continue
        print(f"auto-upload: week {week}: uploading {n} row(s) from {path.name} "
              f"({len(pending)} not yet in ledger: {', '.join(pending[:5])}"
              f"{' ...' if len(pending) > 5 else ''})")
        r = subprocess.run(
            [str(PY), str(REPO / "upload_netnew_datasift.py"),
             "--csv", str(path), "--week", str(week), "--headless"],
            cwd=str(REPO), timeout=3600)
        if r.returncode != 0:
            print(f"auto-upload: week {week}: upload FAILED (rc={r.returncode}) -- "
                  "rows stay out of the ledger and re-appear in tomorrow's NETNEW")
            rc_all = 1
    return rc_all


if __name__ == "__main__":
    sys.exit(main())
