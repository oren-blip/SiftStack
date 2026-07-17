"""Zillow listing-status lookup for the pre-mail buy-box filter.

County GIS only knows a sale once the deed is recorded post-close, so it never
sees live MLS activity — a house under contract, actively listed, or sold last
month but not yet recorded. Oren catches these by hand off the Zillow URL
(Kincaid 26E000830-170 Week 29: county record still shows a 2001/2008 sale, but
Zillow shows it sold Jan 2025). This module automates that check.

Approach (feasibility proven 2026-07-17): Firecrawl fetches the property's
Zillow page — it renders and returns full content, no block — and a cheap LLM
pass pulls the actual status out of the ~200KB (which also contains Zillow's
"For Sale"/"For Rent" nav boilerplate, so a keyword grep would false-positive;
the LLM reads the property's own status banner).

Design constraints, all lead-protective per Oren:
  * FAIL TOWARD KEEPING. status="unknown" on any fetch/parse failure or an
    unsure LLM. A blocked page, a Firecrawl outage, or a low-confidence read
    must never drop a lead.
  * Disk-cached ~4 days: a listing status doesn't change overnight, and the
    week is re-polished nightly (Mon+Tue). Keyed by normalized address.
  * Budget-gated + off switch (ZILLOW_DISABLE=1): a network+LLM call per row is
    the session's biggest runtime add, so callers only check rows that survive
    every cheaper filter.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

import config as cfg
from llm_client import chat_json

logger = logging.getLogger(__name__)

_DISABLED = os.environ.get("ZILLOW_DISABLE", "") == "1"
_CACHE_PATH = Path("output") / ".zillow_status_cache.json"
_CACHE_TTL_DAYS = int(os.environ.get("ZILLOW_CACHE_TTL_DAYS", "4"))
# Cap Firecrawl spend per run; shares no counter with the obituary enricher's
# budget, so keep it modest — only survivor rows are ever checked.
_BUDGET = int(os.environ.get("ZILLOW_BUDGET", "120"))
_CACHE_VERSION = 1

# Statuses that mean "already in play — a mailer to the heir is wasted." Only
# these, at high confidence, justify an auto-drop. off_market / unknown never do.
DROP_STATUSES = {"for_sale", "pending", "under_contract", "sold_recently"}

_lock = threading.Lock()
_calls_used = 0
_cache: dict[str, dict] | None = None


@dataclass
class ZillowStatus:
    status: str            # for_sale|pending|under_contract|sold_recently|off_market|unknown
    confidence: str        # high|low
    sale_date: str | None  # ISO, when status == sold_recently
    detail: str            # short human string for Notes / logs

    def should_drop(self) -> bool:
        return self.confidence == "high" and self.status in DROP_STATUSES


_UNKNOWN = ZillowStatus("unknown", "low", None, "")


def available() -> bool:
    return bool(cfg.FIRECRAWL_API_KEY) and not _DISABLED


def _norm_addr(street: str, city: str, state: str, zip_: str) -> str:
    return re.sub(r"\s+", " ",
                  f"{street} {city} {state} {zip_}".strip().upper())


# ── Disk cache ────────────────────────────────────────────────────────

def _cache_load() -> dict[str, dict]:
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _cache
    if not isinstance(data, dict) or data.get("_version") != _CACHE_VERSION:
        return _cache
    cutoff = datetime.now() - timedelta(days=_CACHE_TTL_DAYS)
    for k, v in (data.get("entries") or {}).items():
        try:
            if datetime.fromisoformat(v.get("ts", "")) >= cutoff:
                _cache[k] = v
        except (ValueError, AttributeError):
            continue
    return _cache


def _cache_get(key: str) -> ZillowStatus | None:
    entry = _cache_load().get(key)
    if not entry:
        return None
    try:
        if datetime.fromisoformat(entry["ts"]) < datetime.now() - timedelta(days=_CACHE_TTL_DAYS):
            return None
        return ZillowStatus(**entry["status"])
    except (ValueError, TypeError, KeyError):
        return None


def _cache_put(key: str, status: ZillowStatus) -> None:
    store = _cache_load()
    store[key] = {"ts": datetime.now().isoformat(timespec="seconds"),
                  "status": asdict(status)}
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"_version": _CACHE_VERSION, "entries": store}),
                       encoding="utf-8")
        tmp.replace(_CACHE_PATH)
    except OSError as e:
        logger.warning("zillow_status: cache write failed: %s", e)


# ── Fetch + extract ───────────────────────────────────────────────────

def _fetch_zillow_markdown(street: str, city: str, state: str, zip_: str) -> str:
    """Firecrawl-render the property's Zillow page. The /homes/..._rb/ search
    URL redirects to the single homedetails page when the address is unique;
    Firecrawl follows it. Empty string on any failure (→ unknown → keep)."""
    global _calls_used
    with _lock:
        if _calls_used >= _BUDGET:
            return ""
        _calls_used += 1
    slug = re.sub(r"[^A-Za-z0-9]+", "-",
                  f"{street} {city} {state} {zip_}".strip()).strip("-")
    url = f"https://www.zillow.com/homes/{slug}_rb/"
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {cfg.FIRECRAWL_API_KEY}",
                     "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "waitFor": 6000},
            timeout=60,
        )
        if r.status_code != 200:
            logger.debug("zillow_status: Firecrawl HTTP %d for %s", r.status_code, url)
            return ""
        return (r.json().get("data", {}) or {}).get("markdown", "") or ""
    except (requests.RequestException, ValueError) as e:
        logger.debug("zillow_status: fetch failed for %s: %s", url, e)
        return ""


_EXTRACT_SYSTEM = (
    "You read a Zillow property page (markdown) and report the property's OWN "
    "current listing status. Ignore site navigation and 'For Sale'/'For Rent' "
    "menu tabs — report only the status banner for THIS property. Reply JSON "
    "only."
)


def _extract_status(markdown: str, addr: str) -> ZillowStatus:
    if not markdown:
        return _UNKNOWN
    prompt = (
        f"Property: {addr}\n\n"
        "From the Zillow page below, return JSON:\n"
        '{"status": one of "for_sale"|"pending"|"under_contract"|'
        '"sold_recently"|"off_market"|"unknown",\n'
        ' "sale_date": "YYYY-MM-DD" or null (only if recently sold),\n'
        ' "confidence": "high"|"low",\n'
        ' "detail": short human phrase like "Active listing $240k" or '
        '"Sold 2025-01-14"}\n\n'
        "Rules:\n"
        "- \"sold_recently\" ONLY if the page shows a sale dated within ~24 "
        "months of today. An older sale is \"off_market\".\n"
        "- Use \"unknown\" with low confidence if the page didn't load, is a "
        "search-results list (not one property), or the status is unclear.\n"
        "- Only say \"high\" confidence when the status is unambiguous for this "
        "exact property.\n\n"
        f"PAGE:\n{markdown[:12000]}"
    )
    try:
        data = chat_json(prompt, system=_EXTRACT_SYSTEM, max_tokens=300)
    except Exception as e:  # noqa: BLE001
        logger.debug("zillow_status: LLM extract failed: %s", e)
        return _UNKNOWN
    if not isinstance(data, dict):
        return _UNKNOWN
    status = str(data.get("status") or "unknown").strip().lower()
    valid = {"for_sale", "pending", "under_contract",
             "sold_recently", "off_market", "unknown"}
    if status not in valid:
        return _UNKNOWN
    conf = "high" if str(data.get("confidence")).lower() == "high" else "low"
    sale_date = data.get("sale_date")
    sale_date = str(sale_date)[:10] if sale_date else None
    detail = str(data.get("detail") or "").strip()[:80]
    return ZillowStatus(status, conf, sale_date, detail)


def get_status(street: str, city: str, state: str, zip_: str) -> ZillowStatus:
    """Return the property's Zillow listing status. Cached; fails to 'unknown'
    (→ keep) on any error. Never raises."""
    if not available():
        return _UNKNOWN
    if not street.strip():
        return _UNKNOWN
    key = _norm_addr(street, city, state, zip_)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    md = _fetch_zillow_markdown(street, city, state, zip_)
    status = _extract_status(md, key)
    # Only cache a decisive read. An 'unknown' from a Firecrawl budget-skip or a
    # transient blip must be retried next run, not frozen for 4 days.
    if status.status != "unknown" or md:
        _cache_put(key, status)
    return status
