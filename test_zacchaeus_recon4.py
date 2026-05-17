"""Zacchaeus recon round 4: bump page size, paginate, count occurrences of
our 3 target counties (Cabarrus, Catawba, Iredell) across the full grid.
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        page = await (await browser.new_context(viewport={"width": 1600, "height": 900})).new_page()
        await page.goto("https://www.zls-nc.com/listings", wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        # Click I AGREE
        await page.locator('text="I AGREE"').first.click()
        await page.wait_for_timeout(4000)
        # Try bumping page size — look for a select/combobox near "Page Size"
        # First scroll to bottom to bring pager into view
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)

        # Try increasing page size — DevExtreme typically uses select.dx-selectbox
        for sel in [
            'select',
            '[role="combobox"]',
            '.dx-selectbox',
        ]:
            cands = await page.locator(sel).all()
            print(f"  selector {sel!r}: {len(cands)}")

        # Brute-force: dump the FULL body now (no pagination), count target counties
        full_body = await page.inner_text("body")
        Path("output/zacchaeus_recon").mkdir(parents=True, exist_ok=True)
        Path("output/zacchaeus_recon/after_agree_full.txt").write_text(full_body, encoding="utf-8")
        for target in ["Cabarrus", "Catawba", "Iredell", "Lincoln", "Mecklenburg", "Rowan", "Gaston"]:
            hits = full_body.count(target)
            print(f"    {target}: {hits} occurrence(s) on page 1")

        # Click "Last Page" pager and re-dump to peek at end
        # Find pagination controls
        await page.wait_for_timeout(2000)
        # Bump page size by clicking the page-size dropdown if available
        # DevExtreme grid: "Page Size:" usually has an arrow next to it
        try:
            psz = page.locator('text="Page Size:"').first
            if await psz.count() > 0:
                # The number sits to its right; try clicking the dropdown
                parent = psz.locator('xpath=..')
                ddl = parent.locator('input, .dx-dropdowneditor-input, [role="combobox"]').first
                if await ddl.count() > 0:
                    await ddl.click()
                    await page.wait_for_timeout(500)
                    # Look for "All" or a high number
                    for opt_text in ["100", "50", "All"]:
                        opt = page.locator(f'text="{opt_text}"').first
                        if await opt.count() > 0:
                            print(f"  switching page size to {opt_text}")
                            await opt.click()
                            await page.wait_for_timeout(3000)
                            break
        except Exception as e:
            print(f"  page-size bump failed: {e}")

        # Final scrape after page-size bump
        full_body = await page.inner_text("body")
        Path("output/zacchaeus_recon/after_agree_large_pagesize.txt").write_text(full_body, encoding="utf-8")
        # Final count
        print("\n  AFTER page-size bump:")
        for target in ["Cabarrus", "Catawba", "Iredell", "Lincoln", "Mecklenburg", "Rowan", "Gaston"]:
            hits = full_body.count(target)
            print(f"    {target}: {hits} occurrence(s)")

        # Count rows in grid: each row contains "Tax Office" and a parcel
        parcel_lines = re.findall(r'^\S+ County Tax Office\b', full_body, re.MULTILINE)
        print(f"\n  Total 'X County Tax Office' rows visible: {len(parcel_lines)}")

        print("\n  Holding browser 25s...")
        await page.wait_for_timeout(25_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
