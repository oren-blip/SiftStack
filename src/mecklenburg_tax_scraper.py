"""Scrape Mecklenburg County's in-rem tax foreclosure inventory.

Source: ArcGIS MapServer feature layer powering the county's tax foreclosure
map experience (https://tax.mecknc.gov/services/tax-foreclosure-properties).
Pure HTTP / JSON — no Playwright, no auth, no CAPTCHA.

Layer:  https://meckags.mecklenburgcountync.gov/server/rest/services/TaxForeclosures/MapServer/0

Each feature is one parcel under in-rem tax foreclosure (NCGS 105-375). Volume
is small (~600 statewide) so a single query with no pagination retrieves all
records. The layer's maxRecordCount is 2000.

Field map (only fields we surface to NoticeData):
  situs            -> address (e.g. "2214 LAKEVIEW LN" — no city)
  po_name          -> city  (e.g. "CHARLOTTE")
  zip              -> zip
  latitude/longitude -> NoticeData.latitude / .longitude
  due_amount       -> tax_delinquent_amount
  bill_count       -> tax_delinquent_years (count of unpaid annual bills)
  parcel_id        -> parcel_id
  proptype         -> property_type ("Residential" / "Commercial" / "Land Only")
  amt_totalvalue   -> estimated_value (assessor's total assessed; rough Zestimate proxy)
  num_bedrooms     -> bedrooms
  cnt_fullbaths    -> bathrooms
  doc_path         -> report_url (BPO PDF if available)

Owner name is NOT in this layer — leave blank; downstream enrichment (e.g.
polaris3g parcel lookup) can fill it in later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

import config
from notice_parser import NoticeData

logger = logging.getLogger(__name__)


MECK_TAX_LAYER_URL = (
    "https://meckags.mecklenburgcountync.gov/server/rest/services/"
    "TaxForeclosures/MapServer/0"
)

# Filter values for the `proptype` field
_RESIDENTIAL = {"residential"}
_COMMERCIAL = {"commercial"}
_LAND_ONLY_PROPLABEL = {"land only"}


def _state_file() -> Path:
    return config.PROJECT_ROOT / "mecklenburg_tax_last_run.json"


def _seen_ids_file() -> Path:
    return config.PROJECT_ROOT / "mecklenburg_tax_seen_ids.json"


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


# ── HTTP fetch ────────────────────────────────────────────────────────


def fetch_all_features(
    layer_url: str = MECK_TAX_LAYER_URL,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Query the layer for all features. Returns a list of attribute dicts.

    The layer has no public OBJECTID range guarantee, so we use a simple
    `1=1` predicate; volume is well under the 2000 maxRecordCount so a
    single request retrieves everything. If volume ever exceeds 2000,
    add OBJECTID-paged fetches here.
    """
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    url = f"{layer_url}/query"
    logger.info("Mecklenburg tax: GET %s", url)
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    payload = r.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS API error: {payload['error']}")

    feats = payload.get("features", []) or []
    if payload.get("exceededTransferLimit"):
        logger.warning(
            "Mecklenburg tax: exceededTransferLimit=true (only %d records returned). "
            "Add OBJECTID-paged fetch if this becomes a problem.",
            len(feats),
        )

    return [feat.get("attributes", {}) for feat in feats]


# ── Field mapping ─────────────────────────────────────────────────────


def _title(s: str | None) -> str:
    """Normalize ALLCAPS text from the layer to Title Case."""
    if not s:
        return ""
    s = " ".join(s.split())
    return s.title() if s.isupper() else s


def _str(v: Any) -> str:
    """Convert any feature value to its string form (empty for None)."""
    if v is None:
        return ""
    return str(v).strip()


