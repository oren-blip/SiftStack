"""One-shot: push the 2026-08-12 deep-prospecting results to DataSift.

3 court-confirmed PR upgrades (Parties API) + 2 deed-confirmed mailing fixes
(county GIS), each re-skip-traced after the edit (~$0.15/record, 5 records).
Reuses pr_upgrade_step's hardened owner-edit machinery (verify-by-reload,
never write blank over existing).
"""
import asyncio
import os
import sys

sys.path.insert(0, r"d:\SiftStack")
sys.path.insert(0, r"d:\SiftStack\src")
os.chdir(r"d:\SiftStack")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from datasift_core import login
from pr_upgrade_step import _open_owner_page, _edit_owner, _trace_owner, logger

UPS = [
    # Court-confirmed PR upgrades (old = current DataSift owner name)
    {"case": "26E001041-350", "address": "221 Fielding St", "old": "Heirs Preidt",
     "first": "Julia", "last": "Stone", "pr": "Julia Stone",
     "mail_street": "180 Lane 201 Crooked Lake", "mail_city": "Angola",
     "mail_state": "IN", "mail_zip": "46703"},
    {"case": "26E000801-790", "address": "1002 W Stokes St", "old": "Heirs Williams",
     "first": "Joseph", "last": "Conner", "pr": "Joseph Conner",
     "mail_street": "2455 NC Hwy 153", "mail_city": "China Grove",
     "mail_state": "NC", "mail_zip": "28023"},
    {"case": "26E002976-590", "address": "16018 River Tree Ln", "old": "Heirs Robertson",
     "first": "Ann", "last": "Fiery", "pr": "Ann Fiery",
     "mail_street": "4336 Silo Ln", "mail_city": "Charlotte",
     "mail_state": "NC", "mail_zip": "28226"},
    # Deed-confirmed mailing fixes (name unchanged — trace was failing on a
    # synthesized property-address mailing)
    {"case": "26E000780-480", "address": "106 Friendly Cir", "old": "Nicollette Wodecki",
     "first": "Nicollette", "last": "Wodecki", "pr": "Nicollette Wodecki",
     "mail_street": "208 Wickersham Dr", "mail_city": "Statesville",
     "mail_state": "NC", "mail_zip": "28625"},
    {"case": "26E000795-790", "address": "2683 Oddie Rd", "old": "Martha Foster",
     "first": "Martha", "last": "Foster", "pr": "Martha B. Foster",
     "mail_street": "815 Peach Orchard Rd", "mail_city": "Salisbury",
     "mail_state": "NC", "mail_zip": "28147-8329"},
]


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("credentials missing")
        return 2
    done = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("login failed")
                return 1
            for u in UPS:
                try:
                    if not await _open_owner_page(page, u["address"]):
                        logger.warning("%s: record not found by address %r",
                                       u["case"], u["address"])
                        continue
                    if not await _edit_owner(page, u):
                        continue
                except Exception as e:  # noqa: BLE001
                    logger.warning("%s: failed (%s)", u["case"], e)
                    continue
                logger.info("%s: contact/mailing updated (%s)", u["case"], u["pr"])
                if await _trace_owner(page, u):
                    logger.info("%s: Skip Trace Owner fired", u["case"])
                else:
                    logger.warning("%s: Skip Trace Owner button not found", u["case"])
                done += 1
        finally:
            await browser.close()
    logger.info("done: %d/%d applied", done, len(UPS))
    return 0 if done == len(UPS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
