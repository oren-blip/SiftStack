"""NC eCourts Smart Search scraper for probate (Estates) + foreclosure (SP) cases.

Source: https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29 (Odyssey —
the statewide NC court portal from Tyler Technologies, rolled out Oct 2025 to
all 100 counties).

The portal is gated by an AWS WAF "Human Verification" challenge that we
solve via CapSolver (see aws_waf_solver.py). The voucher is the value of
the `aws-waf-token` cookie. Once set on `.tylertech.cloud`, the cookie
typically remains valid for several hours, so we persist it to disk and
only re-solve when expired.

Smart Search form fields (post-WAF):
  - caseCriteria.CaseType_input    → "Estates" / "Special Proceedings (non-confidential)"
  - caseCriteria.FileDateStart     → MM/DD/YYYY
  - caseCriteria.FileDateEnd       → MM/DD/YYYY
  - .smartsearch-location-checkbox → 100 NC counties (all checked by default)
  - #btnSSSubmit                   → submit

Notice that probate cases in eCourts give us decedent name + PR + filing
date + case number, but NOT the full notice body (that's published in the
local newspaper). For our pipeline this is enough — the obituary +
property-lookup enrichers run from decedent name alone.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PwTimeout,
    async_playwright,
)

import config
from aws_waf_solver import WAFSolveError, solve_aws_waf
from ecourts_case_api import CaseDetailClient, extract_case_id
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


PORTAL_URL = "https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29"
SMART_SEARCH_URL = f"{PORTAL_URL}#SmartSearchSS"


# Case type combobox values (from Kendo combobox dataSource — see recon)
CASE_TYPE_BY_NOTICE_TYPE: dict[str, str] = {
    "probate": "Estates",
    "foreclosure": "Special Proceedings (non-confidential)",
}

# NC case-number format: <YY><TYPE><SEQ>-<COUNTY>
# Estates cases use "E", Special Proceedings use "SP".
# The Search Criteria field accepts wildcards via "*", so a pattern like
# "26E00*" returns every Estates case filed in 2026 with sequence ≥ 000.
CASE_NUMBER_PREFIX: dict[str, str] = {
    "probate":     "E00",   # Estates
    "foreclosure": "SP",    # Special Proceedings
}


def _search_criteria_for(notice_type: str, year: int) -> str:
    """Build a wildcard search-criteria string for the requested type + year.

    Per operator's manual workflow: '26E00*' returns all 2026 Estates cases.
    '26SP*' returns all 2026 Special Proceedings cases.
    """
    yy = f"{year % 100:02d}"
    prefix = CASE_NUMBER_PREFIX.get(notice_type, "")
    return f"{yy}{prefix}*"


def _state_file() -> Path:
    return config.PROJECT_ROOT / "ecourts_last_run.json"


def _waf_cookies_file() -> Path:
    return config.PROJECT_ROOT / "ecourts_waf_cookies.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "ecourts_seen_ids.json"


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


# ── WAF cookie persistence ────────────────────────────────────────────


def _load_cached_waf_cookie() -> dict | None:
    """Load the cached aws-waf-token cookie. Returns None if missing/expired."""
    data = config.load_state(_waf_cookies_file())
    if not data:
        return None
    saved_at = data.get("saved_at")
    if not saved_at:
        return None
    try:
        age = datetime.now() - datetime.fromisoformat(saved_at)
    except Exception:
        return None
    # WAF cookies typically last hours but no guarantee; treat 4h as safe TTL
    if age > timedelta(hours=4):
        logger.info("eCourts: cached WAF cookie is %s old — discarding", age)
        return None
    return data


def _save_waf_cookie(cookie_value: str, user_agent: str) -> None:
    config.save_state(_waf_cookies_file(), {
        "saved_at": datetime.now().isoformat(),
        "aws_waf_token": cookie_value,
        "user_agent": user_agent,
    })


# ── WAF gate handling ─────────────────────────────────────────────────


async def _is_waf_gate(page: Page) -> bool:
    """Return True if we're stuck on the AWS WAF 'Human Verification' page."""
    try:
        title = await page.title()
    except Exception:
        return True
    if "Human Verification" in title:
        return True
    # Sometimes the title is empty during reload — also probe for gokuProps
    try:
        has_props = await page.evaluate(
            "() => typeof window.gokuProps === 'object'"
        )
        return bool(has_props)
    except Exception:
        return False


async def _solve_and_inject_waf(
    browser,
    initial_ctx: BrowserContext,
    initial_page: Page,
) -> tuple[BrowserContext, Page]:
    """Solve the WAF and return (fresh_ctx, fresh_page) past the gate.

    Builds a fresh context with the matching UA + pre-seeded cookie and
    closes the original — that's the pattern proven during recon.
    """
    if not config.CAPSOLVER_API_KEY:
        raise WAFSolveError("CAPSOLVER_API_KEY not set")

    props = await initial_page.evaluate(
        "() => (typeof window.gokuProps === 'object' && window.gokuProps) || null"
    )
    if not props:
        raise WAFSolveError("window.gokuProps not present on WAF page")

    logger.info("eCourts: solving AWS WAF via CapSolver")
    result = solve_aws_waf(
        api_key=config.CAPSOLVER_API_KEY,
        site_url=initial_page.url,
        aws_key=props["key"],
        aws_iv=props["iv"],
        aws_context=props["context"],
        timeout=180,
    )
    voucher = result["voucher"]
    ua = result["userAgent"] or _DEFAULT_UA
    _save_waf_cookie(voucher, ua)

    # Rebuild context with matching UA + pre-seeded cookie
    await initial_ctx.close()
    new_ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=ua)
    await new_ctx.add_cookies([{
        "name": "aws-waf-token",
        "value": voucher,
        "domain": ".tylertech.cloud",
        "path": "/",
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }])
    new_ctx.set_default_timeout(60_000)
    new_page = await new_ctx.new_page()
    await new_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=45_000)
    await new_page.wait_for_timeout(2500)
    if await _is_waf_gate(new_page):
        raise WAFSolveError("voucher accepted but still showing WAF gate after reload")
    logger.info("eCourts: past WAF gate")
    return new_ctx, new_page


_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ── Smart Search form driving ────────────────────────────────────────


