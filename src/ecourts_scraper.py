"""NC eCourts Smart Search scraper for probate (Estates) + foreclosure (SP) cases.

Source: https://portal-nc.tylertech.cloud/Portal/Home/Dashboard/29 (Tyler Tech
Odyssey statewide NC portal, rolled out Oct 2025 to all 100 counties).

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
from datetime import datetime, timedelta
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


async def _set_date_range(page: Page, start: str, end: str) -> None:
    """Set the file-date range via direct JS value + change event.

    The Tyler datepickers wrap the raw input with a custom widget that
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
    for _ in range(20):  # up to ~20 seconds
        await page.wait_for_timeout(1000)
        for sel in grid_selectors:
            try:
                if await page.locator(sel).first.count() > 0:
                    return True
            except Exception:
                pass
    # Fall back: give it networkidle one more time
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PwTimeout:
        pass
    return True


# ── Results parsing ───────────────────────────────────────────────────


# Result row pattern in the eCourts results table:
#   <tr> ... <td>case number link</td> <td>filing date</td> <td>parties</td> ...
# We extract via DOM query (selectors observed during smoke testing).
async def _parse_results(page: Page, county: str, notice_type: str) -> list[NoticeData]:
    """Walk the results table and build NoticeData list."""
    notices: list[NoticeData] = []

    # Lightweight post-submit log so 0-result runs are diagnosable
    try:
        body = await page.inner_text("body")
        logger.info(
            "eCourts: post-submit — title=%r body_len=%d",
            await page.title(), len(body),
        )
    except Exception:
        pass

    rows = await page.evaluate(
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
    logger.info("eCourts: %d result row(s) for %s/%s", len(rows), county, notice_type)
    if not rows:
        return notices

    # eCourts result-row cell order (observed for Mecklenburg estates):
    #   cells[0] = "" (checkbox column, always empty)
    #   cells[1] = case number    (e.g. "26E001794-590")
    #   cells[2] = style / parties (e.g. "IN THE MATTER OF THE ESTATE OF Helen Barbara Barlow")
    #   cells[3] = filing date    (MM/DD/YYYY)
    #   cells[4] = case sub-type  (e.g. "Decedents' Estate - Small Estate")
    #   cells[5] = case status    (e.g. "Pending")
    #   cells[6] = court location (e.g. "Mecklenburg Clerk of Superior Court")
    # Kendo grids interleave empty rows for expand/detail panes — skip those.
    case_no_re = re.compile(r"\d{2}[A-Z]{1,3}\d{3,6}-?\d{0,3}")

    for row in rows:
        cells = row.get("cells", [])
        if not cells:
            continue

        # Find the cell that contains the case number (it's not always cells[0]
        # due to the checkbox column + occasional layout variations)
        case_no = ""
        case_no_idx = -1
        for i, c in enumerate(cells):
            c = c.strip().replace(" ", "")
            if c and case_no_re.fullmatch(c):
                case_no = c
                case_no_idx = i
                break
        if not case_no:
            continue  # interleaved empty row or non-data row

        # style is the cell right after the case number
        style = ""
        if case_no_idx + 1 < len(cells):
            style = cells[case_no_idx + 1].strip()

        # Filing date — search all cells for first MM/DD/YYYY
        filing_date = ""
        for c in cells:
            m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", c)
            if m:
                filing_date = m.group(1)
                break

        # Decedent / grantor extraction
        # Probate styles look like "IN THE MATTER OF THE ESTATE OF <NAME>" or
        # "IN RE: ESTATE OF <NAME>" or just "<NAME>".
        # Foreclosure SPs look like "<GRANTOR> vs. <TRUSTEE>" or similar.
        primary_name = style
        for prefix in [
            r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+ESTATE\s+OF\s+",
            r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+GUARDIANSHIP\s+OF\s+",
            r"^IN\s+THE\s+MATTER\s+OF\s+THE\s+TRUST\s+OF\s+",
            r"^IN\s+RE:?\s*ESTATE\s+OF\s+",
            r"^IN\s+RE:?\s+",
            r"^ESTATE\s+OF\s+",
            r"^GUARDIANSHIP\s+OF\s+",
        ]:
            primary_name = re.sub(prefix, "", primary_name, flags=re.IGNORECASE)
        # Strip trailing "vs. <TRUSTEE>" for foreclosures
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

        # source_url: Tyler doesn't expose direct case-detail URLs in result
        # rows (link is "#"). Use the case number as the stable dedup key.
        href = row.get("href") or ""
        if not href or href.endswith("#"):
            href = f"{PORTAL_URL}#case={case_no}"

        # Stash the Register-of-Actions case id (from the caseLink's data-url
        # attribute) on the notice so the post-parse loop can fetch parties.
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
        )
        # _roa_id is a transient attribute used by _enrich_with_parties below
        notice._roa_id = case_id_hex  # type: ignore[attr-defined]
        if notice_type == "probate":
            notice.decedent_name = primary_name
        else:
            notice.owner_name = primary_name
        notices.append(notice)

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
            _time.sleep(0.8)  # be a good citizen — polite cadence between cases
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

        # If the search-results decedent name was blank or partial, refresh
        # it from the canonical Parties data
        dec = detail.decedent
        if dec and (not n.decedent_name or len(n.decedent_name) < len(dec.full_name)):
            n.decedent_name = dec.full_name

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
        # so the Parties API client (pure HTTP) can use them.
        ctx_cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        waf_cookie = next((c for c in ctx_cookies if c["name"] == "aws-waf-token"), None)
        waf_token_for_api = waf_cookie["value"] if waf_cookie else ""
        ua_for_api = (cached.get("user_agent") if cached else _DEFAULT_UA) or _DEFAULT_UA

        await ctx.close()
        await browser.close()

    # Per-case enrichment via OData Parties endpoint (pure HTTP — no browser)
    # Fills executor + beneficiaries from each case's Register of Actions
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
