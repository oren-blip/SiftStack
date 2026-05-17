"""Playwright recon for NC eCourts portal Turnstile + Smart Search flow.

Goals:
  1. Confirm Cloudflare Turnstile is present
  2. Find the Turnstile sitekey (needed for 2Captcha)
  3. Confirm whether Turnstile auto-passes for browsers or needs explicit solving
  4. If it passes / we can solve it, navigate to Smart Search and dump the form
  5. Document selectors for: county dropdown, case-type dropdown, date range, submit
"""

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("output/ecourts_recon")
OUT.mkdir(parents=True, exist_ok=True)

PORTAL_HOME = "https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29"
SMART_SEARCH = "https://portal-nc.tylertech.cloud/Portal/Home/WorkspaceMode?p=0"  # may vary


async def dump(page, name: str) -> dict:
    (OUT / f"{name}.html").write_text(await page.content(), encoding="utf-8")
    try:
        await page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    except Exception:
        pass
    body = await page.inner_text("body")
    (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
    info = await page.evaluate(
        """
        () => {
            // Cloudflare Turnstile detection
            const turnstileWidget = document.querySelector('.cf-turnstile, [data-sitekey][data-callback], iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]');
            let sitekey = null;
            let turnstileSrc = null;
            if (turnstileWidget) {
                sitekey = turnstileWidget.getAttribute('data-sitekey');
                turnstileSrc = turnstileWidget.tagName === 'IFRAME' ? turnstileWidget.src : null;
            }
            // Cloudflare interstitial detection
            const cfChallenge = document.querySelector('#cf-please-wait, #challenge-form, #challenge-running');
            // Form / search input detection
            const inputs = Array.from(document.querySelectorAll('input, select, textarea, button'))
                .filter(el => el.offsetWidth || el.offsetHeight)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || null,
                    id: el.id || null,
                    name: el.name || null,
                    placeholder: el.placeholder || null,
                    visibleText: (el.innerText || '').trim().slice(0, 80),
                })).slice(0, 50);
            const links = Array.from(document.querySelectorAll('a'))
                .map(a => ({href: a.href, text: (a.innerText || '').trim().slice(0, 80)}))
                .filter(l => l.text)
                .slice(0, 30);
            return {
                url: location.href,
                title: document.title,
                turnstileSitekey: sitekey,
                turnstileSrc,
                hasCfChallenge: !!cfChallenge,
                bodyLen: document.body.innerText.length,
                inputs,
                links,
            };
        }
        """
    )
    return info


async def main() -> None:
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

        print(f"\n--> {PORTAL_HOME}")
        try:
            await page.goto(PORTAL_HOME, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            print(f"  goto err: {e}")
            return

        # Wait for either Turnstile to render or page to load past it
        await page.wait_for_timeout(5000)
        info1 = await dump(page, "01_initial")
        print(f"  title={info1['title']}  url={info1['url']}")
        print(f"  turnstileSitekey={info1['turnstileSitekey']}")
        print(f"  turnstileSrc={info1['turnstileSrc']}")
        print(f"  cfChallenge={info1['hasCfChallenge']}")
        print(f"  bodyLen={info1['bodyLen']}")

        # Wait longer for Turnstile to resolve (it sometimes auto-passes for trusted browsers)
        print("\n  Waiting 12s for Turnstile to settle...")
        await page.wait_for_timeout(12_000)
        info2 = await dump(page, "02_after_wait")
        print(f"  title={info2['title']}  url={info2['url']}")
        print(f"  turnstileSitekey={info2['turnstileSitekey']}")
        print(f"  cfChallenge={info2['hasCfChallenge']}")
        print(f"  bodyLen={info2['bodyLen']}")
        print(f"  visible inputs: {len(info2['inputs'])}")
        print(f"  visible links: {len(info2['links'])}")
        for ln in info2['links'][:10]:
            print(f"    {ln['text'][:60]} -> {ln['href']}")

        # If we appear to be past Turnstile, try clicking through to Smart Search
        if not info2['hasCfChallenge'] and info2['bodyLen'] > 500:
            print("\n  Looks like we're past Turnstile. Looking for Smart Search link...")
            # Common UI: a tile or link labeled "Smart Search" or "Court Records"
            for sel in [
                'text="Smart Search"',
                'text="Court Records"',
                'a[href*="SmartSearch"]',
                'a:has-text("Smart Search")',
            ]:
                loc = page.locator(sel).first
                cnt = await loc.count()
                if cnt > 0:
                    print(f"  Found {sel} (count={cnt})")
                    href = await loc.evaluate('el => el.href || el.getAttribute("data-href") || null')
                    print(f"  href={href}")
                    try:
                        await loc.click(timeout=5_000)
                        await page.wait_for_timeout(5000)
                        info3 = await dump(page, "03_after_click")
                        print(f"  post-click url: {info3['url']}")
                        print(f"  post-click inputs: {len(info3['inputs'])}")
                        for inp in info3['inputs'][:20]:
                            print(f"    [{inp['tag']}/{inp['type']}] id={inp['id']!r} placeholder={inp['placeholder']!r}")
                        break
                    except Exception as e:
                        print(f"  click err: {e}")

        # Save full info summary
        (OUT / "summary.json").write_text(
            json.dumps({"01_initial": info1, "02_after_wait": info2}, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n  Files saved to {OUT}/")
        print("\n  Holding browser open 30s for inspection...")
        await page.wait_for_timeout(30_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