async def _navigate_to_smart_search(page: Page) -> None:
    """Click the Smart Search link / tile on the dashboard."""
    # The dashboard renders Smart Search at #SmartSearchSS — direct nav works
    if "SmartSearchSS" not in page.url:
        await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(2500)
    # Wait for the search form to appear
    try:
        await page.wait_for_selector("#btnSSSubmit", state="attached", timeout=20_000)
    except PwTimeout:
        logger.warning("eCourts: Smart Search submit button never rendered")
        raise


async def _open_advanced_filters(page: Page) -> None:
    """Click the toggle that reveals CaseType / dates / county filters."""
    # The advanced options toggle has id 'caseCriteria_AdvancedSearchOptionsOpen'
    try:
        toggle = page.locator("#caseCriteria_AdvancedSearchOptionsOpen").first
        if await toggle.count() > 0:
            # Check if already open — if so the click would close it
            try:
                aria_expanded = await toggle.get_attribute("aria-expanded")
            except Exception:
                aria_expanded = None
            if aria_expanded != "true":
                try:
                    await toggle.click(timeout=5_000)
                except Exception:
                    await toggle.evaluate("el => el.click()")
                await page.wait_for_timeout(800)
    except Exception:
        logger.debug("eCourts: advanced filter toggle not found / already open", exc_info=True)


async def _set_case_type(page: Page, value: str) -> None:
    """Pick a value in the Kendo CaseType combobox."""
    # Method 1: set the underlying input via Kendo data widget API
    try:
        ok = await page.evaluate(
            """(value) => {
                if (window.jQuery && window.jQuery('#caseCriteria_CaseType').data('kendoComboBox')) {
                    const w = window.jQuery('#caseCriteria_CaseType').data('kendoComboBox');
                    w.value(value);
                    w.trigger('change');
                    return true;
                }
                return false;
            }""",
            value,
        )
        if ok:
            return
    except Exception:
        pass
    # Method 2: type into the visible Kendo input
    try:
        loc = page.locator("input[name='caseCriteria.CaseType_input']").first
        await loc.click(timeout=5_000)
        await loc.fill("")
        await loc.type(value, delay=30)
        await page.wait_for_timeout(500)
        # Press Enter to commit
        await loc.press("Enter")
    except Exception:
        logger.exception("eCourts: failed to set case type %r", value)
        raise


async def _set_case_status(page: Page, value: str) -> None:
    """Pick a value in the Kendo CaseStatus combobox/dropdown.

    This is Odyssey's server-side status filter ("Filter by Case Status"
    under Advanced Filtering Options → Case Search Criteria). Setting
    it to "Pending" makes Odyssey return only active cases — way more
    reliable than scanning grid cells client-side for status strings
    (which misses any label variant we haven't hardcoded).

    Mirrors _set_case_type's two-method approach: Kendo widget API first,
    fall back to typing into the visible input.
    """
    try:
        ok = await page.evaluate(
            """(value) => {
                if (!window.jQuery) return false;
                const $el = window.jQuery('#caseCriteria_CaseStatus');
                if (!$el.length) return false;
                // Could be a ComboBox or a DropDownList depending on Odyssey build
                const w = $el.data('kendoComboBox') || $el.data('kendoDropDownList');
                if (!w) return false;
                w.value(value);
                w.trigger('change');
                return true;
            }""",
            value,
        )
        if ok:
            return
    except Exception:
        pass
    # Method 2: type into the visible Kendo input
    try:
        loc = page.locator("input[name='caseCriteria.CaseStatus_input']").first
        await loc.click(timeout=5_000)
        await loc.fill("")
        await loc.type(value, delay=30)
        await page.wait_for_timeout(500)
        await loc.press("Enter")
    except Exception:
        logger.exception("eCourts: failed to set case status %r", value)
        raise


async def _set_date_range(page: Page, start: str, end: str) -> None:
    """Set the file-date range via direct JS value + change event.

    The Odyssey datepickers wrap the raw input with a custom widget that
    leaves the underlying <input> with zero offsetSize → Playwright treats
    it as 'not visible' and refuses to click/fill. Going around it with
    native JS is the reliable path.
    """
    ok = await page.evaluate(
        """({start, end}) => {
            const set = (id, val) => {
                const el = document.getElementById(id);
                if (!el) return false;
                el.value = val;
                el.dispatchEvent(new Event('input',  {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                if (window.jQuery) {
                    try { window.jQuery(el).trigger('change').blur(); } catch (e) {}
                }
                return true;
            };
            const a = set('caseCriteria.FileDateStart', start);
            const b = set('caseCriteria.FileDateEnd',   end);
            return a && b;
        }""",
        {"start": start, "end": end},
    )
    if not ok:
        raise RuntimeError("eCourts: date inputs not found in DOM")


async def _select_only_county(page: Page, county: str) -> None:
    """Uncheck all county checkboxes except the target.

    `county` is the bare name without ' County' suffix (e.g. 'Mecklenburg').
    """
    target = f"{county} County".strip().lower()
    await page.evaluate(
        """(target) => {
            const boxes = document.querySelectorAll('input.smartsearch-location-checkbox');
            boxes.forEach(b => {
                const val = (b.value || '').toLowerCase();
                const want = val === target;
                if (b.checked !== want) {
                    b.click();
                }
            });
        }""",
        target,
    )
    await page.wait_for_timeout(300)


async def _set_search_criteria(page: Page, value: str) -> None:
    """Fill the main 'Search Criteria' textbox.

    eCourts requires a non-empty value here even when filtering by date + county.
    A single letter passes validation and behaves as a name-substring filter,
    so 'a' returns most cases (since most people have an 'a' somewhere in name).
    """
    await page.evaluate(
        """(value) => {
            const el = document.getElementById('caseCriteria_SearchCriteria');
            if (!el) return false;
            el.value = value;
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }""",
        value,
    )


