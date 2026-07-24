"""LandPortal external API — vacant-parcel market value lookup.

Rescues vacant parcels that the county tax value badly undersells. NC county
assessed values on raw land are often a small fraction of real market value:
Lowman 26E000824-170 Week 29 — county tax value $5,300, but LandPortal's
`tlp_estimate` was $56,454. Before the scrap-land floor (Step 1.82/1.92) drops a
sub-$10K vacant parcel, we re-value it here and keep it when it's really a lead.

Two-step lookup — the cheap step is effectively unlimited, the metered step is
used sparingly:

  1. GET /search        find the propertyid by parcel number. ~100k/day quota,
                        decremented only on non-empty results. Effectively free.
  2. GET /property-data fetch `tlp_estimate` (+ county value, acreage). Only
                        ~10 calls/day on the daily single_property_limit, then it
                        dips into `subscription export tokens`. So we call it ONLY
                        for the handful of borderline vacant parcels being dropped.

Successful (fips, pin) -> value results are cached to disk (output/.landportal_cache.json)
so nightly rebuilds don't re-spend the tiny property-data quota on parcels already
resolved. Set LANDPORTAL_DISABLE=1 to bypass entirely; delete the cache file to clear.

Docs: https://landportal.com/wp-json/lp-rest-api/v1  (External API Reference, v1)
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

import requests

try:
    import config as _cfg  # when run with src/ on the path
    _KEY = getattr(_cfg, "LANDPORTAL_API_KEY", "") or os.getenv("LANDPORTAL_API_KEY", "")
except Exception:  # pragma: no cover
    _KEY = os.getenv("LANDPORTAL_API_KEY", "")

_BASE = "https://landportal.com/wp-json/lp-rest-api/v1"
_TIMEOUT = 30
_CACHE_PATH = Path("output") / ".landportal_cache.json"
_CACHE_TTL_DAYS = 30

# 5-digit FIPS for the NC counties SiftStack covers. LandPortal keys property
# data by FIPS, so a lookup can't run without this. Extend when a new county
# joins the pipeline.
_NC_COUNTY_FIPS = {
    "cabarrus": "37025",
    "catawba": "37035",
    "gaston": "37071",
    "iredell": "37097",
    "lincoln": "37109",
    "mecklenburg": "37119",
    "rowan": "37159",
}

# Once the daily single_property_limit AND export tokens are exhausted, the API
# returns 403 "Single property limit reached". Latch it so we stop spending calls
# for the rest of the run instead of hammering a wall.
_quota_exhausted = False
_cache: dict | None = None


def county_fips(county: str) -> str:
    return _NC_COUNTY_FIPS.get((county or "").strip().lower(), "")


def available() -> bool:
    """True when a key is configured and the feature isn't disabled."""
    return bool(_KEY) and os.getenv("LANDPORTAL_DISABLE") != "1"


def _norm_pin(pin: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", (pin or "")).upper()


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(_cache, dict):
            _cache = {}
    except Exception:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache), encoding="utf-8")
    except Exception:
        pass


def _get(path: str, params: dict) -> tuple[int, dict]:
    """GET with one retry on transient (5xx / network) failure per LandPortal's
    retry guidance. Returns (status, json) — status 0 for a network error."""
    headers = {"Authorization": f"Bearer {_KEY}"}
    for attempt in range(2):
        try:
            resp = requests.get(f"{_BASE}{path}", params=params,
                                headers=headers, timeout=_TIMEOUT)
        except requests.RequestException:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return (0, {})
        if resp.status_code >= 500 and attempt == 0:
            time.sleep(1.0)
            continue
        try:
            return (resp.status_code, resp.json())
        except ValueError:
            return (resp.status_code, {})
    return (0, {})


def _find_propertyid(pin: str, fips: str) -> int | None:
    """Resolve a parcel number to a LandPortal propertyid via /search (free).
    Prefers a feature whose APN matches the PIN once punctuation is stripped;
    falls back to the single result when there's exactly one."""
    status, body = _get("/search", {"type": "parcelnumb", "query": pin, "fips": fips})
    if status != 200 or not body.get("success"):
        return None
    feats = ((body.get("data") or {}).get("features")) or []
    want = _norm_pin(pin)
    for f in feats:
        props = f.get("properties") or {}
        if _norm_pin(props.get("apn", "")) == want and props.get("propertyid"):
            return int(props["propertyid"])
    if len(feats) == 1:
        pid = (feats[0].get("properties") or {}).get("propertyid")
        return int(pid) if pid else None
    return None


