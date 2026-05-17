"""Smoke test Mecklenburg delinquent-bill scraper."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mecklenburg_delinquent_scraper import scrape_mecklenburg_delinquent  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_mecklenburg_delinquent(
        years=["2025"],
        buckets=["$1,000.00 - $4,999.99"],   # single bucket for fast smoke
        seen_ids={},
        max_records=8,
        max_pages_per_bucket=2,
        headless=True,
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county/type:  {n.county} / {n.notice_type}")
        print(f"  owner:        {n.owner_name!r}")
        print(f"  property:     {n.address!r}, {n.city!r} {n.zip!r}")
        print(f"  parcel:       {n.parcel_id}")
        print(f"  amount due:   ${n.tax_delinquent_amount}  (year {n.tax_delinquent_years})")
        print(f"  source_url:   {n.source_url}")
        print()


if __name__ == "__main__":
    main()