async def _submit_search(page: Page) -> bool:
    """Click Submit, wait for results grid to populate (AJAX after page nav).

    The button triggers a same-page navigation to /Portal/Home/WorkspaceMode,
    which then AJAX-loads the result grid. We wait for the grid container
    OR a 'no results' / error message to appear.
    """
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=45_000):
            await page.click("#btnSSSubmit", timeout=10_000)
    except PwTimeout:
        # Submit might be AJAX — give it a beat
        await page.wait_for_timeout(2000)
    except Exception:
        logger.exception("eCourts: submit click failed")
        return False

    # Wait for the result grid to render (AJAX after navigation)
    grid_selectors = [
        ".k-grid-table tbody tr",
        ".k-grid",
        "table[id*='Grid']",
        "#grdSearchResults",
        "text=/no\\s+(records|results|matches)/i",
        "text=/error/i",
    ]
    grid_ready = False
    for _ in range(20):  # up to ~20 seconds
        await page.wait_for_timeout(1000)
        for sel in grid_selectors:
            try:
                if await page.locator(sel).first.count() > 0:
                    grid_ready = True
                    break
            except Exception:
                pass
        if grid_ready:
            break
    if not grid_ready:
        # Fall back: give it networkidle one more time
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PwTimeout:
            pass

    # Bump the Kendo "items per page" dropdown to its max value so we get
    # all results in one go instead of the default 10. The pager has a
    # <select class="k-dropdown ...> with options like 10/20/50/100.
    try:
        await _maximize_page_size(page)
    except Exception:
        logger.debug("eCourts: page-size bump failed (continuing with default)", exc_info=True)

    return True


async def _maximize_page_size(page: Page) -> None:
    """Switch the Kendo grid pager to its largest items-per-page value.

    The pager renders a styled select with options like 10/20/50/100.
    We find the max numeric option and pick it via the Kendo widget API.
    """
    max_n = await page.evaluate(
        """() => {
            // Find the kendo dropdown inside the pager
            const select = document.querySelector('.k-pager-sizes select, .k-pager-info ~ * select, select[name="PageSize"]')
                || Array.from(document.querySelectorAll('select')).find(s => {
                    const opts = Array.from(s.options || []).map(o => o.value);
                    return opts.some(v => /^\\d+$/.test(v));
                });
            if (!select) return 0;
            const opts = Array.from(select.options || [])
                .map(o => parseInt(o.value || '', 10))
                .filter(n => !isNaN(n));
            if (!opts.length) return 0;
            const maxv = Math.max(...opts);
            // Set via Kendo widget if present, else native + dispatch change
            if (window.jQuery) {
                try {
                    const w = window.jQuery(select).data('kendoDropDownList');
                    if (w) { w.value(String(maxv)); w.trigger('change'); return maxv; }
                } catch (e) {}
            }
            select.value = String(maxv);
            select.dispatchEvent(new Event('change', {bubbles: true}));
            return maxv;
        }"""
    )
    if max_n and max_n > 10:
        logger.info("eCourts: bumped page size to %d", max_n)
        # Wait for the grid to re-render with the bigger page
        await page.wait_for_timeout(2500)


# ── Results parsing ───────────────────────────────────────────────────


# Result row pattern in the eCourts results table:
#   <tr> ... <td>case number link</td> <td>filing date</td> <td>parties</td> ...
# We extract via DOM query (selectors observed during smoke testing).
async def _extract_rows_from_grid(page: Page) -> list[dict]:
    """Extract the current visible Kendo grid rows into [{cells, data_url, ...}]."""
    return await page.evaluate(
        """() => {
            const rows = [];
            // Try a sequence of selectors — most specific first
            const selectors = [
                '.k-grid-content tbody tr',
                '.k-grid-table tbody tr',
                'table.k-selectable tbody tr',
                '[role="grid"] tbody tr',
                '.k-grid tbody tr',
                'table[id*="Grid"] tbody tr',
                '#grdSearchResults tbody tr',
                // Last resort — any table row that has any tds
                'table tbody tr',
            ];
            let trs = [];
            for (const sel of selectors) {
                trs = Array.from(document.querySelectorAll(sel)).filter(
                    tr => tr.querySelectorAll('td').length > 0
                );
                if (trs.length > 0) break;
            }
            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim());
                // The actual case link is `a.caseLink`; other anchors in
                // the row are hidden Kendo expand/collapse icons.
                const caseAnchor = tr.querySelector('a.caseLink') || tr.querySelector('a[href]');
                const dataUrl = caseAnchor ? (caseAnchor.getAttribute('data-url') || '') : '';
                rows.push({
                    cells,
                    href: caseAnchor ? caseAnchor.href : null,
                    data_url: dataUrl,
                    text: tr.innerText.trim().slice(0, 500),
                });
            }
            return rows;
        }"""
    )


async def _click_next_page(page: Page) -> bool:
    """Try to advance the Kendo grid to the next page. Returns True if it did.

    Odyssey's pager renders next-page as `<a class="k-link"><span class="k-icon k-i-arrow-e">`.
    Disabled state adds `k-state-disabled` on the anchor.
    """
    return await page.evaluate(
        """() => {
            // Find all anchors that contain a 'next page' icon (arrow-e or arrow-60-right)
            const links = Array.from(document.querySelectorAll('a.k-link'));
            for (const a of links) {
                const icon = a.querySelector('.k-i-arrow-e, .k-i-arrow-60-right, .k-i-chevron-right');
                if (!icon) continue;
                if (a.classList.contains('k-state-disabled') || a.classList.contains('k-disabled')) continue;
                // Found the active 'next page' button
                a.click();
                return true;
            }
            return false;
        }"""
    )


# ── Estates Case Status / Case Type classification ────────────────────
# County clerks label a FINISHED estate differently: Mecklenburg + Catawba
# use "Closed"; the other 5 counties use "Disposed - Clerk of Superior
# Court". So statuses MUST be matched by PREFIX, never exact equality — a
# 2026-06-27 live recon of all 7 counties found ~280 "Disposed - Clerk..."
# rows silently leaking past the old exact-match drop set. The Estates
# status vocabulary is tiny (Pending / Closed / Disposed-variant / rare
# "Active Reopened"); see the project_ecourts_estate_status_vocab memory.
_FINISHED_STATUS_PREFIXES = (
    "DISPOSED", "CLOSED", "INACTIVE", "ARCHIVED",
    "ADMINISTRATIVE CLOSURE",
    "TRANSFER",  # "Transfer to Another County" — case left this county
)
# "Active Reopened" starts with ACTIVE; handled as reopened (priority) first.
_ACTIVE_STATUS_PREFIXES = ("PENDING", "ACTIVE", "OPEN", "FILED", "RECEIVED")

