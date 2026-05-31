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
    "Case Status",
    "Deceased Owner",
    "Personal Representative",
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
    "Property Value",
    "Notes",
    "Beneficiaries",
    "Phone 1",
    "Tags",
    "List",
    # Heir / Decision Maker columns — populated for rows that lack a
    # court-named executor, via heir_prospect_no_executor.py (obituary
    # survivors + multi-tier skip trace). Stays blank for executor rows.
    "DM Name",
    "DM Relationship",
    "DM Phone",
    "DM Email",
    "DM 2 Name",
    "DM 2 Relationship",
    "DM 3 Name",
    "DM 3 Relationship",
]

# Columns that exist in the data but are hidden from the xlsx display.
# Case Status is a silent guardrail — every kept row should be "Pending"
# (polish drops Disposed/Closed). Hiding it removes visual noise but
# preserves the field for audit / debugging / future use.
HIDDEN_FROM_WORKBOOK = {"Case Status"}

# County values for the Sheets dropdown validation
NC_COUNTY_OPTIONS = [
    "Cabarrus", "Catawba", "Gaston", "Iredell", "Lincoln", "Mecklenburg", "Rowan",
]

# Per-county row tints — subtle pastel backgrounds so rows visually group
# by county when the sheet is sorted by County. Picked low-saturation
# shades that pair with the dark green header + don't clash.
NC_COUNTY_COLORS: dict[str, str] = {
    "Cabarrus":    "D6EAF8",  # light blue
    "Catawba":     "D5F5E3",  # light green
    "Gaston":      "FCF3CF",  # light yellow (close to FTM band)
    "Iredell":     "FADBD8",  # light pink
    "Lincoln":     "E8DAEF",  # light lavender
    "Mecklenburg": "FDEBD0",  # light peach
    "Rowan":       "D1F2EB",  # light teal
}
# Fallback for unknown counties (white = no fill)
NC_COUNTY_DEFAULT_COLOR = ""


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


def _build_notes(extra_parcels: list[NoticeData] | None = None) -> str:
    """Build the Notes block — extra-parcel notes only (beneficiaries moved
    to their own column in build 1.0.30+).
    """
    return _format_extra_parcels(extra_parcels or [])


def _build_beneficiaries(notice: NoticeData) -> str:
    """Format the beneficiary list for its own column.

    One beneficiary per line (multi-line cell content). Each line:
        "Last, First Middle — street, city ST zip"
    """
    if not notice.beneficiaries_json:
        return ""
    try:
        bens = json.loads(notice.beneficiaries_json)
    except (ValueError, TypeError):
        return ""
    if not bens:
        return ""
    lines: list[str] = []
    for b in bens:
        name = (b.get("name") or "").strip()
        street = (b.get("street") or "").strip()
        city = (b.get("city") or "").strip()
        state = (b.get("state") or "").strip()
        zipc = (b.get("zip") or "").strip()
        addr_bits: list[str] = []
        if street:
            addr_bits.append(street)
        csz = " ".join(filter(None, [city + "," if city else "", state, zipc])).strip()
        if csz:
            addr_bits.append(csz)
        addr = ", ".join(addr_bits)
        if name and addr:
            lines.append(f"{name} - {addr}")
        elif name:
            lines.append(name)
        elif addr:
            lines.append(addr)
    return "\n".join(lines)


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

    DM Name / DM Relationship / DM 2 / DM 3 are populated from
    `notice.decision_maker_*` (set by the obituary enricher when
    `--nc-obituary` runs). Phone/Email columns are left blank — DataSift's
    post-upload skip-trace fills those.
    """
    tag = tag_override or _iso_week_tag(notice.date_added)
    exec_full = " ".join(filter(None, [notice.executor_first_name, notice.executor_last_name])).strip()
    return {
        "File Date":          _format_date(notice.date_added),
        "County":             notice.county,
        "Case No.":           notice.case_number,
        "Case Status":        notice.case_status,
        "Deceased Owner":     _format_decedent(notice.decedent_name),
        "Personal Representative": exec_full,
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
        "Property Value":   notice.estimated_value or "",
        "Notes":            _build_notes(extra_parcels=extra_parcels),
        "Beneficiaries":    _build_beneficiaries(notice),
        "Phone 1":          notice.primary_phone,
        "Tags":             tag,
        "List":             "PROBATE",
        "DM Name":          notice.decision_maker_name or "",
        "DM Relationship":  notice.decision_maker_relationship or "",
        "DM Phone":         "",
        "DM Email":         "",
        "DM 2 Name":        notice.decision_maker_2_name or "",
        "DM 2 Relationship": notice.decision_maker_2_relationship or "",
        "DM 3 Name":        notice.decision_maker_3_name or "",
        "DM 3 Relationship": notice.decision_maker_3_relationship or "",
    }


def _market_value_key(n: NoticeData) -> float:
    """Read estimated_value as a float; 0 when missing."""
    try:
        return float(n.estimated_value or 0)
    except (TypeError, ValueError):
        return 0.0


def _main_parcel_priority(n: NoticeData) -> tuple[int, int, float]:
    """Sort key for picking the 'main' parcel per decedent.

    Priority (sorted DESCENDING, so highest tuple wins):
      1. SOLELY-owned beats jointly-owned. Jointly-owned property
         typically transfers via right of survivorship (e.g. decedent
         + surviving spouse) and isn't part of probate — only solely-
         owned parcels are actual probate assets. This is the most
         important signal: even a vacant lot that's solely owned beats
         a jointly-owned mansion.
      2. Residential beats vacant beats commercial within same
         ownership tier — vacant lots and commercial parcels should
         be NOTES, not the main lead.
      3. Within same use-class, highest market value wins.

    Sole/joint tier:
      1 = solely owned (probate asset)
      0 = jointly owned (transfers by survivorship — not in probate)
    Use-class tier (higher = preferred):
      3 = SFR / Residential / Townhouse / Condo / MH
      2 = anything not classified (unknown — could be residential)
      1 = Vacant Land
      0 = Commercial / Industrial / Office
    """
    sole_tier = 0 if getattr(n, "is_jointly_owned", False) else 1
    use = (getattr(n, "property_use_simple", "") or "").upper()
    if "COMMERCIAL" in use or "INDUSTRIAL" in use or "OFFICE" in use:
        use_tier = 0
    elif "VACANT" in use or "LAND" in use:
        use_tier = 1
    elif use in {"SFR", "RESIDENTIAL", "TOWNHOUSE", "CONDO", "MH",
                 "MULTI-FAMILY", "DUPLEX"}:
        use_tier = 3
    else:
        use_tier = 2
    return (sole_tier, use_tier, _market_value_key(n))


def collapse_by_case(notices: list[NoticeData]) -> list[tuple[NoticeData, list[NoticeData]]]:
    """Group notices by case_number; return [(main_parcel, [extra_parcels])].

    Main parcel selection (in order of preference):
      1. Residential / SFR / Condo / Townhouse (the actual house)
      2. Unknown use-type (when no classification is available)
      3. Vacant land
      4. Commercial / industrial
    Within same use-tier, highest estimated_value wins.

    Notices without a case_number get returned individually.
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
        items_sorted = sorted(items, key=_main_parcel_priority, reverse=True)
        main, extras = items_sorted[0], items_sorted[1:]
        out.append((main, extras))
    return out


