"""Submit a Mecklenburg delinquent search via Playwright and dump the results table."""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://taxbill.co.mecklenburg.nc.us/publicwebaccess/BillDelinquentSearch.aspx"
OUT = Path("output/mecktax_recon")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)

        # List visible select options
        for name in ["yearValue", "lookupDelinquentCriterion"]:
            try:
                opts = await page.locator(f'select[name="{name}"] option').all_inner_texts()
                print(f"  {name}: {opts}")
            except Exception as e:
                print(f"  {name}: ERR {e}")

        # Pick: year=2025 (full year of delinquencies), balance=$10k+ (highest distress)
        try:
            await page.select_option('select[name="yearValue"]', label="2025")
            await page.select_option('select[name="lookupDelinquentCriterion"]', label="$10,000 - Higher")
        except Exception as e:
            print(f"  select err: {e}")

        # Click Go
        await page.click('input[name="btnGo_Delinquent"]')
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(4000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        (OUT / "02_results.html").write_text(await page.content(), encoding="utf-8")
        body = await page.inner_text("body")
        (OUT / "02_results.txt").write_text(body, encoding="utf-8")
        print(f"\n  Results body len: {len(body)}")

        # Probe the results table
        info = await page.evaluate(
            """() => {
                const tbl = document.getElementById('tblSearchResults');
                if (!tbl) return {error: 'tblSearchResults not found'};
                const headers = Array.from(tbl.querySelectorAll('thead th, thead td, tr:first-child th, tr:first-child td')).map(h => h.innerText.trim());
                const rows = Array.from(tbl.querySelectorAll('tbody tr')).slice(0, 5).map(tr =>
                    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
                );
                const totalRows = tbl.querySelectorAll('tbody tr').length;
                return {headers, sampleRows: rows, totalRows};
            }"""
        )
        print(f"\n  Table probe: {info}")

        # Also check pagination
        page_text_count = re.findall(r"\b\d+\s+result", body, re.IGNORECASE)
        print(f"\n  result-count strings: {page_text_count[:3]}")

        await page.wait_for_timeout(20_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
