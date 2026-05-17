"""Smoke test: scrape 2 Mecklenburg foreclosure notices end-to-end via the NC
scraper, print the parsed NoticeData. Bypasses enrichment pipeline.

Run:
    .venv\\Scripts\\python.exe test_nc_scraper_smoke.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import NCSavedSearch  # noqa: E402
from nc_scraper import scrape_nc_all  # noqa: E402

# Force headed mode for smoke test — ncnotices.com appears to redirect
# headless browsers to a parking domain. Monkey-patch the launch opts so we
# don't have to change the public scraper API just for diagnostics.
_orig_launch = None


def _patch_headed() -> None:
    from playwright import async_api as _pw_async
    _orig = _pw_async.BrowserType.launch

    async def _launch_headed(self, **kwargs):
        kwargs["headless"] = False
        kwargs.setdefault("slow_mo", 150)
        return await _orig(self, **kwargs)

    _pw_async.BrowserType.launch = _launch_headed


_patch_headed()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    searches = [
        NCSavedSearch(
            county="Mecklenburg",
            notice_type="foreclosure",
            category="Foreclosure",
            keyword=None,
        ),
    ]

    notices = await scrape_nc_all(
        mode="historical",          # 365-day window for guaranteed hits
        searches=searches,
        max_notices=2,              # cap at 2 to keep this fast
        seen_ids={},                # ignore prior runs
    )

    print(f"\n=== SCRAPED {len(notices)} NOTICES ===\n")
    for i, n in enumerate(notices, 1):
        print(f"--- Notice {i} ---")
        print(f"  county:       {n.county}")
        print(f"  state:        {n.state}")
        print(f"  notice_type:  {n.notice_type}")
        print(f"  date_added:   {n.date_added}")
        print(f"  auction_date: {n.auction_date}")
        print(f"  owner_name:   {n.owner_name!r}")
        print(f"  address:      {n.address!r}")
        print(f"  city/zip:     {n.city!r} / {n.zip!r}")
        print(f"  source_url:   {n.source_url}")
        print(f"  raw_text:     {n.raw_text[:200]}...")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
