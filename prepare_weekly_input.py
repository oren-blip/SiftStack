"""Group raw NC scrape outputs by ISO week and emit a merged per-week file.

After `scripts/nc_weekly_scrape.bat` runs, raw FTM CSVs land in `output/`
with timestamps like `nc_estates_ftm_2026-05-22_143301.csv`. This script
groups them by the ISO week of their `File Date` content, dedupes by
(County, Case No.) keeping the latest write, and produces:

    output/nc_estates_ftm_<TS>_week<N>_merged.csv

which is what `fix_addresses_and_prep.py` picks up.

A single weekly scrape captures a whole ISO week's filings in one file —
no merging across multiple raw files needed unless you ran partial-day
scrapes. The dedup handles overlap automatically.

Usage:
    python prepare_weekly_input.py                  # process all raw scrapes
    python prepare_weekly_input.py --only-latest    # only last 7 days of raw files
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from reenrich_ftm_executors import write_csv  # noqa: E402

from iso_week_archive import get_archived_weeks  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("prepare_weekly")


# Match raw scrape outputs: nc_estates_ftm_YYYY-MM-DD_HHMMSS.csv (no _weekN suffix)
RAW_RE = re.compile(r"^nc_estates_ftm_\d{4}-\d{2}-\d{2}_\d{6}\.csv$")


def parse_file_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def file_dominant_iso_week(rows: list[dict]) -> tuple[int, int] | None:
    """Return (year, iso_week) of the most common File Date in this file."""
    counts: Counter[tuple[int, int]] = Counter()
    for r in rows:
        d = parse_file_date(r.get("File Date", ""))
        if d:
            yw = d.isocalendar()
            counts[(yw.year, yw.week)] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def find_raw_scrapes(only_latest_days: int = 0) -> list[Path]:
    """Return all raw scrape CSVs in output/ AND output/archive_pre_validation/.

    Archived raws still hold valid case data that seen_ids skips on re-scrape;
    the dedup below ((county, case_no), newer-file-wins) handles overlap safely.
    """
    raws = [p for p in Path("output").glob("nc_estates_ftm_*.csv")
            if RAW_RE.match(p.name)]
    archive_dir = Path("output") / "archive_pre_validation"
    if archive_dir.is_dir():
        raws += [p for p in archive_dir.glob("nc_estates_ftm_*.csv")
                 if RAW_RE.match(p.name)]
    if only_latest_days:
        cutoff = datetime.now() - timedelta(days=only_latest_days)
        raws = [p for p in raws if datetime.fromtimestamp(p.stat().st_mtime) > cutoff]
    return sorted(raws)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-latest", type=int, default=14,
                    help="Only include raw scrapes modified in the last N days (default 14)")
    args = ap.parse_args()

    raws = find_raw_scrapes(args.only_latest)
    if not raws:
        logger.warning("No raw scrape CSVs found in output/ (within last %d days)", args.only_latest)
        return

    logger.info("Found %d raw scrape file(s) in last %d days", len(raws), args.only_latest)

    # Group rows by ISO week. Dedup by (county, case_no) — newer file wins
    by_week: dict[tuple[int, int], dict[tuple[str, str], dict]] = defaultdict(dict)
    for fp in raws:
        with fp.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        wk = file_dominant_iso_week(rows)
        if not wk:
            logger.warning("  %s: no file_date column or all blank, skipping", fp.name)
            continue
        added = 0
        for r in rows:
            key = (r.get("County", ""), (r.get("Case No.") or "").strip() or f"_blank_{id(r)}")
            by_week[wk][key] = r
            added += 1
        logger.info("  %s -> week %d %d (%d rows)", fp.name, wk[1], wk[0], added)

    archived = get_archived_weeks()
    if archived:
        logger.info("Archived ISO weeks (will skip): %s", sorted(archived))

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for (year, week), keyed in sorted(by_week.items()):
        if week in archived:
            logger.info("  ISO week %d is archived, skipping (%d rows ignored)",
                        week, len(keyed))
            continue
        rows = list(keyed.values())
        out_path = Path("output") / f"nc_estates_ftm_{ts}_week{week}_merged.csv"
        write_csv(rows, out_path)
        logger.info("Wrote: %s (%d unique rows for ISO week %d %d)",
                    out_path.name, len(rows), week, year)


if __name__ == "__main__":
    main()