def attrs_to_notice(attrs: dict[str, Any]) -> NoticeData:
    """Map one ArcGIS feature → NoticeData."""
    parcel_id = _str(attrs.get("parcel_id") or attrs.get("gis_parcel_id"))
    situs = _title(attrs.get("situs"))
    city = _title(attrs.get("po_name"))
    zip_code = _str(attrs.get("zip"))
    lat = _str(attrs.get("latitude"))
    lng = _str(attrs.get("longitude"))
    due = attrs.get("due_amount")
    bill_count = attrs.get("bill_count")
    total_value = attrs.get("amt_totalvalue")
    proptype = _str(attrs.get("proptype"))
    proplabel = _str(attrs.get("proplabel"))
    bedrooms = attrs.get("num_bedrooms")
    bathrooms = attrs.get("cnt_fullbaths")
    halfbaths = attrs.get("cnt_halfbaths")
    bpo_pdf = _str(attrs.get("doc_path"))

    # Total bath count = full + 0.5 * half (DataSift convention)
    bath_value = ""
    if bathrooms is not None or halfbaths is not None:
        total = float(bathrooms or 0) + 0.5 * float(halfbaths or 0)
        # Render as int if whole, else as float
        bath_value = str(int(total)) if total == int(total) else str(total)

    notice = NoticeData(
        county="Mecklenburg",
        state="NC",
        notice_type="tax_sale",
        date_added=datetime.now().strftime("%Y-%m-%d"),
        address=situs,
        city=city,
        zip=zip_code,
        latitude=lat,
        longitude=lng,
        parcel_id=parcel_id,
        tax_delinquent_amount=_str(due),
        tax_delinquent_years=_str(bill_count),
        estimated_value=_str(total_value),
        property_type=proplabel or proptype,  # "Land Only" is more specific than "Residential"
        bedrooms=_str(bedrooms),
        bathrooms=bath_value,
        report_url=bpo_pdf,
        # Deep-link back to the parcel — ArcGIS doesn't expose a per-feature
        # URL, but the parcel ID is enough to re-find via the experience map.
        source_url=(
            f"https://meckags.mecklenburgcountync.gov/server/rest/services/"
            f"TaxForeclosures/MapServer/0/query?where=parcel_id%3D%27{parcel_id}%27"
            f"&outFields=*&f=html"
        ) if parcel_id else "",
        raw_text=(
            f"In-rem tax foreclosure (Mecklenburg County NC). "
            f"Parcel {parcel_id} at {situs}, {city} {zip_code}. "
            f"Amount due: ${_str(due)} across {_str(bill_count)} unpaid tax bill(s). "
            f"Property type: {proptype or proplabel}. "
            f"Assessed value: ${_str(total_value)}. "
            f"Attorney: {_str(attrs.get('attorney'))}. "
        ),
    )
    return notice


# ── Public entry ─────────────────────────────────────────────────────


def scrape_mecklenburg_tax_foreclosures(
    *,
    include_vacant: bool = False,
    include_commercial: bool = False,
    seen_ids: dict[str, str] | None = None,
    max_records: int = 0,
) -> list[NoticeData]:
    """Fetch Mecklenburg in-rem tax foreclosures, filter, return NoticeData.

    Args:
        include_vacant: if False (default), drop "Land Only" parcels
        include_commercial: if False (default), drop Commercial properties
        seen_ids: cross-run dedup cache keyed by parcel_id. If None, loaded
            from disk. Records already in the cache are skipped.
        max_records: if > 0, stop after this many records (smoke testing).
    """
    if seen_ids is None:
        seen_ids = load_seen_ids()
    logger.info(
        "Mecklenburg tax: %d previously-seen parcel(s) in cache",
        len(seen_ids),
    )

    try:
        attrs_list = fetch_all_features()
    except Exception:
        logger.exception("Mecklenburg tax: feature fetch failed")
        return []

    logger.info("Mecklenburg tax: %d total parcels returned by layer", len(attrs_list))

    kept: list[NoticeData] = []
    filtered_vacant = filtered_commercial = filtered_seen = 0

    for attrs in attrs_list:
        proptype = _str(attrs.get("proptype")).lower()
        proplabel = _str(attrs.get("proplabel")).lower()
        parcel_id = _str(attrs.get("parcel_id") or attrs.get("gis_parcel_id"))

        if not include_vacant and proplabel in _LAND_ONLY_PROPLABEL:
            filtered_vacant += 1
            continue
        if not include_commercial and proptype in _COMMERCIAL:
            filtered_commercial += 1
            continue
        if parcel_id and parcel_id in seen_ids:
            filtered_seen += 1
            continue

        notice = attrs_to_notice(attrs)
        kept.append(notice)
        if parcel_id:
            seen_ids[parcel_id] = notice.date_added
        if max_records and len(kept) >= max_records:
            break

    save_seen_ids(seen_ids)
    save_last_run_date()

    logger.info(
        "Mecklenburg tax: kept %d (filtered: vacant=%d commercial=%d seen=%d)",
        len(kept), filtered_vacant, filtered_commercial, filtered_seen,
    )
    return kept
