"""Scrape Zacchaeus Legal Services (zls-nc.com) for active NC tax foreclosure
sales in our target counties.

Architecture:
  1. Navigate to https://www.zls-nc.com/listings (Wix shell)
  2. Click the "I AGREE" disclaimer button — reveals a DevExtreme-style data
     grid embedded in the page
  3. Bump grid page size to its max (100) to retrieve as many rows as possible
     in a single render
  4. Read body.innerText — each row is rendered as a tab-delimited line in
     the order: Tax Office, Parcel #, Status, Sale Date, Upset Deadline,
     Opening Bid, Current Bid, Notice, ⚠️ Address (last 2 columns sometimes
     empty)
  5. Regex-match rows for our target counties (Cabarrus + Catawba — Iredell
     confirmed empty as of 2026-05-17 recon)
  6. Filter out finalized states (Sale Confirmed / Redeemed); keep
     Pending Confirmation / Upset Bidding in Progress / Courthouse Sale

NOTE: Zacchaeus publishes a strong disclaimer that addresses are
"provided by others and are not certified" — the address field on each row
should be treated as a hint, not authoritative. Downstream Smarty enrichment
will validate.
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


LISTINGS_URL = "https://www.zls-nc.com/listings"

# Counties Zacchaeus actively represents within our 7-county scope (confirmed
# 2026-05-17). Iredell appears in their per-county slug URL but has zero
# active listings; revisit periodically.
ZACCHAEUS_TARGET_COUNTIES = ["Cabarrus", "Catawba"]

# Statuses we KEEP — actively for sale or in upset window
_ACTIVE_STATUSES = {
    "pending confirmation",
    "upset bidding in progress",
    "courthouse sale",
}

# Statuses we DROP — finalized
_FINAL_STATUSES = {
    "sale confirmed",
    "sale confirmed / deed recorded",
    "deed recorded",
    "redeemed",
    "postponed",  # postponed sales aren't actionable until rescheduled
}


# ── State helpers ─────────────────────────────────────────────────────


def _state_file() -> Path:
    return config.PROJECT_ROOT / "zacchaeus_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "zacchaeus_seen_ids.json"


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


# ── Row parsing ───────────────────────────────────────────────────────


# Sample rendered row (tabs and newlines as seen in body.innerText):
#   "Cabarrus County Tax Office\t11035 0077.10\tPending Confirmation\t2/19/2026\tn/a\tn/a\t$21,000.00\t\nNotice\n\t⚠️ 169 Glenwood Dr SW, Concord, NC 28025\t"
# Some rows have no address (the last cell is empty).
ROW_RE = re.compile(
    r"^(?P<county>[A-Z][A-Za-z]+)\s+County\s+Tax\s+Office\t"
    r"(?P<parcel>[^\t]+?)\t"
    r"(?P<status>[^\t]+?)\t"
    r"(?P<sale_date>[^\t]+?)\t"
    r"(?P<upset>[^\t]+?)\t"
    r"(?P<opening>[^\t]+?)\t"
    r"(?P<current>[^\t]+?)\t"
    r"\s*\nNotice\n"
    r"(?:\t(?:⚠️\s*(?P<addr_line>[^\t\n]+))?\t)?",
    re.MULTILINE,
)


# Address suffix: split "169 Glenwood Dr SW, Concord, NC 28025" → street/city/zip
ADDR_PARTS_RE = re.compile(
    r"^(?P<street>.+?),\s*(?P<city>[^,]+?),\s*NC\s+(?P<zip>\d{5})\s*$"
)


def _parse_money(s: str) -> str:
    """Normalize '$21,000.00' -> '21000.00'. Returns '' for 'n/a' / 'To be...'."""
    s = (s or "").strip()
    if not s or s.lower().startswith(("n/a", "to be")):
        return ""
    return s.replace("$", "").replace(",", "").strip()


def _parse_sale_date(s: str) -> str:
    """'2/19/2026' -> '2026-02-19'. Returns '' for unparseable."""
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def split_address(addr_line: str) -> tuple[str, str, str]:
    """Split '169 Glenwood Dr SW, Concord, NC 28025' → (street, city, zip)."""
    if not addr_line:
        return "", "", ""
    m = ADDR_PARTS_RE.match(addr_line.strip())
    if not m:
        # Best-effort: just keep the whole thing as street
        return addr_line.strip(), "", ""
    return m.group("street").strip(), m.group("city").strip(), m.group("zip")


def parse_rows(body_text: str, target_counties: set[str]) -> list[dict]:
    """Walk body.innerText and yield one dict per matching row.

    target_counties is a set of properly-cased county names (e.g. {"Cabarrus"}).
    """
    found: list[dict] = []
    target_lower = {c.lower() for c in target_counties}
    for m in ROW_RE.finditer(body_text):
        county = m.group("county").strip()
        if county.lower() not in target_lower:
            continue
        status = m.group("status").strip()
        if status.lower() in _FINAL_STATUSES:
            continue
        if status.lower() not in _ACTIVE_STATUSES:
            # Keep unknown statuses but log — surfaces new states early
            logger.info("Zacchaeus: unfamiliar status '%s' — keeping (county=%s)", status, county)
        found.append({
            "county": county,
            "parcel": m.group("parcel").strip(),
            "status": status,
            "sale_date": m.group("sale_date").strip(),
            "upset_deadline": m.group("upset").strip(),
            "opening_bid": m.group("opening").strip(),
            "current_bid": m.group("current").strip(),
            "address_line": (m.group("addr_line") or "").strip(),
        })
    return found


def row_to_notice(row: dict) -> NoticeData:
    """Map one parsed row → NoticeData."""
    street, city, zipc = split_address(row["address_line"])
    opening = _parse_money(row["opening_bid"])
    current = _parse_money(row["current_bid"])
    sale_date = _parse_sale_date(row["sale_date"])

    # Synthetic ID for cross-run dedup: county+parcel is stable per record
    dedup_id = f"{row['county']}::{row['parcel']}"

    return NoticeData(
        county=row["county"],
        state="NC",
        notice_type="tax_sale",
        date_added=datetime.now().strftime("%Y-%m-%d"),
        auction_date=sale_date,
        address=street,
        city=city,
        zip=zipc,
        parcel_id=row["parcel"],
        # Use the opening bid (or current bid if higher) as the amount owed
        # signal. Zacchaeus doesn't expose due_amount directly; opening bid
        # is typically tax + costs + fees.
        tax_delinquent_amount=current or opening,
        source_url=f"https://www.zls-nc.com/listings#{dedup_id}",
        raw_text=(
            f"NC tax foreclosure sale (Zacchaeus Legal Services). "
            f"County: {row['county']}. Parcel: {row['parcel']}. "
            f"Status: {row['status']}. Sale date: {row['sale_date']}. "
            f"Upset bid deadline: {row['upset_deadline']}. "
            f"Opening bid: {row['opening_bid']}. Current bid: {row['current_bid']}. "
            f"Address (per Zacchaeus, uncertified): {row['address_line'] or '(none on file)'}."
        ),
    )


# ── Playwright driver ────────────────────────────────────────────────


async def _bump_page_size(page: Page, target: int = 100) -> None:
    """Try to expand the grid's page-size dropdown to its max.

    DevExtreme page sizes are usually 5, 10, 20, 50, 100. We try 100 first
    and fall back to a smaller value if 100 isn't an option.
    """
    try:
        psize = page.locator('text="Page Size:"').first
        if await psize.count() == 0:
            logger.debug("Zacchaeus: 'Page Size:' label not found — keeping default")
            return
        # The dropdown sits to the right of the label
        parent = psize.locator("xpath=..")
        ddl = parent.locator("input, [role='combobox']").first
        if await ddl.count() == 0:
            return
        await ddl.click()
        await page.wait_for_timeout(400)
        for candidate in [str(target), "50", "25"]:
            opt = page.locator(f'text="{candidate}"').first
            if await opt.count() > 0:
                await opt.click()
                logger.info("Zacchaeus: page size set to %s", candidate)
                await page.wait_for_timeout(3000)
                return
    except Exception:
        logger.debug("Zacchaeus: page-size bump failed", exc_info=True)


async def _scrape_grid_page(
    page: Page, target_counties: set[str],
) -> list[dict]:
    body = await page.inner_text("body")
    return parse_rows(body, target_counties)


async def _click_next_page(page: Page) -> bool:
    """Advance to the next grid page. Returns True if advanced."""
    # DevExtreme: pager has a "Next page" button with aria-label or role=button
    for sel in [
        '[aria-label="Next page"]',
        '.dx-pager .dx-next-button',
        '.dx-navigate-button.dx-next-button',
        '[class*="next" i][class*="button" i]',
    ]:
        loc = page.locator(sel).first
        try:
            cnt = await loc.count()
        except Exception:
            cnt = 0
        if cnt == 0:
            continue
        # Skip if disabled
        try:
            cls = await loc.get_attribute("class") or ""
            if "disabled" in cls.lower():
                return False
        except Exception:
            pass
        try:
            await loc.click(timeout=5000)
            await page.wait_for_timeout(2000)
            return True
        except Exception:
            continue
    return False


async def scrape_zacchaeus(
    *,
    counties: list[str] | None = None,
    seen_ids: dict[str, str] | None = None,
    headless: bool = True,
    max_pages: int = 5,
) -> list[NoticeData]:
    """Scrape Zacchaeus active tax foreclosure sales for the requested counties.

    Args:
        counties: subset of ZACCHAEUS_TARGET_COUNTIES; defaults to all.
        seen_ids: cross-run dedup cache (loaded from disk if None).
        headless: pass False to debug visually.
        max_pages: cap on Next-page clicks (each page = ~100 rows after bump).
    """
    if counties is None:
        counties = list(ZACCHAEUS_TARGET_COUNTIES)
    target = {c for c in counties if c in ZACCHAEUS_TARGET_COUNTIES}
    if not target:
        logger.info("Zacchaeus: none of the requested counties are covered")
        return []

    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info("Zacchaeus: %d previously-seen IDs in cache; targeting %s",
                len(seen_ids), sorted(target))

    notices: list[NoticeData] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await ctx.new_page()

        try:
            await page.goto(LISTINGS_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except PwTimeout:
                pass
            await page.wait_for_timeout(3000)

            # Dismiss the disclaimer
            agree = page.locator('text="I AGREE"').first
            if await agree.count() == 0:
                logger.error("Zacchaeus: 'I AGREE' button missing — page state unexpected")
                return []
            await agree.click(timeout=10_000)
            await page.wait_for_timeout(4000)

            await _bump_page_size(page, target=100)

            # Walk grid pages until either max_pages reached or no more next button
            for page_idx in range(max_pages):
                rows = await _scrape_grid_page(page, target)
                logger.info("Zacchaeus page %d: matched %d row(s) for target counties",
                            page_idx + 1, len(rows))
                for row in rows:
                    notice = row_to_notice(row)
                    dedup_id = f"{row['county']}::{row['parcel']}"
                    if dedup_id in seen_ids:
                        logger.debug("Zacchaeus: skipping already-seen %s", dedup_id)
                        continue
                    seen_ids[dedup_id] = notice.date_added
                    notices.append(notice)

                advanced = await _click_next_page(page)
                if not advanced:
                    logger.info("Zacchaeus: no more grid pages")
                    break

        finally:
            await browser.close()

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("Zacchaeus: total %d new notice(s) across %s",
                len(notices), sorted(target))
    return notices


def scrape_zacchaeus_sync(**kw) -> list[NoticeData]:
    """Sync wrapper for the async scraper — convenient for the CLI dispatcher."""
    return asyncio.run(scrape_zacchaeus(**kw))
