"""Smoke test: fetch Mecklenburg tax foreclosures end-to-end.

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_mecklenburg_smoke.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mecklenburg_tax_scraper import scrape_mecklenburg_tax_foreclosures  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_mecklenburg_tax_foreclosures(
        include_vacant=False,
        include_commercial=False,
        seen_ids={},          # ignore prior runs
        max_records=8,        # keep output small
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county:      {n.county}")
        print(f"  notice_type: {n.notice_type}")
        print(f"  address:     {n.address!r}")
        print(f"  city/zip:    {n.city!r} / {n.zip!r}")
        print(f"  lat/lng:     {n.latitude} / {n.longitude}")
        print(f"  parcel_id:   {n.parcel_id}")
        print(f"  tax_due:     ${n.tax_delinquent_amount}  ({n.tax_delinquent_years} bills)")
        print(f"  estimated:   ${n.estimated_value}")
        print(f"  prop_type:   {n.property_type}")
        print(f"  beds/baths:  {n.bedrooms} / {n.bathrooms}")
        print(f"  report_url:  {n.report_url}")
        print()


if __name__ == "__main__":
    main()
