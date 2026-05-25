"""Final FTM CSV polish before DataSift upload.

Two transformations the user wants applied to every weekly FTM output
right before upload:

1. **Filter out rows with no property** — drop any row whose Parcel ID
   is blank. These are decedents whose property records didn't surface
   in any of our county GIS lookups (rented, lived with family, owned
   in another county, held in trust/LLC, or just no real estate). They
   aren't actionable real-estate leads.

2. **Convert no-executor rows to "Heirs of [Decedent]" contact** — for
   the remaining rows that have a property but no court-named executor,
   replace the executor identity with "Heirs of [Decedent Name]" and
   point the mailing address at the property itself. This puts the row
   into a ready-to-upload state — DataSift's built-in skip trace will
   find whoever currently lives at the address (heir, tenant, or
   confirmed-vacant signal).

Fields written for the "Heirs of" contact:
- Personal Representative: "Heirs of {Decedent}"
- First Name:        "Heirs"
- Last Name:         decedent's last name (parsed via split_decedent_name)
- Mailing Address:   property street
- Mailing City:      property city
- Mailing State:     "NC"
- Mailing Zip:       property zip

Rows that already have a court-named executor are untouched.

Usage:
    python prepare_for_datasift.py
    python prepare_for_datasift.py --csv output/nc_estates_ftm_X.csv
    python prepare_for_datasift.py --keep-no-parcel  # skip step 1
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_gis_lookup import split_decedent_name  # noqa: E402
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prep_datasift")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="FTM CSV path (default: latest in output/)")
    ap.add_argument("--keep-no-parcel", action="store_true",
                    help="Don't drop rows with no Parcel ID (default: drop them)")
    args = ap.parse_args()

    src_csv = Path(args.csv) if args.csv else max(Path("output").glob("nc_estates_ftm_*.csv"))
    logger.info("Source: %s", src_csv)
    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    logger.info("Loaded %d rows", len(rows))

    # ── Step 1: Filter out no-parcel rows ────────────────────────────
    if args.keep_no_parcel:
        kept = rows
        dropped = 0
    else:
        dropped_rows = [r for r in rows if not (r.get("Parcel ID") or "").strip()]
        kept = [r for r in rows if (r.get("Parcel ID") or "").strip()]
        dropped = len(dropped_rows)
        logger.info("Step 1: dropped %d rows with no Parcel ID (kept %d)", dropped, len(kept))
        if dropped_rows:
            from collections import Counter
            by_county = Counter(r["County"] for r in dropped_rows)
            logger.info("  Dropped by county: %s", dict(sorted(by_county.items())))

    # ── Step 2: Convert no-executor rows to "Heirs of [Decedent]" ───
    heirs_applied = 0
    for r in kept:
        if (r.get("Personal Representative") or "").strip():
            continue  # has executor — leave it alone
        decedent = (r.get("Deceased Owner") or "").strip()
        if not decedent or "IN THE MATTER" in decedent.upper():
            continue  # nothing useful to write
        # Get decedent's last name for the Last Name slot
        _first, _mid, last = split_decedent_name(decedent)
        # Build the "Heirs of" contact identity
        r["Personal Representative"] = f"Heirs of {decedent}"
        r["First Name"] = "Heirs"
        r["Last Name"] = last.title() if last.isupper() else last
        # Point mailing address at the property itself
        prop_addr = (r.get("Property Address") or "").strip()
        prop_city = (r.get("Property City") or "").strip()
        prop_zip = (r.get("Property Zip") or "").strip()
        if prop_addr:
            r["Mailing Address"] = prop_addr
        if prop_city:
            r["Mailing City"] = prop_city
        r["Mailing State"] = "NC"
        if prop_zip:
            r["Mailing Zip"] = prop_zip
        heirs_applied += 1
    logger.info("Step 2: rewrote %d no-executor rows as 'Heirs of [Decedent]'",
                heirs_applied)

    # ── Write outputs ────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_csv = Path("output") / f"nc_estates_ftm_{ts}_datasift.csv"
    out_xlsx = Path("output") / f"nc_estates_ftm_{ts}_datasift.xlsx"
    write_csv(kept, out_csv)
    write_xlsx(kept, out_xlsx)

    logger.info("=" * 60)
    logger.info("DataSift-ready file written:")
    logger.info("  Rows in:  %d", len(rows))
    logger.info("  Dropped:  %d (no parcel)", dropped)
    logger.info("  Heirs:    %d (Executor renamed to 'Heirs of [Decedent]')", heirs_applied)
    logger.info("  Rows out: %d", len(kept))
    logger.info("  CSV:      %s", out_csv)
    logger.info("  XLSX:     %s", out_xlsx)


if __name__ == "__main__":
    main()
