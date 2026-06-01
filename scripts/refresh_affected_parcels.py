"""One-off: refresh parcel data for the 8 Week 22 cases where main-parcel
selection picked the wrong parcel (joint-owned residence instead of solely-
owned probate asset). Uses the new c682de6 logic so the workbook reflects
the fix without a full re-scrape.

Affected cases (Cabarrus 4 + Rowan 4) from Oren's manual-vs-workbook diff.

Run:
    python scripts/refresh_affected_parcels.py
Output:
    - Edits the latest Week 22 *_datasift.csv in place
    - Re-runs consolidate_weeks.py automatically
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nc_gis_lookup import (
    extract_co_owner_names,
    filter_for_lead_quality,
    is_likely_survivorship,
    lookup_properties,
    simplify_use_code,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("refresh")

# (case_no, county, decedent_name) — pulled from Oren's manual-vs-workbook diff
AFFECTED = [
    ("26E000566-120", "Cabarrus", "Bonds, Bobby Ray"),
    ("26E000574-120", "Cabarrus", "bailey, jerry allen"),
    ("26E000577-120", "Cabarrus", "Sifford, Margaret Jane Cline"),
    ("26E000565-120", "Cabarrus", "Miller, Marion Russell Jr."),
    ("26E000575-790", "Rowan",    "Yelton , Ernest Lamar"),
    ("26E000583-790", "Rowan",    "Austin, Donald Frank"),
    ("26E000589-790", "Rowan",    "Corley, Sandra Rabon"),
    ("26E000594-790", "Rowan",    "Simmons, Tommy M."),
]


def _main_parcel_sort_key(c, decedent: str, beneficiaries_json: str) -> tuple:
    """Mirror nc_ftm_writer._main_parcel_priority on PropertyCandidate.
    (probate_tier, use_tier, market_value) — descending.

    In-probate when sole OR joint-with-non-beneficiary (likely TIC).
    Survivorship when joint with a court-recognized beneficiary.
    """
    is_joint = bool(c.is_jointly_owned)
    is_survivorship = is_likely_survivorship(c.owner_name, decedent, beneficiaries_json)
    in_probate = (not is_joint) or (is_joint and not is_survivorship)
    probate_tier = 1 if in_probate else 0
    if c.is_commercial:
        use_class = "COMMERCIAL"
    elif c.is_vacant_land:
        use_class = "VACANT"
    elif c.is_residential:
        use_class = "RESIDENTIAL"
    else:
        use_class = "UNKNOWN"
    if in_probate:
        use_tier = {"RESIDENTIAL": 3, "UNKNOWN": 2, "VACANT": 1, "COMMERCIAL": 0}[use_class]
    else:
        use_tier = {"VACANT": 3, "UNKNOWN": 2, "RESIDENTIAL": 1, "COMMERCIAL": 0}[use_class]
    mv = float(c.market_value or 0)
    return (probate_tier, use_tier, mv)


def _format_extras_note(extras: list) -> str:
    if not extras:
        return ""
    lines = [f"PLUS {len(extras)} PARCEL{'S' if len(extras) > 1 else ''}"]
    for e in extras:
        bits = []
        if e.pid:
            bits.append(str(e.pid))
        addr = " ".join(filter(None, [e.situs_address or "", e.situs_city_override or "", e.situs_zip_override or ""])).strip()
        if addr:
            bits.append(addr)
        joint_tag = "[JOINT]" if e.is_jointly_owned else "[SOLE]"
        use_tag = "[VACANT]" if e.is_vacant_land else ("[COMMERCIAL]" if e.is_commercial else "")
        if use_tag:
            bits.append(use_tag)
        bits.append(joint_tag)
        lines.append("  " + " | ".join(bits))
    return "\n".join(lines)


def refresh_row(row: dict) -> tuple[bool, str]:
    cn = (row.get("Case No.") or "").strip()
    county = (row.get("County") or "").strip()
    dec = (row.get("Deceased Owner") or "").strip()
    if not (cn and county and dec):
        return False, "missing case/county/decedent"

    candidates = lookup_properties(dec, county, min_score=0.7)
    kept = filter_for_lead_quality(candidates)
    if not kept:
        return False, f"no qualifying candidates after filter (raw={len(candidates)})"

    # Pull beneficiaries from the CSV row if available (added in build 1.0.30)
    bens_json = (row.get("Beneficiaries") or "").strip()
    # Note: row's Beneficiaries column is the rendered text, not the raw JSON.
    # For the cross-reference we need json — fall back to text-based parsing.
    # If it's plain text we treat it as a single JSON-encodable structure.
    # The text format is one beneficiary per line like "Last, First — addr".
    if bens_json and not bens_json.startswith("["):
        import json as _json
        synth = []
        for line in bens_json.splitlines():
            name = line.split("-")[0].split("—")[0].strip()
            if name and name.lower() != "beneficiary":
                synth.append({"name": name})
        bens_json = _json.dumps(synth)

    kept.sort(key=lambda c: _main_parcel_sort_key(c, dec, bens_json), reverse=True)
    main = kept[0]
    extras = kept[1:]

    old_pid = row.get("Parcel ID", "")
    old_prop = row.get("Property Address", "")

    row["Parcel ID"] = main.pid
    row["Property Address"] = main.situs_address or ""
    row["Property City"] = main.situs_city_override or ""
    row["Property Zip"] = main.situs_zip_override or ""
    row["Property use"] = simplify_use_code(main.use_code, main.use_description, main.county)
    if main.market_value is not None:
        row["Property Value"] = f"{main.market_value:.0f}"
    notes = _format_extras_note(extras)
    if notes:
        row["Notes"] = notes
    else:
        row["Notes"] = ""

    joint_tag = "[JOINT]" if main.is_jointly_owned else "[SOLE]"
    return True, f"{cn} {county} | {dec} | OLD pid={old_pid} prop={old_prop!r} | NEW pid={main.pid} prop={main.situs_address!r} {joint_tag} ({len(extras)} extras)"


def main() -> int:
    # Latest Week 22 datasift CSV
    candidates = sorted(Path("output").glob("nc_estates_ftm_*_week22_datasift.csv"))
    if not candidates:
        logger.error("No Week 22 datasift CSV found")
        return 1
    src = candidates[-1]
    logger.info("Source: %s", src.name)

    with src.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames
        rows = list(reader)

    targets = {(cn, co) for cn, co, _ in AFFECTED}
    updated = 0
    failed = 0
    for r in rows:
        key = ((r.get("Case No.") or "").strip(), (r.get("County") or "").strip())
        if key not in targets:
            continue
        ok, msg = refresh_row(r)
        if ok:
            updated += 1
            logger.info("UPDATED %s", msg)
        else:
            failed += 1
            logger.warning("SKIP    %s | %s", key, msg)

    logger.info("Done: updated=%d failed=%d", updated, failed)

    # Write back
    with src.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    logger.info("Wrote %s", src.name)

    # Rebuild XLSX sibling
    xlsx = src.with_suffix(".xlsx")
    if xlsx.exists():
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(cols)
        for r in rows:
            ws.append([r.get(c, "") for c in cols])
        wb.save(xlsx)
        logger.info("Wrote %s", xlsx.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
