"""One-off: upsert a single corrected row (text touches + optional fields)
onto an existing PROBATE record by property address.

Usage: python upsert_touches_oneoff.py <touches_csv> [Field=Value ...]
"""
import asyncio
import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

from playwright.async_api import async_playwright  # noqa: E402
import config  # noqa: E402,F401  (loads .env)
from datasift_core import login, get_credentials  # noqa: E402
from datasift_uploader import upload_csv  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("upsert_oneoff")


async def main() -> int:
    src = Path(sys.argv[1])
    extra = dict(a.split("=", 1) for a in sys.argv[2:])
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    for r in rows:
        r.update(extra)
    out = src.with_name(src.stem + "_upsert.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("Upsert CSV: %s (%d row(s), extra fields: %s)",
             out, len(rows), list(extra) or "none")

    email, password = get_credentials()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                log.error("login failed")
                return 1
            up = await upload_csv(page, out, mode="add",
                                  list_name="PROBATE", existing_list=True,
                                  finish=True)
            if not up.get("success"):
                log.error("upsert failed: %s", up.get("message"))
                return 1
            log.info("Upsert committed.")
            return 0
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
