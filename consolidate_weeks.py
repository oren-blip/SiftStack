"""Consolidate weekly NC Estates DataSift CSVs into one multi-tab workbook.

Mirrors the user's manual FTM-style workbook: one XLSX with a tab per
week (Week 20, Week 21, etc.), each tab styled identically (dark green
header, yellow banding, single-line rows, County dropdown, frozen
header). Tabs are sorted by ISO week ascending so the oldest week is
the leftmost tab and the newest is rightmost.

The workbook filename is `FTM_2026_NC_Estates_throughWeekN.xlsx` —
overwritten with each run so there's always one canonical workbook.

Usage:
    # Auto-pick the latest DataSift CSV per ISO week from output/
    python consolidate_weeks.py

    # Specify exact files (in any order)
    python consolidate_weeks.py \
        output/nc_estates_ftm_X_week20_datasift.csv \
        output/nc_estates_ftm_Y_week21_datasift.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_ftm_writer import FTM_COLUMNS, HIDDEN_FROM_WORKBOOK, NC_COUNTY_COLORS, NC_COUNTY_OPTIONS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("consolidate")


# Same styling constants used in nc_ftm_writer / reenrich_ftm_executors
_HEADER_FILL = "1B5E20"
_BAND_FILL = "FFFDE7"
_DEFAULT_ROW_HEIGHT = 16
_COL_WIDTHS = {
    "File Date": 11, "County": 14, "Case No.": 18, "Deceased Owner": 32,
    "Personal Representative": 25, "First Name": 16, "Last Name": 18,
    "Mailing Address": 28, "Mailing City": 16, "Mailing State": 7, "Mailing Zip": 8,
    "Parcel ID": 16, "Property Address": 28, "Property City": 16,
    "Property State": 8, "Property Zip": 8, "Property use": 14,
    "Property Value": 14,
    "Notes": 40, "Beneficiaries": 80, "Phone 1": 14, "Tags": 26, "List": 10,
    "DM Name": 22, "DM Relationship": 14, "DM Phone": 14, "DM Email": 26,
    "DM 2 Name": 22, "DM 2 Relationship": 14,
    "DM 3 Name": 22, "DM 3 Relationship": 14,
}


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # Back-compat: pre-rename CSVs used "Executor Full Name".
    for r in rows:
        if "Executor Full Name" in r and "Personal Representative" not in r:
            r["Personal Representative"] = r.pop("Executor Full Name")
    return rows


def week_from_csv(rows: list[dict]) -> tuple[int, int]:
    """Pull the ISO (year, week) from the most common Tags value.

    Tag pattern: 'NC Estates Week N YYYY'. Falls back to (year, week) of
    the most common File Date if the tag is missing or unparseable.
    """
    tag_pat = re.compile(r"NC Estates Week (\d+) (\d{4})", re.IGNORECASE)
    tag_counts: Counter[tuple[int, int]] = Counter()
    for r in rows:
        m = tag_pat.search(r.get("Tags") or "")
        if m:
            tag_counts[(int(m.group(2)), int(m.group(1)))] += 1
    if tag_counts:
        return tag_counts.most_common(1)[0][0]
    # Fallback: derive from File Date
    date_counts: Counter[tuple[int, int]] = Counter()
    for r in rows:
        d = (r.get("File Date") or "").strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                dt = datetime.strptime(d, fmt)
                yw = dt.isocalendar()
                date_counts[(yw.year, yw.week)] += 1
                break
            except ValueError:
                continue
    if date_counts:
        return date_counts.most_common(1)[0][0]
    return (datetime.now().year, datetime.now().isocalendar().week)


def auto_pick_weekly_files() -> dict[tuple[int, int], Path]:
    """Pick the most recent CSV per (year, week) from output/.

    Considers BOTH naming patterns:
      *_weekN_datasift.csv                 (Step 4 output)
      *_weekN_<ts>_ecourts_backfilled.csv  (post-Step-5 eCourts name-search
                                            backfill — has additional Case
                                            No. fills that the datasift CSV
                                            doesn't have yet)

    The backfilled file is strictly more complete (it's built FROM the
    datasift CSV by adding backfilled Case No. values), so when both
    exist for the same week we prefer the latest backfilled file.
    """
    by_week: dict[tuple[int, int], tuple[Path, int]] = {}
    # Priority 0 = datasift, 1 = ecourts_backfilled (higher wins)
    for pattern, priority in [
        ("nc_estates_ftm_*_week*_datasift.csv", 0),
        ("nc_estates_ftm_*_week*_ecourts_backfilled.csv", 1),
    ]:
        for fp in sorted(Path("output").glob(pattern)):
            m = re.search(r"_week(\d+)", fp.name)
            if not m:
                continue
            ym = re.search(r"_(\d{4})-\d{2}-\d{2}_", fp.name)
            year = int(ym.group(1)) if ym else datetime.now().year
            wk = int(m.group(1))
            key = (year, wk)
            existing = by_week.get(key)
            # Pick higher priority. Within same priority, newest filename wins
            # (sorted ascending, so later iterations overwrite earlier).
            if existing is None or priority >= existing[1]:
                by_week[key] = (fp, priority)
    return {k: v[0] for k, v in by_week.items()}


def add_tab(wb, title: str, rows: list[dict]) -> None:
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, PatternFill, Alignment

    ws = wb.create_sheet(title=title[:31])  # XLSX tab name max 31 chars

    # Sort rows by County then Case No. so each county groups together
    rows = sorted(rows, key=lambda r: ((r.get("County") or "ZZZ"), r.get("Case No.", "")))

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color=_HEADER_FILL, end_color=_HEADER_FILL, fill_type="solid")
    for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        cell = ws.cell(row=1, column=c_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 20

    # Per-county color tint (replaces old yellow-alternating band)
    county_fills = {
        c: PatternFill(start_color=h, end_color=h, fill_type="solid")
        for c, h in NC_COUNTY_COLORS.items()
    }
    multiline_cols = {"Notes", "Beneficiaries"}
    for r_idx, r in enumerate(rows, start=2):
        row_fill = county_fills.get(r.get("County", ""))
        for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
            val = r.get(col_name, "")
            if col_name in multiline_cols and val:
                val = " | ".join(s.strip() for s in str(val).split("\n") if s.strip())
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
            if row_fill:
                cell.fill = row_fill
        ws.row_dimensions[r_idx].height = _DEFAULT_ROW_HEIGHT

    county_col_idx = FTM_COLUMNS.index("County") + 1
    county_col_letter = get_column_letter(county_col_idx)
    county_formula = '"' + ",".join(NC_COUNTY_OPTIONS) + '"'
    dv = DataValidation(type="list", formula1=county_formula, allow_blank=True)
    dv.error = "Pick one of the 7 NC counties"
    dv.errorTitle = "Invalid county"
    dv.prompt = "Select a NC county"
    dv.promptTitle = "County"
    ws.add_data_validation(dv)
    dv.add(f"{county_col_letter}2:{county_col_letter}1048576")

    for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        dim = ws.column_dimensions[get_column_letter(c_idx)]
        dim.width = _COL_WIDTHS.get(col_name, 14)
        if col_name in HIDDEN_FROM_WORKBOOK:
            dim.hidden = True
    ws.freeze_panes = "A2"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_files", nargs="*",
                    help="DataSift CSV files (in any order). Omit to auto-pick "
                         "the latest per ISO week from output/.")
    ap.add_argument("--output", default=None,
                    help="Output XLSX path (default: FTM_<year>_NC_Estates_throughWeek<N>.xlsx)")
    args = ap.parse_args()

    if args.csv_files:
        files = [Path(p) for p in args.csv_files]
        per_week = {}
        for fp in files:
            rows = load_csv(fp)
            yr, wk = week_from_csv(rows)
            per_week[(yr, wk)] = (fp, rows)
    else:
        auto = auto_pick_weekly_files()
        per_week = {}
        for key, fp in auto.items():
            per_week[key] = (fp, load_csv(fp))

    if not per_week:
        logger.error("No DataSift CSV files found. Pass paths as args or run "
                     "prepare_for_datasift.py first.")
        sys.exit(1)

    logger.info("Consolidating %d weekly file(s):", len(per_week))
    for (yr, wk), (fp, rows) in sorted(per_week.items()):
        logger.info("  Week %d %d: %s (%d rows)", wk, yr, fp.name, len(rows))

    from openpyxl import Workbook
    wb = Workbook()
    # Workbook starts with a default empty "Sheet" — remove it
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Add tabs sorted by (year, week) ascending — oldest left, newest right
    for (yr, wk), (_fp, rows) in sorted(per_week.items()):
        title = f"Week {wk} {yr}"
        add_tab(wb, title, rows)
        logger.info("Added tab '%s' with %d rows", title, len(rows))

    # Default output filename: through the latest week
    latest_yr, latest_wk = sorted(per_week.keys())[-1]
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path("output") / f"FTM_{latest_yr}_NC_Estates_throughWeek{latest_wk}.xlsx"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    logger.info("Wrote consolidated workbook: %s", out_path)


if __name__ == "__main__":
    main()