# FTM-style color palette
_HEADER_FILL_COLOR = "1B5E20"        # dark green
_HEADER_TEXT_COLOR = "FFFFFF"        # white
_BAND_FILL_COLOR = "FFFDE7"          # very light yellow (banded rows)
_DEFAULT_ROW_HEIGHT = 16             # single-line height


def write_ftm_xlsx(
    notices: list[NoticeData],
    out_path: Path,
    *,
    tag_override: str = "",
    collapse_multi_parcel: bool = True,
) -> int:
    """Write the FTM Estates output as XLSX with a County dropdown.

    Styling: dark-green header with white bold text + alternating white /
    pale-yellow banded rows. Single-line row height (Notes shown truncated
    in cell but full content preserved in the underlying value — hover or
    expand row to see).

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

    # Sort rows by County (alphabetical) then by Case No. — keeps each
    # county's leads grouped together for visual scan-ability.
    rows.sort(key=lambda r: ((r.get("County") or "ZZZ"), r.get("Case No.", "")))

    wb = Workbook()
    ws = wb.active
    ws.title = "NC Estates"

    # Header row — dark green fill, bold white text
    header_font = Font(bold=True, color=_HEADER_TEXT_COLOR)
    header_fill = PatternFill(start_color=_HEADER_FILL_COLOR,
                              end_color=_HEADER_FILL_COLOR, fill_type="solid")
    for col_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 20

    # Data rows — single-line height, per-county color tint (replaces the
    # old yellow-alternating-band so county groups are visually distinct).
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

    # County dropdown — applied to the full County column
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

    # Column widths — make the important fields legible
    col_widths = {
        "File Date": 11, "County": 14, "Case No.": 18, "Deceased Owner": 32,
        "Personal Representative": 25, "First Name": 16, "Last Name": 18,
        "Mailing Address": 28, "Mailing City": 16, "Mailing State": 7, "Mailing Zip": 8,
        "Parcel ID": 16, "Property Address": 28, "Property City": 16,
        "Property State": 8, "Property Zip": 8, "Property use": 14,
        "Property Value": 14,
        "Notes": 40, "Beneficiaries": 80, "Phone 1": 14, "Tags": 26, "List": 10,
        # Heir / Decision Maker columns
        "DM Name": 22, "DM Relationship": 14, "DM Phone": 14, "DM Email": 26,
        "DM 2 Name": 22, "DM 2 Relationship": 14,
        "DM 3 Name": 22, "DM 3 Relationship": 14,
    }
    for c_idx, col_name in enumerate(FTM_COLUMNS, start=1):
        dim = ws.column_dimensions[get_column_letter(c_idx)]
        dim.width = col_widths.get(col_name, 14)
        if col_name in HIDDEN_FROM_WORKBOOK:
            dim.hidden = True

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
