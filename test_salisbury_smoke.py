"""Smoke test Salisbury Post scraper end-to-end."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from salisbury_post_scraper import scrape_salisbury_post  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = scrape_salisbury_post(
        types=["probate", "foreclosure"],
        seen_ids={},
        max_pages=3,        # keep it small for smoke test
        max_records=10,
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
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text:     {n.raw_text[:200]}...")
        print()


if __name__ == "__main__":
    main()
