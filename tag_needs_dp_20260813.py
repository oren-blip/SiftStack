"""One-off: add the 'Needs DP' tag to still-'Heirs' records of the 8/11 upload.

Flow (mirrors text_touch_step.py):
  1. Login, export Phone Enrichment filtered to tag 'NC Upload 2026-08-11'.
  2. Keep rows whose First Name == 'Heirs' (still unhealed in DataSift).
  3. Write CSV: Property address/city/state/zip + Tags='Needs DP'.
  4. Add Data -> existing PROBATE list (upsert by address) -> tag lands on record.
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
from datasift_uploader import export_phone_enrichment, upload_csv  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tag_needs_dp")

TAG = "NC Upload 2026-08-11"
OUT = REPO / "output" / "needs_dp_tag_NC_Upload_2026-08-11.csv"


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("DataSift login failed")
                return 1

            logger.info("Exporting records (tag=%r)...", TAG)
            res = await export_phone_enrichment(page, filter_tag=TAG)
            if not res.get("success") or not res.get("download_path"):
                logger.error("Export failed: %s", res.get("message"))
                return 1

            heirs = []
            with open(res["download_path"], newline="",
                      encoding="utf-8-sig", errors="replace") as f:
                for row in csv.DictReader(f):
                    if (row.get("First Name") or "").strip().lower() == "heirs":
                        heirs.append(row)
            logger.info("Export rows with First Name == 'Heirs': %d", len(heirs))
            for r in heirs:
                logger.info("  %s | %s %s | existing tags: %s",
                            r.get("Property address"), r.get("First Name"),
                            r.get("Last Name"), r.get("Tags"))
            if not heirs:
                logger.info("Nothing to tag — all healed. Done.")
                return 0

            already = [r for r in heirs
                       if "needs dp" in (r.get("Tags") or "").lower()]
            todo = [r for r in heirs if r not in already]
            if already:
                logger.info("%d already carry Needs DP — skipping those.", len(already))
            if not todo:
                logger.info("All Heirs rows already tagged. Done.")
                return 0

            with open(OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Property address", "Property city",
                            "Property state", "Property zip", "Tags"])
                for r in todo:
                    w.writerow([r.get("Property address", ""),
                                r.get("Property city", ""),
                                r.get("Property state", ""),
                                r.get("Property zip", ""),
                                "Needs DP"])
            logger.info("Wrote %s (%d rows)", OUT, len(todo))

            up = await upload_csv(page, OUT, mode="add",
                                  list_name="PROBATE", existing_list=True,
                                  finish=True)
            if not up.get("success"):
                logger.error("Upload failed: %s — upload %s by hand.",
                             up.get("message"), OUT)
                return 1
            logger.info("'Needs DP' tag pushed onto %d records.", len(todo))
            return 0
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
