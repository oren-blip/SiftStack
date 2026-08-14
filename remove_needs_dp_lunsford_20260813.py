"""One-shot (Oren approved 2026-08-13 "go"): remove the now-obsolete
'Needs DP' tag from the SOLVED Lunsford record.

Lunsford 26E000782-480 (3028 Jennings Rd, Olin) was tagged 'Needs DP' with the
other still-'Heirs' 8/11-upload records, then healed the same day: court named
Lisa Hall, pushed via pr_upgrade_step --week 33. The tag would leave a solved
case in the Needs DP work filter.

Flow: Records search '3028 Jennings Rd' -> require EXACTLY one matching row
(text-verified) -> manage_bulk_action(Remove tags, ['Needs DP'],
pre_filtered=True) which chip-verifies the tag and aborts unless exactly one
confirm button is found.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, r"d:\SiftStack")
sys.path.insert(0, r"d:\SiftStack\src")
os.chdir(r"d:\SiftStack")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from datasift_core import login
from datasift_uploader import manage_bulk_action, _dismiss_popups

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("untag_lunsford")

ADDRESS = "3028 Jennings Rd"
TAG = "Needs DP"


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("credentials missing")
        return 2
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("login failed")
                return 1
            await page.goto("https://app.reisift.io/records/properties",
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await _dismiss_popups(page)
            search = page.locator('input[placeholder*="Search for records"]')
            if await search.count() == 0:
                logger.error("search box not found")
                return 1
            await search.first.fill(ADDRESS)
            await page.wait_for_timeout(2500)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(4000)

            rows = page.locator('[class*="TableRowContainer"]')
            n = await rows.count()
            if n != 1:
                logger.error("expected exactly 1 row for %r, got %d — ABORT",
                             ADDRESS, n)
                return 1
            row_text = (await rows.first.inner_text()).replace("\n", " ")
            if "jennings" not in row_text.lower():
                logger.error("row is not the Jennings Rd record: %r — ABORT",
                             row_text[:200])
                return 1
            logger.info("matched row: %s", row_text[:160])

            res = await manage_bulk_action(page, filter_tag="",
                                           menu_item="Remove tags",
                                           values=[TAG], expected_max=1,
                                           pre_filtered=True)
            logger.info("remove-tag result: %s", res)
            return 0 if res.get("success") else 1
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
