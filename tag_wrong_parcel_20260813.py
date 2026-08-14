"""One-off: tag the Ricardo 26E001058-350 record 'Wrong Parcel - Do Not Mail'.

All 5 parcels on the record belong to a different, living Kenneth John Ricardo
(mails to Elkhorn City, KY) — verified by Oren on Gaston GIS 2026-08-13 and
blocked in manual_parcel_rejects.txt. Same treatment as Baker 26E002844-590.

Mechanism (mirrors tag_needs_dp_20260813.py): 1-row CSV with the record's
exact uploaded address -> Add Data into the existing PROBATE list -> DataSift
merges by address and the tag lands on the record. Tags are additive on merge;
no other columns are sent so nothing else can be touched.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))

import config  # noqa: E402  (loads .env)
from playwright.async_api import async_playwright  # noqa: E402
from datasift_core import login  # noqa: E402
from datasift_uploader import upload_csv  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tag_wrong_parcel")

OUT = REPO / "output" / "wrong_parcel_ricardo_26E001058.csv"

# Exactly as uploaded 8/7 in nc_estates_ftm_2026-08-07_185204_week32_datasift_upload.csv
ROW = {
    "Property Street Address": "HEATHER LN",
    "Property City": "Mount Holly",
    "Property State": "NC",
    "Property ZIP Code": "28120",
    "Tags": "Wrong Parcel - Do Not Mail",
}


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(ROW))
        w.writeheader()
        w.writerow(ROW)
    logger.info("Wrote %s", OUT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("DataSift login failed")
                return 1
            up = await upload_csv(page, OUT, mode="add",
                                  list_name="PROBATE", existing_list=True,
                                  finish=True)
            if not up.get("success"):
                logger.error("Upload failed: %s — upload %s by hand.",
                             up.get("message"), OUT)
                return 1
            logger.info("'Wrong Parcel - Do Not Mail' pushed onto HEATHER LN / "
                        "Mount Holly 28120 (case 26E001058-350).")
            return 0
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
