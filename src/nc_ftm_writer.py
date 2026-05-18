"""NC Estates CSV writer in the user's manual FTM-style format.

Matches the column layout in `FTM_2026_NC Estates - Week N YYYY` files:

    File Date, County, Case No., Deceased Owner, First Name, Last Name,
    Mailing Address, Mailing City, Mailing State, Mailing Zip,
    Parcel ID, Property Address, Property City, Property State,
    Property Zip, Property use, Notes, Phone 1, Tags, List

- "First Name" / "Last Name" are the EXECUTOR's (Affiant/Applicant/etc).
- "Mailing *" are the EXECUTOR's mailing address.
- "Property *" + "Parcel ID" come from the county GIS lookup.
- "Notes" is freeform — beneficiary list block, extra parcel notes, etc.
- "Tags" = "NC Estates Week {N} {YYYY}" (ISO week of the file date).
- "List" = "PROBATE".

Records are grouped by case so the multi-parcel rows from one decedent
(e.g. 9 parcels for the Thrower estate) share the executor data.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from notice_parser import NoticeData

logger = logging.getLogger(__name__)


FTM_COLUMNS = [
    "File Date",
    "County",
    "Case No.",
    "Deceased Owner",
    "Executor Full Name",
    "First Name",
    "Last Name",
    "Mailing Address",
    "Mailing City",
    "Mailing State",
    "Mailing Zip",
    "Parcel ID",
    "Property Address",
    "Property City",
    "Property State",
    "Property Zip",
    "Property use",
    "Notes",
    "Phone 1",
    "Tags",
    "List",
]

# County values for the Sheets dropdown validation
NC_COUNTY_OPTIONS = [
    "Cabarrus", "Catawba", "Gaston", "Iredell", "Lincoln", "Mecklenburg", "Rowan",
]


def _format_date(yyyymmdd: str) -> str:
    """Convert 'YYYY-MM-DD' → 'M/D/YYYY' to match the FTM file."""
    if not yyyymmdd:
        return ""
    try:
        d = datetime.strptime(yyyymmdd, "%Y-%m-%d")
        return f"{d.month}/{d.day}/{d.year}"
    except ValueError:
        return yyyymmdd


def _format_decedent(name: str) -> str:
    """Convert 'First Middle Last' → 'Last, First Middle' (FTM convention).

    Already-comma-formatted names pass through. Trust/business names pass through.
    """
    if not name or "," in name or " trust" in name.lower() or " llc" in name.lower():
        return name
    tokens = name.strip().split()
    if len(tokens) < 2:
        return name
    last = tokens[-1]
    rest = " ".join(tokens[:-1])
    return f"{last}, {rest}"


def _format_extra_parcels(extras: list[NoticeData]) -> str:
    """Format a 'PLUS N PARCELS' note for additional properties of a decedent.

    Each extra is rendered as: 'parcel_id  property_address, city zip [USE]'
    so the user can see what's been collapsed off the main row.
    """
    if not extras:
        return ""
    lines = [f"PLUS {len(extras)} PARCEL{'S' if len(extras) > 1 else ''}"]
    for e in extras:
        bits = []
        if e.parcel_id:
            bits.append(e.parcel_id)
        addr = " ".join(filter(None, [e.address, e.city, e.zip])).strip()
        if addr:
            bits.append(addr)
        if e.property_use_simple:
            bits.append(f"[{e.property_use_simple}]")
        lines.append("  " + " | ".join(bits))
    return "\n".join(lines)


def _build_notes(notice: NoticeData, *, extra_parcels: list[NoticeData] | None = None) -> str:
    """Build the multi-line Notes block — beneficiary list + extra parcel notes."""
    parts: list[str] = []
    extra_block = _format_extra_parcels(extra_parcels or [])
    if extra_block:
        parts.append(extra_block)
    if notice.beneficiaries_json:
        try:
            bens = json.loads(notice.beneficiaries_json)
        except (ValueError, TypeError):
            bens = []
        if bens:
            if parts:
                parts.append("")  # blank separator
            parts.append("Beneficiary")
            for b in bens:
                name = b.get("name", "")
                street = b.get("street", "")
                city = b.get("city", "")
                state = b.get("state", "")
                zipc = b.get("zip", "")
                if name:
                    parts.append(name)
                if street:
                    parts.append(street)
                citystatezip = ", ".join(filter(None, [city, " ".join(filter(None, [state, zipc])).strip()]))
                if citystatezip:
                    parts.append(citystatezip)
    return "\n".join(parts)


def _iso_week_tag(date_str: str) -> str:
    """Build 'NC Estates Week N YYYY' from a YYYY-MM-DD date string."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
    except ValueError:
        d = datetime.now()
    week = d.isocalendar()[1]
    return f"NC Estates Week {week} {d.year}"


