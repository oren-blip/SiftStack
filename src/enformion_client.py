"""Enformion / Endato Person Search client — phone fallback for named PRs.

Wired in from the deep-prospecting v4 skill (.claude/skills/deep-prospecting):
one PersonSearch on a person anchored to their OWN mailing address ("City, ST
ZIP") returns their current phones. Used by nc_deep_prospect.py Phase 2 as a
FALLBACK when Tracerfy returns no phone for a court-named PR. ~$0.35 per
MATCH; misses are free.

Inert until credentials exist: set ENFORMION_AP_NAME / ENFORMION_AP_PASSWORD
in .env (Enformion Console -> API access profile, NOT the website login).
Off-switch: NC_ENFORMION=0.

Persistent disk cache (output/.nc_enformion_cache.json): the daily build
re-runs deep prospecting on the same in-progress week each night, so
successful lookups are remembered for NC_ENFORMION_CACHE_TTL_DAYS (default
14) and never re-billed. Misses are NOT cached (free anyway, and they retry
next run in case the person gets indexed). Delete the file to clear; bump
_PERSIST_VERSION when the result schema changes.

Skill gotchas honored (see references/enformion-person-search.md):
  - failure = HTTP status, never the always-present `error` object
  - surname match = whole last-name token, not a substring
  - isDeceased may be a bool or a "true"/"yes" string
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger("enformion")

PERSON_SEARCH_URL = "https://devapi.enformion.com/PersonSearch"
COST_PER_MATCH = 0.35          # billed per MATCH; misses are free
_TIMEOUT = 45
_MAX_PHONES = 6                # cap per person (skill Step D discipline)

_CACHE_PATH = Path("output") / ".nc_enformion_cache.json"
_PERSIST_VERSION = 1
_TTL_DAYS = float(os.environ.get("NC_ENFORMION_CACHE_TTL_DAYS", "14"))


def credentials_present() -> bool:
    return bool(os.environ.get("ENFORMION_AP_NAME")
                and os.environ.get("ENFORMION_AP_PASSWORD"))


def enabled() -> bool:
    """Creds in the environment AND not switched off via NC_ENFORMION=0."""
    return credentials_present() and os.environ.get("NC_ENFORMION") != "0"


# ── Persistent cache (mirrors the nc_gis_lookup pattern) ──────────────────

def _load_cache() -> dict:
    if os.environ.get("NC_ENFORMION_CACHE_DISABLE") == "1":
        return {}
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if data.get("version") != _PERSIST_VERSION:
            return {}
        return data.get("entries", {})
    except Exception:  # noqa: BLE001 — missing/corrupt cache is just empty
        return {}


def _save_cache(entries: dict) -> None:
    if os.environ.get("NC_ENFORMION_CACHE_DISABLE") == "1":
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps({"version": _PERSIST_VERSION, "entries": entries}),
            encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("could not persist Enformion cache: %s", e)


def _cache_key(first: str, last: str, city: str, state: str, zip_code: str) -> str:
    return "|".join(p.strip().lower() for p in (first, last, city, state, zip_code))


# ── Response parsing ──────────────────────────────────────────────────────

def _is_deceased(person: dict) -> bool:
    v = person.get("isDeceased")
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("true", "yes", "1")


def _last_name_token(person: dict) -> str:
    nm = person.get("name") or {}
    last = (nm.get("lastName") or "").strip()
    return last.split()[-1].lower() if last else ""


def _best_match(resp: dict, last: str, city: str, zip_code: str) -> dict | None:
    """Pick the person whose surname matches as a WHOLE token, preferring one
    whose address history overlaps the anchor (zip first, then city)."""
    persons = (resp.get("persons") or resp.get("people")
               or resp.get("results") or [])
    want = (last or "").strip().split()[-1].lower()
    cands = [p for p in persons if isinstance(p, dict)
             and _last_name_token(p) == want]
    if not cands:
        return None

    def overlap(p: dict) -> int:
        addrs = " ".join((a.get("fullAddress") or "").lower()
                         for a in (p.get("addresses") or [])
                         if isinstance(a, dict))
        s = 0
        if zip_code and zip_code.strip()[:5] in addrs:
            s += 2
        if city and city.strip().lower() in addrs:
            s += 1
        return s

    cands.sort(key=overlap, reverse=True)
    return cands[0]


def _extract_phones(person: dict) -> dict:
    """{"primary": str, "mobiles": [...], "landlines": [...]} — connected
    mobiles first, deduped, capped at _MAX_PHONES total."""
    mobiles: list[str] = []
    landlines: list[str] = []
    seen: set[str] = set()
    entries = [e for e in (person.get("phoneNumbers") or []) if isinstance(e, dict)]
    # Connected numbers ahead of stale ones within each bucket.
    entries.sort(key=lambda e: bool(e.get("isConnected")), reverse=True)
    for e in entries:
        num = (e.get("phoneNumber") or "").strip()
        digits = "".join(c for c in num if c.isdigit())
        if not digits or digits in seen or len(seen) >= _MAX_PHONES:
            continue
        seen.add(digits)
        ptype = (e.get("phoneType") or "").lower()
        if "wireless" in ptype or "mobile" in ptype:
            mobiles.append(num)
        else:
            landlines.append(num)
    primary = mobiles[0] if mobiles else (landlines[0] if landlines else "")
    return {"primary": primary, "mobiles": mobiles, "landlines": landlines}


# ── The one public lookup ─────────────────────────────────────────────────

def person_search_phones(first: str, last: str, city: str, state: str,
                         zip_code: str) -> dict | None:
    """PersonSearch one person anchored to their mailing address.

    Returns {"primary","mobiles","landlines","is_deceased","matched_name"}
    or None on a miss / error. Hits are disk-cached; misses are not.
    Requires a ZIP — Enformion rejects name+city as insufficient criteria.
    """
    first, last = (first or "").strip(), (last or "").strip()
    if not (first and last and zip_code):
        return None
    key = _cache_key(first, last, city, state, zip_code)
    cache = _load_cache()
    hit = cache.get(key)
    if hit and (time.time() - hit.get("ts", 0)) < _TTL_DAYS * 86400:
        return hit["result"]

    addr2 = " ".join(p for p in (f"{city.strip()}," if city.strip() else "",
                                 (state or "NC").strip(), zip_code.strip()) if p)
    body = {"FirstName": first, "LastName": last,
            "Addresses": [{"AddressLine2": addr2}],
            "Page": 1, "ResultsPerPage": 5}
    try:
        r = requests.post(
            PERSON_SEARCH_URL,
            headers={
                "galaxy-ap-name": os.environ["ENFORMION_AP_NAME"],
                "galaxy-ap-password": os.environ["ENFORMION_AP_PASSWORD"],
                "galaxy-search-type": "Person",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=body, timeout=_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — network failure, retry next run
        logger.warning("Enformion request failed for %s %s: %s", first, last, e)
        return None
    # Failure = HTTP status. A 200 with a populated `error` object is still a
    # success — Enformion returns {inputErrors:[],warnings:[]} on EVERY call.
    if r.status_code != 200:
        logger.warning("Enformion HTTP %s for %s %s", r.status_code, first, last)
        return None
    try:
        resp = r.json()
    except ValueError:
        logger.warning("Enformion non-JSON response for %s %s", first, last)
        return None

    person = _best_match(resp, last, city, zip_code)
    if person is None:
        return None  # miss — free, and NOT cached so late indexing retries

    nm = person.get("name") or {}
    result = _extract_phones(person)
    result["is_deceased"] = _is_deceased(person)
    result["matched_name"] = " ".join(
        p for p in (nm.get("firstName"), nm.get("lastName")) if p)
    cache[key] = {"ts": time.time(), "result": result}
    _save_cache(cache)
    return result
