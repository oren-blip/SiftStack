"""Mecktimes Playwright recon — does headed browser bypass the 403?

If yes: find the search interface, dump a sample notice.
If no (paywall): document and exit.
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUTPUT_DIR = Path("output/mecktimes_recon")


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=120)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()

        for url in [
            "https://publicnotices.mecktimes.com/",
            "https://mecktimes.com/public-notice/",
            "https://publicnotices.mecktimes.com/search",
            "https://mecktimes.com/category/public-notices/",
        ]:
            print(f"\n--> {url}")
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception as e:
                print(f"  goto err: {e}")
                continue
            status = resp.status if resp else "?"
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)
            final_url = page.url
            body = await page.inner_text("body")
            print(f"  status={status}  final={final_url}  body_chars={len(body)}")
            # Quick analysis
            import re
            notice_words = sum(body.lower().count(w) for w in [
                "notice of foreclosure", "notice to creditors", "trustee", "estate of"
            ])
            paywall = any(w in body.lower() for w in [
                "subscribe to read", "subscription required", "log in to continue",
                "premium content", "members only",
            ])
            counties = sorted(set(re.findall(
                r"\b(Mecklenburg|Charlotte|Cabarrus|Iredell)\b", body)))
            print(f"  notice-keyword hits: {notice_words}  paywall_markers: {paywall}  counties: {counties}")
            # Save
            slug = url.replace("/", "_").replace(":", "")[-60:]
            (OUTPUT_DIR / f"{slug}.html").write_text(await page.content(), encoding="utf-8")
            (OUTPUT_DIR / f"{slug}.txt").write_text(body, encoding="utf-8")
            await page.screenshot(path=str(OUTPUT_DIR / f"{slug}.png"), full_page=True)
            print(f"  saved: {slug}.html/.txt/.png")

        print("\n  Hold 30s for inspection...")
        await page.wait_for_timeout(30_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
