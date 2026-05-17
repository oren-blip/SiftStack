"""Recon: capture all network requests when opening a case detail page.

Goal: figure out why the /app/RegisterOfActions/ SPA renders blank under
Playwright. The URL ends in /anon/portalembed (unauthenticated view), so
auth isn't the issue. Likely candidates: failed XHR, headless detection,
iframe-expected rendering.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from ecourts_scraper import (  # noqa: E402
    PORTAL_URL,
    _DEFAULT_UA,
    _is_waf_gate,
    _load_cached_waf_cookie,
    _navigate_to_smart_search,
    _open_advanced_filters,
    _select_only_county,
    _set_case_type,
    _set_date_range,
    _set_search_criteria,
    _solve_and_inject_waf,
    _submit_search,
)


OUT_DIR = Path("output/ecourts_case_detail_recon")
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("recon")

    end = datetime.now()
    start = end - timedelta(days=14)
    mdy_start = start.strftime("%m/%d/%Y")
    mdy_end = end.strftime("%m/%d/%Y")

    async with async_playwright() as pw:
        # Headed (visible) — to rule out headless detection
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=_DEFAULT_UA)
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()

        cached = _load_cached_waf_cookie()
        if cached:
            log.info("recon: reusing cached WAF cookie")
            await ctx.close()
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=cached.get("user_agent") or _DEFAULT_UA,
            )
            await ctx.add_cookies([{
                "name": "aws-waf-token",
                "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }])
            ctx.set_default_timeout(60_000)
            page = await ctx.new_page()

        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)

        await _navigate_to_smart_search(page)
        await _open_advanced_filters(page)
        await _set_search_criteria(page, "26E00*")
        await _set_case_type(page, "Estates")
        await _set_date_range(page, mdy_start, mdy_end)
        await _select_only_county(page, "Mecklenburg")
        await _submit_search(page)
        await page.wait_for_timeout(3000)

        # Click the case link — capture the new tab + all its network activity
        log.info("clicking first caseLink")
        first_link = page.locator("a.caseLink").first

        roa_page = None
        try:
            async with ctx.expect_page(timeout=20_000) as new_page_info:
                await first_link.click(timeout=10_000, force=True)
            roa_page = await new_page_info.value
            log.info("opened new tab")
        except Exception as e:
            log.warning("no new tab opened: %s", e)
            roa_page = page

        # Hook ALL network requests/responses
        reqs: list[dict] = []

        def on_request(req):
            reqs.append({
                "phase": "REQUEST",
                "method": req.method,
                "url": req.url[:300],
                "resource_type": req.resource_type,
            })

        def on_response(resp):
            reqs.append({
                "phase": "RESPONSE",
                "status": resp.status,
                "url": resp.url[:300],
                "ok": resp.ok,
            })

        def on_request_failed(req):
            reqs.append({
                "phase": "FAILED",
                "method": req.method,
                "url": req.url[:300],
                "error": str(req.failure),
            })

        roa_page.on("request", on_request)
        roa_page.on("response", on_response)
        roa_page.on("requestfailed", on_request_failed)

        # Also capture console messages — they might reveal SPA errors
        console_msgs: list[str] = []

        def on_console(msg):
            console_msgs.append(f"[{msg.type}] {msg.text[:200]}")

        roa_page.on("console", on_console)

        # Wait for SPA to either render or error out
        log.info("waiting up to 25s for ROA SPA to render...")
        body_text = ""
        for sec in range(1, 26):
            await roa_page.wait_for_timeout(1000)
            try:
                body_text = await roa_page.inner_text("body")
            except Exception:
                body_text = ""
            if len(body_text) > 200:
                log.info("ROA hydrated at %ds (body=%d chars)", sec, len(body_text))
                break

        log.info("Final: url=%s title=%s body=%d chars",
                 roa_page.url, await roa_page.title(), len(body_text))

        # Network summary
        log.info("Network activity (%d events):", len(reqs))
        for r in reqs:
            if r.get("resource_type") in ("image", "font", "stylesheet"):
                continue  # filter noise
            if r["phase"] == "REQUEST":
                log.info("  -> %s %s [%s]", r["method"], r["url"], r["resource_type"])
            elif r["phase"] == "RESPONSE":
                log.info("  <- %d %s %s", r["status"], "OK" if r["ok"] else "FAIL", r["url"])
            elif r["phase"] == "FAILED":
                log.info("  !! FAILED %s %s : %s", r["method"], r["url"], r["error"])

        log.info("Console messages (%d):", len(console_msgs))
        for m in console_msgs[:30]:
            log.info("  %s", m)

        # Dump rendered HTML + screenshot
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (OUT_DIR / f"roa_full_{ts}.html").write_text(await roa_page.content(), encoding="utf-8")
        await roa_page.screenshot(path=str(OUT_DIR / f"roa_full_{ts}.png"), full_page=True)

        # If still blank, try iframe approach — embed inside a wrapper page
        if len(body_text) < 200:
            log.info("=== Trying iframe embed approach ===")
            current_url = roa_page.url
            wrapper_html = f"""<!doctype html><html><head><title>wrap</title></head><body>
                <iframe id=fr src='{current_url}' style='width:1400px;height:900px;border:0'></iframe>
            </body></html>"""
            iframe_page = await ctx.new_page()
            await iframe_page.set_content(wrapper_html)
            log.info("waiting 15s for iframe to render")
            await iframe_page.wait_for_timeout(15_000)
            frames = iframe_page.frames
            log.info("frames: %d", len(frames))
            for f in frames:
                log.info("  frame url=%s", f.url)
                try:
                    ft = await f.evaluate("() => document.body ? document.body.innerText.length : 0")
                    log.info("  frame body length: %d", ft)
                except Exception as e:
                    log.info("  frame error: %s", e)

        await roa_page.wait_for_timeout(2000)
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
