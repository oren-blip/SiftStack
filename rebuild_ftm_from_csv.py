"""Rebuild the FTM CSV + XLSX from an existing FTM CSV — quick way to apply
column / formatting changes without re-running the full pipeline (which
takes ~50 min thanks to Tyler's throttle).

Reads the latest nc_estates_ftm_*.csv, adds the new 'Executor Full Name'
column, and writes both CSV (new column added) + XLSX (with County dropdown).
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_ftm_writer import FTM_COLUMNS, NC_COUNTY_OPTIONS  # noqa: E402


def main() -> None:
    src_csv = Path("output/nc_estates_ftm_2026-05-17_211501.csv")
    if not src_csv.exists():
        print(f"ERROR: source file missing: {src_csv}")
        sys.exit(1)

    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {src_csv.name}")

    # Add the new Executor Full Name column derived from First + Last
    for r in rows:
        first = (r.get("First Name") or "").strip()
        last = (r.get("Last Name") or "").strip()
        r["Executor Full Name"] = " ".join(filter(None, [first, last])).strip()

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    csv_path = Path("output") / f"nc_estates_ftm_{ts}.csv"
    xlsx_path = Path("output") / f"nc_estates_ftm_{ts}.xlsx"

    # Write the CSV with the new column order
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FTM_COLUMNS, quoting=csv.QUOTE_MINIMAL,
                                extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"Wrote CSV: {csv_path}")

    # Write the XLSX with County dropdown
    _write_xlsx(rows, xlsx_path)
    print(f"Wrote XLSX: {xlsx_path}")


def _write_xlsx(rows: list[dict], out_path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "NC Estates"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    for col_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")

    for r_idx, r in enumerate(rows, start=2):
        for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=r.get(col_name, ""))
            if col_name == "Notes":
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    # County dropdown
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

    col_widths = {
        "File Date": 11, "County": 14, "Case No.": 18, "Deceased Owner": 32,
        "Executor Full Name": 25, "First Name": 16, "Last Name": 18,
        "Mailing Address": 28, "Mailing City": 16, "Mailing State": 7, "Mailing Zip": 8,
        "Parcel ID": 16, "Property Address": 28, "Property City": 16,
        "Property State": 8, "Property Zip": 8, "Property use": 14,
        "Notes": 60, "Phone 1": 14, "Tags": 26, "List": 10,
    }
    for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = col_widths.get(col_name, 14)

    ws.freeze_panes = "A2"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


if __name__ == "__main__":
    main()
