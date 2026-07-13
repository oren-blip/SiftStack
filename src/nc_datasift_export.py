"""Export polished NC probate rows to a DataSift-native upload CSV.

The pipeline's FTM columns ("Property Address", "Property Zip", …) don't match
DataSift's field names ("Property Street Address", "Property ZIP Code", …), so
every upload needed manual column-mapping in the wizard. This writes a CSV whose
headers ARE DataSift's field names, so the upload auto-maps with no dragging.

Per Oren (2026-07-11):
  - drop the List column — he selects the master "PROBATE" list in the wizard.
  - drop the Zillow URL — DataSift shows the listing in the property record.
  - Tags column auto-populated with exactly "Courthouse Data" and
    "NC Estates Week <N> 2026" so he no longer types them in the wizard.
  - File Date maps to DataSift's custom "Probate Open Date" field.
  - Owner First/Last = the PR (the mail contact), Decedent Name = the deceased.
  - Phone 2-9 / Email 2-5 emitted empty so Tracerfy / DataSift skip-trace numbers
    land in the right built-in fields.
"""
from __future__ import annotations

import csv
from pathlib import Path

# Our property classification (SFR/MH/Vacant Land) goes to a DataSift CUSTOM
# field named "Property Type", NOT the built-in "Structure Type". DataSift's
# built-in Structure Type is enrichment-controlled — it derives it from its own
# property database and ignores an uploaded value (Oren confirmed it wouldn't
# populate). A custom text field preserves our own buy-box classification, so we
# send the raw value as-is. Oren must create the "Property Type" custom field in
# DataSift once for this column to auto-map.
_PROPERTY_TYPE_FIELD = "Property Type"

# Empty phone/email slots so Tracerfy / DataSift skip-trace numbers map cleanly.
_PHONE_SLOTS = [f"Phone {i}" for i in range(1, 10)]   # Phone 1-9
_EMAIL_SLOTS = [f"Email {i}" for i in range(1, 6)]    # Email 1-5

# (DataSift header, source FTM key or None). None => constant/derived in
# _row_to_datasift. Order = column order in the file.
_FIELD_MAP: list[tuple[str, str | None]] = [
    ("Property Street Address", "Property Address"),
    ("Property City",           "Property City"),
    ("Property State",          "Property State"),
    ("Property ZIP Code",       "Property Zip"),
    ("Owner First Name",        "First Name"),
    ("Owner Last Name",         "Last Name"),
    ("Mailing Street Address",  "Mailing Address"),
    ("Mailing City",            "Mailing City"),
    ("Mailing State",           "Mailing State"),
    ("Mailing ZIP Code",        "Mailing Zip"),
    *[(p, None) for p in _PHONE_SLOTS],
    *[(e, None) for e in _EMAIL_SLOTS],
    # Removed 2026-07-12 per Oren: Estimated Value (DataSift's own enrichment
    # step fills it), County, Notice Type (all rows are probate), Owner Deceased,
    # Date of Death — none needed in the upload.
    ("Property Type",           None),   # custom field <- raw Property use
    # APN dropped 2026-07-12: DataSift's parcel field is enrichment-controlled
    # (derived from its own property DB by address, like Estimated Value /
    # Structure Type) — it ignores an uploaded APN and won't auto-map it. Let
    # DataSift's "Enrich Property Information" fill it. Every remaining column
    # now auto-maps by name, so no manual drag is ever needed.
    ("Personal Representative", "Personal Representative"),
    ("Probate Open Date",       "File Date"),
    ("decedent",                "Deceased Owner"),   # matches Oren's DataSift custom field "decedent"
    ("Decision Maker",          "DM Name"),
    ("DM Relationship",         "DM Relationship"),
    ("DM 2 Name",               "DM 2 Name"),
    ("DM 2 Relationship",       "DM 2 Relationship"),
    ("DM 3 Name",               "DM 3 Name"),
    ("DM 3 Relationship",       "DM 3 Relationship"),
    ("Beneficiaries",           "Beneficiaries"),   # Oren's DataSift custom field
    ("Notes",                   "Notes"),
    ("Tags",                    None),   # "Courthouse Data,NC Estates Week N 2026"
]

DATASIFT_UPLOAD_COLUMNS = [h for h, _ in _FIELD_MAP]


def _tags_for_week(week: int | None, year: int) -> str:
    tags = ["Courthouse Data"]
    if week:
        tags.append(f"NC Estates Week {week} {year}")
    return ",".join(tags)   # DataSift CSV tag separator is a comma


def _row_to_datasift(r: dict, tags: str) -> dict:
    out: dict[str, str] = {}
    for header, src in _FIELD_MAP:
        if src is not None:
            out[header] = (r.get(src) or "").strip()

    # Phones: Phone 1 = pipeline Phone 1, else the DM's phone. Phone 2 = the DM
    # phone if it wasn't already used as Phone 1. The rest stay empty for
    # Tracerfy / DataSift skip-trace to fill.
    for p in _PHONE_SLOTS:
        out[p] = ""
    for e in _EMAIL_SLOTS:
        out[e] = ""
    p1 = (r.get("Phone 1") or "").strip()
    dm_phone = (r.get("DM Phone") or "").strip()
    if p1:
        out["Phone 1"] = p1
        if dm_phone and dm_phone != p1:
            out["Phone 2"] = dm_phone
    elif dm_phone:
        out["Phone 1"] = dm_phone
    out["Email 1"] = (r.get("DM Email") or "").strip()

    out[_PROPERTY_TYPE_FIELD] = (r.get("Property use") or "").strip()
    out["Tags"] = tags
    return out


def write_datasift_upload_csv(rows: list[dict], path: str | Path,
                              week: int | None = None, year: int = 2026) -> int:
    """Write `rows` (polished FTM dicts) to a DataSift-native upload CSV.

    `week`/`year` populate the per-week Tags. Returns rows written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = _tags_for_week(week, year)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=DATASIFT_UPLOAD_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(_row_to_datasift(r, tags))
    return len(rows)
