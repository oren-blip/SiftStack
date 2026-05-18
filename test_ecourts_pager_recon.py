"""Probe the Cabarrus eCourts results page to see the pager state."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from ecourts_scraper import (  # noqa: E402
    PORTAL_URL, _DEFAULT_UA, _is_waf_gate, _load_cached_waf_cookie,
    _navigate_to_smart_search, _open_advanced_filters, _select_only_county,
    _set_case_type, _set_date_range, _set_search_criteria, _solve_and_inject_waf,
    _submit_search,
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("recon")

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
        await _set_date_range(page, "05/11/2026", "05/17/2026")
        await _select_only_county(page, "Cabarrus")
        await _submit_search(page)
        await page.wait_for_timeout(3000)

        # Probe the pager + result count
        probe = await page.evaluate(
            """() => {
                const out = {};
                // All text near the pager
                const pager = document.querySelector('.k-pager-wrap, .k-pager-info, .k-pager');
                out.pager_text = pager ? pager.innerText.slice(0, 500) : null;
                // Items-per-page dropdown
                const select = document.querySelector('.k-pager-sizes select, select[name="PageSize"]');
                if (select) {
                    out.page_size_options = Array.from(select.options).map(o => o.value);
                    out.page_size_current = select.value;
                } else {
                    out.page_size_select = null;
                }
                // All buttons in pager area — to find next-page selector
                const pagerArea = document.querySelector('.k-pager-wrap');
                if (pagerArea) {
                    out.pager_buttons = Array.from(pagerArea.querySelectorAll('a, button, span'))
                        .slice(0, 20)
                        .map(el => ({tag: el.tagName, cls: el.className, text: (el.innerText || '').trim().slice(0,40), aria: el.getAttribute('aria-label')}));
                }
                // Count rows in the grid currently
                const grid_rows = document.querySelectorAll('.k-grid-content tbody tr, .k-grid-table tbody tr');
                out.grid_row_count = grid_rows.length;
                // Total-result message ("The search returned X cases...")
                const msg = document.querySelector('.alert, .k-messagebox, [class*="warning"]');
                out.alert_text = msg ? msg.innerText.slice(0, 300) : null;
                // Full body text snippet near top
                out.body_top = (document.body.innerText || '').slice(0, 500);
                return out;
            }"""
        )
        log.info("=== Pager / grid probe ===")
        for k, v in probe.items():
            log.info("  %s: %s", k, v)

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
