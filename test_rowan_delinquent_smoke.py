"""Smoke test Rowan delinquent-tax XLSX scraper."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rowan_delinquent_scraper import scrape_rowan_delinquent  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_rowan_delinquent(
        min_balance=2000.0,
        seen_ids={},
        max_records=10,
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county/type:  {n.county} / {n.notice_type}")
        print(f"  owner:        {n.owner_name!r}")
        print(f"  owner mail:   {n.owner_street!r}, {n.owner_city!r} {n.owner_state!r} {n.owner_zip!r}")
        print(f"  parcel:       {n.parcel_id}")
        print(f"  balance:      ${n.tax_delinquent_amount}  (year {n.tax_delinquent_years})")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw[:150]:    {n.raw_text[:150]}...")
        print()


if __name__ == "__main__":
    main()
