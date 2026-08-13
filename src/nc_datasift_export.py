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
import json
import re
from pathlib import Path

# Manual-archive index of cases Oren has already pulled by hand and uploaded to
# DataSift himself (built by build_manual_archive_index.py from his FTM workbook).
MANUAL_INDEX_PATH = Path("output") / ".manual_archive_index.json"

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
    # Property Type dropped 2026-07-15 per Oren: DataSift's "Enrich Property
    # Information" step fills the structure type from its own property DB, so
    # uploading our raw Property use is redundant.
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


# Tag stamped on any row whose Phone 1 / secondary phone was pulled straight
# from a court-filed PDF (cover sheet / family history / funeral bill). Lets
# Oren filter court-verified numbers apart from DataSift skip-trace numbers.
# The signal is the "pdf-phone" marker nc_phone_backfill writes into Match Reason.
COURT_PHONE_TAG = "court-verified-phone"
# Same idea for the Enformion PersonSearch fallback (nc_deep_prospect writes
# "enformion-phone" into Match Reason) — honest phone-source labeling so the
# CRM never implies these came from Tracerfy or DataSift skip trace.
ENFORMION_PHONE_TAG = "enformion-phone"

# Tag for rows whose contact is the "Heirs of <Decedent>" placeholder. Skip
# trace matches a PERSON by name — nobody is named "Heirs", so every paid
# trace of these rows is guaranteed-empty spend, and worse, the trace marks
# them "already skipped" so they park in the '01. Skipped No Numbers' preset
# looking finished instead of surfacing as needs-research. These rows get
# this tag INSTEAD of the per-upload trace-scope tag, so the post-upload
# skip trace never sees them (Weeks 32-33: 7 of 17 phoneless rows were paid
# traces of "Heirs Shands" / "Heirs Baker" / etc.).
NEEDS_DP_TAG = "Needs DP"

# Per-upload trace-scope tag prefix. write_datasift_upload_csv stamps
# "Skip Trace <run stamp> [WN]" onto every NON-placeholder row; then
# upload_netnew_datasift.py reads the tag back out of the CSV and scopes the
# paid post-upload skip trace to it (instead of the batch tag, which covers
# the Heirs rows too).
TRACE_TAG_PREFIX = "Skip Trace "


def is_heirs_placeholder(r: dict) -> bool:
    """True when the row's contact is the 'Heirs of <Decedent>' fallback, not
    a real person (FTM row: First Name is literally 'Heirs')."""
    if (r.get("First Name") or "").strip().lower() == "heirs":
        return True
    return (r.get("Personal Representative") or "").strip().lower().startswith("heirs of")


def _tags_for_week(week: int | None, year: int) -> str:
    tags = ["Courthouse Data"]
    if week:
        tags.append(f"NC Estates Week {week} {year}")
    return ",".join(tags)   # DataSift CSV tag separator is a comma


def _row_to_datasift(r: dict, tags: str, trace_tag: str | None = None) -> dict:
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

    # Vacant lots have no street-numbered address ("KING WILKINSON RD"), so
    # DataSift's address-based enrichment can't resolve their parcel and leaves
    # it blank — even though our pipeline found it. The parcel column isn't
    # uploaded (DataSift ignores an uploaded APN), so surface it in Notes for
    # vacant-land rows only, where it's the sole way to keep the number, along
    # with a LandPortal deep link to the parcel (Oren works vacant lots there).
    # See Painter 26E000440-540 (Week 29): pipeline had 3665410548, DataSift blank.
    parcel = (r.get("Parcel ID") or "").strip()
    if parcel and "vacant" in (r.get("Property use") or "").lower():
        note = out.get("Notes", "").strip()
        additions = []
        if parcel not in note:
            additions.append(f"[Parcel ID: {parcel}]")
        try:
            from landportal_lookup import get_property_url
            url = get_property_url(parcel, r.get("County", ""))
        except Exception:
            url = ""
        if url and url not in note:
            additions.append(f"LandPortal: {url}")
        if additions:
            out["Notes"] = "\n".join([note] + additions).strip() if note else "\n".join(additions)

    # Append phone-source tags when this row's number came from a court PDF
    # or the Enformion fallback (never overwrites the base per-week tags).
    mr = r.get("Match Reason") or ""
    extra = [t for marker, t in (("pdf-phone", COURT_PHONE_TAG),
                                 ("enformion-phone", ENFORMION_PHONE_TAG))
             if marker in mr]
    # Carry the FTM row's own workflow tags through to DataSift. These are
    # Oren's lead flags ("Lot Cluster", "Surviving Spouse?", "Multi-Signer
    # (N)", "Verify: No PR Address", ...) — before 2026-08-12 this column was
    # silently dropped, so none of them were filterable in DataSift.
    extra += [t.strip() for t in (r.get("Tags") or "").split(",") if t.strip()]
    # Placeholder contacts get "Needs DP" INSTEAD of the trace-scope tag, so
    # the paid post-upload skip trace never wastes a charge on a non-person.
    if is_heirs_placeholder(r):
        extra.append(NEEDS_DP_TAG)
    elif trace_tag:
        extra.append(trace_tag)
    seen: set[str] = set()
    all_tags = []
    for t in tags.split(",") + extra:
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            all_tags.append(t)
    out["Tags"] = ",".join(all_tags)
    return out


