"""Print the DataSift week-tag for the most recent NC upload.

Used by scripts/score_phones.bat so the user never types the tag. Derives the
week from the latest output workbook / upload CSV (matches exactly what was
uploaded); falls back to the current ISO week. An explicit week number can be
passed as the first arg to override.

    python scripts/current_week_tag.py        -> latest week from output/
    python scripts/current_week_tag.py 28     -> forces week 28
"""
import datetime
import glob
import os
import re
import sys

YEAR = datetime.date.today().year


def _latest_week() -> str | None:
    cands = (glob.glob("output/FTM_*_NC_Estates_throughWeek*.xlsx")
             + glob.glob("output/nc_estates_*week*_datasift*.csv"))
    if not cands:
        return None
    latest = max(cands, key=os.path.getmtime)
    m = re.search(r"[Ww]eek0*(\d+)", os.path.basename(latest))
    return m.group(1) if m else None


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        week = sys.argv[1].strip()
    else:
        week = _latest_week() or str(datetime.date.today().isocalendar()[1])
    print(f"NC Estates Week {week} {YEAR}")


if __name__ == "__main__":
    main()
