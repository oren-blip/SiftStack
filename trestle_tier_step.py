"""Trestle tier step: score DataSift's skip-traced phones and tag them.

The nightly pipeline Trestle-scores the phones IT found (Tracerfy + court
PDFs) before upload, but the phones DataSift's own skip trace adds afterward
live only inside DataSift and are never scored. This closes that gap:

  1. Export the Phone Enrichment CSV from DataSift, filtered to a tag
     (default: the current week's "NC Estates Week N YYYY" upload tag) —
     MUST run after the DataSift skip trace has finished, so the export
     carries the new numbers.
  2. Score every phone through Trestle phone_intel (deduped).
  3. Write phone_tags_for_datasift.csv (Phone Number | Phone Tag) and
     upload it back via "Update Data -> Tag phones by phone number", so
     callers see Dial First/Second/... tags on the DataSift record.

Usage:
    python trestle_tier_step.py --week 31                # tag "NC Estates Week 31 2026"
    python trestle_tier_step.py --tag "NC Estates Week 31 2026"
    python trestle_tier_step.py --week 31 --dry-run      # export + score, no tag upload
    python trestle_tier_step.py --week 31 --headless
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402  (loads .env)
from playwright.async_api import async_playwright  # noqa: E402
from datasift_core import login  # noqa: E402
from datasift_uploader import export_phone_enrichment, upload_phone_tags  # noqa: E402
from phone_validator import (  # noqa: E402
    read_phones_from_csv, process_phones,
    write_datasift_tags_csv, write_detailed_csv,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tier_step")


async def run(tag: str, *, dry_run: bool, headless: bool) -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    api_key = os.environ.get("TRESTLE_API_KEY", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2
    if not api_key:
        logger.error("TRESTLE_API_KEY not set")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("DataSift login failed")
                return 1
            logger.info("Exporting Phone Enrichment CSV (tag=%r)...", tag)
            res = await export_phone_enrichment(page, filter_tag=tag)
            if not res.get("success") or not res.get("download_path"):
                logger.error("Export failed: %s", res.get("message"))
                return 1
            export_csv = Path(res["download_path"])
            logger.info("Exported: %s", export_csv)

            phones, n_rows, n_cols = read_phones_from_csv(export_csv)
            logger.info("Export: %d rows, %d phone columns, %d phone values "
                        "(%d unique)", n_rows, n_cols, len(phones),
                        len({c for _, c in phones}))
            if not phones:
                logger.warning("No phones in the export — did the DataSift "
                               "skip trace finish before this ran?")
                return 1

            results, errors = process_phones(phones, api_key)
            logger.info("Scored %d phones (%d errors)", len(results), len(errors))
            tags_csv = write_datasift_tags_csv(results, "output")
            write_detailed_csv(results, "output")
            by_tier: dict[str, int] = {}
            for r in results:
                by_tier[r["assigned_tag"]] = by_tier.get(r["assigned_tag"], 0) + 1
            for t in sorted(by_tier):
                logger.info("  %-14s %d", t, by_tier[t])

            if dry_run:
                logger.info("--dry-run: skipping tag upload. Tags CSV: %s", tags_csv)
                return 0
            logger.info("Uploading phone tags back to DataSift...")
            up = await upload_phone_tags(page, tags_csv)
            if not up.get("success"):
                logger.error("Tag upload failed: %s — upload %s by hand via "
                             "Upload File -> Update Data -> Tag phones by phone number.",
                             up.get("message"), tags_csv)
                return 1
            logger.info("Phone tags uploaded — callers now see dial-priority "
                        "tags on this week's records.")
            return 0
        finally:
            await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None, help="ISO week for the upload tag")
    ap.add_argument("--year", type=int, default=datetime.now().year)
    ap.add_argument("--tag", default=None, help="explicit tag (overrides --week)")
    ap.add_argument("--dry-run", action="store_true", help="export + score only")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    tag = args.tag or (f"NC Estates Week {args.week} {args.year}" if args.week else None)
    if not tag:
        ap.error("--week or --tag required")
    return asyncio.run(run(tag, dry_run=args.dry_run, headless=args.headless))


if __name__ == "__main__":
    raise SystemExit(main())
