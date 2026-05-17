"""Playwright recon for Kania Law Firm — render the Ninja Tables widget and
dump the populated table for Mecklenburg foreclosure listings.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUTPUT_DIR = Path("output/kania_recon")
URL = "https://kanialawfirm.com/tax-foreclosures-mecklenburg-county/foreclosure-listings/"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        page = await (await browser.new_context(viewport={"width": 1600, "height": 900})).new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)  # Ninja Tables hydration

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "rendered.html").write_text(await page.content(), encoding="utf-8")
        body = await page.inner_text("body")
        (OUTPUT_DIR / "rendered_body.txt").write_text(body, encoding="utf-8")
        await page.screenshot(path=str(OUTPUT_DIR / "rendered.png"), full_page=True)

        # Probe the table
        info = await page.evaluate("""
            () => {
                const tbl = document.getElementById('footable_213701');
                if (!tbl) return {error: 'table not found'};
                const headers = Array.from(tbl.querySelectorAll('thead th')).map(th => th.innerText.trim());
                const rows = Array.from(tbl.querySelectorAll('tbody tr')).map(tr =>
                    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
                );
                return {headers, rowCount: rows.length, sampleRows: rows.slice(0, 5)};
            }
        """)
        print(f"\n  Table probe: {info}")

        print(f"\n  body length: {len(body)}")
        # Count addresses & rows in body
        import re
        addrs = re.findall(r"\d{2,5}\s+[A-Z][A-Za-z]+\s+(?:St|Ave|Rd|Dr|Ln|Ct|Cir|Way|Blvd|Pkwy|Pl)\b", body)
        cases = re.findall(r"\d{2}[A-Z]{2}\d{6}", body)
        money = re.findall(r"\$[\d,]+\.\d{2}", body)
        print(f"  addresses: {len(addrs)}  cases: {len(cases)}  money: {len(money)}")
        if addrs[:5]:
            for a in addrs[:5]:
                print(f"    addr: {a}")

        print("\n  Holding browser 30s...")
        await page.wait_for_timeout(30_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
