"""One-off owner search against the raw county tax layers.

For manual pulls: when a decedent doesn't show up on a county's public GIS
search page, run this — it queries the same raw parcel layer the pipeline
uses, which exposes second-owner / co-owner fields the public search page
doesn't index (e.g. a deceased wife listed as Jan1Own2 behind her husband
on Iredell — Maynard, Korene S, Week 31).

Usage:
    python gis_lookup.py "Maynard, Korene S" Iredell
    python gis_lookup.py "Smith, John" Mecklenburg --min-score 0.4
    python gis_lookup.py "THE PIERCE FAMILY TRUST" Catawba --min-score 0.3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help='Decedent name — "Last, First Middle" or "First Middle Last"')
    ap.add_argument("county", help="Cabarrus / Catawba / Gaston / Iredell / Lincoln / Mecklenburg / Rowan")
    ap.add_argument("--min-score", type=float, default=0.4,
                    help="Match threshold 0-1 (default 0.4 — the review band; pipeline "
                         "auto-accepts at 0.7)")
    args = ap.parse_args()

    import logging
    logging.basicConfig(level=logging.WARNING)  # keep the output clean
    from nc_gis_lookup import lookup_properties

    cands = lookup_properties(args.name, args.county.title(), min_score=args.min_score)
    if not cands:
        print(f"No parcels matched {args.name!r} in {args.county} at score >= {args.min_score}.")
        print("Try --min-score 0.3, or a different name order/spelling.")
        return 1

    print(f"{len(cands)} parcel(s) for {args.name!r} in {args.county} "
          f"(best name-match first; pipeline auto-accepts >= 0.7):\n")
    for c in sorted(cands, key=lambda c: (-c.match_score, -(c.market_value or 0))):
        val = f"${c.market_value:,.0f}" if c.market_value else "value n/a"
        print(f"  PID {c.pid}   [match {c.match_score:.2f}]")
        print(f"    Deed owner : {c.owner_name}")
        print(f"    Property   : {c.situs_address or '(no situs address)'}")
        print(f"    Tax bill to: {c.mailing_address or '(none)'}")
        extras = [val, c.use_description or c.use_code]
        if c.year_built:
            extras.append(f"built {c.year_built}")
        if c.lot_area:
            extras.append(f"{c.lot_area:.2f} ac")
        print(f"    {'  |  '.join(str(e) for e in extras if e)}")
        print(f"    Owner off-site: {'yes (KEEP signal)' if c.owner_offsite else 'no — tax bill goes to the property'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
