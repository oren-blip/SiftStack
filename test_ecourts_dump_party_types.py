"""Dump every ConnectionType seen across the 10 test cases to identify
which roles the user's manual workflow treats as 'executor'."""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ecourts_case_api import CaseDetailClient, extract_case_id  # noqa: E402
from ecourts_scraper import (  # noqa: E402
    PORTAL_URL, _DEFAULT_UA, _is_waf_gate, _load_cached_waf_cookie,
    _navigate_to_smart_search, _open_advanced_filters, _select_only_county,
    _set_case_type, _set_date_range, _set_search_criteria, _solve_and_inject_waf,
    _submit_search,
)
from playwright.async_api import async_playwright  # noqa: E402


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Re-use the cached WAF cookie
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        cached = _load_cached_waf_cookie()
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=cached.get("user_agent") or _DEFAULT_UA,
        )
        await ctx.add_cookies([{
            "name": "aws-waf-token",
            "value": cached["aws_waf_token"],
            "domain": ".tylertech.cloud",
            "path": "/", "httpOnly": False, "secure": True, "sameSite": "Lax",
        }])
        page = await ctx.new_page()
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)
        await _navigate_to_smart_search(page)
        await _open_advanced_filters(page)
        await _set_search_criteria(page, "26E00*")
        await _set_case_type(page, "Estates")
        await _set_date_range(page, "05/03/2026", "05/17/2026")
        await _select_only_county(page, "Mecklenburg")
        await _submit_search(page)
        await page.wait_for_timeout(3000)

        case_data = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a.caseLink')).slice(0, 10).map(a => ({
                caseno: a.title, data_url: a.getAttribute('data-url'),
            }))"""
        )
        cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        waf = next((c for c in cookies if c["name"] == "aws-waf-token"), None)
        ua = cached.get("user_agent") or _DEFAULT_UA

        await ctx.close()
        await browser.close()

    client = CaseDetailClient(waf_token=waf["value"], user_agent=ua)
    all_types: dict[str, int] = {}
    for cd in case_data:
        case_no = cd["caseno"]
        hex_id = extract_case_id(cd["data_url"])
        detail = client.fetch_detail(hex_id)
        print(f"\n=== {case_no} ===")
        if not detail.parties:
            print("  (no parties returned)")
            continue
        for p in detail.parties:
            print(f"  [{p.connection_type:30s}] {p.full_name}")
            all_types[p.connection_type] = all_types.get(p.connection_type, 0) + 1

    print("\n=== ConnectionType frequency across 10 cases ===")
    for t, c in sorted(all_types.items(), key=lambda x: -x[1]):
        print(f"  {c:3d}  {t}")


if __name__ == "__main__":
    asyncio.run(main())
