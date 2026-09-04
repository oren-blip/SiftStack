"""One-off probe: what does the group search page actually render?

Prints the resolved URL, title, selector counts and a text sample, and saves a
screenshot, so the harvester's extraction can be aimed at the real DOM instead
of a guess.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".fb_profile"
OUT = ROOT / "output" / "fb_harvest"
OUT.mkdir(parents=True, exist_ok=True)
GROUP = "CharlotteRealEstateInvestors"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE), headless=False, viewport={"width": 1400, "height": 1000},
        user_agent=UA, args=["--disable-blink-features=AutomationControlled"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    for label, url in [
        ("GROUP HOME", f"https://www.facebook.com/groups/{GROUP}"),
        ("GROUP SEARCH", f"https://www.facebook.com/groups/{GROUP}/search/?q=plumber"),
    ]:
        print("\n" + "=" * 70)
        print(label, "->", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        for _ in range(3):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(2500)
        print("  resolved url :", page.url)
        print("  title        :", page.title())
        counts = page.evaluate(
            """() => ({
                article: document.querySelectorAll('[role="article"]').length,
                feed: document.querySelectorAll('[role="feed"]').length,
                feedKids: document.querySelectorAll('[role="feed"] > div').length,
                main: document.querySelectorAll('[role="main"]').length,
                gridcell: document.querySelectorAll('[role="gridcell"]').length,
                storyMsg: document.querySelectorAll('[data-ad-comet-preview="message"], [data-ad-preview="message"]').length,
                anyPostLink: document.querySelectorAll('a[href*="/posts/"], a[href*="multi_permalinks"]').length,
                bodyLen: (document.body.innerText || '').length,
            })"""
        )
        print("  selectors    :", counts)
        txt = page.evaluate("() => (document.body.innerText||'').slice(0, 1200)")
        print("  --- text sample ---")
        print("  " + txt.replace("\n", "\n  ")[:1200])
        shot = OUT / f"probe_{label.split()[1].lower()}.png"
        page.screenshot(path=str(shot), full_page=False)
        print("  screenshot   :", shot)

    ctx.close()
