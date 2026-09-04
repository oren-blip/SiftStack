"""READ-ONLY one-off: find the Rowan estate case for the Adolphus Rd /
"Heiligh Reuben Jr Heirs" record Oren flagged (DataSift uuid
d0d0be79-f2ae-4918-bcff-738a896b1b48, no Case No. on file).

Dumps RAW grid rows (no status/type policy drops) for several name spellings
so we can see even Disposed / closed estate files.

    python probe_ecourts_heilig_20260904.py [--headed]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from ecourts_scraper import (  # noqa: E402
    CASE_TYPE_BY_NOTICE_TYPE, PORTAL_URL, SMART_SEARCH_URL, _DEFAULT_UA,
    _extract_rows_from_grid, _is_waf_gate, _load_cached_waf_cookie,
    _navigate_to_smart_search, _open_advanced_filters, _select_only_county,
    _set_case_type, _set_date_range, _set_search_criteria, _solve_and_inject_waf,
    _submit_search,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("heilig")

QUERIES = [q for q in (__import__("os").environ.get("HQ","Heiligh, Reuben").split("|")) if q]
COUNTY = "Rowan"
START = __import__("os").environ.get("HSTART","01/01/2015")
END = __import__("os").environ.get("HEND","09/04/2026")


async def run(headed: bool) -> None:
    out: dict[str, list] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        cached = _load_cached_waf_cookie()
        ua = (cached or {}).get("user_agent") or _DEFAULT_UA
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=ua)
        if cached:
            log.info("reusing cached WAF cookie")
            await ctx.add_cookies([{
                "name": "aws-waf-token", "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud", "path": "/", "httpOnly": False,
                "secure": True, "sameSite": "Lax"}])
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            log.info("WAF gate — solving")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)
        await _navigate_to_smart_search(page)

        for q in QUERIES:
            log.info("--- searching %r in %s (%s..%s), no status filter ---",
                     q, COUNTY, START, END)
            await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(1500)
            await _open_advanced_filters(page)
            try:
                await _set_search_criteria(page, q)
                await _set_case_type(page, CASE_TYPE_BY_NOTICE_TYPE["probate"])
                await _set_date_range(page, START, END)
                await _select_only_county(page, COUNTY)
                if not await _submit_search(page):
                    log.warning("submit failed for %r", q)
                    out[q] = []
                    continue
                rows = await _extract_rows_from_grid(page)
            except Exception:
                log.exception("search failed for %r", q)
                out[q] = []
                continue
            log.info("  %d raw grid row(s)", len(rows))
            for r in rows:
                cells = [c.strip() for c in r.get("cells", []) if c.strip()]
                if cells:
                    print("   |", " || ".join(cells[:8]), " roa=", r.get("data_url","")[:40])
            out[q] = rows
        await browser.close()

    p = Path("output") / "heilig_ecourts_probe_20260904.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s", p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.headed))