def notice_to_ftm_row(
    notice: NoticeData,
    *,
    tag_override: str = "",
    extra_parcels: list[NoticeData] | None = None,
) -> dict[str, str]:
    """Convert one NoticeData record to a single FTM-format dict.

    `extra_parcels` (if any) get listed in Notes as 'PLUS N PARCELS: ...'
    so a decedent with multiple properties collapses to one row.
    """
    tag = tag_override or _iso_week_tag(notice.date_added)
    exec_full = " ".join(filter(None, [notice.executor_first_name, notice.executor_last_name])).strip()
    return {
        "File Date":          _format_date(notice.date_added),
        "County":             notice.county,
        "Case No.":           notice.case_number,
        "Deceased Owner":     _format_decedent(notice.decedent_name),
        "Executor Full Name": exec_full,
        "First Name":         notice.executor_first_name,
        "Last Name":          notice.executor_last_name,
        "Mailing Address":  notice.owner_street,
        "Mailing City":     notice.owner_city,
        "Mailing State":    notice.owner_state,
        "Mailing Zip":      notice.owner_zip,
        "Parcel ID":        notice.parcel_id,
        "Property Address": notice.address,
        "Property City":    notice.city,
        "Property State":   notice.state if notice.state == "NC" else "NC",
        "Property Zip":     notice.zip,
        "Property use":     notice.property_use_simple,
        "Notes":            _build_notes(notice, extra_parcels=extra_parcels),
        "Phone 1":          notice.primary_phone,
        "Tags":             tag,
        "List":             "PROBATE",
    }


def _market_value_key(n: NoticeData) -> float:
    """Sort key for picking the 'main' parcel per decedent — highest value wins."""
    try:
        return float(n.estimated_value or 0)
    except (TypeError, ValueError):
        return 0.0


def collapse_by_case(notices: list[NoticeData]) -> list[tuple[NoticeData, list[NoticeData]]]:
    """Group notices by case_number; return [(main_parcel, [extra_parcels])].

    Main parcel = the one with the highest estimated_value. Falls back to
    the first if values are equal/missing. Notices without a case_number
    are returned individually with no extras.
    """
    groups: dict[str, list[NoticeData]] = {}
    out: list[tuple[NoticeData, list[NoticeData]]] = []
    for n in notices:
        key = n.case_number or f"_no_case_{id(n)}"
        groups.setdefault(key, []).append(n)
    for key, items in groups.items():
        if len(items) == 1:
            out.append((items[0], []))
            continue
        items_sorted = sorted(items, key=_market_value_key, reverse=True)
        main, extras = items_sorted[0], items_sorted[1:]
        out.append((main, extras))
    return out


def write_ftm_xlsx(
    notices: list[NoticeData],
    out_path: Path,
    *,
    tag_override: str = "",
    collapse_multi_parcel: bool = True,
) -> int:
    """Write the FTM Estates output as XLSX with a County dropdown.

    Imports openpyxl lazily because not all callers need XLSX.
    Returns the number of data rows written.
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Font, PatternFill, Alignment

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if collapse_multi_parcel:
        groups = collapse_by_case(notices)
        rows = [notice_to_ftm_row(main, tag_override=tag_override, extra_parcels=extras)
                for main, extras in groups]
    else:
        rows = [notice_to_ftm_row(n, tag_override=tag_override) for n in notices]

    wb = Workbook()
    ws = wb.active
    ws.title = "NC Estates"

    # Header row
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    for col_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")

    # Data rows
    for r_idx, r in enumerate(rows, start=2):
        for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=r.get(col_name, ""))
            # Wrap Notes column so beneficiary blocks render readably
            if col_name == "Notes":
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    # County dropdown — applied to the full County column
    county_col_idx = FTM_COLUMNS.index("County") + 1
    county_col_letter = get_column_letter(county_col_idx)
    # Quote each county and join with commas — Excel/Sheets dropdown format
    county_formula = '"' + ",".join(NC_COUNTY_OPTIONS) + '"'
    dv = DataValidation(type="list", formula1=county_formula, allow_blank=True)
    dv.error = "Pick one of the 7 NC counties"
    dv.errorTitle = "Invalid county"
    dv.prompt = "Select a NC county"
    dv.promptTitle = "County"
    ws.add_data_validation(dv)
    dv.add(f"{county_col_letter}2:{county_col_letter}1048576")

    # Column widths — make the important fields legible
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

    # Freeze the header row so it stays visible on scroll
    ws.freeze_panes = "A2"

    wb.save(out_path)
    logger.info("Wrote %d NC Estates rows to %s", len(rows), out_path)
    return len(rows)


def write_ftm_csv(
    notices: list[NoticeData],
    out_path: Path,
    *,
    tag_override: str = "",
    collapse_multi_parcel: bool = True,
) -> int:
    """Write NoticeData list to a CSV matching the FTM Estates format.

    With `collapse_multi_parcel=True` (default), decedents with multiple
    parcels collapse to one row (highest-value parcel as main; the rest
    listed in Notes as 'PLUS N PARCELS: ...'). Set False to emit one
    row per parcel.

    Returns the number of rows written.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if collapse_multi_parcel:
        groups = collapse_by_case(notices)
        rows = [notice_to_ftm_row(main, tag_override=tag_override, extra_parcels=extras)
                for main, extras in groups]
    else:
        rows = [notice_to_ftm_row(n, tag_override=tag_override) for n in notices]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FTM_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    logger.info("Wrote %d NC Estates rows to %s", len(rows), out_path)
    return len(rows)