def get_vacant_market_value(pin: str, county: str) -> dict | None:
    """Return LandPortal's market read for a parcel, or None if unavailable.

    Result dict: {tlp_estimate, county_value, acres, source}. `tlp_estimate` is
    LandPortal's algorithmic market value (the figure shown in their UI) — the
    number we use to decide whether an apparently-scrap vacant lot is a real
    lead. Never raises; returns None on missing key, no FIPS, no match, or an
    exhausted property-data quota.
    """
    global _quota_exhausted
    if not available():
        return None
    fips = county_fips(county)
    if not fips or not pin:
        return None

    cache = _load_cache()
    ck = f"{fips}:{_norm_pin(pin)}"
    hit = cache.get(ck)
    if isinstance(hit, dict) and hit.get("_v") == 1:
        age_days = (time.time() - hit.get("_ts", 0)) / 86400
        if age_days <= _CACHE_TTL_DAYS:
            return hit.get("result")  # may be None (cached "no value")

    if _quota_exhausted:
        return None

    pid = _find_propertyid(pin, fips)
    if pid is None:
        # Cache the miss so we don't re-search every rebuild (search is free but
        # this also short-circuits the whole path). Misses expire with the TTL.
        cache[ck] = {"_v": 1, "_ts": time.time(), "result": None}
        _save_cache()
        return None

    status, body = _get("/property-data", {"propertyid": str(pid), "fips": fips})
    if status == 403:
        _quota_exhausted = True
        print("  LANDPORTAL: property-data quota exhausted for today — "
              "skipping further re-valuations this run")
        return None
    if status != 200 or not body.get("success"):
        return None

    prop = (body.get("data") or {}).get("property") or {}
    tlp = prop.get("tlp_estimate")
    result = None
    if tlp is not None:
        try:
            result = {
                "tlp_estimate": float(tlp),
                "county_value": _to_float(prop.get("markettotalvalue")
                                          or prop.get("assdtotalvalue")),
                "acres": _to_float(prop.get("lotsizeacres")),
                "source": "landportal",
            }
        except (TypeError, ValueError):
            result = None

    cache[ck] = {"_v": 1, "_ts": time.time(), "result": result}
    _save_cache()
    return result


_PROPERTY_URL = "https://landportal.com/?property="
_LINCOLN_PARCEL_URL = ("https://arcgisserver.lincolncountync.gov/arcgis/rest/"
                       "services/Server_TaxParcelViewerSP/MapServer/0/query")


def _build_property_url(fips: str, apn: str, propertyid) -> str:
    """LandPortal's shareable deep link is ?property=<base64 of a query string>.
    Verified against a live browser URL (Painter, Lincoln 26E000440-540):
    fips=37109&apn=24578&propertyid=97844945 → the exact ?property= token."""
    payload = f"fips={fips}&apn={apn}&propertyid={propertyid}"
    token = base64.b64encode(payload.encode()).decode()
    return _PROPERTY_URL + urllib.parse.quote(token)


def _search_feature(query: str, fips: str) -> dict | None:
    """First /search feature's properties for a parcel query, or None."""
    status, body = _get("/search", {"type": "parcelnumb", "query": query, "fips": fips})
    if status != 200 or not body.get("success"):
        return None
    feats = ((body.get("data") or {}).get("features")) or []
    return (feats[0].get("properties") or {}) if feats else None


def _lincoln_tax_parcel_id(pin: str) -> str:
    """Translate a Lincoln geo-PIN to its tax-account id (PARCELID). LandPortal
    indexes Lincoln by PARCELID (e.g. 24578), NOT the PIN (3665410548), so a
    /search on the PIN returns nothing. The county GIS record we already read
    carries both. Best-effort; returns "" on any failure."""
    try:
        r = requests.get(_LINCOLN_PARCEL_URL, timeout=_TIMEOUT, params={
            "where": f"PIN='{pin}'", "outFields": "PARCELID",
            "returnGeometry": "false", "f": "json"})
        feats = r.json().get("features", [])
        if feats:
            return str(feats[0].get("attributes", {}).get("PARCELID") or "").strip()
    except Exception:  # pragma: no cover
        return ""
    return ""


def get_property_url(parcel_id: str, county: str) -> str:
    """Return a landportal.com deep link for a parcel, or "" if unresolvable.

    Most NC counties resolve directly from our stored parcel number (LandPortal
    reformats it to its dashed APN). Lincoln is the exception — it indexes by the
    tax-account id, so we translate PIN → PARCELID first. Result (including a ""
    miss) is cached to disk so nightly rebuilds don't re-query. Never raises.
    """
    if not available():
        return ""
    fips = county_fips(county)
    if not fips or not parcel_id:
        return ""

    cache = _load_cache()
    ck = f"url:{fips}:{_norm_pin(parcel_id)}"
    hit = cache.get(ck)
    if isinstance(hit, dict) and hit.get("_v") == 1:
        if (time.time() - hit.get("_ts", 0)) / 86400 <= _CACHE_TTL_DAYS:
            return hit.get("result") or ""

    props = _search_feature(parcel_id, fips)
    if props is None and (county or "").strip().lower() == "lincoln":
        alt = _lincoln_tax_parcel_id(parcel_id)
        if alt:
            props = _search_feature(alt, fips)

    url = ""
    if props and props.get("propertyid") and props.get("apn"):
        url = _build_property_url(fips, str(props["apn"]), props["propertyid"])

    cache[ck] = {"_v": 1, "_ts": time.time(), "result": url}
    _save_cache()
    return url


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
