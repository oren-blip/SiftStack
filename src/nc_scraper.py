"""Scrape ncnotices.com (NC Press Association public-notice aggregator).

Architectural twin of scraper.py but:
  - No login (public site)
  - No CAPTCHA (none on any page)
  - Searches are built per-run from NCSavedSearch — there is no
    saved-search dropdown on the site

Each NCSavedSearch produces one (county, notice_type) search. The flow per
search is:
  1. Navigate to Search.aspx
  2. Set date range (last N days via radio + textbox)
  3. Pick category dropdown (foreclosure) OR keyword (probate / tax)
  4. Tick the county checkbox
  5. Submit, bump per-page to 50, iterate result rows
  6. For each row, click View2 → parse detail page → back
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta

from playwright.async_api import Page, TimeoutError as PwTimeout, async_playwright

import config
from config import (
    NC_SAVED_SEARCHES,
    NC_SEARCH_URL,
    NC_SEL_CATEGORY,
    NC_SEL_CURRENT_PAGE,
    NC_SEL_DATE_LAST_DAYS_INPUT,
    NC_SEL_DATE_LAST_DAYS_RADIO,
    NC_SEL_KEYWORD,
    NC_SEL_MATCH_ALL,
    NC_SEL_MATCH_ANY,
    NC_SEL_MATCH_EXACT,
    NC_SEL_NEXT_PAGE,
    NC_SEL_PER_PAGE,
    NC_SEL_SUBMIT,
    NC_SEL_TOTAL_PAGES,
    NC_SEL_VIEW_BUTTON_PATTERN,
    NC_SEEN_IDS_FILE,
    NC_STATE_FILE,
    NCSavedSearch,
    REQUEST_DELAY_MAX,
    REQUEST_DELAY_MIN,
    SEEN_IDS_PRUNE_DAYS,
)
from data_formatter import _notice_id_from_url
from foreclosure_filter import is_valid_foreclosure
from nc_notice_parser import parse_nc_notice_page
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


async def _delay() -> None:
    await asyncio.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))


# ── Form filling ──────────────────────────────────────────────────────


async def _navigate_to_search(page: Page) -> bool:
    """Open the NC search form, ready for a fresh query."""
    try:
        await page.goto(NC_SEARCH_URL, wait_until="load", timeout=45_000)
    except PwTimeout:
        logger.warning("NC Search.aspx load timed out")
        return False
    except Exception:
        logger.warning("NC Search.aspx load failed", exc_info=True)
        return False

    # Best-effort settle — networkidle on this ASP.NET site is unreliable
    # (chat widgets / analytics keep connections open).
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PwTimeout:
        pass

    # Wait for the search submit button explicitly — the form is hydrated via
    # an UpdatePanel and isn't present at DOMContentLoaded.
    try:
        await page.wait_for_selector(NC_SEL_SUBMIT, state="attached", timeout=20_000)
    except PwTimeout:
        logger.error("NC Search.aspx loaded but submit button never rendered (URL=%s)",
                     page.url)
        try:
            from pathlib import Path
            debug_dir = Path("output/nc_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(debug_dir / "navigate_fail.png"), full_page=True)
            (debug_dir / "navigate_fail.html").write_text(await page.content(), encoding="utf-8")
            logger.error("Debug snapshot written to %s", debug_dir)
        except Exception:
            pass
        return False
    return True


async def _set_date_range(page: Page, days: int) -> None:
    """Configure the date filter to 'In the last N days'."""
    # Pick the "Last N days" radio
    try:
        await page.check(NC_SEL_DATE_LAST_DAYS_RADIO)
    except Exception:
        logger.debug("Could not click 'Last N days' radio — may already be selected")
    # Set the days value
    try:
        await page.fill(NC_SEL_DATE_LAST_DAYS_INPUT, str(days))
    except Exception:
        logger.warning("Could not set 'Last N days' value — leaving default")


async def _select_category(page: Page, category: str) -> None:
    """Pick a Popular Search category (e.g. 'Foreclosure'). Triggers postback."""
    try:
        async with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            await page.select_option(NC_SEL_CATEGORY, label=category)
    except PwTimeout:
        # Some category picks don't trigger nav — fall back to a settle wait
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PwTimeout:
            pass
    except Exception as e:
        logger.warning("Category select '%s' failed: %s", category, e)


async def _fill_keyword(page: Page, keyword: str, match_type: str) -> None:
    """Fill the free-text keyword box and pick the match-type radio."""
    try:
        await page.fill(NC_SEL_KEYWORD, keyword)
    except Exception as e:
        logger.warning("Keyword fill failed: %s", e)
        return

    radio = {
        "ALL": NC_SEL_MATCH_ALL,
        "ANY": NC_SEL_MATCH_ANY,
        "EXACT": NC_SEL_MATCH_EXACT,
    }.get(match_type.upper(), NC_SEL_MATCH_EXACT)
    try:
        await page.check(radio)
    except Exception:
        logger.debug("Match-type radio click failed — using site default")


async def _check_county(page: Page, county: str) -> bool:
    """Tick the checkbox for the given NC county.

    The county checkbox list is below the fold by default — scroll the
    matching <label> into view before clicking. Returns True on success.
    """
    # Match label by exact text (case-insensitive). There are ~100 counties
    # so use first-match by label text.
    selector = f'label:has-text("{county}")'
    try:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            logger.error("County checkbox label '%s' not found on page", county)
            return False
        # Scroll into view (the checkbox list is in a scrollable panel)
        try:
            await loc.evaluate("el => el.scrollIntoView({behavior: 'instant', block: 'center'})")
        except Exception:
            pass
        await loc.click()
        await _delay()  # ASP.NET postback settle
        return True
    except Exception as e:
        logger.error("Failed to tick county checkbox '%s': %s", county, e)
        return False


async def _submit_search(page: Page) -> bool:
    """Click the search button and wait for results to land."""
    try:
        async with page.expect_navigation(wait_until="networkidle", timeout=30_000):
            await page.click(NC_SEL_SUBMIT)
    except PwTimeout:
        logger.warning("Search submission timed out — checking if results loaded anyway")
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PwTimeout:
            return False
    except Exception:
        logger.exception("Search submission failed")
        return False
    return True


async def _set_per_page_50(page: Page) -> None:
    """Bump the results-per-page dropdown to the max (50)."""
    try:
        dd = await page.query_selector(NC_SEL_PER_PAGE)
        if not dd:
            return
        current = await dd.input_value()
        if current != "50":
            await page.select_option(NC_SEL_PER_PAGE, "50")
            await page.wait_for_load_state("networkidle", timeout=15_000)
            await _delay()
    except Exception:
        logger.debug("Per-page bump failed — continuing with default", exc_info=True)


async def _get_page_info(page: Page) -> tuple[int, int]:
    """Return (current_page, total_pages) from the pager labels."""
    try:
        cur_el = await page.query_selector(NC_SEL_CURRENT_PAGE)
        tot_el = await page.query_selector(NC_SEL_TOTAL_PAGES)
        if not cur_el or not tot_el:
            return 1, 1
        cur = (await cur_el.inner_text()).strip()
        tot_text = (await tot_el.inner_text()).strip()
        m = re.search(r"\d+", tot_text)
        return int(cur), int(m.group(0)) if m else 1
    except Exception:
        return 1, 1


# ── Per-search execution ──────────────────────────────────────────────


async def _run_nc_search(
    page: Page,
    search: NCSavedSearch,
    days: int,
    seen_ids: dict[str, str] | None,
    on_page_batch=None,
    max_notices: int = 0,
    llm_api_key: str | None = None,
) -> list[NoticeData]:
    """Execute one NCSavedSearch end-to-end. Returns parsed NoticeData list."""
    label = f"{search.county}/{search.notice_type}"
    logger.info("Running NC search: %s (last %d days)", label, days)

    if not await _navigate_to_search(page):
        return []
    await _set_date_range(page, days)

    if search.category:
        await _select_category(page, search.category)
        await _delay()
    if search.keyword:
        await _fill_keyword(page, search.keyword, search.match_type)
        await _delay()

    if not await _check_county(page, search.county):
        return []

    if not await _submit_search(page):
        logger.error("  %s: search submission failed", label)
        return []

    await _set_per_page_50(page)

    notices: list[NoticeData] = []
    current, total = await _get_page_info(page)
    logger.info("  %s: %d page(s) of results", label, total)

    while True:
        logger.info("  %s: scraping page %d/%d", label, current, total)
        page_notices = await _scrape_results_page(
            page, search, seen_ids, llm_api_key,
        )
        notices.extend(page_notices)

        if on_page_batch and page_notices:
            try:
                await on_page_batch(page_notices)
            except Exception:
                logger.exception("on_page_batch callback failed")

        if max_notices and len(notices) >= max_notices:
            logger.info("  %s: reached max_notices=%d, stopping", label, max_notices)
            return notices[:max_notices]

        if current >= total:
            break

        # Advance to next page
        next_btn = await page.query_selector(NC_SEL_NEXT_PAGE)
        disabled = False
        if next_btn:
            disabled_attr = await next_btn.get_attribute("disabled")
            disabled = disabled_attr is not None
        if not next_btn or disabled:
            break
        try:
            await next_btn.click()
            await page.wait_for_load_state("networkidle", timeout=20_000)
            await _delay()
        except Exception:
            logger.exception("  %s: failed to advance to next page", label)
            break
        current, total = await _get_page_info(page)

    logger.info("  %s: scraped %d notice(s)", label, len(notices))
    return notices


async def _scrape_results_page(
    page: Page,
    search: NCSavedSearch,
    seen_ids: dict[str, str] | None,
    llm_api_key: str | None,
) -> list[NoticeData]:
    """Click each View button on the current results page → parse → back."""
    notices: list[NoticeData] = []

    try:
        await page.wait_for_selector(NC_SEL_VIEW_BUTTON_PATTERN, state="attached", timeout=20_000)
    except PwTimeout:
        logger.warning("  %s/%s: no View buttons on this page",
                       search.county, search.notice_type)
        return notices

    view_buttons = await page.query_selector_all(NC_SEL_VIEW_BUTTON_PATTERN)
    total = len(view_buttons)
    logger.info("  %d result(s) on this page", total)

    for idx in range(total):
        # Re-query after each back-navigation
        view_buttons = await page.query_selector_all(NC_SEL_VIEW_BUTTON_PATTERN)
        if idx >= len(view_buttons):
            logger.warning("  Button index %d out of range (%d buttons)", idx, len(view_buttons))
            break

        btn = view_buttons[idx]

        # Cross-run dedup short-circuit: parse the ID out of onclick
        # ("location.href='Details.aspx?SID=...&ID=NNN'") so we can skip
        # detail navigation entirely for already-seen notices.
        onclick = await btn.get_attribute("onclick") or ""
        m = re.search(r"ID=(\d+)", onclick)
        if seen_ids is not None and m and m.group(1) in seen_ids:
            logger.debug("  Skipping already-seen notice ID=%s", m.group(1))
            continue

        try:
            await btn.click()
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except PwTimeout:
            logger.warning("  View click timed out for idx=%d", idx)
            await _safe_back(page)
            continue
        except Exception:
            logger.exception("  View click failed for idx=%d", idx)
            await _safe_back(page)
            continue

        try:
            notice = await parse_nc_notice_page(
                page, search.county, search.notice_type, llm_api_key,
            )
        except Exception:
            logger.exception("  Parse failed at idx=%d", idx)
            await _safe_back(page)
            continue

        nid = _notice_id_from_url(notice.source_url)
        if seen_ids is not None and nid:
            seen_ids[nid] = notice.date_added or datetime.now().strftime("%Y-%m-%d")

        if not is_valid_foreclosure(notice):
            logger.debug("  Filtered (not first-to-market foreclosure): %s", notice.source_url)
        elif not _county_matches(notice, search):
            logger.debug(
                "  Filtered (wrong county: body=%s vs search=%s)",
                notice.county, search.county,
            )
        else:
            notices.append(notice)

        await _safe_back(page)
        await _delay()

    return notices


def _county_matches(notice: NoticeData, search: NCSavedSearch) -> bool:
    """Reject notices where the body clearly names a different NC county.

    If the parser couldn't extract a body county (blank), keep the notice
    (benefit of the doubt). Otherwise both must agree case-insensitively.
    """
    if not notice.county.strip():
        return True
    return notice.county.strip().lower() == search.county.strip().lower()


async def _safe_back(page: Page) -> None:
    """Navigate back to the results page; tolerate any error."""
    try:
        await page.go_back()
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        logger.debug("Back-navigation failed", exc_info=True)


# ── State helpers ─────────────────────────────────────────────────────


def load_nc_last_run_date() -> str | None:
    data = config.load_state(NC_STATE_FILE)
    return data.get("last_run_date")


def save_nc_last_run_date() -> None:
    config.save_state(NC_STATE_FILE, {"last_run_date": datetime.now().strftime("%Y-%m-%d")})


def load_nc_seen_ids() -> dict[str, str]:
    data = config.load_state(NC_SEEN_IDS_FILE)
    if not data:
        return {}
    cutoff = (datetime.now() - timedelta(days=SEEN_IDS_PRUNE_DAYS)).strftime("%Y-%m-%d")
    pruned = {nid: d for nid, d in data.items() if d >= cutoff}
    if len(pruned) < len(data):
        logger.info("Pruned %d NC seen IDs older than %d days",
                    len(data) - len(pruned), SEEN_IDS_PRUNE_DAYS)
    return pruned


def save_nc_seen_ids(seen: dict[str, str]) -> None:
    config.save_state(NC_SEEN_IDS_FILE, seen)


# ── Public entry point ───────────────────────────────────────────────


async def scrape_nc_all(
    mode: str = "daily",
    searches: list[NCSavedSearch] | None = None,
    proxy_url: str | None = None,
    on_batch=None,
    since_date_override: str | None = None,
    llm_api_key: str | None = None,
    max_notices: int = 0,
    seen_ids: dict[str, str] | None = None,
) -> list[NoticeData]:
    """Run all configured NC searches and return aggregated NoticeData.

    Args:
        mode: "daily" (only since last run) or "historical" (last 365 days).
        searches: Subset of NC_SAVED_SEARCHES to run. Defaults to all.
        proxy_url: Optional residential proxy.
        on_batch: Optional async callback(list[NoticeData]) per page.
        since_date_override: YYYY-MM-DD to override daily/historical window.
        llm_api_key: Anthropic key for LLM fallback parsing.
        max_notices: Stop after this many notices (0 = no limit).
        seen_ids: Cross-run dedup cache. If None, loaded from NC_SEEN_IDS_FILE.
    """
    if searches is None:
        searches = NC_SAVED_SEARCHES

    if seen_ids is None:
        seen_ids = load_nc_seen_ids()
    logger.info("NC cross-run dedup: %d previously-seen notice IDs", len(seen_ids))

    # Decide how many days back to fetch
    days = _days_window(mode, since_date_override)
    logger.info("NC scrape window: last %d day(s)", days)

    all_notices: list[NoticeData] = []
    async with async_playwright() as pw:
        launch_opts: dict = {"headless": True}
        if proxy_url:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            proxy_cfg: dict = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                proxy_cfg["username"] = parsed.username
            if parsed.password:
                proxy_cfg["password"] = parsed.password
            launch_opts["proxy"] = proxy_cfg
            logger.info("NC scraper using proxy: %s:%s", parsed.hostname, parsed.port)

        browser = await pw.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        context.set_default_timeout(60_000)
        page = await context.new_page()

        for search in searches:
            remaining = (max_notices - len(all_notices)) if max_notices else 0
            try:
                results = await _run_nc_search(
                    page, search, days,
                    seen_ids=seen_ids,
                    on_page_batch=on_batch,
                    max_notices=remaining,
                    llm_api_key=llm_api_key,
                )
                all_notices.extend(results)
            except Exception:
                logger.exception("NC search failed: %s/%s", search.county, search.notice_type)

            # Incremental persistence — survive a later crash
            try:
                save_nc_seen_ids(seen_ids)
            except Exception:
                logger.exception("Failed to persist NC seen_ids after %s/%s",
                                 search.county, search.notice_type)

            if max_notices and len(all_notices) >= max_notices:
                logger.info("Reached max_notices=%d, stopping", max_notices)
                break

        await browser.close()

    if mode == "daily":
        save_nc_last_run_date()
    save_nc_seen_ids(seen_ids)

    logger.info("NC total notices scraped: %d", len(all_notices))
    return all_notices


def _days_window(mode: str, since_date_override: str | None) -> int:
    """Translate mode/override into a 'last N days' value for the site form."""
    if since_date_override:
        try:
            dt = datetime.strptime(since_date_override, "%Y-%m-%d")
            return max(1, (datetime.now() - dt).days)
        except ValueError:
            logger.warning("Bad since_date_override '%s' — falling back to mode default",
                           since_date_override)

    if mode == "historical":
        return 365

    # Daily — use stored last-run date if present, default to 7-day window
    last = load_nc_last_run_date()
    if last:
        try:
            dt = datetime.strptime(last, "%Y-%m-%d")
            return max(1, (datetime.now() - dt).days + 1)  # +1 to include same-day races
        except ValueError:
            pass
    return 7