# Case Type column values (Estates category). Only "Decedents' Estate"
# rows are real probate leads. Guardianship + minor/incapacitated-funds
# cases are LIVING persons filed under Estates — never a death lead.
_NON_DECEDENT_TYPE_RE = re.compile(
    r"GUARDIANSHIP|FUNDS\s+DEPOSITED|\bMINOR\b|\bINCAPACITATED\b|CONSERVATOR", re.I)
_SMALL_ESTATE_TYPE_RE = re.compile(r"SMALL\s+ESTATE", re.I)
_DECEDENT_ESTATE_TYPE_RE = re.compile(r"DECEDENT", re.I)

# Legacy exact-match sets — kept only for the _parse_results telemetry
# counter and external importers (dump_estate_statuses.py). The keep/drop
# DECISION now flows through _classify_estate_row below, not these.
_DROP_CASE_STATUSES = {"DISPOSED", "CLOSED", "INACTIVE", "TRANSFERRED"}
_KEEP_CASE_STATUSES = {"PENDING", "ACTIVE", "OPEN", "REOPENED"}
_KNOWN_CASE_STATUSES = _DROP_CASE_STATUSES | _KEEP_CASE_STATUSES

# Fallback window (days) used ONLY when the Case Type column is unreadable.
# Small Estate Affidavits are Filed and Disposed the same day; a Disposed
# row filed within this window is almost certainly a Small Estate (regular
# full-administration probate takes months to Dispose). With the Type
# column now captured, this is a safety net rather than the primary signal.
SMALL_ESTATE_RECENT_DAYS = 14


def _status_is_finished(status: str) -> bool:
    s = status.strip().upper()
    return any(s.startswith(p) for p in _FINISHED_STATUS_PREFIXES)


def _status_is_active(status: str) -> bool:
    s = status.strip().upper()
    return any(s.startswith(p) for p in _ACTIVE_STATUS_PREFIXES)


def _filed_within(filing_date: str, days: int) -> bool:
    if not filing_date:
        return False
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(filing_date, fmt).date()
            return 0 <= (date.today() - d).days <= days
        except ValueError:
            continue
    return False


def _classify_estate_row(case_type: str, status: str, filing_date: str) -> tuple[str, str]:
    """Decide keep/drop for an Estates grid row from its Case Type + Status.

    Returns (action, tag): action is "keep" or "drop"; tag is an optional
    marker ("priority-reopened" / "small-estate" / a drop-reason) for logs.

    Policy (Oren 2026-06-27, verified against live portal vocabulary):
      • Guardianship / minor-funds TYPE      → DROP (living person, not a death lead)
      • Reopened estate                      → KEEP (priority — new asset surfaced)
      • Active / Pending status              → KEEP (active probate = prime lead)
      • Finished (Disposed*/Closed/Transfer) → KEEP Small Estate (heir owns it now),
                                               DROP Full Administration (probate over,
                                               freshness gone, often sold during admin).
                                               Type unreadable → SMALL_ESTATE_RECENT_DAYS
                                               file-date fallback.
      • Blank / unknown status               → KEEP (never silently drop)
    """
    t = (case_type or "").upper()
    s = (status or "").upper()

    if t and _NON_DECEDENT_TYPE_RE.search(t):
        return "drop", "non-decedent-type"
    if "REOPENED" in s:                 # "Active Reopened"
        return "keep", "priority-reopened"
    if _status_is_active(s):
        return "keep", ""
    if _status_is_finished(s):
        if _SMALL_ESTATE_TYPE_RE.search(t):
            return "keep", "small-estate"
        if _DECEDENT_ESTATE_TYPE_RE.search(t):
            return "drop", "finished-full-admin"
        # Type column unreadable — fall back to the file-date heuristic.
        if _filed_within(filing_date, SMALL_ESTATE_RECENT_DAYS):
            return "keep", "small-estate"
        return "drop", "finished-unknown-type"
    return "keep", ""


