"""Fetch the Tyler OData /Parties JSON for a known case ID and dump the shape."""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import asyncio
import requests
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


async def grab_case_ids() -> list[dict]:
    """Run a Mecklenburg probate search and return the first N case hex IDs + WAF cookie."""
    end = datetime.now()
    start = end - timedelta(days=14)
    mdy_start = start.strftime("%m/%d/%Y")
    mdy_end = end.strftime("%m/%d/%Y")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=_DEFAULT_UA)
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()

        cached = _load_cached_waf_cookie()
        if cached:
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

        case_links = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a.caseLink')).slice(0, 5).map(a => ({
                caseno: a.title,
                data_url: a.getAttribute('data-url'),
            }))"""
        )
        # Extract WAF cookie from context for the HTTP session
        cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        waf = next((c for c in cookies if c["name"] == "aws-waf-token"), None)
        ua_used = cached.get("user_agent") if cached else _DEFAULT_UA
        await ctx.close()
        await browser.close()

        return {
            "cases": case_links,
            "waf_token": waf["value"] if waf else None,
            "user_agent": ua_used,
        }


def extract_id(data_url: str) -> str:
    """Pull the id query param out of /app/RegisterOfActions/?id=..."""
    import re
    m = re.search(r"[?&]id=([0-9A-F]+)", data_url, re.IGNORECASE)
    return m.group(1) if m else ""


def fetch_parties(hex_id: str, waf_token: str, user_agent: str) -> dict:
    url = (
        f"https://portal-nc.tylertech.cloud/app/RegisterOfActionsService/"
        f"Parties('{hex_id}')?mode=portalembed&$top=50&$skip=0"
    )
    r = requests.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://portal-nc.tylertech.cloud/app/RegisterOfActions/",
            "Origin": "https://portal-nc.tylertech.cloud",
        },
        cookies={"aws-waf-token": waf_token} if waf_token else {},
        timeout=30,
    )
    return {"status": r.status_code, "text": r.text}


def fetch_case_summary(hex_id: str, waf_token: str, user_agent: str) -> dict:
    url = (
        f"https://portal-nc.tylertech.cloud/app/RegisterOfActionsService/"
        f"CaseSummariesSlim?key={hex_id}&mode=portalembed"
    )
    r = requests.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://portal-nc.tylertech.cloud/app/RegisterOfActions/",
            "Origin": "https://portal-nc.tylertech.cloud",
        },
        cookies={"aws-waf-token": waf_token} if waf_token else {},
        timeout=30,
    )
    return {"status": r.status_code, "text": r.text}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("recon")

    info = asyncio.run(grab_case_ids())
    log.info("got %d cases, waf=%s ua=%s",
             len(info["cases"]), bool(info["waf_token"]), info["user_agent"][:80] if info["user_agent"] else None)

    for case in info["cases"][:3]:
        hex_id = extract_id(case["data_url"])
        log.info("\n=== %s (id=%s) ===", case["caseno"], hex_id[:32] + "...")

        summary = fetch_case_summary(hex_id, info["waf_token"], info["user_agent"])
        log.info("CaseSummariesSlim: HTTP %d (%d chars)", summary["status"], len(summary["text"]))
        if summary["status"] == 200 and summary["text"]:
            try:
                obj = json.loads(summary["text"])
                log.info("  parsed summary keys: %s", list(obj.keys()) if isinstance(obj, dict) else f"list[{len(obj)}]")
                log.info("  sample: %s", json.dumps(obj, indent=2)[:1500])
            except Exception as e:
                log.warning("  json parse failed: %s; raw: %s", e, summary["text"][:500])

        parties = fetch_parties(hex_id, info["waf_token"], info["user_agent"])
        log.info("Parties: HTTP %d (%d chars)", parties["status"], len(parties["text"]))
        if parties["status"] == 200 and parties["text"]:
            try:
                obj = json.loads(parties["text"])
                log.info("  parsed parties: %s", type(obj).__name__)
                log.info("  full json:\n%s", json.dumps(obj, indent=2)[:4000])
            except Exception as e:
                log.warning("  json parse failed: %s; raw: %s", e, parties["text"][:500])

        # Dump full JSON to disk
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (OUT_DIR / f"summary_{case['caseno']}_{ts}.json").write_text(summary["text"], encoding="utf-8")
        (OUT_DIR / f"parties_{case['caseno']}_{ts}.json").write_text(parties["text"], encoding="utf-8")


if __name__ == "__main__":
    main()
