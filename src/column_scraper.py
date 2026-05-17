"""Scrape NC public-notice subdomains hosted on column.us.

Three subdomains, one per county (single template — same selectors apply):
  - statesville.column.us       → Iredell County
  - independenttribune.column.us → Cabarrus County
  - hickoryrecord.column.us     → Catawba County

The column.us React app renders full notice bodies inline in the result list
(no detail-page click needed). Each rendered notice is a 5-line block in the
page innerText:

    <PUBLICATION NAME>
    <Notice Category>            e.g. "Foreclosure Sale", "Notice to Creditors"
    <Full notice body — one line, can be 500-3000 chars>
    <COUNTY> COUNTY, NORTH CAROLINA
    <YYYY-MM-DD>

No CAPTCHA, no Cloudflare, no login. Pagination via a "Load More" button.

Categories we keep (everything else dropped during parsing):
  - "Foreclosure Sale"          → notice_type = "foreclosure"
  - "Notice to Creditors"       → notice_type = "probate"
  - "Estate (Probate) Filings"  → notice_type = "probate"
  - "Tax Foreclosure Sale"      → notice_type = "tax_sale"  (rare on column)
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PwTimeout, async_playwright

import config
from foreclosure_filter import is_valid_foreclosure
from nc_notice_parser import parse_nc_notice_text
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


# ── Subdomain → (county, publication-name-header) mapping ────────────
# Publication name must match exactly what appears in the result list
# header line (uppercase, no punctuation).
COLUMN_SUBDOMAINS: list[tuple[str, str, str]] = [
    ("statesville",        "Iredell",     "STATESVILLE RECORD AND LANDMARK"),
    ("independenttribune", "Cabarrus",    "CONCORD INDEPENDENT TRIBUNE"),
    ("hickoryrecord",      "Catawba",     "HICKORY DAILY RECORD"),
]


# ── Category → notice_type mapping ───────────────────────────────────
CATEGORY_TO_NOTICE_TYPE: dict[str, str] = {
    "Foreclosure Sale": "foreclosure",
    "Notice to Creditors": "probate",
    "Estate (Probate) Filings": "probate",
    "Tax Foreclosure Sale": "tax_sale",
}


# ── State helpers ─────────────────────────────────────────────────────


def _state_file() -> Path:
    return config.PROJECT_ROOT / "column_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "column_seen_ids.json"


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


# ── Parsing the linearized result text ────────────────────────────────


# COL-NC-NNNNNN appears at the end of every notice — use it as a per-record ID
# so we can dedupe cross-run without parsing the full URL (notices don't have
# their own permanent URLs on column.us — they're just rendered inline).
COL_ID_RE = re.compile(r"\bCOL-[A-Z]{2}-\d{4,8}\b")

# Date that appears as the closing line of each block, e.g. "2026-05-16"
ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")

# County footer, e.g. "CATAWBA COUNTY, NORTH CAROLINA"
COUNTY_FOOTER_RE = re.compile(
    r"^([A-Z][A-Z ]+?)\s+COUNTY,\s+NORTH\s+CAROLINA$",
    re.IGNORECASE,
)


def split_into_notices(
    page_text: str, publication: str, expected_county: str,
) -> list[dict]:
    """Split the result-page innerText into per-notice blocks.

    Returns a list of dicts: {category, body, county, date, col_id}.
    Only blocks that look like complete notices (have a category + county
    footer + ISO date) are returned. Non-notice categories are kept here —
    callers filter by category afterwards.
    """
    lines = [ln.strip() for ln in page_text.splitlines()]

    notices: list[dict] = []
    i = 0
    n = len(lines)
    pub_upper = publication.upper()
    expected_county_upper = expected_county.upper()

    while i < n:
        # Each notice begins with a line that exactly equals the publication
        # name (in caps). The next line is the category, then the body, then
        # the county footer, then the ISO date. The body is a single long
        # line — column.us renders it that way.
        if lines[i].upper() == pub_upper and i + 4 < n:
            category = lines[i + 1]
            body = lines[i + 2]
            footer = lines[i + 3]
            date_line = lines[i + 4]

            county_m = COUNTY_FOOTER_RE.match(footer)
            date_m = ISO_DATE_RE.match(date_line)

            if county_m and date_m and body and category and len(body) > 30:
                col_m = COL_ID_RE.search(body)
                notices.append({
                    "category": category,
                    "body": body,
                    "county": county_m.group(1).strip().title(),
                    "date": date_m.group(1),
                    "col_id": col_m.group(0) if col_m else "",
                })
                i += 5
                continue
        i += 1

    if notices:
        # Sanity-check that at least some notices map to the expected county
        matched_county = sum(1 for nx in notices if nx["county"].upper() == expected_county_upper)
        if matched_county == 0:
            logger.warning(
                "Parsed %d notices from %s but none are for expected county '%s'",
                len(notices), publication, expected_county,
            )
    return notices


# ── Playwright automation ─────────────────────────────────────────────


async def _delay() -> None:
    await asyncio.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))


async def _load_more_until(
    page: Page,
    *,
    max_loads: int,
    since_date: str | None,
) -> None:
    """Click 'Load More' repeatedly to expand the result list.

    Stops when:
      - "Load More" button disappears (end of results), OR
      - max_loads clicks performed, OR
      - the oldest visible date is older than since_date (daily mode cutoff)
    """
    for n in range(max_loads):
        # Find "Load More" — the button is rendered below the fold, so a
        # naive .click() times out waiting for visibility. Scroll it into
        # view first, then dispatch a JS click which doesn't require
        # visibility (the React handler doesn't care).
        btn = page.locator('button[aria-label="Load more notices"]').first
        if await btn.count() == 0:
            logger.info("    Load More button gone — reached end of results")
            return

        # Early-stop if we've gone past the date cutoff
        if since_date:
            oldest = await _oldest_visible_date(page)
            if oldest and oldest < since_date:
                logger.info(
                    "    Oldest visible date %s < cutoff %s — stopping pagination",
                    oldest, since_date,
                )
                return

        try:
            await btn.evaluate("el => el.scrollIntoView({behavior: 'instant', block: 'center'})")
            await page.wait_for_timeout(200)
            await btn.click(timeout=10_000)
        except PwTimeout:
            # Visibility-based click still timed out — fall back to JS click
            try:
                await btn.evaluate("el => el.click()")
            except Exception:
                logger.warning("    Load More click failed at iteration %d", n + 1, exc_info=True)
                return
        except Exception:
            logger.warning("    Load More click failed at iteration %d", n + 1, exc_info=True)
            return

        # Wait for new results to render — React appends to the list
        await page.wait_for_timeout(1500)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PwTimeout:
            pass
        await _delay()


async def _oldest_visible_date(page: Page) -> str | None:
    """Scan visible text for the oldest YYYY-MM-DD date that follows a
    'COUNTY, NORTH CAROLINA' footer (those are notice publication dates).
    """
    try:
        text = await page.inner_text("body")
    except Exception:
        return None
    dates = re.findall(
        r"COUNTY,\s+NORTH\s+CAROLINA\s+(\d{4}-\d{2}-\d{2})",
        text, re.IGNORECASE,
    )
    return min(dates) if dates else None


async def _scrape_subdomain(
    page: Page,
    slug: str,
    county: str,
    publication: str,
    *,
    since_date: str | None,
    max_loads: int,
    seen_ids: dict[str, str] | None,
) -> list[NoticeData]:
    """Open one column.us subdomain, paginate, parse → NoticeData list."""
    url = f"https://{slug}.column.us/search"
    logger.info("Column scraper: %s (county=%s, publication=%s)", url, county, publication)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PwTimeout:
        logger.error("  Timed out loading %s", url)
        return []

    # SPA hydration — give React 3s to render initial results
    await page.wait_for_timeout(3000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PwTimeout:
        pass

    # Wait for at least one notice block to be present (publication name in caps).
    try:
        await page.wait_for_function(
            f"document.body.innerText.includes({publication!r})",
            timeout=20_000,
        )
    except PwTimeout:
        logger.error("  Publication header '%s' never rendered — site state unexpected", publication)
        return []

    await _load_more_until(page, max_loads=max_loads, since_date=since_date)

    text = await page.inner_text("body")
    blocks = split_into_notices(text, publication, county)
    logger.info("  Parsed %d notice block(s) from %s", len(blocks), slug)

    notices: list[NoticeData] = []
    for block in blocks:
        # Skip notices outside our target categories
        notice_type = CATEGORY_TO_NOTICE_TYPE.get(block["category"])
        if notice_type is None:
            continue

        # Daily-mode cutoff
        if since_date and block["date"] < since_date:
            continue

        # Cross-run dedup via COL-NC-NNNNNN ID
        col_id = block["col_id"]
        if seen_ids is not None and col_id and col_id in seen_ids:
            continue

        notice = parse_nc_notice_text(
            raw_text=block["body"],
            county=block["county"] or county,
            notice_type=notice_type,
            source_url=f"https://{slug}.column.us/search?col={col_id}" if col_id else url,
            date_added=block["date"],
        )

        if seen_ids is not None and col_id:
            seen_ids[col_id] = block["date"]

        if notice_type == "foreclosure" and not is_valid_foreclosure(notice):
            logger.debug("  Filtered (not trustee sale): %s", col_id)
            continue

        notices.append(notice)

    logger.info("  Kept %d/%d notices after category + dedup + filter", len(notices), len(blocks))
    return notices


# ── Public entry point ───────────────────────────────────────────────


async def scrape_column_all(
    mode: str = "daily",
    subdomains: list[tuple[str, str, str]] | None = None,
    types: list[str] | None = None,
    counties: list[str] | None = None,
    *,
    since_date_override: str | None = None,
    max_loads_per_subdomain: int = 20,
    seen_ids: dict[str, str] | None = None,
    on_batch=None,
) -> list[NoticeData]:
    """Scrape all configured column.us NC subdomains.

    Args:
        mode: "daily" or "historical"
        subdomains: subset of COLUMN_SUBDOMAINS to scrape (defaults to all 3)
        types: filter to these notice types (e.g. ["foreclosure", "probate"])
        counties: filter subdomains to these counties (case-insensitive)
        since_date_override: YYYY-MM-DD; overrides mode-based cutoff
        max_loads_per_subdomain: cap on "Load More" clicks per subdomain (each
            click adds ~20 notices; 20 clicks ≈ 400 notices)
        seen_ids: cross-run dedup cache (loaded from disk if None)
        on_batch: optional async callback(list[NoticeData]) per subdomain
    """
    if subdomains is None:
        subdomains = list(COLUMN_SUBDOMAINS)
    if counties:
        wanted = {c.lower() for c in counties}
        subdomains = [s for s in subdomains if s[1].lower() in wanted]
    if not subdomains:
        logger.warning("No column.us subdomains match the requested counties")
        return []

    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info("Column scraper: %d previously-seen notice IDs in cache", len(seen_ids))

    since_date = _resolve_since_date(mode, since_date_override)
    logger.info("Column scraper: since_date cutoff = %s", since_date or "(none)")

    type_filter = {t.lower() for t in types} if types else None

    all_notices: list[NoticeData] = []
    async with async_playwright() as pw:
        # column.us is a public React SPA — headed=False works (no parking
        # redirect like ncnotices). Default to headless for production runs.
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        context.set_default_timeout(60_000)
        page = await context.new_page()

        for slug, county, publication in subdomains:
            try:
                results = await _scrape_subdomain(
                    page, slug, county, publication,
                    since_date=since_date,
                    max_loads=max_loads_per_subdomain,
                    seen_ids=seen_ids,
                )
                if type_filter:
                    results = [n for n in results if n.notice_type in type_filter]
                all_notices.extend(results)
                if on_batch and results:
                    try:
                        await on_batch(results)
                    except Exception:
                        logger.exception("on_batch callback failed")
            except Exception:
                logger.exception("Subdomain failed: %s", slug)

            # Incremental persistence after each subdomain — survive crashes
            try:
                save_seen_ids(seen_ids)
            except Exception:
                logger.exception("Failed to persist column seen_ids after %s", slug)

        await browser.close()

    if mode == "daily":
        save_last_run_date()
    save_seen_ids(seen_ids)
    logger.info("Column scraper: total %d notices", len(all_notices))
    return all_notices


def _resolve_since_date(mode: str, override: str | None) -> str | None:
    """Resolve the publication-date cutoff for the scrape."""
    if override:
        return override
    if mode == "historical":
        return (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    # Daily mode: use stored last_run_date or default to 7-day lookback
    last = load_last_run_date()
    if last:
        return last
    return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
