"""Smoke test the Zacchaeus scraper end-to-end."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from zacchaeus_scraper import scrape_zacchaeus_sync  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_zacchaeus_sync(
        counties=["Cabarrus", "Catawba"],
        seen_ids={},
        headless=True,
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    by_county: dict[str, int] = {}
    for n in notices:
        by_county[n.county] = by_county.get(n.county, 0) + 1
    print(f"By county: {by_county}\n")

    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county/type:  {n.county} / {n.notice_type}")
        print(f"  parcel:       {n.parcel_id}")
        print(f"  auction_date: {n.auction_date}")
        print(f"  address:      {n.address!r}")
        print(f"  city/zip:     {n.city!r} / {n.zip!r}")
        print(f"  amount due:   ${n.tax_delinquent_amount}")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text:     {n.raw_text[:150]}...")
        print()


if __name__ == "__main__":
    main()