def _name_token_key(name: str) -> str:
    """Order-independent name key. MUST stay identical to
    build_manual_archive_index.py:name_token_key and
    fix_addresses_and_prep.py:_name_token_key so the archive keys line up.
    """
    s = (name or "").upper()
    s = re.sub(r"\bAKA\b.*", "", s)
    s = re.sub(r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR)\.?\b", "", s)
    tokens = sorted(t for t in re.findall(r"[A-Z]+", s) if len(t) >= 3)
    return " ".join(tokens)


def _norm_addr(addr: str) -> str:
    """Collapse an address to letters+digits only, uppercased — so '123 Main St'
    and '123 MAIN STREET' still won't collide, but '123 Main St' vs '123  Main
    St.' do. DataSift itself merges only on near-exact address text, so this is a
    deliberately loose key used ONLY to spot cases already in the manual file."""
    return re.sub(r"[^A-Z0-9]", "", (addr or "").upper())


# Through this ISO week, Oren uploaded his manual pulls to DataSift himself, so
# archive-matched cases must stay OUT of the pipeline upload (they're already
# in the CRM under his address text). From the NEXT week on he stops uploading
# separately (2026-07-29): the pipeline upload carries EVERY workbook row —
# his hand-pulled cases included — in one combined upload, and only the upload
# ledger (what WE already committed) excludes.
MANUAL_SEPARATE_UPLOADS_THROUGH_WEEK = 31


def _archive_week(label: str) -> int:
    m = re.search(r"week\s*0*(\d+)", label or "", re.I)
    return int(m.group(1)) if m else -1  # unknown week = treat as historical


def load_manual_archive(index_path: str | Path = MANUAL_INDEX_PATH) -> dict | None:
    """Load the manual-archive index into fast lookup maps (key -> ISO week of
    the manual entry). Returns None if the index file is missing/unreadable
    (caller then skips net-new filtering)."""
    try:
        with Path(index_path).open(encoding="utf-8") as f:
            entries = json.load(f).get("_entries", {})
    except (OSError, ValueError):
        return None
    case_nos: dict[str, int] = {}
    name_keys: dict[str, int] = {}
    addrs: dict[tuple[str, str], int] = {}
    for key, e in entries.items():
        wk = _archive_week(e.get("week", ""))
        cn = (e.get("case_no") or "").strip().upper()
        if cn:
            case_nos[cn] = wk
        name_keys[key] = wk
        pa = _norm_addr(e.get("property_address", ""))
        if pa:
            addrs[(pa, (e.get("property_zip") or "").strip()[:5])] = wk
    return {"case_nos": case_nos, "name_keys": name_keys, "addrs": addrs}


def in_manual_archive(row: dict, arc: dict) -> int | None:
    """The ISO week of Oren's manual entry for this row, or None if he never
    pulled it. -1 = archive entry with no parseable week (historical master).

    Matched three ways (any hit = his), strongest first:
      1. Case No. exact — the most reliable key.
      2. County + decedent name-token key — the archive's own key; catches rows
         whose Case No. is blank/differs.
      3. Property address + ZIP — catches name-spelling drift between his hand
         entry and eCourts (e.g. 'Katherine' vs 'Catherine') for the SAME house.
    """
    cn = (row.get("Case No.") or "").strip().upper()
    if cn and cn in arc["case_nos"]:
        return arc["case_nos"][cn]
    county = (row.get("County") or "").strip().upper()
    dec = row.get("Deceased Owner") or ""
    key = f"{county}||{_name_token_key(dec)}"
    if county and dec and key in arc["name_keys"]:
        return arc["name_keys"][key]
    pa = _norm_addr(row.get("Property Address", ""))
    ak = (pa, (row.get("Property Zip") or "").strip()[:5])
    if pa and ak in arc["addrs"]:
        return arc["addrs"][ak]
    return None


