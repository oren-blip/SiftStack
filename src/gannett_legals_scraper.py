"""Scrape Gannett iPublish Marketplace legal notices.

The Gannett classifieds platform at `classifieds.gannettclassifieds.com`
hosts legal notices for many Gannett-owned papers. Each paper has a slug
(e.g. `gas` = Gaston Gazette). Notices are organized by category:
  - /marketplace/<slug>/category/legals/foreclosure
  - /marketplace/<slug>/category/legals/notice-to-creditors
  - /marketplace/<slug>/category/legals/  (all legals — superset)

Each notice is rendered inline on the index page with a truncated body
and a "Show more »" link to its detail page at
`/marketplace/<slug>/advert/<slug-segment>_<id>`. The detail page has the
full notice body.

For our scope: Gaston Gazette covers Gaston County (slug=gas). Other
Gannett-owned NC papers (Asheville Citizen-Times, Fayetteville Observer)
exist on the same platform but aren't currently in our 7-county scope.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

import config
from foreclosure_filter import is_valid_foreclosure
from nc_notice_parser import parse_nc_notice_text
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


BASE = "https://classifieds.gannettclassifieds.com"

# Paper slug → (county, NC papers we cover today)
PAPER_SLUGS: dict[str, str] = {
    "gas": "Gaston",  # Gaston Gazette
    # Future: "ash" = Asheville Citizen-Times (Buncombe), "fay" = Fayetteville Observer
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Category-path → notice_type
CATEGORY_TO_TYPE: dict[str, str] = {
    "notice-to-creditors": "probate",
    "foreclosure":         "foreclosure",
    "trustee-sales":       "foreclosure",
    "tax-foreclosure":     "tax_sale",
}


# ── State helpers ─────────────────────────────────────────────────────


def _state_file() -> Path:
    return config.PROJECT_ROOT / "gannett_legals_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "gannett_legals_seen_ids.json"


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


# ── HTTP ──────────────────────────────────────────────────────────────


def fetch(url: str, session: requests.Session) -> str | None:
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                return r.text
            logger.warning("Gannett: %s -> %d (attempt %d/3)", url, r.status_code, attempt + 1)
        except Exception as e:
            logger.warning("Gannett: %s err %d/3: %s", url, attempt + 1, e)
        time.sleep(1 + attempt)
    return None


# ── Parsing ───────────────────────────────────────────────────────────


# Index-page advert blocks: <div id="advert_<id>" ...> ... <a href="/marketplace/<slug>/advert/...">Show more</a>
ADVERT_BLOCK_RE = re.compile(
    r'<div\s+id="advert_(?P<advert_id>\d+)"[^>]*>(?P<inner>.*?)(?=<div\s+id="advert_|<div\s+id="advert_loader|<script|$)',
    re.IGNORECASE | re.DOTALL,
)
ADVERT_URL_RE = re.compile(
    r'href="(/marketplace/[\w-]+/advert/[^"]+)"',
    re.IGNORECASE,
)
POST_DATE_RE = re.compile(
    r'<time\s+datetime="(\d{4}-\d{2}-\d{2})',
    re.IGNORECASE,
)


def _strip_html(s: str) -> str:
    s = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
           .replace("&#187;", "»").replace("&quot;", '"'))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_index_page(html: str) -> list[dict]:
    """Extract advert blocks from a category index page.

    Returns a list of dicts: {advert_id, advert_url, post_date, preview_text}.
    """
    found: list[dict] = []
    for m in ADVERT_BLOCK_RE.finditer(html):
        advert_id = m.group("advert_id")
        inner = m.group("inner")
        url_m = ADVERT_URL_RE.search(inner)
        if not url_m:
            continue
        advert_url = url_m.group(1)
        date_m = POST_DATE_RE.search(inner)
        post_date = date_m.group(1) if date_m else ""
        preview = _strip_html(inner)[:400]
        found.append({
            "advert_id": advert_id,
            "advert_url": advert_url,
            "post_date": post_date,
            "preview": preview,
        })
    return found


# Detail-page body extraction. The body sits inside a panel with class
# "panel-body" or a div with class "advert-text" — extract the largest
# text block on the page after stripping page chrome.
DETAIL_BODY_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:advert-text|panel-body)[^"]*"[^>]*>(?P<body>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def extract_detail_body(detail_html: str) -> str:
    """Extract just the notice text from a Gannett detail page."""
    # Prefer the labeled body div
    m = DETAIL_BODY_RE.search(detail_html)
    if m:
        return _strip_html(m.group("body"))
    # Fallback: longest text block
    full = _strip_html(detail_html)
    # Find the "NOTICE" substring and grab a generous slice after it
    nm = re.search(r"NOTICE\s+(?:TO\s+CREDITORS|OF\s+(?:FORECLOSURE\s+)?SALE|OF\s+TRUSTEE)",
                   full, re.IGNORECASE)
    if nm:
        return full[nm.start():nm.start() + 4000]
    return full[:4000]


# ── Public entry ─────────────────────────────────────────────────────


def scrape_gannett_legals(
    *,
    counties: list[str] | None = None,
    types: list[str] | None = None,
    seen_ids: dict[str, str] | None = None,
    max_pages: int = 10,
    polite_delay: float = 0.7,
    max_records: int = 0,
) -> list[NoticeData]:
    """Scrape Gannett iPublish Marketplace legal notices for requested counties.

    Args:
        counties: subset of PAPER_SLUGS values (e.g. ["Gaston"]).
        types: filter to these notice_types (e.g. ["probate", "foreclosure"]).
        seen_ids: cross-run dedup cache keyed by advert_id.
        max_pages: cap on index pages per (slug, category).
        polite_delay: seconds between detail-page fetches.
    """
    if counties is None:
        counties = list(PAPER_SLUGS.values())
    target_counties = {c for c in counties if c in PAPER_SLUGS.values()}
    if not target_counties:
        logger.info("Gannett: none of the requested counties are covered")
        return []

    # Filter slugs to requested counties
    slugs = [slug for slug, county in PAPER_SLUGS.items() if county in target_counties]

    if seen_ids is None:
        seen_ids = load_seen_ids()
    type_filter = {t.lower() for t in types} if types else None
    logger.info("Gannett: %d seen IDs; slugs=%s types=%s",
                len(seen_ids), slugs, sorted(type_filter) if type_filter else "(all)")

    session = requests.Session()
    notices: list[NoticeData] = []

    for slug in slugs:
        county_name = PAPER_SLUGS[slug]
        # Choose which categories to fetch based on requested types
        categories = [
            (path, ntype) for path, ntype in CATEGORY_TO_TYPE.items()
            if type_filter is None or ntype in type_filter
        ]
        for cat_path, cat_type in categories:
            for page in range(1, max_pages + 1):
                index_url = (
                    f"{BASE}/marketplace/{slug}/category/legals/{cat_path}"
                    + (f"?page={page}" if page > 1 else "")
                )
                html = fetch(index_url, session)
                if not html:
                    logger.warning("Gannett: %s page %d unreachable; stop", index_url, page)
                    break

                ads = parse_index_page(html)
                new_ads = [a for a in ads if a["advert_id"] not in seen_ids]
                logger.info(
                    "Gannett: %s/%s page %d -> %d ads (%d new)",
                    slug, cat_path, page, len(ads), len(new_ads),
                )
                if not ads:
                    break  # no more pages
                if not new_ads and page > 1:
                    break  # nothing new on later pages

                for ad in new_ads:
                    detail_url = BASE + ad["advert_url"]
                    detail_html = fetch(detail_url, session)
                    time.sleep(polite_delay)
                    if not detail_html:
                        continue
                    body = extract_detail_body(detail_html)
                    if not body or len(body) < 50:
                        logger.debug("Gannett: empty body for advert %s", ad["advert_id"])
                        continue

                    notice = parse_nc_notice_text(
                        raw_text=body,
                        county=county_name,
                        notice_type=cat_type,
                        source_url=detail_url,
                        date_added=ad["post_date"] or datetime.now().strftime("%Y-%m-%d"),
                    )

                    # Filter cross-county notices (Gannett publishes regional)
                    if notice.county.strip().lower() != county_name.lower():
                        logger.debug(
                            "Gannett: dropping non-%s notice (county=%s, ad=%s)",
                            county_name, notice.county, ad["advert_id"],
                        )
                        continue
                    if cat_type == "foreclosure" and not is_valid_foreclosure(notice):
                        continue

                    notices.append(notice)
                    seen_ids[ad["advert_id"]] = notice.date_added

                    if max_records and len(notices) >= max_records:
                        logger.info("Gannett: hit max_records=%d, stopping", max_records)
                        save_seen_ids(seen_ids)
                        save_last_run_date()
                        return notices

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("Gannett: %d notice(s) total across %s", len(notices), sorted(target_counties))
    return notices
