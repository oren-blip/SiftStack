"""
Selector discovery script for NC eCourts portal.

Solves the Amazon WAF CAPTCHA via CapSolver, then dumps the post-WAF
search form HTML and all interactive element selectors.

Run with: .venv\\Scripts\\python.exe src\\discover_selectors.py
Requires: CAPSOLVER_API_KEY set in .env
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path so we can import config + aws_waf_solver
sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright
import config
from aws_waf_solver import solve_aws_waf

PORTAL_URL = "https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29"
OUT      = Path(__file__).parent.parent / "selector_report.txt"
HTML_OUT = Path(__file__).parent.parent / "portal_page.html"


async def dump_elements(page):
    return await page.evaluate("""() => {
        const results = [];
        const tags = [
            'input','select','textarea','button',
            '[role="combobox"]','[role="listbox"]','[role="button"]',
            '[role="searchbox"]','[role="textbox"]','[role="option"]',
            'a[href*="/Case"]','a[href*="/Portal"]','label',
        ];
        tags.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const info = {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    dataTestId: el.getAttribute('data-testid') || '',
                    dataId: el.getAttribute('data-id') || '',
                    className: (el.className || '').slice(0, 100),
                    text: (el.innerText || el.textContent || '').trim().slice(0, 100),
                    role: el.getAttribute('role') || '',
                    href: (el.getAttribute('href') || '').slice(0, 80),
                    options: [],
                };
                if (el.tagName === 'SELECT') {
                    info.options = Array.from(el.options).map(o => ({value: o.value, text: o.text}));
                }
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl) info.labelText = lbl.innerText.trim();
                }
                results.push(info);
            });
        });
        return results;
    }""")


async def main():
    if not config.CAPSOLVER_API_KEY:
        print("⚠ CAPSOLVER_API_KEY not set in .env")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"\\nNavigating to {PORTAL_URL} to trigger WAF ...")
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(8)

        title = await page.title()
        print(f"Title: {title}")

        if "Human Verification" in title:
            print("WAF detected — extracting parameters from window.gokuProps ...")
            params = await page.evaluate("""() => {
                if (typeof window.gokuProps !== 'undefined' && window.gokuProps) {
                    return {
                        key:     window.gokuProps.key     || '',
                        iv:      window.gokuProps.iv      || '',
                        context: window.gokuProps.context || '',
                    };
                }
                return null;
            }""")

            if not params or not params.get("key"):
                print("ERROR: Could not extract gokuProps from page")
                await browser.close()
                return

            print(f"  key     = {params['key'][:40]}...")
            print(f"  iv      = {params['iv']}")
            print(f"  context = {params['context'][:40]}...")

            print("Submitting to CapSolver (AntiAwsWafTaskProxyLess) ...")
            try:
                res = solve_aws_waf(
                    api_key=config.CAPSOLVER_API_KEY,
                    site_url=PORTAL_URL,
                    aws_key=params["key"],
                    aws_iv=params["iv"],
                    aws_context=params["context"],
                )
                voucher = res["voucher"]
                ua = res["userAgent"]
                print(f"  Token received (len={len(voucher)})")
                print(f"  User-Agent   = {ua}")

                # We MUST use the user-agent provided by CapSolver for the cookie to be valid
                await context.close()
                context = await browser.new_context(user_agent=ua)
                await context.add_cookies([{
                    "name":   "aws-waf-token",
                    "value":  voucher,
                    "domain": ".tylertech.cloud",
                    "path":   "/",
                }])
                page = await context.new_page()
                print("\\nNavigating to portal with WAF cookie ...")
                await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(8)
                title = await page.title()
                print(f"Title after solving: {title}")
            except Exception as e:
                print(f"CapSolver failed: {e}")
                await browser.close()
                return

        print("\\nWaiting for search form to render ...")
        await asyncio.sleep(10)

        url = page.url
        title = await page.title()
        print(f"Final URL:   {url}")
        print(f"Final title: {title}")

        html = await page.content()
        HTML_OUT.write_text(html, encoding="utf-8")
        print(f"HTML saved:  {HTML_OUT}  ({len(html):,} bytes)")

        elements = await dump_elements(page)
        print(f"Elements found: {len(elements)}")

        lines = ["=" * 70, "NC ECOURTS — INTERACTIVE ELEMENTS (post-WAF)", "=" * 70,
                 f"URL:   {url}", f"Title: {title}", f"Elements: {len(elements)}", ""]

        for el in elements:
            lines.append("-" * 50)
            lines.append(f"TAG:         {el['tag']}")
            if el['id']:           lines.append(f"ID:          #{el['id']}")
            if el['name']:         lines.append(f"NAME:        {el['name']}")
            if el['type']:         lines.append(f"TYPE:        {el['type']}")
            if el['role']:         lines.append(f"ROLE:        {el['role']}")
            if el['placeholder']:  lines.append(f"PLACEHOLDER: {el['placeholder']}")
            if el['ariaLabel']:    lines.append(f"ARIA-LABEL:  {el['ariaLabel']}")
            if el.get('labelText'):lines.append(f"LABEL:       {el['labelText']}")
            if el['dataTestId']:   lines.append(f"TESTID:      {el['dataTestId']}")
            if el['text']:         lines.append(f"TEXT:        {el['text']}")
            if el['href']:         lines.append(f"HREF:        {el['href']}")
            if el['className']:    lines.append(f"CLASS:       {el['className']}")
            if el['options']:
                lines.append(f"OPTIONS ({len(el['options'])}):")
                for opt in el['options'][:30]:
                    lines.append(f"  [{opt['value']}] {opt['text']}")
            lines.append("")

        OUT.write_text("\\n".join(lines), encoding="utf-8")
        print(f"\\nSelector report: {OUT}")

        print("\\nBrowser stays open 5s ...")
        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
