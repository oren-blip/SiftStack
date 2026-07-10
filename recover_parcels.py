"""Recover missing parcels by re-running county GIS with name variations.

For rows in the FTM CSV with no Parcel ID, generate name variations and
try each against the county GIS until a high-confidence match appears.
Captures property address, parcel ID, and property use type.

Variations tried (in order):
  1. Original decedent name (handles comma + space formats automatically)
  2. First + Last only (drop middle) — for cases where GIS records omit
     the middle name and our matcher's token-overlap fell below threshold
  3. Last name only at the default 0.6 last-only score floor — recovers
     spouse joint-ownership cases where the decedent's first name doesn't
     appear in the parcel owner string

Rows where NO variation finds a match are reported as "no property in
county under that name". These are likely genuine non-leads (decedent
rented, lived with family, owned in another county, held in trust/LLC).
They stay in the output with empty parcel fields so you can decide
whether to mail-to-property-address (if there's an executor mailing) or
drop the row entirely.

Usage:
    python recover_parcels.py
    python recover_parcels.py --csv output/nc_estates_ftm_X.csv
    python recover_parcels.py --min-score 0.5    # looser threshold
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nc_gis_lookup import (  # noqa: E402
    _candidate_to_address_parts,
    filter_for_lead_quality,
    lookup_properties,
    pick_best_candidate,
    simplify_use_code,
    split_decedent_name,
)
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("recover_parcels")


# Slow-GIS counties — kept in sync with fix_addresses_and_prep.py:_SLOW_GIS_COUNTIES.
_SLOW_GIS_COUNTIES = {"cabarrus"}


def name_variations(decedent: str, county: str = "") -> list[str]:
    """Return distinct name strings to retry GIS lookup with.

    Order matches Oren's manual search workflow:
      1. "LAST FIRST MIDDLE"
      2. "LAST FIRST M" (middle initial)
      3. decedent as-passed (e.g. "Last, First Middle") — fast counties only

    Dropped 2026-05-30 per user: "FIRST MIDDLE LAST" and bare "LAST".

    Slow-GIS counties (Cabarrus's polaris3g averages 4-6 min per call)
    stop after positions 1-2.
    """
    first, mid, last = split_decedent_name(decedent)
    mid_initial = mid[0] if mid else ""

    if county.lower() in _SLOW_GIS_COUNTIES:
        if last and first and mid:
            raw = [
                f"{last} {first} {mid}".strip(),
                f"{last} {first} {mid_initial}".strip(),
            ]
        elif last and first:
            raw = [f"{last} {first}".strip()]
        else:
            raw = [decedent]
    else:
        raw = [
            f"{last} {first} {mid}".strip() if (last and first and mid) else None,
            f"{last} {first} {mid_initial}".strip() if (last and first and mid) else None,
            decedent,
        ]
    seen: set[str] = set()
    out: list[str] = []
    for v in raw:
        v_norm = (v or "").strip()
        if v_norm and v_norm.upper() not in seen:
            seen.add(v_norm.upper())
            out.append(v_norm)
    return out


def apply_property_to_row(row: dict, c) -> None:
    """Apply a PropertyCandidate to a CSV row dict."""
    street, city, zipc = _candidate_to_address_parts(c)
    row["Parcel ID"] = c.pid or ""
    row["Property Address"] = street
    row["Property City"] = city
    row["Property State"] = "NC"
    row["Property Zip"] = zipc
    if not (row.get("Property use") or "").strip() and c.use_code:
        row["Property use"] = simplify_use_code(c.use_code, c.use_description, c.county)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="FTM CSV path (default: latest in output/)")
    ap.add_argument("--min-score", type=float, default=0.7,
                    help="GIS match score threshold (default 0.7; lower = "
                         "looser, recovers more but more false-positive risk)")
    ap.add_argument("--inter-row-delay", type=float, default=0.5,
                    help="Sleep seconds between rows (default 0.5)")
    args = ap.parse_args()

    src_csv = Path(args.csv) if args.csv else max(Path("output").glob("nc_estates_ftm_*.csv"))
    logger.info("Source CSV: %s", src_csv)
    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    logger.info("Loaded %d rows", len(rows))

    # Targets: rows with no parcel, has a decedent name, decedent is not garbage
    target = [
        r for r in rows
        if not (r.get("Parcel ID") or "").strip()
        and (r.get("Deceased Owner") or "").strip()
        and "IN THE MATTER" not in (r.get("Deceased Owner") or "").upper()
    ]
    skipped_garbage = sum(
        1 for r in rows
        if not (r.get("Parcel ID") or "").strip()
        and "IN THE MATTER" in (r.get("Deceased Owner") or "").upper()
    )
    logger.info("Targets: %d rows with no parcel + valid decedent (%d skipped — garbage decedent)",
                len(target), skipped_garbage)

    recovered = 0
    no_match = 0
    by_county_recovered: dict[str, int] = {}
    by_county_no_match: dict[str, int] = {}

    for i, r in enumerate(target, 1):
        county = r["County"]
        dec = r["Deceased Owner"]
        if i > 1:
            time.sleep(args.inter_row_delay)

        variations = name_variations(dec, county)
        found = None
        used_variation = ""
        for v in variations:
            try:
                results = lookup_properties(v, county, min_score=args.min_score)
            except Exception:
                logger.exception("Lookup error for %s/%s (variation %r)", county, dec, v)
                continue
            if not results:
                continue
            # Apply heir-occupancy + commercial filters
            kept = filter_for_lead_quality(results)
            if not kept:
                continue
            # Pick the best parcel (suffix > score > decedent-address affinity >
            # middle name > use_tier > value > acres) — collapse_by_case will
            # treat it as main and list extras in Notes.
            best = pick_best_candidate(kept, dec, r.get("Decedent Address") or "")
            if not best:
                continue
            found = best
            used_variation = v
            break

        if found:
            apply_property_to_row(r, found)
            recovered += 1
            by_county_recovered[county] = by_county_recovered.get(county, 0) + 1
            logger.info("[%3d/%d] %s/%-30s OK via %r -> %s",
                        i, len(target), county, dec[:30], used_variation,
                        (found.situs_address or "?")[:50])
        else:
            no_match += 1
            by_county_no_match[county] = by_county_no_match.get(county, 0) + 1
            logger.info("[%3d/%d] %s/%-30s no match (tried %d variations)",
                        i, len(target), county, dec[:30], len(variations))

    # Write outputs
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_csv = Path("output") / f"nc_estates_ftm_{ts}.csv"
    out_xlsx = Path("output") / f"nc_estates_ftm_{ts}.xlsx"
    write_csv(rows, out_csv)
    write_xlsx(rows, out_xlsx)

    logger.info("=" * 60)
    logger.info("Recovered: %d   No match: %d   Garbage decedents skipped: %d",
                recovered, no_match, skipped_garbage)
    logger.info("By county recovered: %s", dict(sorted(by_county_recovered.items())))
    logger.info("By county no-match: %s   (these likely have no property under "
                "decedent's name in our 7 counties — candidates to drop or to "
                "mail 'Estate of [Deceased]' to executor mailing address only)",
                dict(sorted(by_county_no_match.items())))


if __name__ == "__main__":
    main()
