"""Solve the AWS WAF gate on portal-nc.tylertech.cloud via 2Captcha, then dump
the post-gate Dashboard + Smart Search form for analysis.

Run:
    $env:PYTHONIOENCODING="utf-8"; .venv\\Scripts\\python.exe test_ecourts_solve.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent / "src"))
from aws_waf_solver import solve_aws_waf, WAFSolveError  # noqa: E402

OUT = Path("output/ecourts_recon")
OUT.mkdir(parents=True, exist_ok=True)

PORTAL_URL = "https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29"
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")


async def fetch_gokuprops(page) -> dict | None:
    props = await page.evaluate(
        "() => (typeof window.gokuProps === 'object' && window.gokuProps) || null"
    )
    if not props:
        print("  window.gokuProps not found — WAF page may have already passed")
        return None
    print(f"  WAF gokuProps found:")
    print(f"    key      = {props['key'][:60]}... ({len(props['key'])} chars)")
    print(f"    iv       = {props['iv']}")
    print(f"    context  = {props['context'][:60]}... ({len(props['context'])} chars)")
    return props


async def solve_waf_v2(browser, ctx, page) -> tuple[bool, dict | None]:
    """Solve WAF, then RESTART the context with CapSolver's userAgent and
    inject the cookie on the fresh context. Returns (success, new_ctx)."""
    if not CAPSOLVER_API_KEY:
        print("  CAPSOLVER_API_KEY not set"); return False, None

    props = await fetch_gokuprops(page)
    if not props:
        return False, None

    print("\n  Sending to CapSolver (typical solve 5-60s)...")
    try:
        result = solve_aws_waf(
            api_key=CAPSOLVER_API_KEY,
            site_url=page.url,
            aws_key=props["key"],
            aws_iv=props["iv"],
            aws_context=props["context"],
            timeout=180,
        )
    except WAFSolveError as e:
        print(f"  CapSolver err: {e}")
        return False, None

    voucher = result["voucher"]
    cs_ua = result["userAgent"]
    print(f"  Got voucher: {voucher[:60]}... ({len(voucher)} chars)")
    print(f"  CapSolver userAgent: {cs_ua[:80]}")
    print(f"  raw solution keys: {list(result['raw'].keys())}")

    # Close the original context — we need a fresh one with the matching UA
    await ctx.close()
    new_ctx = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=cs_ua or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    # Pre-seed the aws-waf-token cookie on .tylertech.cloud
    await new_ctx.add_cookies([{
        "name": "aws-waf-token",
        "value": voucher,
        "domain": ".tylertech.cloud",
        "path": "/",
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }])
    new_page = await new_ctx.new_page()
    print(f"\n  Fresh context with CapSolver UA + pre-seeded cookie")
    print(f"  Loading {PORTAL_URL}...")
    await new_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
    await new_page.wait_for_timeout(3000)
    print(f"  post-cookie title: {await new_page.title()}")
    print(f"  post-cookie url: {new_page.url}")

    # Wait extra in case the page needs hydration after passing WAF
    if "Human Verification" in (await new_page.title()):
        print(f"  Still on WAF — try waiting 8s...")
        await new_page.wait_for_timeout(8000)
        print(f"  after wait title: {await new_page.title()}")

    return True, {"ctx": new_ctx, "page": new_page, "result": result}


async def main() -> None:
    if not CAPSOLVER_API_KEY:
        print("CAPSOLVER_API_KEY missing in .env; abort.")
        sys.exit(1)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()

        print(f"--> Loading {PORTAL_URL}")
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3000)
        print(f"  initial title: {await page.title()}")

        if "Human Verification" in (await page.title()):
            ok, payload = await solve_waf_v2(browser, ctx, page)
            if not ok or not payload:
                print("WAF solve failed; abort.")
                return
            ctx = payload["ctx"]
            page = payload["page"]
            print(f"  post-solve title: {await page.title()}")
            print(f"  post-solve url:   {page.url}")
        else:
            print("  No WAF challenge present (already past).")

        # Save cookies for reuse
        cookies = await ctx.cookies()
        (OUT / "post_waf_cookies.txt").write_text(
            "\n".join(f"{c['name']}={c['value']}  domain={c['domain']}" for c in cookies),
            encoding="utf-8",
        )
        print(f"\n  {len(cookies)} cookies saved")

        # Dump the dashboard
        (OUT / "post_waf_dashboard.html").write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(OUT / "post_waf_dashboard.png"), full_page=True)
        body = await page.inner_text("body")
        (OUT / "post_waf_dashboard.txt").write_text(body, encoding="utf-8")
        print(f"\n  dashboard body chars: {len(body)}")

        # Look for "Smart Search" link / tile
        sm_link_info = await page.evaluate("""
            () => {
                const matches = [];
                for (const el of document.querySelectorAll('a, button, [role="link"], [role="button"]')) {
                    const txt = (el.innerText || '').trim();
                    if (/smart search|court records|case records|search records/i.test(txt)) {
                        matches.push({tag: el.tagName, href: el.href || null, text: txt.slice(0, 80)});
                    }
                }
                return matches;
            }
        """)
        print(f"\n  Smart-Search-like candidates ({len(sm_link_info)}):")
        for m in sm_link_info:
            print(f"    [{m['tag']}] {m['text']}  -> href={m['href']}")

        # If we have a Smart Search link, navigate
        if sm_link_info:
            target = sm_link_info[0]
            print(f"\n--> Clicking '{target['text']}'...")
            try:
                if target["href"]:
                    await page.goto(target["href"], wait_until="domcontentloaded", timeout=30_000)
                else:
                    await page.locator(f'text="{target["text"]}"').first.click()
                await page.wait_for_timeout(5000)
                (OUT / "post_waf_smart_search.html").write_text(await page.content(), encoding="utf-8")
                await page.screenshot(path=str(OUT / "post_waf_smart_search.png"), full_page=True)
                body2 = await page.inner_text("body")
                (OUT / "post_waf_smart_search.txt").write_text(body2, encoding="utf-8")
                print(f"  Smart Search body chars: {len(body2)}")
                # Catalog form fields
                fields = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('input, select, textarea, button'))
                          .filter(el => el.offsetWidth || el.offsetHeight)
                          .map(el => ({
                              tag: el.tagName.toLowerCase(),
                              type: el.type || null,
                              id: el.id || null,
                              name: el.name || null,
                              placeholder: el.placeholder || null,
                              label: (el.previousSibling && el.previousSibling.textContent || '').trim().slice(0, 40),
                          })).slice(0, 60)
                """)
                print(f"\n  Smart Search visible form fields: {len(fields)}")
                for f in fields[:30]:
                    print(f"    [{f['tag']}/{f.get('type', '?')}] id={f['id']!r} name={f['name']!r} placeholder={f['placeholder']!r}")
            except Exception as e:
                print(f"  navigation err: {e}")

        print("\n  Holding browser open 45s for visual inspection...")
        await page.wait_for_timeout(45_000)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
