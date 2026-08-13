"""One-shot: push the 2026-08-12 evening DP results to DataSift.

1. Hatcher 26E002853-590: mailing -> 5705 Verducci Ln, Waxhaw NC 28173
   (the estate parcel's own tax-mailing address for deed co-owner ELIZABETH W
   HATCHER = Beth Whitley Hatcher), then Skip Trace Owner.
2. Baker 26E002844-590: Skip Trace Owner on the freshly re-uploaded
   6034 Shining Oak Ln record (its batch trace tag wasn't filterable yet).
3. Tracerfy phones ($0.08, output/dp_tracerfy_20260812_results.json) pushed
   onto the records by property address via the Update Data wizard.
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, r"d:\SiftStack")
sys.path.insert(0, r"d:\SiftStack\src")
os.chdir(r"d:\SiftStack")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from datasift_core import login
from datasift_uploader import upload_phones_by_address
from pr_upgrade_step import _open_owner_page, _edit_owner, _trace_owner, logger

HATCHER = {"case": "26E002853-590", "address": "10015 Franklin Dr",
           "old": "Beth Hatcher", "first": "Beth", "last": "Hatcher",
           "pr": "Beth Whitley Hatcher",
           "mail_street": "5705 Verducci Ln", "mail_city": "Waxhaw",
           "mail_state": "NC", "mail_zip": "28173"}
BAKER = {"case": "26E002844-590", "address": "6034 Shining Oak Ln",
         "old": "Shirley Baker", "first": "Shirley", "last": "Baker",
         "pr": "Shirley H. Baker"}

PHONES_CSV = Path("output") / "dp_phones_20260812.csv"
PHONE_ROWS = [
    # Dale Mahaffey (DM 2, GIS 207 Brushy Creek Rd Union Grove) -> Mahaffey record
    {"Property Street Address": "0 Luther Barger Rd", "Property City": "Salisbury",
     "Property State": "NC", "Property ZIP Code": "28146",
     "Phone 1": "7045922126"},
    # Gary Grahl (DM 2, GIS 4907 Stagecoach Rd Iron Station) -> Brown/Stanley record
    {"Property Street Address": "1192 Alf Hoover Rd", "Property City": "Lincolnton",
     "Property State": "NC", "Property ZIP Code": "28092",
     "Phone 1": "7045173681", "Phone 2": "7047321693"},
    # Beth Hatcher (PR) + Katarina Ward (DM 3) -> Hatcher record
    {"Property Street Address": "10015 Franklin Dr", "Property City": "Charlotte",
     "Property State": "NC", "Property ZIP Code": "28214",
     "Phone 1": "7046344916", "Phone 2": "7048476120", "Phone 3": "7048226652"},
]


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("credentials missing")
        return 2
    cols = ["Property Street Address", "Property City", "Property State",
            "Property ZIP Code"] + [f"Phone {i}" for i in range(1, 10)]
    with PHONES_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in PHONE_ROWS:
            w.writerow({c: r.get(c, "") for c in cols})
    ok = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("login failed")
                return 1
            # 1. Hatcher mailing fix + trace
            if await _open_owner_page(page, HATCHER["address"]) and \
                    await _edit_owner(page, HATCHER):
                logger.info("%s: mailing updated to Waxhaw", HATCHER["case"])
                if await _trace_owner(page, HATCHER):
                    logger.info("%s: Skip Trace Owner fired", HATCHER["case"])
                ok += 1
            else:
                logger.warning("%s: mailing update FAILED", HATCHER["case"])
            # 2. Baker owner trace
            if await _open_owner_page(page, BAKER["address"]):
                if await _trace_owner(page, BAKER):
                    logger.info("%s: Skip Trace Owner fired", BAKER["case"])
                    ok += 1
                else:
                    logger.warning("%s: Skip Trace Owner button not found", BAKER["case"])
            else:
                logger.warning("%s: record not found by address %r",
                               BAKER["case"], BAKER["address"])
            # 3. Tracerfy phones by property address
            res = await upload_phones_by_address(page, PHONES_CSV)
            logger.info("phones-by-address: %s", res)
            if res.get("success"):
                ok += 1
        finally:
            await browser.close()
    logger.info("done: %d/3 steps OK", ok)
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
