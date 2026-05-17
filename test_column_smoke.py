"""Smoke test: scrape Hickory Daily Record (Catawba) via column_scraper,
print parsed NoticeData. Bypasses enrichment pipeline.

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_column_smoke.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from column_scraper import scrape_column_all  # noqa: E402


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    notices = await scrape_column_all(
        mode="historical",
        counties=["Catawba"],          # just one subdomain
        types=["foreclosure", "probate"],
        max_loads_per_subdomain=2,     # only ~40-60 notices, fast
        seen_ids={},                   # ignore prior runs
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")

    by_type: dict[str, int] = {}
    for n in notices:
        by_type[n.notice_type] = by_type.get(n.notice_type, 0) + 1
    print(f"By type: {by_type}\n")

    for i, n in enumerate(notices[:8], 1):
        print(f"--- Notice {i} ---")
        print(f"  type:         {n.notice_type}")
        print(f"  county:       {n.county}")
        print(f"  state:        {n.state}")
        print(f"  date_added:   {n.date_added}")
        print(f"  auction_date: {n.auction_date}")
        print(f"  owner_name:   {n.owner_name!r}")
        print(f"  decedent:     {n.decedent_name!r}")
        print(f"  address:      {n.address!r}")
        print(f"  city/zip:     {n.city!r} / {n.zip!r}")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text:     {n.raw_text[:150]}...")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
