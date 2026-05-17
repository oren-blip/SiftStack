"""Playwright recon for Zacchaeus Legal Services (zls-nc.com).

Static HTML is a 6.5KB Wix shell — listings are loaded dynamically. Use
Playwright to render each per-county page and dump:
  - Post-hydration HTML + screenshot + body innerText
  - Outbound link structure (do listings link to per-property pages or PDFs?)
  - Repeated DOM blocks that look like listing cards

Targets: cabarrus-county, catawba-county, iredell-county (our 3 in-scope NC
counties; lincoln-county / mecklenburg-county / etc may also exist).

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_zacchaeus_recon.py
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUTPUT_DIR = Path("output/zacchaeus_recon")
TARGETS = [
    ("listings_root",  "https://www.zls-nc.com/listings"),
    ("cabarrus",       "https://www.zls-nc.com/cabarrus-county"),
    ("catawba",        "https://www.zls-nc.com/catawba-county"),
    ("iredell",        "https://www.zls-nc.com/iredell-county"),
]


async def explore_one(name: str, url: str, headed: bool) -> dict:
    findings: dict = {"name": name, "url": url}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed, slow_mo=100 if headed else 0)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        print(f"\n--> {name}: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            print(f"     load err: {e}")
            findings["error"] = str(e)
            await browser.close()
            return findings

        # Wix hydration — wait longer
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await page.wait_for_timeout(4000)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / f"{name}.html").write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(OUTPUT_DIR / f"{name}.png"), full_page=True)
        body = await page.inner_text("body")
        (OUTPUT_DIR / f"{name}_body.txt").write_text(body, encoding="utf-8")

        # Summary
        summary = await page.evaluate("""
            () => {
                const txt = (el) => (el && el.innerText) ? el.innerText.trim() : '';
                const links = Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({href: a.href, text: txt(a).slice(0, 120)}))
                    .filter(l => l.text && l.href);
                // Look for repeated card-like blocks
                const articles = document.querySelectorAll('article');
                const dataLists = document.querySelectorAll('[data-list-id]');
                const wixRepeaters = document.querySelectorAll('[data-hook*="repeater" i], [class*="Repeater" i]');
                const grids = document.querySelectorAll('[role="grid"], [role="list"]');
                // Wix Pro Gallery
                const galleries = document.querySelectorAll('[id^="pro-gallery"]');
                return {
                    bodyLen: document.body.innerText.length,
                    linkCount: links.length,
                    sampleLinks: links.slice(0, 20),
                    pdfLinks: links.filter(l => l.href.includes('.pdf')).slice(0, 10),
                    articles: articles.length,
                    dataLists: dataLists.length,
                    wixRepeaters: wixRepeaters.length,
                    grids: grids.length,
                    galleries: galleries.length,
                    iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({src: f.src, name: f.name, id: f.id})).slice(0, 10),
                };
            }
        """)
        findings["summary"] = summary
        print(f"     bodyLen={summary['bodyLen']}  links={summary['linkCount']}  "
              f"articles={summary['articles']}  repeaters={summary['wixRepeaters']}  "
              f"grids={summary['grids']}  galleries={summary['galleries']}  pdfs={len(summary['pdfLinks'])}")
        if summary['iframes']:
            print(f"     iframes: {summary['iframes']}")
        if summary['pdfLinks']:
            print("     PDF links:")
            for l in summary['pdfLinks'][:6]:
                print(f"       - {l['text'][:80]} -> {l['href']}")
        # Spot-check body for property-like data
        import re
        addrs = re.findall(r"\d{2,5}\s+[A-Z][A-Za-z]+\s+(?:St|Ave|Rd|Dr|Ln|Ct|Cir|Way|Blvd|Pkwy|Pl|Hwy|Highway)\b", body)
        cases = re.findall(r"\d{2}[A-Z]{2}\d{6}", body)
        money = re.findall(r"\$[\d,]+\.\d{2}", body)
        print(f"     in body: addrs={len(addrs)}  cases={len(cases)}  money={len(money)}")
        if addrs: print(f"       sample addrs: {addrs[:3]}")
        if cases: print(f"       sample cases: {cases[:3]}")

        await browser.close()
    return findings


async def main() -> None:
    headed = "--headed" in sys.argv
    all_findings = {}
    for name, url in TARGETS:
        all_findings[name] = await explore_one(name, url, headed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(all_findings, indent=2, default=str), encoding="utf-8")
    print(f"\n=== Recon complete. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