UPLOAD_LEDGER_PATH = Path("output") / ".netnew_uploaded.json"


def _case_no(row: dict) -> str:
    return (row.get("Case No.") or "").strip().upper()


def load_upload_ledger(path: str | Path = UPLOAD_LEDGER_PATH) -> set[str]:
    """Case numbers a prior pipeline NETNEW upload already committed to
    DataSift. Empty set when the ledger doesn't exist yet."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            return {str(c).strip().upper() for c in json.load(f).get("cases", [])}
    except (OSError, ValueError):
        return set()


def record_uploaded_cases(case_nos: list[str],
                          path: str | Path = UPLOAD_LEDGER_PATH) -> int:
    """Append committed-upload case numbers to the ledger (idempotent).
    Called by upload_netnew_datasift.py AFTER the wizard's Finish commits.
    Returns the ledger's new total."""
    existing = load_upload_ledger(path)
    merged = existing | {c.strip().upper() for c in case_nos if c and c.strip()}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump({"cases": sorted(merged)}, f, indent=1)
    return len(merged)


def write_datasift_upload_csv(rows: list[dict], path: str | Path,
                              week: int | None = None, year: int = 2026,
                              write_netnew: bool = True) -> int:
    """Write `rows` (polished FTM dicts) to a DataSift-native upload CSV.

    `week`/`year` populate the per-week Tags. Returns rows written.

    When `write_netnew` is set and the manual-archive index exists, ALSO writes a
    `<name>_NETNEW.csv` sibling containing only the cases NOT already in
    DataSift — excluded when EITHER Oren pulled the case by hand (manual-archive
    index) OR a prior pipeline upload committed it (the upload ledger,
    output/.netnew_uploaded.json, appended by upload_netnew_datasift.py after
    each committed upload). Without the ledger, a case uploaded from Monday's
    NETNEW re-appeared in Tuesday's and got re-skip-traced (pay-per-record).
    The full file stays for reference.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = _tags_for_week(week, year)
    # Per-upload trace-scope tag: unique per pipeline run AND per week file
    # (the nightly writes week32 + week33 files with the same run stamp — a
    # date-only tag would make the second upload's skip trace re-charge the
    # first batch). upload_netnew_datasift.py reads this back from the CSV.
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{6})", path.stem)
    stamp = f"{m.group(1)} {m.group(2)}" if m else \
        __import__("datetime").datetime.now().strftime("%Y-%m-%d %H%M%S")
    trace_tag = f"{TRACE_TAG_PREFIX}{stamp}" + (f" W{week}" if week else "")
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=DATASIFT_UPLOAD_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(_row_to_datasift(r, tags, trace_tag))

    if write_netnew:
        arc = load_manual_archive()
        uploaded = load_upload_ledger()
        netnew_path = path.with_name(f"{path.stem}_NETNEW.csv")
        if arc is None:
            # No index -> can't tell what's already his. Mirror the full file so
            # the NETNEW name still exists, but the caller's log flags it.
            netnew_rows = list(rows)
        else:
            def _already_in_datasift(r: dict) -> bool:
                if _case_no(r) in uploaded:
                    return True  # a prior pipeline upload committed it
                wk = in_manual_archive(r, arc)
                # Archive-matched cases are excluded only for the weeks Oren
                # still uploaded his manual himself. From Week
                # MANUAL_SEPARATE_UPLOADS_THROUGH_WEEK+1 on, the combined
                # upload carries his cases too (his rule, 2026-07-29).
                return wk is not None and wk <= MANUAL_SEPARATE_UPLOADS_THROUGH_WEEK
            netnew_rows = [r for r in rows if not _already_in_datasift(r)]
        with netnew_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=DATASIFT_UPLOAD_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in netnew_rows:
                w.writerow(_row_to_datasift(r, tags, trace_tag))
        # Sidecar manifest: the upload CSV itself has no Case No. column, so
        # upload_netnew_datasift.py reads THIS to append the committed cases
        # to the upload ledger.
        with netnew_path.with_suffix(".cases.json").open("w", encoding="utf-8") as f:
            json.dump({"cases": sorted({_case_no(r) for r in netnew_rows if _case_no(r)})},
                      f, indent=1)

    return len(rows)
