"""Retry the 3 tag mini-uploads that failed in fix_tags_20260814.py
('Could not find file input element' — wizard state leaks when uploads run
back-to-back on one page). Fresh browser per upload. CSVs already on disk."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login, upload_csv

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("retry_tagfix")

CSVS = [
    REPO / "output" / "tagfix_20260814_Lot_Cluster.csv",
    REPO / "output" / "tagfix_20260814_Multi_Signer__2_.csv",
    REPO / "output" / "tagfix_20260814_Verify__No_PR_Address.csv",
]


async def one(csv_path: Path) -> bool:
    email = os.environ["DATASIFT_EMAIL"]
    password = os.environ["DATASIFT_PASSWORD"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, email, password):
                logger.error("Login failed for %s", csv_path.name)
                return False
            up = await upload_csv(page, csv_path, mode="add",
                                  list_name="PROBATE", existing_list=True,
                                  finish=True)
            ok = bool(up.get("success"))
            logger.info("%s -> %s", csv_path.name,
                        "OK" if ok else f"FAILED: {up.get('message')}")
            return ok
        finally:
            await browser.close()


async def main() -> int:
    missing = [c for c in CSVS if not c.exists()]
    if missing:
        logger.error("CSV(s) not found: %s", missing)
        return 2
    results = [await one(c) for c in CSVS]
    logger.info("Done: %d/%d succeeded.", sum(results), len(results))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
