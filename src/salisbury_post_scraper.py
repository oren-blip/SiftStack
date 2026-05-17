"""Scrape Salisbury Post AdHunter for Rowan County public notices.

Source: https://marketplace.salisburypost.com/AdHunter/SalisburyPost/Home/Search?majorClass=2600
(majorClass 2600 = Public Notices)

Pure HTTP, server-rendered, no auth, no CAPTCHA. The search index lists
~10 ads per page across N pages (typically 10-15). Each ad link is
`/AdHunter/SalisburyPost/Home/Ad/<id>` and the detail page contains the
full notice body wrapped in lots of category navigation chrome.

Notice body extraction: find the substring between "Ad Text No. <id>" and
the trailing `)-->` (an inline-comment terminator from a hidden script tag).
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


BASE = "https://marketplace.salisburypost.com"
SEARCH_URL = f"{BASE}/AdHunter/SalisburyPost/Home/Search?majorClass=2600"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Title prefix → notice_type
# "SP-NTC" = Salisbury Post - Notice to Creditors (probate)
# Add more as discovered (SP-NOFS would be Notice of Foreclosure Sale, etc.)
TITLE_PREFIX_MAP = {
    "SP-NTC": "probate",
    "SP-NOFS": "foreclosure",
    "SP-TS":   "tax_sale",
}

# Body-keyword fallback if title prefix is unrecognized
BODY_KEYWORD_MAP = [
    ("notice of foreclosure sale", "foreclosure"),
    ("substitute trustee", "foreclosure"),
    ("trustee's sale", "foreclosure"),
    ("notice of trustee", "foreclosure"),
    ("tax foreclosure", "tax_sale"),
    ("notice to creditors", "probate"),
    ("estate of", "probate"),
]


# ── State helpers ─────────────────────────────────────────────────────


def _state_file() -> Path:
    return config.PROJECT_ROOT / "salisbury_post_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "salisbury_post_seen_ids.json"


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


# ── HTTP fetching ─────────────────────────────────────────────────────


def fetch(url: str, session: requests.Session) -> str | None:
    """GET with retry. Returns response text or None on failure."""
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code == 200:
                return r.text
            logger.warning("Salisbury: %s returned %d (attempt %d/3)", url, r.status_code, attempt + 1)
        except Exception as e:
            logger.warning("Salisbury: %s err (attempt %d/3): %s", url, attempt + 1, e)
        time.sleep(1 + attempt)
    return None


# ── Parsing ───────────────────────────────────────────────────────────


AD_LINK_RE = re.compile(r'href="(/AdHunter/SalisburyPost/Home/Ad/\d+)"')

# Capture posted date from "Posted: <MM/DD/YYYY>"
POSTED_RE = re.compile(r"Posted:\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.IGNORECASE)


def parse_index_page(html: str) -> list[str]:
    """Extract /Home/Ad/<id> URLs from a search-results page."""
    return sorted(set(AD_LINK_RE.findall(html)))


# Title appears as "<PREFIX> <Name>" near the top of the page, repeated.
# We extract it from the <title> tag for reliability.
TITLE_TAG_RE = re.compile(r"<title>([^<]*?)</title>", re.IGNORECASE)


# The full notice body lives between "Ad Text No. <num> " and ")-->"
# (the latter is an inline-script terminator that wraps the body for the
# email-share feature). Use a non-greedy match.
AD_TEXT_RE = re.compile(
    r"Ad\s+Text\s+No\.\s+\d+\s+(?P<body>.*?)\)-->",
    re.IGNORECASE | re.DOTALL,
)


def _strip_html(s: str) -> str:
    """Remove tags + collapse whitespace + decode common entities."""
    s = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_notice(ad_html: str) -> tuple[str, str, str, str]:
    """From an Ad detail page, pull (title, notice_type, body, posted_date).

    Returns ('', '', '', '') if no notice body was found.
    """
    title_m = TITLE_TAG_RE.search(ad_html)
    title = (title_m.group(1) if title_m else "").strip()
    # Strip " - Ad Hunter" suffix common in titles
    title = re.sub(r"\s*-\s*Ad\s+Hunter\s*$", "", title)

    # Notice type from title prefix
    notice_type = ""
    for prefix, ntype in TITLE_PREFIX_MAP.items():
        if title.upper().startswith(prefix):
            notice_type = ntype
            break

    # Body extraction
    text_only = _strip_html(ad_html)
    body_m = AD_TEXT_RE.search(text_only)
    body = body_m.group("body").strip() if body_m else ""

    # If we couldn't classify from title, sniff body keywords
    if not notice_type and body:
        low = body.lower()
        for kw, ntype in BODY_KEYWORD_MAP:
            if kw in low:
                notice_type = ntype
                break

    # Posted date
    posted_m = POSTED_RE.search(text_only)
    posted = ""
    if posted_m:
        raw = posted_m.group(1).strip()
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                posted = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

    return title, notice_type, body, posted


# ── Public entry ─────────────────────────────────────────────────────


def scrape_salisbury_post(
    *,
    types: list[str] | None = None,
    seen_ids: dict[str, str] | None = None,
    max_pages: int = 20,
    polite_delay: float = 0.7,
    max_records: int = 0,
) -> list[NoticeData]:
    """Scrape Salisbury Post AdHunter public notices for Rowan County.

    Args:
        types: filter to these notice_types (e.g. ["probate", "foreclosure"]).
            Defaults to all supported types.
        seen_ids: cross-run dedup cache keyed by Ad ID. Loaded from disk if None.
        max_pages: cap on search-index pages to walk.
        polite_delay: seconds between Ad detail-page fetches.
        max_records: stop after this many NoticeData (0 = no cap).
    """
    if seen_ids is None:
        seen_ids = load_seen_ids()
    type_filter = {t.lower() for t in types} if types else None
    logger.info(
        "Salisbury Post: %d seen IDs in cache; type filter=%s",
        len(seen_ids), sorted(type_filter) if type_filter else "(all)",
    )

    session = requests.Session()
    notices: list[NoticeData] = []
    fetched_ad_ids: set[str] = set()

    for page_idx in range(1, max_pages + 1):
        url = SEARCH_URL if page_idx == 1 else f"{SEARCH_URL}&page={page_idx}"
        html = fetch(url, session)
        if not html:
            logger.warning("Salisbury Post: index page %d unreachable; stopping", page_idx)
            break
        ad_urls = parse_index_page(html)
        new_ad_urls = [u for u in ad_urls if u.rsplit("/", 1)[-1] not in fetched_ad_ids]
        logger.info(
            "Salisbury Post: index page %d -> %d ads (%d new)",
            page_idx, len(ad_urls), len(new_ad_urls),
        )
        if not new_ad_urls:
            # No new ads on this page = either pagination exhausted or duplicates
            if page_idx > 1:
                logger.info("Salisbury Post: no new ads, assuming end of results")
                break
            # Page 1 with 0 ads = empty result set
            break

        for ad_url in new_ad_urls:
            ad_id = ad_url.rsplit("/", 1)[-1]
            fetched_ad_ids.add(ad_id)

            if ad_id in seen_ids:
                logger.debug("Salisbury Post: skipping already-seen ad %s", ad_id)
                continue

            full_url = BASE + ad_url
            ad_html = fetch(full_url, session)
            if not ad_html:
                continue
            time.sleep(polite_delay)

            title, notice_type, body, posted = extract_notice(ad_html)
            if not body:
                logger.debug("Salisbury Post: no body in %s (title=%s)", ad_id, title)
                continue
            if not notice_type:
                logger.debug("Salisbury Post: unclassified type for %s (title=%s)", ad_id, title)
                continue
            if type_filter and notice_type not in type_filter:
                continue

            notice = parse_nc_notice_text(
                raw_text=body,
                county="Rowan",  # fallback; body-extracted county overrides
                notice_type=notice_type,
                source_url=full_url,
                date_added=posted or datetime.now().strftime("%Y-%m-%d"),
            )

            # Salisbury Post publishes regional notices (Forsyth/Davie/etc.)
            # alongside Rowan — drop anything outside Rowan since other-county
            # coverage is handled by their respective scrapers (column.us etc).
            if notice.county.strip().lower() != "rowan":
                logger.debug(
                    "Salisbury Post: dropping non-Rowan notice (county=%s, ad=%s)",
                    notice.county, ad_id,
                )
                continue

            # Foreclosure filter (no-op for non-foreclosure types)
            if notice_type == "foreclosure" and not is_valid_foreclosure(notice):
                logger.debug("Salisbury Post: foreclosure filter dropped %s", ad_id)
                continue

            notices.append(notice)
            seen_ids[ad_id] = notice.date_added

            if max_records and len(notices) >= max_records:
                logger.info("Salisbury Post: hit max_records=%d, stopping", max_records)
                save_seen_ids(seen_ids)
                save_last_run_date()
                return notices

    save_seen_ids(seen_ids)
    save_last_run_date()
    logger.info("Salisbury Post: %d notice(s) returned", len(notices))
    return notices
