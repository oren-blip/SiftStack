"""Export polished NC probate rows to a DataSift-native upload CSV.

The pipeline's FTM columns ("Property Address", "Property Zip", …) don't match
DataSift's field names ("Property Street Address", "Property ZIP Code", …), so
every upload needed manual column-mapping in the wizard. This writes a CSV whose
headers ARE DataSift's field names, so the upload auto-maps with no dragging.

Per Oren (2026-07-11):
  - drop Tags and List — he uploads to a master "Probate" list and tags by week
    inside DataSift, so those columns are redundant.
  - drop the Zillow URL — DataSift shows the listing in the property record after
    upload.

The header order below is the emit order. Beneficiaries is a custom field Oren
added in DataSift; DataSift maps a header of the same name to it.
"""
from __future__ import annotations

import csv
from pathlib import Path

# (DataSift header, source FTM key or None). None => constant/derived, handled
# in _row_to_datasift. Order = column order in the file.
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
    ("Phone 1",                 None),   # Phone 1, else DM Phone
    ("Email 1",                 "DM Email"),
    ("Estimated Value",         "Property Value"),
    ("Structure Type",          "Property use"),
    ("Parcel ID",               "Parcel ID"),
    ("Personal Representative", "Personal Representative"),
    ("County",                  "County"),
    ("Notice Type",             None),   # constant "Probate"
    ("Owner Deceased",          None),   # constant "Yes"
    ("Date Added",              "File Date"),
    ("Decedent Name",           "Deceased Owner"),
    ("Date of Death",           "Date of Death (App)"),
    ("Decision Maker",          "DM Name"),
    ("DM Relationship",         "DM Relationship"),
    ("DM 2 Name",               "DM 2 Name"),
    ("DM 2 Relationship",       "DM 2 Relationship"),
    ("DM 3 Name",               "DM 3 Name"),
    ("DM 3 Relationship",       "DM 3 Relationship"),
    ("Beneficiaries",           "Beneficiaries"),   # Oren's DataSift custom field
    ("Notes",                   "Notes"),
]

DATASIFT_UPLOAD_COLUMNS = [h for h, _ in _FIELD_MAP]


def _row_to_datasift(r: dict) -> dict:
    out: dict[str, str] = {}
    for header, src in _FIELD_MAP:
        if src is not None:
            out[header] = (r.get(src) or "").strip()
    # Phone 1: prefer the pipeline's Phone 1; fall back to the DM's phone.
    out["Phone 1"] = (r.get("Phone 1") or r.get("DM Phone") or "").strip()
    # Constants — every NC row is a probate with a deceased owner.
    out["Notice Type"] = "Probate"
    out["Owner Deceased"] = "Yes"
    return out


def write_datasift_upload_csv(rows: list[dict], path: str | Path) -> int:
    """Write `rows` (polished FTM dicts) to a DataSift-native upload CSV.

    Returns the number of rows written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=DATASIFT_UPLOAD_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(_row_to_datasift(r))
    return len(rows)
