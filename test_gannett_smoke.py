"""Smoke test Gannett iPublish Marketplace scraper for Gaston Gazette."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from gannett_legals_scraper import scrape_gannett_legals  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_gannett_legals(
        counties=["Gaston"],
        types=["probate", "foreclosure"],
        seen_ids={},
        max_pages=2,
        max_records=8,
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    by_type: dict[str, int] = {}
    for n in notices:
        by_type[n.notice_type] = by_type.get(n.notice_type, 0) + 1
    print(f"By type: {by_type}\n")

    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  type:         {n.notice_type}")
        print(f"  county:       {n.county}")
        print(f"  date_added:   {n.date_added}")
        print(f"  decedent:     {n.decedent_name!r}")
        print(f"  owner/PR:     {n.owner_name!r}")
        print(f"  property:     {n.address!r}, {n.city!r} {n.zip!r}")
        print(f"  auction_date: {n.auction_date}")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text[:200]: {n.raw_text[:200]}...")
        print()


if __name__ == "__main__":
    main()
