"""Recon: open an eCourts case detail page and dump it for selector analysis.

Strategy: re-use the existing scraper infrastructure (cached WAF cookie +
Smart Search form fill) to land on the results page, then click the first
result row and dump the resulting page (URL + title + full HTML body) to
disk so we can find the right selectors for executor + beneficiaries.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402

import config  # noqa: E402
from ecourts_scraper import (  # noqa: E402
    PORTAL_URL,
    SMART_SEARCH_URL,
    _DEFAULT_UA,
    _is_waf_gate,
    _load_cached_waf_cookie,
    _navigate_to_smart_search,
    _open_advanced_filters,
    _select_only_county,
    _set_case_type,
    _set_date_range,
    _set_search_criteria,
    _solve_and_inject_waf,
    _submit_search,
)


OUT_DIR = Path("output/ecourts_case_detail_recon")
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("recon")

    end = datetime.now()
    start = end - timedelta(days=14)
    mdy_start = start.strftime("%m/%d/%Y")
    mdy_end = end.strftime("%m/%d/%Y")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, user_agent=_DEFAULT_UA,
        )
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()

        cached = _load_cached_waf_cookie()
        if cached:
            log.info("recon: reusing cached WAF cookie")
            await ctx.close()
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=cached.get("user_agent") or _DEFAULT_UA,
            )
            await ctx.add_cookies([{
                "name": "aws-waf-token",
                "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }])
            ctx.set_default_timeout(60_000)
            page = await ctx.new_page()

        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        if await _is_waf_gate(page):
            log.info("recon: WAF gate hit, solving")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)

        await _navigate_to_smart_search(page)
        await _open_advanced_filters(page)

        # Run a Mecklenburg probate search to get a few result rows
        await _set_search_criteria(page, "26E00*")
        await _set_case_type(page, "Estates")
        await _set_date_range(page, mdy_start, mdy_end)
        await _select_only_county(page, "Mecklenburg")
        await _submit_search(page)

        # Wait a beat for results
        await page.wait_for_timeout(3000)
        log.info("recon: results page url=%s title=%s", page.url, await page.title())

        # Find the first result row and look for clickable elements / link
        row_info = await page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('.k-grid-content tbody tr, .k-grid-table tbody tr, table tbody tr'))
                  .filter(tr => tr.querySelectorAll('td').length > 0);
                if (!rows.length) return {error: 'no rows'};
                const first = rows[0];
                const cells = Array.from(first.querySelectorAll('td')).map(td => (td.innerText || '').trim());
                const links = Array.from(first.querySelectorAll('a')).map(a => ({
                    text: a.innerText.trim().slice(0, 80),
                    href: a.href,
                    onclick: a.getAttribute('onclick'),
                    id: a.id,
                    className: a.className,
                }));
                const buttons = Array.from(first.querySelectorAll('button')).map(b => ({
                    text: b.innerText.trim().slice(0, 80),
                    onclick: b.getAttribute('onclick'),
                }));
                return {cells, links, buttons};
            }"""
        )
        log.info("recon: first row analysis:")
        log.info("  cells: %s", row_info.get("cells"))
        log.info("  links: %s", row_info.get("links"))
        log.info("  buttons: %s", row_info.get("buttons"))

        # Try to click the first case-number link (Kendo grid uses `.caseLink`
        # on the case# anchor; other links in the row are hidden expand icons)
        case_link = page.locator("a.caseLink").first
        click_ok = False
        if await case_link.count() > 0:
            try:
                # Open in same tab — capture URL changes
                href_before = page.url
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                    await case_link.click(timeout=10_000)
                click_ok = True
            except Exception as e:
                log.warning("recon: click expect-navigation failed: %s — trying without nav wait", e)
                try:
                    await case_link.click(timeout=10_000)
                    await page.wait_for_timeout(4000)
                    click_ok = True
                except Exception as e2:
                    log.error("recon: plain click failed too: %s", e2)
        else:
            log.warning("recon: no clickable case link found in first row")

        if click_ok:
            log.info("recon: navigated to %s (title=%s)", page.url, await page.title())
            await page.wait_for_timeout(3000)

            # Dump the case detail page for offline analysis
            html = await page.content()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = OUT_DIR / f"case_detail_{ts}.html"
            html_path.write_text(html, encoding="utf-8")
            log.info("recon: dumped HTML to %s (%d chars)", html_path, len(html))

            # Try to identify structured sections
            sections = await page.evaluate(
                """() => {
                    // Common selectors used by Tyler Odyssey case detail pages
                    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, fieldset legend, .case-section-header, .panel-heading, [class*="ection"]'))
                      .map(h => h.innerText.trim()).filter(t => t).slice(0, 50);
                    const fieldsets = Array.from(document.querySelectorAll('fieldset')).map(f => ({
                        legend: f.querySelector('legend')?.innerText.trim() || '',
                        text: f.innerText.trim().slice(0, 500),
                    })).slice(0, 30);
                    const labels = Array.from(document.querySelectorAll('label, .field-label, dt, th'))
                      .map(l => l.innerText.trim()).filter(t => t && t.length < 50).slice(0, 80);
                    return {headings, fieldsets, labels};
                }"""
            )
            log.info("recon: headings: %s", sections.get("headings"))
            log.info("recon: labels: %s", sections.get("labels"))
            log.info("recon: fieldsets: %s", sections.get("fieldsets"))

            # Take a screenshot too
            png_path = OUT_DIR / f"case_detail_{ts}.png"
            await page.screenshot(path=str(png_path), full_page=True)
            log.info("recon: screenshot to %s", png_path)

        await page.wait_for_timeout(3000)
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
