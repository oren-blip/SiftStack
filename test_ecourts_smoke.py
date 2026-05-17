"""Smoke test eCourts scraper for Mecklenburg probate (last 7 days)."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ecourts_scraper import scrape_ecourts_sync  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_ecourts_sync(
        counties=["Mecklenburg"],
        types=["probate"],
        since_date_override="2026-05-03",  # 2 weeks back, more results
        seen_ids={},
        max_records=8,
        headless=False,  # watch it run
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county/type:  {n.county} / {n.notice_type}")
        print(f"  date_added:   {n.date_added}")
        print(f"  decedent:     {n.decedent_name!r}")
        print(f"  owner/PR:     {n.owner_name!r}")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text[:200]: {n.raw_text[:200]}...")
        print()


if __name__ == "__main__":
    main()
