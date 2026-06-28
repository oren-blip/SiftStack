"""Diagnostic: dump the distinct Case Status + case-type values that the NC
eCourts (Odyssey) portal actually emits for the **Estates** category.

Two data sources, both printed:

  1. AUTHORITATIVE LIST — the "Filter by Case Status" dropdown options under
     Advanced Filtering Options. After selecting Case Type = "Estates", the
     Kendo combobox enumerates every status Odyssey will ever show for an
     estate case. This is the definitive "what statuses CAN exist" answer.

  2. WHAT ACTUALLY APPEARS — a real Estates search for one county over a date
     window, with the production drop-filter BYPASSED, tallying the distinct
     values in the grid's Status column and the Type/style column (estate
     sub-types like Small Estate / Full Administration / Testate / Intestate)
     with frequency counts.

Usage (run from project root, src on PYTHONPATH):
    python dump_estate_statuses.py                       # Mecklenburg, last 90 days
    python dump_estate_statuses.py Lincoln 60            # county, days-back
    python dump_estate_statuses.py Mecklenburg 120 --headed

Nothing is written to the pipeline state (seen-ids / last-run untouched).
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta

# Windows consoles default to cp1252 and choke on box-drawing glyphs.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright

import ecourts_scraper as es


async def _harvest_status_dropdown(page) -> list[str]:
    """Read every option from the 'Filter by Case Status' combobox.

    Tries the Kendo widget dataSource first (authoritative), then falls back
    to scraping any rendered <option>/<li> text.
    """
    return await page.evaluate(
        """() => {
            const out = [];
            const push = (v) => {
                if (v == null) return;
                const s = String(v).trim();
                if (s && !out.includes(s)) out.push(s);
            };
            // 1. Kendo widget dataSource (most reliable)
            try {
                if (window.jQuery) {
                    const $el = window.jQuery('#caseCriteria_CaseStatus');
                    const w = $el.data('kendoComboBox') || $el.data('kendoDropDownList');
                    if (w && w.dataSource) {
                        const data = w.dataSource.data();
                        for (const item of data) {
                            if (typeof item === 'string') push(item);
                            else push(item.text ?? item.Text ?? item.value ?? item.Value ?? item.name);
                        }
                    }
                }
            } catch (e) {}
            // 2. Fallback: native <select> options
            try {
                const sel = document.querySelector('#caseCriteria_CaseStatus');
                if (sel && sel.options) {
                    for (const o of sel.options) push(o.textContent);
                }
            } catch (e) {}
            // 3. Fallback: rendered Kendo listbox <li> items (open the popup first)
            try {
                document.querySelectorAll(
                    '#caseCriteria_CaseStatus-list li, ul[id*="CaseStatus"] li'
                ).forEach(li => push(li.textContent));
            } catch (e) {}
            return out;
        }"""
    )


async def main(county: str, days_back: int, headless: bool) -> None:
    since = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
    until = datetime.now().strftime("%m/%d/%Y")
    year = datetime.now().year
    criteria = es._search_criteria_for("probate", year)

    print(f"\n=== Estates status/type recon — {county} County, {since}..{until} ===")
    print(f"    search criteria = {criteria!r}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        cached = es._load_cached_waf_cookie()
        ua = (cached.get("user_agent") if cached else es._DEFAULT_UA) or es._DEFAULT_UA
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=ua)
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()
        if cached:
            await ctx.add_cookies([{
                "name": "aws-waf-token", "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud", "path": "/",
                "httpOnly": False, "secure": True, "sameSite": "Lax",
            }])

        await page.goto(es.PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
        if await es._is_waf_gate(page):
            print("    WAF gate hit — solving (consumes a CapSolver credit)...")
            ctx, page = await es._solve_and_inject_waf(browser, ctx, page)

        await es._navigate_to_smart_search(page)
        await es._open_advanced_filters(page)
        await es._set_case_type(page, "Estates")
        await page.wait_for_timeout(1200)  # let the status list repopulate for Estates

        # ── 1. Authoritative dropdown options ────────────────────────────
        dropdown = await _harvest_status_dropdown(page)
        print("── 1. Case Status dropdown options (authoritative list for Estates) ──")
        if dropdown:
            for opt in dropdown:
                print(f"     • {opt}")
        else:
            print("     (could not read dropdown — relying on grid tally below)")
        print()

        # ── 2. What actually appears in a real Estates search ────────────
        await es._set_search_criteria(page, criteria)
        await es._set_case_type(page, "Estates")
        await es._set_date_range(page, since, until)
        await es._select_only_county(page, county)
        if not await es._submit_search(page):
            print("    search submit failed — no grid tally available")
            await ctx.close(); await browser.close()
            return
        await es._maximize_page_size(page)

        status_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        # Live keep/drop validation against the real _row_to_notice classifier
        kept_by_type: Counter[str] = Counter()
        dropped_count = 0
        case_no_re = es.re.compile(r"\d{2}[A-Z]{1,3}\d{3,6}-?\d{0,3}")
        total_rows = 0
        page_idx = 0
        while True:
            page_idx += 1
            rows = await es._extract_rows_from_grid(page)
            data_rows = 0
            for row in rows:
                cells = row.get("cells", [])
                # locate the case-number cell (same logic as _row_to_notice)
                idx = -1
                for i, c in enumerate(cells):
                    if case_no_re.fullmatch(c.strip().replace(" ", "")):
                        idx = i
                        break
                if idx < 0:
                    continue
                data_rows += 1
                # Run the production classifier on the live row
                n = es._row_to_notice(row, county, "probate")
                if n is None:
                    dropped_count += 1
                else:
                    kept_by_type[n.case_type or "(no type)"] += 1
                # type/style column sits right after the case number
                if idx + 1 < len(cells):
                    style = cells[idx + 1].strip()
                    if style:
                        type_counts[style] += 1
                # status = any cell matching a known status, else tag UNRECOGNIZED
                found = ""
                for c in cells:
                    cu = c.strip().upper()
                    if cu in es._KNOWN_CASE_STATUSES:
                        found = c.strip()
                        break
                if found:
                    status_counts[found] += 1
                else:
                    # No known status word in any cell. Capture every cell that
                    # is NOT the case#, NOT the caption (idx+1), NOT a date, and
                    # non-empty — one of these is the true (unmapped) status.
                    cand = []
                    for j, c in enumerate(cells):
                        cc = c.strip()
                        if not cc or j == idx or j == idx + 1:
                            continue
                        if es.re.search(r"\d{1,2}/\d{1,2}/\d{4}", cc):
                            continue
                        cand.append(cc)
                    status_counts[f"<unmapped cells> {' | '.join(cand)[:120]}"] += 1
            total_rows += data_rows
            if data_rows == 0 or not await es._click_next_page(page):
                break
            await page.wait_for_timeout(1500)
            if page_idx > 40:  # safety cap
                break

        print(f"── 3. Live classifier result — {sum(kept_by_type.values())} kept / "
              f"{dropped_count} dropped (of {total_rows}) ──")
        for val, n in kept_by_type.most_common():
            print(f"     KEEP {n:>4}  {val}")
        print()

        print(f"── 2. Grid tally — {total_rows} Estates rows across {page_idx} page(s) ──")
        print("   Case Status column (distinct values + counts):")
        for val, n in status_counts.most_common():
            mark = ""
            vu = val.strip().upper()
            if vu in es._DROP_CASE_STATUSES:
                mark = "  [currently DROPPED]"
            elif vu in es._KEEP_CASE_STATUSES:
                mark = "  [currently KEPT]"
            print(f"     {n:>4}  {val}{mark}")
        print("\n   Type / case-style column (estate sub-types + counts):")
        for val, n in type_counts.most_common():
            print(f"     {n:>4}  {val}")
        print()

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    county = args[0] if len(args) > 0 else "Mecklenburg"
    days_back = int(args[1]) if len(args) > 1 else 90
    headed = "--headed" in sys.argv
    asyncio.run(main(county, days_back, headless=not headed))