def _row_to_notice(row: dict, county: str, notice_type: str) -> NoticeData | None:
    """Convert one raw grid row dict into a NoticeData, or None if not a real result row.

    Keep/drop is decided by _classify_estate_row from the grid's Case Type +
    Case Status columns: keep active probate + all Small Estate filings (heir
    owns the property now); drop finished Full Administration estates,
    guardianships, and minor/incapacitated-funds cases. Status is matched by
    prefix so county label variants ("Closed" vs "Disposed - Clerk of Superior
    Court") are handled uniformly.
    """
    cells = row.get("cells", [])
    if not cells:
        return None

    case_no_re = re.compile(r"\d{2}[A-Z]{1,3}\d{3,6}-?\d{0,3}")
    # Find the cell that contains the case number (not always cells[0]
    # due to checkbox column + occasional layout variations)
    case_no = ""
    case_no_idx = -1
    for i, c in enumerate(cells):
        c2 = c.strip().replace(" ", "")
        if c2 and case_no_re.fullmatch(c2):
            case_no = c2
            case_no_idx = i
            break
    if not case_no:
        return None  # interleaved empty row / non-data row

    style = cells[case_no_idx + 1].strip() if case_no_idx + 1 < len(cells) else ""

    filing_date = ""
    for c in cells:
        m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", c)
        if m:
            filing_date = m.group(1)
            break

    # Detect Case Type + Case Status by cell content. Column order varies
    # slightly by county, so match on content rather than fixed offsets.
    # Skip the case-number cell and the caption cell (case_no_idx + 1) — the
    # caption is free text and could contain words like "MINOR" that would
    # spuriously trip the non-decedent type regex.
    detected_type = ""
    detected_status = ""
    for j, c in enumerate(cells):
        if j == case_no_idx or j == case_no_idx + 1:
            continue
        cc = c.strip()
        if not cc:
            continue
        if not detected_type and (
            _SMALL_ESTATE_TYPE_RE.search(cc)
            or _DECEDENT_ESTATE_TYPE_RE.search(cc)
            or _NON_DECEDENT_TYPE_RE.search(cc)
        ):
            detected_type = cc
            continue
        if not detected_status and (
            _status_is_active(cc) or _status_is_finished(cc) or "REOPENED" in cc.upper()
        ):
            detected_status = cc

    action, classify_tag = _classify_estate_row(detected_type, detected_status, filing_date)
    if action == "drop":
        logger.debug(
            "eCourts: dropping %s type=%r status=%r (%s)",
            case_no, detected_type, detected_status, classify_tag,
        )
        return None
    if classify_tag == "priority-reopened":
        logger.info("eCourts: KEEPING reopened estate (priority): %s", case_no)
    elif classify_tag == "small-estate" and _status_is_finished(detected_status):
        logger.info(
            "eCourts: KEEPING Small Estate (heir owns it now): %s filed=%s",
            case_no, filing_date,
        )

    primary_name = style
    for prefix in [
        r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+ESTATE\s+OF\s+",
        r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+GUARDIANSHIP\s+OF\s+",
        r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+TRUST\s+OF\s+",
        # Generic "IN THE MATTER OF <name>" — must come AFTER the more-specific
        # patterns above so they get a chance to strip the "THE X OF" portion.
        # Trailing \s* (not \s+) handles captions with no name (just "IN THE MATTER OF").
        r"^IN\s+THE\s+MATTER\s+OF\s*",
        r"^IN\s+RE:?\s*ESTATE\s+OF\s+",
        r"^IN\s+RE:?\s+",
        r"^ESTATE\s+OF\s+",
        r"^GUARDIANSHIP\s+OF\s+",
    ]:
        primary_name = re.sub(prefix, "", primary_name, flags=re.IGNORECASE)
    primary_name = re.split(r"\s+vs?\.\s+", primary_name, maxsplit=1, flags=re.IGNORECASE)[0]
    primary_name = primary_name.strip().rstrip(",.")

    date_added = filing_date
    if filing_date:
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                date_added = datetime.strptime(filing_date, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

    href = row.get("href") or ""
    if not href or href.endswith("#"):
        href = f"{PORTAL_URL}#case={case_no}"

    data_url = row.get("data_url") or ""
    case_id_hex = extract_case_id(data_url)

    notice = NoticeData(
        county=county,
        state="NC",
        notice_type=notice_type,
        date_added=date_added,
        raw_text=row.get("text", ""),
        source_url=href,
        case_number=case_no,
        case_status=detected_status,
        case_type=detected_type,
    )
    notice._roa_id = case_id_hex  # type: ignore[attr-defined]
    if notice_type == "probate":
        notice.decedent_name = primary_name
    else:
        notice.owner_name = primary_name
    return notice


async def _parse_results(page: Page, county: str, notice_type: str) -> list[NoticeData]:
    """Walk every page of the results grid and build a NoticeData list."""
    notices: list[NoticeData] = []
    seen_case_nos: set[str] = set()

    # Lightweight post-submit log so 0-result runs are diagnosable
    try:
        body = await page.inner_text("body")
        logger.info(
            "eCourts: post-submit — title=%r body_len=%d",
            await page.title(), len(body),
        )
    except Exception:
        pass

    # Walk pages — first page is already visible. After each parse, try
    # to click "next page". Stop when next is disabled or no new rows.
    case_no_re = re.compile(r"\d{2}[A-Z]{1,3}\d{3,6}-?\d{0,3}")
    dropped_status = 0
    for page_idx in range(1, 25):  # hard cap of 25 pages = up to 2500 results
        rows = await _extract_rows_from_grid(page)
        added_on_page = 0
        for row in rows:
            # A "real" case row carries a case number; if _row_to_notice
            # drops it, that's a policy drop (finished full-admin /
            # guardianship), not just an empty layout row.
            is_case_row = any(
                case_no_re.fullmatch(c.strip().replace(" ", "")) for c in row.get("cells", [])
            )
            n = _row_to_notice(row, county, notice_type)
            if not n:
                if is_case_row:
                    dropped_status += 1
                continue
            if n.case_number in seen_case_nos:
                continue
            seen_case_nos.add(n.case_number)
            notices.append(n)
            added_on_page += 1
        logger.info(
            "eCourts: page %d — %d raw rows, %d new notices (%d total, %d dropped-status)",
            page_idx, len(rows), added_on_page, len(notices), dropped_status,
        )
        if added_on_page == 0 and page_idx > 1:
            break  # next page returned no new rows — we're done
        clicked = await _click_next_page(page)
        if not clicked:
            break  # no next-page button (last page)
        await page.wait_for_timeout(1500)  # let the grid re-render

    logger.info("eCourts: %d total result(s) for %s/%s", len(notices), county, notice_type)
    return notices


def _enrich_with_parties(
    notices: list[NoticeData],
    *,
    waf_token: str,
    user_agent: str,
) -> None:
    """For each probate notice with a Register-of-Actions case id, fetch
    the Parties OData endpoint and populate executor + beneficiary fields.

    Mutates notices in place. Failures are logged and skipped (notice keeps
    only the search-results data — decedent + case#).
    """
    import json as _json
    import time as _time
    targets = [n for n in notices if getattr(n, "_roa_id", "") and n.notice_type == "probate"]
    if not targets:
        return
    logger.info("eCourts: enriching %d probate notice(s) via Parties API", len(targets))
    client = CaseDetailClient(waf_token=waf_token, user_agent=user_agent)
    enriched = 0
    guardianships: list[NoticeData] = []
    for i, n in enumerate(targets):
        if i > 0:
            _time.sleep(2.5)  # slow cadence to avoid Odyssey's HTTP 202 throttle
        case_hex = getattr(n, "_roa_id", "")
        detail = client.fetch_detail(case_hex)
        if not detail.parties:
            logger.debug("eCourts API: no parties for %s", n.case_number)
            continue
        # Guardianship cases (living incapacitated person, not a decedent)
        # are filed under Estates but aren't probate leads — flag for removal.
        if detail.is_guardianship:
            logger.info("eCourts: %s is a guardianship case — dropping from probate output", n.case_number)
            guardianships.append(n)
            continue

        # If the search-results decedent name was blank, garbage (failed
        # "IN THE MATTER" strip), or shorter than the canonical Parties
        # name, refresh from the canonical Parties data.
        dec = detail.decedent
        if dec:
            looks_bad = (
                not n.decedent_name
                or "IN THE MATTER" in n.decedent_name.upper()
                or len(n.decedent_name) < len(dec.full_name)
            )
            if looks_bad:
                n.decedent_name = dec.full_name
        else:
            # Parties came back but none matched _DECEDENT_TYPES. Surface
            # the actual connection types so we can extend the set.
            types_seen = sorted({p.connection_type for p in detail.parties if p.connection_type})
            logger.warning(
                "eCourts API: no decedent in parties for %s — caption-name %r kept; types seen: %s",
                n.case_number, n.decedent_name, types_seen,
            )

        ex = detail.executor
        if ex:
            n.executor_first_name = ex.first_name
            n.executor_last_name = ex.last_name
            # Populate the existing PR/contact mailing fields too so the
            # downstream pipeline (Smarty, skip trace, etc.) targets the
            # executor as the primary contact.
            n.owner_name = ex.full_name
            addr = ex.first_address
            if not addr.is_blank():
                n.owner_street = " ".join(filter(None, [addr.line1, addr.line2])).strip()
                n.owner_city = addr.city
                n.owner_state = addr.state
                n.owner_zip = addr.zip

        if detail.beneficiaries:
            ben_list = []
            for b in detail.beneficiaries:
                addr = b.first_address
                ben_list.append({
                    "name": b.full_name,
                    "street": " ".join(filter(None, [addr.line1, addr.line2])).strip(),
                    "city": addr.city,
                    "state": addr.state,
                    "zip": addr.zip,
                })
            n.beneficiaries_json = _json.dumps(ben_list, separators=(",", ":"))

        enriched += 1
    # Strip the guardianship cases from the live notice list
    if guardianships:
        ids_to_drop = {id(n) for n in guardianships}
        # Mutate in place so the caller's list reflects the filter
        notices[:] = [n for n in notices if id(n) not in ids_to_drop]
    logger.info(
        "eCourts: enriched %d/%d notice(s) with parties data; dropped %d guardianship(s)",
        enriched, len(targets), len(guardianships),
    )

    # NOTE: case-doc enrichment used to run here inline, sharing the same
    # WAF cookie used by Parties. But the ViewDocument endpoint requires a
    # fresher WAF cookie than Parties does — by the time Parties finishes
    # its 30+ minutes of work, the cookie is stale and ViewDocument returns
    # HTTP 602 "session invalid" for every fetch. Surfaced Week 26 audit:
    # 51 cases queued, 0 fetched.
    #
    # Case-doc enrichment now runs as a separate post-scrape step in
    # scrape_ecourts(), with a freshly-captured WAF cookie obtained via a
    # brief Playwright session immediately before the doc-fetch batch.


def _apply_will_data(notice: NoticeData, will: dict) -> None:
    """Populate notice.will_* fields from a parse_will() result dict."""
    import json as _json
    try:
        notice.will_data_json = _json.dumps(will, separators=(",", ":"))
    except Exception:
        notice.will_data_json = ""
    notice.will_testator_spouse = (will.get("testator_spouse") or "").strip()
    # Acting-PR pick: prefer the primary executor, unless the row's existing
    # executor name (from Parties API) matches an alternate — in which case
    # the primary predeceased and the alternate is acting.
    people = will.get("people") or []
    primary = next((p for p in people if p.get("role") == "primary_executor"), None)
    alternate = next((p for p in people if p.get("role") == "alternate_executor"), None)
    acting = primary
    if alternate:
        ex_last = (notice.executor_last_name or "").strip().upper()
        ex_first = (notice.executor_first_name or "").strip().upper()
        alt_name = (alternate.get("full_name") or "").upper()
        if ex_last and ex_last in alt_name and (not ex_first or ex_first in alt_name):
            acting = alternate
    if acting:
        notice.will_pr_full_name = (acting.get("full_name") or "").strip()
        notice.will_pr_relationship = (acting.get("relationship") or "").strip()


def _apply_application_data(notice: NoticeData, app: dict) -> None:
    """Populate notice.application_* fields from a parse_application() result dict."""
    import json as _json
    try:
        notice.application_data_json = _json.dumps(app, separators=(",", ":"))
    except Exception:
        notice.application_data_json = ""
    applicant = app.get("applicant") or {}
    notice.application_pr_full_name = (applicant.get("full_name") or "").strip()
    notice.application_pr_relationship = (applicant.get("relationship_to_decedent") or "").strip()
    notice.application_dod = (app.get("date_of_death") or "").strip()
    notice.application_attorney_name = (app.get("attorney_name") or "").strip()
    val = app.get("preliminary_estate_value_usd")
    if val is not None:
        try:
            notice.application_estate_value = f"{int(round(float(val))):,}"
        except (TypeError, ValueError):
            notice.application_estate_value = ""
    heirs = app.get("heirs") or []
    if heirs:
        try:
            notice.application_heirs_json = _json.dumps(heirs, separators=(",", ":"))
        except Exception:
            notice.application_heirs_json = ""


_DOC_APPLIERS = {
    "will": _apply_will_data,
    "application": _apply_application_data,
}


def _enrich_with_case_docs(notices: list[NoticeData], *, waf_token: str,
                            all_cookies: dict | None = None) -> int:
    """For each probate notice with a case_id, fetch + LLM-parse all
    registered doc types (will, application). On miss, add to pending
    queue for retry on subsequent daily runs. Mutates notice fields in
    place; persists case_id_hex onto the notice so polish can find the
    right row to update if a delayed PDF lands later.

    Returns count of notices where at least one doc type was successfully
    parsed (either fresh or from prior-run cache).
    """
    import time as _time
    try:
        import case_pdf_extractor  # triggers DocTypeSpec registration
        from case_pdf_extractor import fetch_and_parse_case_docs
        import case_doc_queue as cdq
        import config as cfg
    except Exception as e:
        logger.warning("Case-doc enrichment unavailable (%s) — skipping", e)
        return 0

    api_key = getattr(cfg, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.info("No ANTHROPIC_API_KEY — skipping case-doc enrichment")
        return 0

    doc_types = list(_DOC_APPLIERS.keys())
    enriched = 0
    for i, n in enumerate(notices):
        case_hex = getattr(n, "_roa_id", "")
        if not case_hex:
            continue
        # Persist case_id onto the notice so it survives to the CSV; the
        # queue keys off it for retries and polish keys off it for late
        # apply-back.
        n.case_id_hex = case_hex
        applied_any = False

        # First check the fetched cache — prior daily runs may have already
        # captured these docs. Apply without re-fetching (free).
        cached_types: list[str] = []
        for dt in doc_types:
            cached = cdq.get_fetched(case_hex, dt)
            if cached:
                applier = _DOC_APPLIERS[dt]
                applier(n, cached)
                cached_types.append(dt)
                applied_any = True
        # Doc types still needed
        still_needed = [dt for dt in doc_types if dt not in cached_types]
        if not still_needed:
            if applied_any:
                enriched += 1
            continue

        if i > 0 and not cached_types:
            _time.sleep(1.5)  # polite cadence on fresh fetches

        try:
            fetched = fetch_and_parse_case_docs(
                case_hex, waf_token=waf_token, doc_types=still_needed, api_key=api_key,
                all_cookies=all_cookies,
            )
        except Exception as e:
            logger.debug("Case-doc fetch failed for %s: %s", n.case_number, e)
            fetched = {dt: [] for dt in still_needed}

        misses: list[str] = []
        for dt in still_needed:
            results = fetched.get(dt) or []
            if not results:
                misses.append(dt)
                continue
            # Multiple matching docs (rare — codicil, amended application).
            # Take the first; cache + apply.
            parsed = results[0]
            cdq.record_fetched(case_hex, dt, parsed)
            cdq.mark_fetched(case_hex, dt)  # in case it was previously pending
            applier = _DOC_APPLIERS[dt]
            applier(n, parsed)
            applied_any = True
            logger.info("eCourts: %s -> %s extracted (%s)",
                        n.case_number, dt, parsed.get("_meta", {}).get("event_label", ""))

        # Queue any misses for retry on subsequent runs
        if misses:
            cdq.add_to_pending(
                case_hex,
                case_number=n.case_number,
                county=n.county,
                notice_type=n.notice_type,
                needed_doc_types=misses,
            )

        if applied_any:
            enriched += 1

    # Housekeeping: expire any stale queue entries past the retry window
    cdq.expire_old()

    summary = cdq.pending_summary()
    if summary["total_cases"]:
        logger.info("eCourts: pending case-docs queue = %d cases, by type: %s",
                    summary["total_cases"], summary["by_doc_type"])
    return enriched


def drain_pending_case_docs(*, waf_token: str, all_cookies: dict | None = None) -> int:
    """Standalone retry pass: walk the pending-doc queue and try to fetch
    each needed doc with the current WAF token. Independent of any active
    scrape — call this at the start of a daily run, before regular
    scraping, so newly-scraped cases benefit from prior-run cache hits.

    `all_cookies` (optional): full cookie jar from the Playwright session.
    api/ViewDocument needs ALB stickiness cookies in addition to
    aws-waf-token to be routed correctly — without them HTTP 602 fires.

    Returns count of doc fetches that succeeded this pass.
    """
    import time as _time
    try:
        import case_pdf_extractor  # triggers registration
        from case_pdf_extractor import fetch_and_parse_case_docs
        import case_doc_queue as cdq
        import config as cfg
    except Exception as e:
        logger.warning("Queue drain unavailable (%s) — skipping", e)
        return 0

    api_key = getattr(cfg, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return 0
    cdq.expire_old()
    pending = cdq.load_pending()
    if not pending:
        return 0
    logger.info("eCourts: draining pending-doc queue — %d case(s) to retry", len(pending))
    fetches = 0
    for i, (case_hex, entry) in enumerate(pending.items()):
        if i > 0:
            _time.sleep(1.5)
        needs = entry.get("needs", [])
        if not needs:
            continue
        try:
            fetched = fetch_and_parse_case_docs(
                case_hex, waf_token=waf_token, doc_types=needs, api_key=api_key,
                all_cookies=all_cookies,
            )
        except Exception as e:
            logger.debug("Queue drain fetch failed for %s: %s", entry.get("case_number"), e)
            continue
        for dt, results in fetched.items():
            if not results:
                continue
            parsed = results[0]
            cdq.record_fetched(case_hex, dt, parsed)
            cdq.mark_fetched(case_hex, dt)
            fetches += 1
            logger.info("Queue drain: %s -> %s landed (%s)",
                        entry.get("case_number"), dt,
                        parsed.get("_meta", {}).get("event_label", ""))
    return fetches


# ── Public entry ─────────────────────────────────────────────────────


async def scrape_ecourts(
    *,
    counties: list[str],
    types: list[str],
    since_date_override: str | None = None,
    seen_ids: dict[str, str] | None = None,
    max_records: int = 0,
    headless: bool = True,
) -> list[NoticeData]:
    """Scrape NC eCourts Smart Search for the requested counties + types.

    Args:
        counties: list of bare county names (e.g. ["Mecklenburg", "Lincoln"]).
        types: subset of {"probate", "foreclosure"}.
        since_date_override: YYYY-MM-DD. Default = last_run_date or 7 days ago.
        seen_ids: cross-run dedup cache keyed by case number.
        max_records: stop after this many (0 = no cap).
        headless: pass False to watch the browser.
    """
    type_filter = [t for t in types if t in CASE_TYPE_BY_NOTICE_TYPE]
    if not counties or not type_filter:
        logger.info("eCourts: nothing to do (counties=%s types=%s)", counties, types)
        return []

    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info(
        "eCourts: %d seen IDs; counties=%s types=%s",
        len(seen_ids), counties, type_filter,
    )

    # Date window
    if since_date_override:
        since_date = since_date_override
    else:
        stored = load_last_run_date()
        if stored:
            since_date = stored
        else:
            since_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    # Convert to MM/DD/YYYY for the form
    try:
        d_start = datetime.strptime(since_date, "%Y-%m-%d")
    except ValueError:
        d_start = datetime.now() - timedelta(days=7)
    d_end = datetime.now()
    mdy_start = d_start.strftime("%m/%d/%Y")
    mdy_end = d_end.strftime("%m/%d/%Y")
    logger.info("eCourts: date range %s..%s", mdy_start, mdy_end)

    notices: list[NoticeData] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, user_agent=_DEFAULT_UA)
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()

        # Try cached cookie first
        cached = _load_cached_waf_cookie()
        if cached:
            logger.info("eCourts: reusing cached WAF cookie")
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
        await page.wait_for_timeout(2500)

        if await _is_waf_gate(page):
            logger.info("eCourts: WAF gate hit (cache miss or expired)")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)

        await _navigate_to_smart_search(page)
        await _open_advanced_filters(page)

        for county in counties:
            for ntype in type_filter:
                case_type_value = CASE_TYPE_BY_NOTICE_TYPE[ntype]
                logger.info("eCourts: search %s / %s (%s)", county, ntype, case_type_value)

                # Reset form state on subsequent iterations
                if county != counties[0] or ntype != type_filter[0]:
                    # Click Clear or just navigate back to Smart Search
                    await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
                    await page.wait_for_timeout(2000)
                    await _open_advanced_filters(page)

                try:
                    # Use a case-number wildcard like '26E00*' (Estates) or
                    # '26SP*' (Special Proceedings). Per operator workflow,
                    # this is the proven way to return real result sets.
                    criteria = _search_criteria_for(ntype, d_end.year)
                    logger.info("eCourts: search criteria=%r", criteria)
                    await _set_search_criteria(page, criteria)
                    await _set_case_type(page, case_type_value)
                    # NOTE: deliberately NOT setting Case Status to "Pending"
                    # anymore. Small Estate Affidavits Dispose the same day
                    # they're filed; pre-filtering by Pending hides them.
                    # _row_to_notice does the carve-out client-side instead
                    # (keep Pending + Disposed-within-SMALL_ESTATE_RECENT_DAYS).
                    await _set_date_range(page, mdy_start, mdy_end)
                    await _select_only_county(page, county)
                    if not await _submit_search(page):
                        continue
                    page_notices = await _parse_results(page, county, ntype)
                except Exception:
                    logger.exception("eCourts: search failed for %s/%s", county, ntype)
                    continue

                for n in page_notices:
                    # Dedup by case-number-bearing source_url
                    nid = n.source_url
                    if nid and nid in seen_ids:
                        continue
                    notices.append(n)
                    if nid:
                        seen_ids[nid] = n.date_added or end_date
                    if max_records and len(notices) >= max_records:
                        break
                if max_records and len(notices) >= max_records:
                    break
            if max_records and len(notices) >= max_records:
                break

        # Capture the WAF token + UA before tearing down the browser context
        # so the Parties API client (pure HTTP) can use them. Also capture
        # the FULL cookie jar — Tyler Tech's api/ViewDocument endpoint
        # appears to require ALB stickiness cookies (AWSALB / AWSALBCORS)
        # to route the request to a backend that recognizes the WAF token.
        # Parties tolerates token-only; ViewDocument returns HTTP 602
        # "session invalid" when only aws-waf-token is sent. Week 26
        # audit: 156 cases queued, 0 fetched.
        ctx_cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        waf_cookie = next((c for c in ctx_cookies if c["name"] == "aws-waf-token"), None)
        waf_token_for_api = waf_cookie["value"] if waf_cookie else ""
        ua_for_api = (cached.get("user_agent") if cached else _DEFAULT_UA) or _DEFAULT_UA
        # Full cookie jar as {name: value} dict — passed alongside waf_token
        # to api/ViewDocument so ALL session cookies travel with the request.
        all_cookies_for_api = {c["name"]: c["value"] for c in ctx_cookies if c.get("name")}
        logger.info("eCourts: captured %d cookies for API (names: %s)",
                    len(all_cookies_for_api), sorted(all_cookies_for_api.keys()))

        await ctx.close()
        await browser.close()

    # Ordering matters here: WAF cookie was just captured (seconds old).
    # Tyler Tech's ViewDocument endpoint is stricter about cookie freshness
    # than the Parties endpoint — by the time Parties finishes its 30+
    # minutes of work, ViewDocument calls return HTTP 602 (Week 26 audit:
    # 51 cases queued, 0 fetched). So do doc-fetch FIRST while cookie is
    # fresh, THEN Parties (which tolerates older cookies).

    # 1. Drain pending-doc queue (cases queued on prior runs whose PDFs
    #    just landed). Runs first because the queue is what makes the
    #    retry feature actually work — and cookie is freshest right now.
    if waf_token_for_api:
        try:
            n_drained = drain_pending_case_docs(waf_token=waf_token_for_api,
                                                 all_cookies=all_cookies_for_api)
            if n_drained:
                logger.info("eCourts: pending-doc drain landed %d new docs", n_drained)
        except Exception:
            logger.exception("eCourts: pending-doc drain failed (continuing)")

    # 2. Case-doc enrichment for THIS run's notices (will + application).
    #    Uses fresh cookie. Adds to pending queue on miss for tomorrow.
    if waf_token_for_api and notices:
        probate_targets = [n for n in notices if getattr(n, "_roa_id", "") and n.notice_type == "probate"]
        if probate_targets:
            try:
                docs_enriched = _enrich_with_case_docs(probate_targets,
                                                       waf_token=waf_token_for_api,
                                                       all_cookies=all_cookies_for_api)
                if docs_enriched:
                    logger.info("eCourts: case-doc data extracted for %d notice(s)", docs_enriched)
            except Exception:
                logger.exception("eCourts: case-doc enrichment failed (continuing)")

    # 3. Parties enrichment last — slow (30+ min for big batches) but
    #    Parties endpoint tolerates cookies several minutes old.
    if waf_token_for_api and notices:
        try:
            _enrich_with_parties(notices, waf_token=waf_token_for_api, user_agent=ua_for_api)
        except Exception:
            logger.exception("eCourts: parties enrichment failed (continuing with bare notices)")

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("eCourts: total %d notice(s)", len(notices))
    return notices


def scrape_ecourts_sync(**kw) -> list[NoticeData]:
    """Sync wrapper for the CLI dispatcher."""
    return asyncio.run(scrape_ecourts(**kw))
