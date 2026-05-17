"""Scrape Mecklenburg County's year-round Delinquent Bill Search.

Source: https://taxbill.co.mecklenburg.nc.us/publicwebaccess/BillDelinquentSearch.aspx
This is a classic ASP.NET WebForms page (__VIEWSTATE / __EVENTVALIDATION).
No login, no CAPTCHA. We drive it via Playwright because the postback flow
is much simpler with a real browser than managing ViewState by hand.

Form:
  - <select name="yearValue">          ALL, 2026, 2025, 2024, ... (one per year)
  - <select name="lookupDelinquentCriterion">  balance buckets ("<$1,000.00",
    "$1,000.00 - $4,999.99", "$5,000.00 - $9,999.99", "$10,000 - Higher")
  - <input  name="btnGo_Delinquent">  submit
  - <table  id="tblSearchResults">    8-column grid + pager

Per-row columns:
  Bill # | Old Bill # | Parcel # | Name | Location | Bill Flags | Billed | Current Due

This is the year-round delinquent inventory — properties that owe taxes
TODAY, regardless of whether they've been referred to foreclosure yet. It
complements `mecklenburg_tax_scraper.py` (which only shows the in-rem
foreclosure cases already filed at the courthouse).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PwTimeout, async_playwright

import config
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


SEARCH_URL = (
    "https://taxbill.co.mecklenburg.nc.us/publicwebaccess/BillDelinquentSearch.aspx"
)

# Balance-bucket labels in the dropdown — matched exactly to the option text
BALANCE_BUCKETS = [
    "<$1,000.00",
    "$1,000.00 - $4,999.99",
    "$5,000.00 - $9,999.99",
    "$10,000 - Higher",
]

# Default buckets when user doesn't override. We skip the <$1k bucket by
# default (it's mostly small unsecured/personal-property bills with low REI
# signal) and skip $10k+ (mostly commercial).
DEFAULT_BUCKETS = ["$1,000.00 - $4,999.99", "$5,000.00 - $9,999.99"]


def _state_file() -> Path:
    return config.PROJECT_ROOT / "meck_delinquent_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "meck_delinquent_seen_ids.json"


def load_last_run_date() -> str | None:
    return config.load_state(_state_file()).get("last_run_date")


def save_last_run_date() -> None:
    config.save_state(_state_file(), {"last_run_date": datetime.now().strftime("%Y-%m-%d")})


def load_seen_ids() -> dict[str, str]:
    data = config.load_state(_seen_ids_file())
    if not data:
        return {}
    cutoff = (datetime.now() - timedelta(days=config.SEEN_IDS_PRUNE_DAYS)).strftime("%Y-%m-%d")
    return {nid: d for nid, d in data.items() if d >= cutoff}


def save_seen_ids(seen: dict[str, str]) -> None:
    config.save_state(_seen_ids_file(), seen)


# ── Address parsing ────────────────────────────────────────────────────


# Location strings look like:
#   "10809 E INDEPENDENCE BV MATTHEWS NC 28105"
#   "N COLLEGE ST CHARLOTTE"                          (no number — vacant land)
#   "1124 MARBLE ST CHARLOTTE NC 28208"
#   "11535 CARMEL COMMONS BV STE 200 CHARLOTTE NC 28226"  (suite mid-string)
#
# The hard part: knowing where the street ends and the city begins. Mecklenburg
# has a small fixed set of municipalities, so we split on those rather than
# trying to guess via a regex.

# All municipalities (and major unincorporated areas) inside Mecklenburg County,
# longest-first so "MINT HILL" matches before "MINT".
_MECK_CITIES: list[str] = sorted(
    [
        "CHARLOTTE", "MATTHEWS", "MINT HILL", "PINEVILLE",
        "HUNTERSVILLE", "CORNELIUS", "DAVIDSON",
    ],
    key=len, reverse=True,
)

# Detect a leading house number — rows without one are "street name only"
# (no specific address) which is typical for vacant land bills.
_HAS_NUMBER = re.compile(r"^\d{1,5}\s+")


def split_location(loc: str) -> tuple[str, str, str]:
    """Split a Mecklenburg location string → (street, city, zip).

    Walks the city whitelist; the city token marks where street ends. ZIP is
    pulled if it follows "NC NNNNN". Vacant-land rows (no leading number)
    return ('', city, zip) so the dispatcher can skip them.
    """
    loc = re.sub(r"\s+", " ", loc).strip()
    if not loc:
        return "", "", ""
    upper = loc.upper()

    matched_city: str = ""
    city_start: int = -1
    # Find the LAST occurrence of any known city (some street names contain
    # city names — e.g. "PINEVILLE-MATTHEWS RD CHARLOTTE" — so prefer the
    # last match, which is the actual city)
    for city in _MECK_CITIES:
        pat = re.compile(r"\b" + re.escape(city) + r"\b")
        for m in pat.finditer(upper):
            if m.start() > city_start:
                city_start = m.start()
                matched_city = city

    if not matched_city:
        # Couldn't recognize a Mecklenburg city — fall back to the whole
        # string as street if it has a number, else give up
        if _HAS_NUMBER.match(loc):
            return loc.title(), "", ""
        return "", "", ""

    street_raw = loc[:city_start].strip().rstrip(",")
    after_city = loc[city_start + len(matched_city):].strip()
    zip_m = re.search(r"\b(\d{5})\b", after_city)
    zipc = zip_m.group(1) if zip_m else ""

    if not _HAS_NUMBER.match(street_raw):
        return "", matched_city.title(), zipc

    return street_raw.title(), matched_city.title(), zipc


# ── Playwright driving ────────────────────────────────────────────────


async def _wait_for_results(page: Page, timeout: float = 20.0) -> None:
    try:
        await page.wait_for_selector("#tblSearchResults tbody tr", timeout=int(timeout * 1000))
    except PwTimeout:
        pass


async def _scrape_results_page(page: Page) -> list[dict]:
    """Extract rows from the current page of tblSearchResults."""
    return await page.evaluate(
        """() => {
            const tbl = document.getElementById('tblSearchResults');
            if (!tbl) return [];
            const rows = [];
            for (const tr of tbl.querySelectorAll('tbody tr')) {
                const cells = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim());
                // Skip the header row + pager row (no parcel #) — keep only rows
                // whose first non-empty cell looks like a bill number.
                if (cells.length < 8) continue;
                const billNo = cells[0] || '';
                if (!/^\\d{7,}-\\d{4}/.test(billNo)) continue;
                rows.push({
                    bill_no:     cells[0],
                    old_bill_no: cells[1],
                    parcel:      cells[2],
                    name:        cells[3],
                    location:    cells[4],
                    flags:       cells[5],
                    billed:      cells[6],
                    current_due: cells[7],
                });
            }
            return rows;
        }"""
    )


async def _click_next_page(page: Page) -> bool:
    """Click the pager's 'Next' link if present. Returns True if advanced."""
    # The pager shows "[Page X of Y]   First.. 1 2 3 4 ..  Next"
    # Try to find the next-page link explicitly
    cur = await page.evaluate(
        """() => {
            const m = document.body.innerText.match(/Page\\s+(\\d+)\\s+of\\s+(\\d+)/i);
            return m ? [parseInt(m[1]), parseInt(m[2])] : null;
        }"""
    )
    if not cur:
        return False
    current, total = cur
    if current >= total:
        return False
    # Find a clickable link whose text is the next page number
    target = str(current + 1)
    for sel in [
        f'a:has-text("{target}")',
        f'a[href*="Page${target}"]',
        f'#tblSearchResults a:has-text("{target}")',
    ]:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0:
                await loc.click(timeout=5_000)
                await page.wait_for_load_state("domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(1500)
                await _wait_for_results(page)
                return True
        except Exception:
            continue
    return False


async def _run_single_query(
    page: Page,
    year: str,
    bucket: str,
    max_pages: int,
) -> list[dict]:
    """Submit one (year, bucket) search and walk all result pages."""
    await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(1500)

    try:
        await page.select_option('select[name="yearValue"]', label=year)
    except Exception as e:
        logger.warning("Meck delinquent: yearValue select '%s' failed: %s", year, e)
        return []
    try:
        await page.select_option('select[name="lookupDelinquentCriterion"]', label=bucket)
    except Exception as e:
        logger.warning("Meck delinquent: bucket select '%s' failed: %s", bucket, e)
        return []

    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            await page.click('input[name="btnGo_Delinquent"]', timeout=10_000)
    except PwTimeout:
        # Some ASP.NET postbacks are same-URL; just wait for results
        await page.wait_for_timeout(2000)

    await _wait_for_results(page)

    all_rows: list[dict] = []
    for page_idx in range(max_pages):
        page_rows = await _scrape_results_page(page)
        all_rows.extend(page_rows)
        logger.info(
            "Meck delinquent: year=%s bucket=%r page %d -> %d rows",
            year, bucket, page_idx + 1, len(page_rows),
        )
        if not page_rows:
            break
        if not await _click_next_page(page):
            break
    return all_rows


# ── Public entry ─────────────────────────────────────────────────────


def scrape_mecklenburg_delinquent(
    *,
    years: list[str] | None = None,
    buckets: list[str] | None = None,
    seen_ids: dict[str, str] | None = None,
    max_pages_per_bucket: int = 20,
    max_records: int = 0,
    headless: bool = True,
) -> list[NoticeData]:
    """Scrape Mecklenburg delinquent property-tax bills.

    Args:
        years:    list of tax-year labels to fetch (e.g. ['2025', '2024']).
                  Defaults to the prior calendar year (current owners typically
                  pay current year on time; prior years signal real distress).
        buckets:  balance-tier labels (see BALANCE_BUCKETS / DEFAULT_BUCKETS).
        seen_ids: cross-run dedup keyed by bill #.
        max_pages_per_bucket: safety cap on pagination.
        max_records: stop after this many records (0 = no cap).
    """
    if years is None:
        years = [str(datetime.now().year - 1)]  # last full year
    if buckets is None:
        buckets = list(DEFAULT_BUCKETS)

    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info(
        "Meck delinquent: %d seen IDs; years=%s buckets=%s",
        len(seen_ids), years, buckets,
    )

    notices: list[NoticeData] = []

    async def _run() -> None:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await ctx.new_page()
            for year in years:
                for bucket in buckets:
                    rows = await _run_single_query(page, year, bucket, max_pages_per_bucket)
                    for row in rows:
                        bill_no = (row.get("bill_no") or "").strip()
                        if not bill_no:
                            continue
                        if bill_no in seen_ids:
                            continue
                        street, city, zipc = split_location(row.get("location", ""))
                        # Skip rows with no usable street address — they're
                        # mostly tangible-personal-property or generic land bills
                        if not street:
                            continue
                        notice = NoticeData(
                            county="Mecklenburg",
                            state="NC",
                            notice_type="tax_delinquent",
                            date_added=datetime.now().strftime("%Y-%m-%d"),
                            address=street,
                            city=city,
                            zip=zipc,
                            parcel_id=(row.get("parcel") or "").strip(),
                            owner_name=(row.get("name") or "").strip(),
                            tax_delinquent_amount=(
                                row.get("current_due") or row.get("billed") or ""
                            ).replace("$", "").replace(",", "").strip(),
                            tax_delinquent_years=year,
                            source_url=SEARCH_URL + f"?bill={bill_no}",
                            raw_text=(
                                f"Mecklenburg delinquent property-tax bill (year {year}). "
                                f"Bill #{bill_no}, parcel {row.get('parcel')}. "
                                f"Owner: {row.get('name')}. Location: {row.get('location')}. "
                                f"Billed: {row.get('billed')}, current due: {row.get('current_due')}. "
                                f"Flags: {row.get('flags')}."
                            ),
                        )
                        notices.append(notice)
                        seen_ids[bill_no] = notice.date_added
                        if max_records and len(notices) >= max_records:
                            await browser.close()
                            return
            await browser.close()

    asyncio.run(_run())

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("Meck delinquent: total %d notice(s)", len(notices))
    return notices
