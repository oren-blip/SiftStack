"""Recon for column.us public-notice platform.

Targets the three NC subdomains that host foreclosure + probate notices for
Iredell, Cabarrus, Catawba. Confirms:
  - Search form structure (filters: category, date, county/keyword)
  - Result list schema (does a row include full body, or just snippet?)
  - Detail page contents — addresses, owners, decedent names actually present?
  - Whether all 3 subdomains share selectors (single-template scraper viability)
  - CAPTCHA / login / Cloudflare presence

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_column_recon.py
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

OUTPUT_DIR = Path("output/column_recon")
TARGETS = [
    ("statesville", "https://statesville.column.us/search"),
    ("independenttribune", "https://independenttribune.column.us/search"),
    ("hickoryrecord", "https://hickoryrecord.column.us/search"),
]


async def snapshot(page: Page, slug: str, name: str) -> dict:
    """Save HTML + screenshot + structured DOM summary for one page."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUTPUT_DIR / f"{slug}_{name}"
    (base.with_suffix(".html")).write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(base.with_suffix(".png")), full_page=True)

    summary = await page.evaluate(
        """
        () => {
            const txt = (el) => (el && el.innerText) ? el.innerText.trim() : null;
            const inputs = Array.from(document.querySelectorAll('input, textarea')).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                id: el.id || null,
                name: el.name || null,
                placeholder: el.placeholder || null,
                visible: !!(el.offsetWidth || el.offsetHeight),
            })).filter(i => i.visible);
            const selects = Array.from(document.querySelectorAll('select')).map(el => ({
                id: el.id || null, name: el.name || null,
                options: Array.from(el.options).map(o => o.text.trim()),
            }));
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]')).map(el => ({
                text: txt(el),
                ariaLabel: el.getAttribute('aria-label'),
            })).filter(b => b.text || b.ariaLabel).slice(0, 30);
            const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
                .map(txt).filter(t => t).slice(0, 15);
            // Look for anything that could be a filter / dropdown / category control
            const filterCandidates = Array.from(
                document.querySelectorAll('[class*="filter" i], [class*="Filter" i], [class*="dropdown" i], [class*="select" i], [data-testid*="filter" i], [data-testid*="category" i]')
            ).map(el => ({
                tag: el.tagName.toLowerCase(),
                cls: el.className.toString().slice(0, 80),
                text: txt(el)?.slice(0, 80) || null,
            })).slice(0, 30);
            return {
                url: location.href,
                title: document.title,
                bodyTextSample: document.body.innerText.slice(0, 600),
                inputCount: inputs.length,
                inputs: inputs.slice(0, 20),
                selects,
                buttons,
                headings,
                filterCandidates,
                hasCloudflare: !!document.querySelector('[id*="cf-"]') || document.body.innerText.includes('Cloudflare'),
                hasTurnstile: !!document.querySelector('[class*="turnstile" i]'),
                hasCaptcha: !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"]'),
            };
        }
        """
    )
    return summary


async def explore_one(slug: str, url: str) -> dict:
    """Recon a single column.us subdomain."""
    findings: dict = {"slug": slug, "url": url}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=150)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1. Search landing
        print(f"\n  --> {slug}: loading {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)  # SPA hydration
            findings["search_landing"] = await snapshot(page, slug, "01_search")
            print(f"     title: {findings['search_landing']['title']}")
            print(f"     inputs: {findings['search_landing']['inputCount']}")
            print(f"     selects: {len(findings['search_landing']['selects'])}")
            print(f"     headings: {findings['search_landing']['headings'][:5]}")
            print(f"     cloudflare?  {findings['search_landing']['hasCloudflare']}")
            print(f"     turnstile?   {findings['search_landing']['hasTurnstile']}")
            print(f"     captcha?     {findings['search_landing']['hasCaptcha']}")
        except Exception as e:
            findings["search_landing_error"] = str(e)
            print(f"     ERR: {e}")
            await browser.close()
            return findings

        # 2. Try searching for "notice of foreclosure" without any filter
        print(f"  --> {slug}: attempting keyword search for 'notice of foreclosure'")
        try:
            search_input = page.locator('input[type="search"], input[placeholder*="search" i], input[type="text"]').first
            if await search_input.count() > 0:
                await search_input.fill("notice of foreclosure")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(4000)
                findings["foreclosure_search"] = await snapshot(page, slug, "02_foreclosure_search")
                print(f"     post-search title: {findings['foreclosure_search']['title']}")
                print(f"     post-search url: {findings['foreclosure_search']['url']}")
                # Pull a chunk of body text to see result format
                body = await page.evaluate("() => document.body.innerText")
                (OUTPUT_DIR / f"{slug}_02_foreclosure_body.txt").write_text(body, encoding="utf-8")
                print(f"     body chars: {len(body)}")
                # Sniff for result links / cards
                links = await page.evaluate("""() => {
                    const a = Array.from(document.querySelectorAll('a'))
                        .map(el => ({href: el.href, text: (el.innerText||'').trim().slice(0,120)}))
                        .filter(x => x.text && x.href && !x.href.includes('column.us#') && x.text.length > 5);
                    return a.slice(0, 15);
                }""")
                findings["foreclosure_result_links"] = links
                print(f"     result-link candidates: {len(links)}")
                for l in links[:5]:
                    print(f"       - {l['text'][:80]}  -->  {l['href']}")
        except Exception as e:
            findings["foreclosure_search_error"] = str(e)
            print(f"     ERR: {e}")

        # 3. Drill into first probably-result link
        try:
            first = next((l for l in findings.get("foreclosure_result_links", [])
                          if "notice" in l["text"].lower() or "foreclosure" in l["text"].lower()
                          or "/notice/" in l["href"] or "/legals/" in l["href"]), None)
            if first:
                print(f"  --> {slug}: drilling into {first['href']}")
                await page.goto(first["href"], wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
                findings["notice_detail"] = await snapshot(page, slug, "03_notice_detail")
                body = await page.evaluate("() => document.body.innerText")
                (OUTPUT_DIR / f"{slug}_03_notice_detail_body.txt").write_text(body, encoding="utf-8")
                print(f"     detail body chars: {len(body)}")
                # Quick test: does the body look like a real notice with address/owner?
                import re as _re
                addr_hits = _re.findall(r"\b\d+\s+[A-Z][A-Za-z\.\s]+(?:Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Lane|Ln)\b", body)
                print(f"     address-like patterns: {len(addr_hits)} (sample: {addr_hits[:2]})")
                pres_rec = _re.findall(r"PRESENT RECORD OWNER", body, _re.IGNORECASE)
                exec_by = _re.findall(r"executed by", body, _re.IGNORECASE)
                made_by = _re.findall(r"made by", body, _re.IGNORECASE)
                print(f"     PRESENT RECORD OWNER: {len(pres_rec)}, executed by: {len(exec_by)}, made by: {len(made_by)}")
            else:
                print(f"  --> {slug}: no obviously-clickable notice link in first 15 results")
        except Exception as e:
            findings["notice_detail_error"] = str(e)
            print(f"     ERR: {e}")

        await browser.close()

    return findings


async def main() -> None:
    all_findings = {}
    for slug, url in TARGETS:
        all_findings[slug] = await explore_one(slug, url)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "column_recon_summary.json").write_text(
        json.dumps(all_findings, indent=2, default=str), encoding="utf-8",
    )
    print(f"\n=== Recon complete. Summary: {OUTPUT_DIR / 'column_recon_summary.json'}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
