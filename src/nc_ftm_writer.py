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


def _build_notes(notice: NoticeData) -> str:
    """Build the multi-line Notes block — beneficiary list, extra notes."""
    parts: list[str] = []
    if notice.beneficiaries_json:
        try:
            bens = json.loads(notice.beneficiaries_json)
        except (ValueError, TypeError):
            bens = []
        if bens:
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


def notice_to_ftm_row(notice: NoticeData, *, tag_override: str = "") -> dict[str, str]:
    """Convert one NoticeData record to a single FTM-format dict."""
    tag = tag_override or _iso_week_tag(notice.date_added)
    return {
        "File Date":        _format_date(notice.date_added),
        "County":           notice.county,
        "Case No.":         notice.case_number,
        "Deceased Owner":   _format_decedent(notice.decedent_name),
        "First Name":       notice.executor_first_name,
        "Last Name":        notice.executor_last_name,
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
        "Notes":            _build_notes(notice),
        "Phone 1":          notice.primary_phone,
        "Tags":             tag,
        "List":             "PROBATE",
    }


def write_ftm_csv(
    notices: list[NoticeData],
    out_path: Path,
    *,
    tag_override: str = "",
) -> int:
    """Write NoticeData list to a CSV matching the FTM Estates format.

    Returns the number of rows written.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [notice_to_ftm_row(n, tag_override=tag_override) for n in notices]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FTM_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    logger.info("Wrote %d NC Estates rows to %s", len(rows), out_path)
    return len(rows)
