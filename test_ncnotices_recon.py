"""Recon for ncnotices.com (NC Press Association public notice aggregator).

Confirms the direct analog to tnpublicnotice.com:
  - Full category dropdown
  - Search submission (Mecklenburg + Foreclosure, last 30 days)
  - Result page structure
  - Detail page contents (address? owner? raw notice text?)

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_ncnotices_recon.py
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUTPUT_DIR = Path("output/nc_recon")
SEARCH_URL = "https://www.ncnotices.com/Search.aspx"


async def dump(page: Page, name: str) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{name}.html").write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(OUTPUT_DIR / f"{name}.png"), full_page=True)
    return await page.evaluate(
        """
        () => {
            const inputs = Array.from(document.querySelectorAll('input, select, textarea, button')).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                id: el.id || null,
                name: el.name || null,
                placeholder: el.placeholder || null,
                value: el.value || null,
                visible: !!(el.offsetWidth || el.offsetHeight),
            }));
            const selects = Array.from(document.querySelectorAll('select')).map(el => ({
                id: el.id || null,
                name: el.name || null,
                ariaLabel: el.getAttribute('aria-label'),
                options: Array.from(el.options).map(o => o.text.trim()),
            }));
            const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4'))
                .map(el => el.innerText.trim()).filter(t => t).slice(0, 20);
            const tables = Array.from(document.querySelectorAll('table')).map(t => {
                const headers = Array.from(t.querySelectorAll('thead th, thead td, tr:first-child th'))
                    .map(h => h.innerText.trim()).filter(t => t);
                const rows = Array.from(t.querySelectorAll('tbody tr, tr')).slice(0, 3).map(r =>
                    Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim().slice(0, 200))
                );
                return { headers, sampleRows: rows, rowCount: t.querySelectorAll('tr').length };
            });
            return { url: location.href, title: document.title, headings, selectCount: selects.length, selects, tables, inputCount: inputs.filter(i => i.visible).length };
        }
        """
    )


async def main() -> None:
    findings = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=150)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1. Search form
        print(f"\n--> Loading {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        findings["search_form"] = await dump(page, "ncn_01_search_form")
        print(f"  title: {findings['search_form']['title']}")
        print(f"  <select> dropdowns: {findings['search_form']['selectCount']}")
        for s in findings["search_form"]["selects"]:
            print(f"    - {s.get('name') or s.get('id')}: {len(s['options'])} options")

        # Print first ~15 options of each dropdown
        for s in findings["search_form"]["selects"]:
            name = s.get("name") or s.get("id") or "(unnamed)"
            opts = s.get("options", [])
            if 2 < len(opts) < 200:  # skip giant pub list, skip 1-option dummies
                print(f"\n  [{name}] full options ({len(opts)}):")
                for o in opts:
                    print(f"    - {o}")

        # 2. Submit a search: Mecklenburg + Foreclosure + Last 30 days
        print("\n--> Submitting search: Mecklenburg county + Foreclosure category, last 30 days")

        # Find county select by inspecting visible select option lists
        county_sel = None
        category_sel = None
        for s in findings["search_form"]["selects"]:
            opts = s.get("options", [])
            opts_lower = [o.lower() for o in opts]
            if "mecklenburg" in opts_lower:
                county_sel = s.get("id") or s.get("name")
            if "foreclosure" in opts_lower:
                category_sel = s.get("id") or s.get("name")

        print(f"  county select: {county_sel}")
        print(f"  category select: {category_sel}")

        # County is checkbox list, not <select> — click Mecklenburg checkbox by label
        try:
            mecklenburg_cb = page.locator('label:has-text("Mecklenburg")').first
            if await mecklenburg_cb.count() > 0:
                await mecklenburg_cb.click()
                print("  clicked Mecklenburg checkbox")
                await page.wait_for_timeout(1500)  # ASP.NET postback
        except Exception as e:
            print(f"  ! Mecklenburg checkbox click failed: {e}")

        if category_sel:
            try:
                await page.select_option(f"#{category_sel}", label="Foreclosure")
                await page.wait_for_timeout(800)
            except Exception as e:
                print(f"  ! category select failed: {e}")

        # Find and fill date range — try the "In the last X days" pattern
        try:
            # ASP.NET often has a textbox for "Last N days"
            num_input = page.locator('input[type="text"][name*="Days"], input[type="text"][id*="Day"]').first
            if await num_input.count() > 0:
                await num_input.fill("30")
                print("  set 'last N days' to 30")
        except Exception:
            pass

        # Find search button (it has empty value, identified by .goButton class)
        search_btn = None
        for sel in [
            '#ctl00_ContentPlaceHolder1_as1_btnGo',
            'input.goButton',
            'input[type="submit"][value*="Search" i]',
            'button:has-text("Search")',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    search_btn = btn
                    print(f"  found search button: {sel}")
                    break
            except Exception:
                continue

        if search_btn:
            await search_btn.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(3000)
            findings["search_results"] = await dump(page, "ncn_02_results")
            print(f"\n  results URL: {findings['search_results']['url']}")
            print(f"  tables on results: {len(findings['search_results']['tables'])}")
            for t in findings["search_results"]["tables"]:
                if t["rowCount"] > 1:
                    print(f"    table headers: {t['headers'][:8]}")
                    print(f"    sample row 1:  {t['sampleRows'][1] if len(t['sampleRows']) > 1 else 'n/a'}")
                    print(f"    row count:     {t['rowCount']}")

            # 3. Click into first result for detail page
            print("\n--> Clicking first result row...")
            try:
                first_link = page.locator('a[href*="Notice"], a[href*="Details"], input[type="submit"][value*="View" i]').first
                if await first_link.count() > 0:
                    await first_link.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(3000)
                    findings["notice_detail"] = await dump(page, "ncn_03_detail")
                    print(f"  detail URL: {findings['notice_detail']['url']}")
                    body_text = await page.evaluate("() => document.body.innerText")
                    detail_path = OUTPUT_DIR / "ncn_03_detail_body.txt"
                    detail_path.write_text(body_text, encoding="utf-8")
                    print(f"  body text saved: {detail_path}  ({len(body_text)} chars)")
                    # Quick address check
                    import re as _re
                    addr_hits = _re.findall(
                        r"\b\d+\s+[A-Z][A-Za-z\.\s]+(?:Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Lane|Ln|Court|Ct|Boulevard|Blvd|Highway|Hwy|Parkway|Pkwy|Trail|Trl|Place|Pl|Way|Circle|Cir)\b",
                        body_text,
                    )
                    print(f"  address-like patterns: {len(addr_hits)}")
                    for a in addr_hits[:5]:
                        print(f"    - {a}")
                else:
                    print("  (no clickable result link found)")
            except Exception as e:
                print(f"  ! detail drill error: {e}")
        else:
            print("  ! search button not found")

        print("\n=== Recon complete. Browser stays open 45s. ===")
        await page.wait_for_timeout(45000)
        await browser.close()

    (OUTPUT_DIR / "ncnotices_recon_summary.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print("\nDone.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
