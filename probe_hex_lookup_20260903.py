"""PROBE ONLY — can eCourts Smart Search find a case by its CASE NUMBER?

Tyler's field is labelled "Record Number or Name", so a case-number search
should work and would be far more robust than the decedent-name search
backfill_case_numbers_from_ecourts.py uses (which forces status=Pending and a
date window — both wrong for old Week-21 cases that are now Disposed).

Writes nothing. Prints what came back.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402
from ecourts_scraper import (  # noqa: E402
    CASE_TYPE_BY_NOTICE_TYPE, PORTAL_URL, SMART_SEARCH_URL, _DEFAULT_UA,
    _is_waf_gate, _load_cached_waf_cookie, _navigate_to_smart_search,
    _open_advanced_filters, _parse_results, _select_only_county,
    _set_case_type, _set_date_range, _set_search_criteria,
    _solve_and_inject_waf, _submit_search,
)

# Three known Week-21/23 cases that have a Case No. but no hex in the workbook.
TESTS = [
    ("Gaston", "26E000738-350"),
    ("Mecklenburg", "26E001795-590"),
    ("Rowan", "26E000383-790"),
]


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                        user_agent=_DEFAULT_UA)
        cached = _load_cached_waf_cookie()
        if cached:
            await ctx.close()
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                            user_agent=cached.get("user_agent") or _DEFAULT_UA)
            await ctx.add_cookies([{
                "name": "aws-waf-token", "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud", "path": "/", "httpOnly": False,
                "secure": True, "sameSite": "Lax"}])
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            print("WAF gate — solving")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)
        await _navigate_to_smart_search(page)

        for county, case_no in TESTS:
            print(f"\n=== {county} / {case_no} ===")
            await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(1500)
            await _open_advanced_filters(page)
            try:
                await _set_search_criteria(page, case_no)
                await _set_case_type(page, CASE_TYPE_BY_NOTICE_TYPE["probate"])
                # NO status filter, very wide date range
                await _set_date_range(page, "01/01/2024", "12/31/2026")
                await _select_only_county(page, county)
                if not await _submit_search(page):
                    print("  submit failed")
                    continue
                results = await _parse_results(page, county, "probate")
            except Exception as e:  # noqa: BLE001
                print(f"  EXC {type(e).__name__}: {e}")
                continue
            print(f"  {len(results)} result(s)")
            for n in results[:5]:
                hexid = getattr(n, "_roa_id", "")
                print(f"    case={n.case_number}  dec={getattr(n,'decedent_name','') or n.owner_name!r}  "
                      f"hex={'YES ' + hexid[:24] + '...' if hexid else 'NONE'}")
        await browser.close()


asyncio.run(main())
