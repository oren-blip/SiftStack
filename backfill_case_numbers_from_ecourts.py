"""Backfill case numbers for blank-case-no rows by searching eCourts by name.

Newspaper-published Notice-to-Creditors arrive in our pipeline without
case numbers. When the manual-archive index (`build_manual_archive_index.py`)
can't match them either, we know they're cases the user hasn't pulled
manually — but they still exist in eCourts somewhere. This script
does a per-decedent Smart Search on Tyler eCourts (broad date window,
filtered by county) to find the case.

For each match: writes the case # + hex ID into the row, then calls the
Parties OData endpoint to populate Executor + Beneficiaries.

For non-matches: leaves the row as-is (truly newspaper-only or filed
under a non-Estates docket).

Usage:
    python backfill_case_numbers_from_ecourts.py
    python backfill_case_numbers_from_ecourts.py --csv output/X.csv
    python backfill_case_numbers_from_ecourts.py --since-days 180  # widen window
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from ecourts_case_api import CaseDetail, CaseDetailClient  # noqa: E402
from ecourts_scraper import (  # noqa: E402
    CASE_TYPE_BY_NOTICE_TYPE,
    PORTAL_URL,
    SMART_SEARCH_URL,
    _DEFAULT_UA,
    _is_waf_gate,
    _load_cached_waf_cookie,
    _navigate_to_smart_search,
    _open_advanced_filters,
    _parse_results,
    _select_only_county,
    _set_case_type,
    _set_date_range,
    _set_search_criteria,
    _solve_and_inject_waf,
    _submit_search,
)
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_case")


def _name_token_key(name: str) -> set[str]:
    """Order-independent token set (3+ char tokens, no AKA, no suffixes)."""
    s = (name or "").upper()
    s = re.sub(r"\bAKA\b.*", "", s)
    s = re.sub(r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR)\.?\b", "", s)
    return {t for t in re.findall(r"[A-Z]+", s) if len(t) >= 3}


def _decedent_search_query(name: str) -> str:
    """Tyler's Smart Search 'Record Number or Name' field expects the name
    in 'Last, First Middle Suffix' format. Most of our data already comes
    that way (from eCourts Parties API), so we pass through. Strip any
    'Aka X Y Z' suffix because Tyler matches the primary name only.
    """
    s = (name or "").strip()
    if not s:
        return ""
    # Strip aliases the eCourts case detail sometimes appends
    s = re.sub(r"\s*[,\s]\s*AKA\s+.*$", "", s, flags=re.IGNORECASE).strip()
    # If no comma (e.g. "Gerald Jackson Huggins"), convert to "Huggins, Gerald Jackson"
    if "," not in s:
        tokens = s.split()
        if len(tokens) >= 2:
            s = f"{tokens[-1]}, {' '.join(tokens[:-1])}"
    return s


def _name_matches(target: str, found: str) -> bool:
    """Loose match — both must share at least 2 normalized tokens."""
    t = _name_token_key(target)
    f = _name_token_key(found)
    if not t or not f:
        return False
    return len(t & f) >= 2


async def search_case_for_decedent(
    browser, ctx, page, county: str, decedent: str,
    mdy_start: str, mdy_end: str,
) -> tuple[str, str] | None:
    """Run a single eCourts Smart Search using the decedent's last name.
    Returns (case_no, hex_id) on a match, or None.
    """
    query = _decedent_search_query(decedent)
    if not query:
        return None

    # Reset form by navigating back to Smart Search
    await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(1500)
    await _open_advanced_filters(page)
    try:
        await _set_search_criteria(page, query)
        await _set_case_type(page, CASE_TYPE_BY_NOTICE_TYPE["probate"])
        await _set_date_range(page, mdy_start, mdy_end)
        await _select_only_county(page, county)
        if not await _submit_search(page):
            return None
        results = await _parse_results(page, county, "probate")
    except Exception:
        logger.exception("Search failed for %s/%s", county, decedent)
        return None

    # Find the result whose decedent name matches
    for n in results:
        cand_name = getattr(n, "decedent_name", "") or getattr(n, "owner_name", "")
        if _name_matches(decedent, cand_name):
            hex_id = getattr(n, "_roa_id", "")
            return (n.case_number, hex_id)
    return None


async def main_async(args) -> None:
    # Prefer the post-polish *_datasift.csv (current polish-pipeline output).
    # Fall back to the legacy *_archive_backfilled.csv name only if no
    # _datasift.csv exists for that week (older pipeline artifact).
    if args.csv:
        src_csv = Path(args.csv)
    else:
        candidates = sorted(Path("output").glob("nc_estates_ftm_*_week*_datasift.csv"))
        if not candidates:
            candidates = sorted(Path("output").glob("nc_estates_ftm_*_archive_backfilled.csv"))
        if not candidates:
            logger.error("No source CSV found in output/ — aborting")
            return
        src_csv = candidates[-1]
    logger.info("Source: %s", src_csv)
    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    logger.info("Loaded %d rows", len(rows))

    blanks = [r for r in rows
              if not (r.get("Case No.") or "").strip()
              and (r.get("Deceased Owner") or "").strip()
              and (r.get("County") or "").strip()]
    logger.info("Blank-case-no rows to backfill: %d", len(blanks))
    if not blanks:
        return

    # Date range — broad window so we catch older cases newspapers are still publishing for
    end = datetime.now()
    start = end - timedelta(days=args.since_days)
    mdy_start, mdy_end = start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
    logger.info("eCourts search window: %s .. %s", mdy_start, mdy_end)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=_DEFAULT_UA)
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()

        cached = _load_cached_waf_cookie()
        if cached:
            logger.info("Reusing cached WAF cookie")
            await ctx.close()
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                            user_agent=cached.get("user_agent") or _DEFAULT_UA)
            await ctx.add_cookies([{
                "name": "aws-waf-token", "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud", "path": "/", "httpOnly": False,
                "secure": True, "sameSite": "Lax",
            }])
            ctx.set_default_timeout(60_000)
            page = await ctx.new_page()

        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            logger.info("WAF gate — solving via CapSolver")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)

        await _navigate_to_smart_search(page)

        # Capture cookies + UA for Parties API
        ctx_cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        waf_cookie = next((c for c in ctx_cookies if c["name"] == "aws-waf-token"), None)
        waf_token = waf_cookie["value"] if waf_cookie else ""
        ua = cached.get("user_agent") if cached else _DEFAULT_UA

        # Run search per blank-case-no row
        backfilled = 0
        no_match = 0
        for i, r in enumerate(blanks, 1):
            county = r["County"]
            dec = r["Deceased Owner"]
            logger.info("[%d/%d] Searching %s for %r", i, len(blanks), county, dec)
            result = await search_case_for_decedent(
                browser, ctx, page, county, dec, mdy_start, mdy_end
            )
            if not result:
                no_match += 1
                logger.info("  ❌ no match in eCourts %s for %r", county, dec)
                continue
            case_no, hex_id = result
            r["Case No."] = case_no
            backfilled += 1
            logger.info("  ✅ Found case=%s (hex=%s)", case_no, hex_id[:16])

            # Use Parties API to fill executor/beneficiaries
            if hex_id and waf_token:
                client = CaseDetailClient(waf_token=waf_token, user_agent=ua)
                parties = client.fetch_parties(hex_id, retries=3)
                if parties:
                    detail = CaseDetail(case_id=hex_id, parties=parties)
                    ex = detail.executor
                    if ex and not (r.get("Personal Representative") or "").strip().startswith("Heirs of"):
                        full = " ".join(filter(None, [ex.first_name, ex.last_name])).strip() or ex.full_name
                        if full and r.get("First Name") == "Heirs":
                            # Heirs-of fallback can be upgraded to real PR
                            r["Personal Representative"] = full
                            r["First Name"] = ex.first_name
                            r["Last Name"] = ex.last_name
                            addr = ex.first_address
                            if not addr.is_blank():
                                r["Mailing Address"] = " ".join(filter(None, [addr.line1, addr.line2])).strip()
                                r["Mailing City"] = addr.city
                                r["Mailing State"] = addr.state
                                r["Mailing Zip"] = addr.zip
                            logger.info("     Upgraded Heirs-of -> %s @ %s", full, r.get("Mailing Address",""))

            # Tag the row
            tag = (r.get("Tags") or "").strip()
            marker = f"ecourts-backfill:{datetime.now().strftime('%Y-%m-%d')}"
            r["Tags"] = f"{tag} | {marker}" if tag else marker

            # Inter-case throttle
            time.sleep(args.inter_case_delay)

        await ctx.close()
        await browser.close()

    # Drop policy: rows whose Case No. is STILL blank after both
    # archive cross-ref AND eCourts name-search are the truly-unfindable
    # ones. They'll cycle through eCourts naturally on the next weekly
    # run if/when the case eventually gets filed under a matching name.
    # Default = drop. Pass --keep-still-blank to override.
    pre_drop = len(rows)
    if not args.keep_still_blank:
        rows = [r for r in rows if (r.get("Case No.") or "").strip()]
        dropped_blank = pre_drop - len(rows)
    else:
        dropped_blank = 0

    # Write output. Use a stable filename pattern so consolidate_weeks
    # finds it: strip any prior _archive_backfilled / _datasift suffix
    # from the source stem.
    stem = src_csv.stem
    for suffix in ("_archive_backfilled", "_datasift"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_csv = Path("output") / f"{stem}_{ts}_ecourts_backfilled.csv"
    out_xlsx = out_csv.with_suffix(".xlsx")
    write_csv(rows, out_csv)
    write_xlsx(rows, out_xlsx)
    logger.info("=" * 60)
    logger.info("Backfilled via eCourts: %d  No-match: %d  Dropped still-blank: %d",
                backfilled, no_match, dropped_blank)
    logger.info("Wrote: %s", out_csv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="CSV path (default: latest *_archive_backfilled.csv in output/)")
    ap.add_argument("--since-days", type=int, default=180,
                    help="Look-back window in days for eCourts search (default 180)")
    ap.add_argument("--headed", action="store_true", help="Watch the browser")
    ap.add_argument("--inter-case-delay", type=float, default=3.0,
                    help="Seconds between searches (default 3)")
    ap.add_argument("--keep-still-blank", action="store_true",
                    help="Keep rows whose Case No. is still blank after the "
                         "eCourts name search. Default is to DROP them — "
                         "they'll cycle through next week's scrape if the "
                         "case gets filed under a findable name.")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
