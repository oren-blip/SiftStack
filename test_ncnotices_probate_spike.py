"""Probate-first spike: confirm NC estate / Notice to Creditors notices
are published on ncnotices.com.

Approach: free-text search for "notice to creditors" (standard probate
publication wording per NCGS 28A-14-1) across all NC counties, last 30 days.
If the result set is large and rows contain decedent + PR/executor info,
ncnotices.com works for probate.

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_ncnotices_probate_spike.py
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUTPUT_DIR = Path("output/nc_recon")
SEARCH_URL = "https://www.ncnotices.com/Search.aspx"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=120)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        print(f"\n--> {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Fill keyword search: "notice to creditors" (Exact Phrase)
        keyword_input = page.locator('#ctl00_ContentPlaceHolder1_as1_txtSearch')
        await keyword_input.fill("notice to creditors")
        print("  filled keyword: 'notice to creditors'")

        # Click "Exact Phrase" radio
        exact_radio = page.locator('label[for="ctl00_ContentPlaceHolder1_as1_rdoType_2"]')
        await exact_radio.click()
        print("  selected Exact Phrase match type")
        await page.wait_for_timeout(1500)

        # Click search
        await page.click('#ctl00_ContentPlaceHolder1_as1_btnGo')
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Capture results
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "probate_spike_results.html").write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(OUTPUT_DIR / "probate_spike_results.png"), full_page=True)
        body = await page.evaluate("() => document.body.innerText")
        (OUTPUT_DIR / "probate_spike_body.txt").write_text(body, encoding="utf-8")

        # Look for result count + sample row body text
        import re as _re
        count_match = _re.search(r"of\s+([\d,]+)", body)
        if count_match:
            print(f"\n  --> Result count: {count_match.group(1)} 'notice to creditors' matches")

        # Sample notice snippets (lines that contain probate keywords)
        sample_hits = []
        for line in body.splitlines():
            line = line.strip()
            if not line or len(line) < 80:
                continue
            low = line.lower()
            if "notice to creditors" in low or ("executor" in low and "estate" in low) or "administrator of the estate" in low:
                sample_hits.append(line[:300])
                if len(sample_hits) >= 5:
                    break

        print(f"\n  --> Found {len(sample_hits)} probate-shaped result snippets. Sample:")
        for i, hit in enumerate(sample_hits, 1):
            print(f"\n  [{i}] {hit}")

        # Quick check: do snippets contain personal-representative + addresses?
        pr_re = _re.compile(r"(?:Executor|Administrator|Personal Representative)[:\s]+([A-Z][A-Za-z\.\s,]+)")
        addr_re = _re.compile(r"\b\d+\s+[A-Z][A-Za-z\.\s]+(?:Street|St\.?|Road|Rd\.?|Drive|Dr\.?|Avenue|Ave\.?|Lane|Ln\.?|Court|Ct\.?)\b")
        pr_hits = pr_re.findall(body)
        addr_hits = addr_re.findall(body)
        print(f"\n  --> PR/Executor name pattern matches: {len(pr_hits)} (sample: {pr_hits[:3]})")
        print(f"  --> Address-like patterns: {len(addr_hits)} (sample: {addr_hits[:3]})")

        print("\n=== Spike done. Browser stays open 30s. ===")
        await page.wait_for_timeout(30000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
