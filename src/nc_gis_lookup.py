"""NC county GIS lookup — search property records by decedent name.

Purpose: probate qualification. eCourts gives us a decedent name but no
property. We use the county's public GIS to find every parcel they owned,
then disqualify any that look heir-occupied (executor's mailing address
matches the property address — they live there, won't sell).

Per-county strategy:
- Mecklenburg → polaris3g.mecklenburgcountync.gov/api/bolt (custom JSON,
  best-in-class data quality, supports lastname+firstname search)
- Other 6 counties → standard ArcGIS FeatureServer endpoints (TBD)

The output of `lookup_properties(decedent_name, county)` is a list of
PropertyCandidate dicts with the fields the pipeline needs to decide
keep / drop.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ── Output dataclass ──────────────────────────────────────────────────


@dataclass
class PropertyCandidate:
    """One parcel found by name search in a county GIS."""
    county: str
    pid: str
    owner_name: str
    situs_address: str          # Property location ("123 Main St City NC")
    mailing_address: str        # Where the tax bill goes
    use_code: str               # County-specific (e.g. polaris3g "R100")
    use_description: str
    market_value: float | None
    year_built: int | None
    bedrooms: int | None
    bathrooms: float | None
    living_sqft: int | None
    lot_area: float | None
    sale_date: str | None
    sale_price: float | None
    # Derived heir-occupancy signal — TRUE means likely vacant or non-heir-occupied (KEEP).
    # FALSE means mailing address matches property address (likely heir lives there → DROP).
    owner_offsite: bool = False
    # Derived land-class flags
    is_residential: bool = False
    is_vacant_land: bool = False
    is_commercial: bool = False
    # Score 0.0-1.0 — how confidently the parcel owner matches the decedent name
    match_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    # Optional explicit overrides for situs city/zip when the situs string
    # itself doesn't contain them (e.g. Cabarrus DataExplorerSearch returns
    # street separately from city/zip).
    situs_city_override: str = ""
    situs_zip_override: str = ""


# ── Name parsing helpers ──────────────────────────────────────────────


# Words to drop from a decedent name before splitting (suffixes, prefixes)
_NAME_NOISE_RE = re.compile(
    r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR|REV|HON|ESQ|MD|PHD|DDS)\.?\b",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    """Strip suffixes/honorifics, collapse whitespace, uppercase."""
    n = _NAME_NOISE_RE.sub("", name or "")
    n = re.sub(r"[^\w\s'-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip().upper()
    return n


def split_decedent_name(name: str) -> tuple[str, str, str]:
    """Best-effort split into (first, middle, last).

    Handles BOTH formats:
    - "Helen Barbara Barlow"        → ("HELEN", "BARBARA", "BARLOW")
    - "Barlow, Helen Barbara"       → ("HELEN", "BARBARA", "BARLOW")  (Tyler API)
    - "Thrower, James W Jr."        → ("JAMES", "W", "THROWER")        (suffix stripped first)
    Single-token names → ("", "", name).
    """
    if not name:
        return ("", "", "")
    # Comma format: "Last, First Middle" — split on comma BEFORE normalizing
    raw = name.strip()
    if "," in raw:
        last_part, _, first_part = raw.partition(",")
        # Suffixes in first_part are handled by _normalize_name's noise strip
        last = _normalize_name(last_part)
        first_mid = _normalize_name(first_part)
        first_tokens = first_mid.split()
        if not first_tokens:
            return ("", "", last)
        if len(first_tokens) == 1:
            return (first_tokens[0], "", last)
        return (first_tokens[0], " ".join(first_tokens[1:]), last)
    # No comma — treat as "First Middle Last"
    norm = _normalize_name(name)
    if not norm:
        return ("", "", "")
    parts = norm.split()
    if len(parts) == 1:
        return ("", "", parts[0])
    if len(parts) == 2:
        return (parts[0], "", parts[1])
    return (parts[0], " ".join(parts[1:-1]), parts[-1])


def _name_match_score(decedent: str, owner_fullname: str) -> float:
    """Score how confidently the owner name matches the decedent.

    Handles BOTH name formats:
    - "Carroll, Iris Jenelle" (Tyler API format — lastname before comma)
    - "Iris Jenelle Carroll" (space-separated, last token is lastname)

    Returns:
      1.0  - first AND last name both appear in owner name (strong match)
      0.7  - lastname + first initial match (e.g. "CARROLL IRIS J" matches
             decedent Iris Jenelle Carroll)
      0.6  - lastname-only decedent (no firstname available)
      0.0  - lastname mismatch
    """
    # Pull decedent's first + last using the same comma-aware logic as split_decedent_name
    d_first, _d_middle, d_last = split_decedent_name(decedent)
    if not d_last:
        return 0.0
    o_tokens = _normalize_name(owner_fullname).split()
    if not o_tokens:
        return 0.0
    o_set = set(o_tokens)
    if d_last not in o_set:
        return 0.0
    if not d_first:
        return 0.6  # lastname-only decedent; lower confidence
    if d_first in o_set:
        return 1.0
    # Initial match — owner has "CARROLL IRIS J" or "CARROLL I J" and decedent is "Iris J Carroll"
    d_first_initial = d_first[0]
    for t in o_tokens:
        if t == d_first_initial:
            return 0.7
        if len(t) <= 2 and t[0] == d_first_initial:
            return 0.7
    # No first-name match — return 0.4 (lastname-only) so caller can decide
    # whether to keep it. With min_score=0.5 it will be dropped, with 0.4 kept.
    return 0.4


# ── Address comparison helpers ────────────────────────────────────────


_ADDR_NOISE_RE = re.compile(r"[.,#]")


def _norm_street(addr: str) -> str:
    """Normalize a street address for comparison (drop city/state/zip + punct)."""
    if not addr:
        return ""
    s = _ADDR_NOISE_RE.sub(" ", addr.upper())
    s = re.sub(r"\b(NC|NORTH\s+CAROLINA|SC|GA|TN|VA)\b.*", "", s)
    s = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", s)
    # Common abbreviations
    repl = {
        " STREET": " ST", " AVENUE": " AVE", " BOULEVARD": " BLVD",
        " ROAD": " RD", " DRIVE": " DR", " LANE": " LN", " COURT": " CT",
        " PLACE": " PL", " PARKWAY": " PKWY", " HIGHWAY": " HWY",
        " CIRCLE": " CIR", " TERRACE": " TER",
    }
    for long, short in repl.items():
        s = s.replace(long, short)
    return re.sub(r"\s+", " ", s).strip()


def _addresses_match(situs: str, mailing: str) -> bool:
    """Return True if the two addresses look like the same physical location.

    We compare just the street portion (house# + street name) — city/zip can
    differ slightly between county records and tax-billing system.
    """
    a = _norm_street(situs)
    b = _norm_street(mailing)
    if not a or not b:
        return False
    # Take the first 4 tokens — usually "1234 MAIN ST"
    a_head = " ".join(a.split()[:4])
    b_head = " ".join(b.split()[:4])
    if a_head == b_head:
        return True
    # Or, the house number + first street word
    a_two = " ".join(a.split()[:2])
    b_two = " ".join(b.split()[:2])
    return a_two == b_two and len(a_two) > 3


# ── Mecklenburg County (polaris3g) ────────────────────────────────────


_POLARIS3G_BASE = "https://polaris3g.mecklenburgcountync.gov/api/bolt"
_POLARIS3G_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
    "Referer": "https://polaris3g.mecklenburgcountync.gov/",
}


def _polaris3g_search(
    *,
    lastname: str,
    firstname: str = "",
    max_pages: int = 20,
    page_size: int = 20,
) -> list[dict]:
    """Page through /api/bolt for an owner name. Returns raw parcel dicts."""
    if not lastname:
        return []
    out: list[dict] = []
    session = requests.Session()
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"lastname": lastname, "page": page}
        if firstname:
            params["firstname"] = firstname
        try:
            r = session.get(
                _POLARIS3G_BASE,
                params=params,
                headers=_POLARIS3G_HEADERS,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error("polaris3g: request failed (page %d): %s", page, e)
            break
        if r.status_code != 200:
            logger.error("polaris3g: HTTP %d on page %d", r.status_code, page)
            break
        try:
            rows = r.json()
        except ValueError:
            logger.error("polaris3g: invalid JSON on page %d", page)
            break
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < page_size:
            break
        time.sleep(0.7)
    return out


# Polaris3g land_use_code prefixes (simplified — see Mecklenburg county docs)
_POLARIS3G_VACANT_PREFIXES = ("V", "AGV", "00")  # vacant land
_POLARIS3G_RESIDENTIAL_PREFIXES = ("R",)          # R100, R122, ...
_POLARIS3G_COMMERCIAL_PREFIXES = ("C", "O", "I")  # commercial / office / industrial


def simplify_use_code(use_code: str, use_description: str = "", county: str = "") -> str:
    """Map a county-specific use_code / description to user's bucket.

    Per the user's FTM_2026_NC Estates manual file, property use is one of:
    SFR, MH, Vacant Land, MH/Vacant, Condo, Townhouse, Commercial.
    Returns empty string when no mapping fits.

    Each NC county uses a different scheme:
    - Mecklenburg polaris3g: R100/R200/R300/V*/C*/O*/I*
    - Cabarrus:              'V' (vacant) or 'I' (improved — assume residential)
    - Catawba:               zoning (R-20, R-40)
    - Lincoln:               ZONING + VACANT flag ('YES'/'NO' in desc field)
    - Gaston:                DESC1_DESC text ('Residential 1 Family', etc)
    - Iredell:               Land_Use_Code (0100 = SFH, 0122 = Waterfront)
    - Rowan:                 NEIGCLAS — no real use field; default to SFR
    """
    code = (use_code or "").strip().upper()
    desc = (use_description or "").strip().upper()
    cty = (county or "").strip().lower()

    if not code and not desc and not cty:
        return ""

    # Per-county short-circuits BEFORE the polaris3g logic
    if cty == "cabarrus":
        if code == "V":
            return "Vacant Land"
        if code == "I":
            return "SFR"  # 'Improved' — assume residential default
        return ""
    if cty == "lincoln":
        # Lincoln stores 'YES'/'NO' in the desc field (VACANT flag)
        if desc == "YES":
            return "Vacant Land"
        if code.startswith("MH") or "MOBILE" in desc:
            return "MH"
        if code.startswith("R"):
            return "SFR"
        return ""
    if cty == "catawba":
        # zoning codes like R-20, R-40, R-3, RU40 — all residential
        if code.startswith("R"):
            return "SFR"
        return ""
    if cty == "iredell":
        if code.startswith("01"):
            return "SFR"
        if code.startswith("02"):
            return "MH"
        if code.startswith("00"):
            return "Vacant Land"
        return ""
    if cty == "rowan":
        # NEIGCLAS isn't a use code; default residential when we have anything
        return "SFR" if (code or desc) else ""
    if cty == "gaston":
        if "MOBILE HOME" in desc or "MANUFACTURED" in desc:
            return "MH"
        if "RESIDENTIAL" in desc or "SINGLE FAMILY" in desc:
            return "SFR"
        if "VACANT" in desc:
            return "Vacant Land"
        if "COMMERCIAL" in desc or "OFFICE" in desc or "INDUSTRIAL" in desc:
            return "Commercial"
        return ""

    # Default (Mecklenburg / polaris3g style)
    if "MOBILE HOME" in desc or "MANUFACTURED" in desc or code.startswith("R200"):
        return "MH"
    if "CONDOMINIUM" in desc or code.startswith("R300"):
        return "Condo"
    if "TOWN HOUSE" in desc or "TOWNHOUSE" in desc or code.startswith("R309"):
        return "Townhouse"
    if code.startswith("R100") or code.startswith("R1") or "SINGLE FAMILY" in desc:
        return "SFR"
    if any(code.startswith(p) for p in _POLARIS3G_VACANT_PREFIXES) or "VACANT" in desc:
        return "Vacant Land"
    if any(code.startswith(p) for p in _POLARIS3G_COMMERCIAL_PREFIXES):
        return "Commercial"
    if code.startswith("R"):
        return "Residential"
    return ""


def _polaris3g_to_candidate(rec: dict, county: str, decedent_name: str) -> PropertyCandidate | None:
    """Convert one polaris3g API record → PropertyCandidate. Returns None if unusable."""
    owners = rec.get("owner") or []
    if not owners:
        return None
    primary = owners[0] or {}

    fullname = (primary.get("fullname") or "").strip()
    mailing = (primary.get("mailing_address") or "").strip()
    situs = ((rec.get("situs") or [""])[0] or "").strip()
    use_code = (rec.get("land_use_code") or "").strip().upper()
    use_desc = (rec.get("land_use_desc") or "").strip()

    # Drop parcels with no usable property address (some condo/vacant entries
    # have only an owner mailing and no situs)
    if not situs:
        return None

    bldg = (rec.get("bldg") or [{}])[0] or {}

    score = _name_match_score(decedent_name, fullname)

    return PropertyCandidate(
        county=county,
        pid=str(rec.get("pid") or rec.get("gisid") or ""),
        owner_name=fullname,
        situs_address=situs,
        mailing_address=mailing,
        use_code=use_code,
        use_description=use_desc,
        market_value=_safe_float(rec.get("market_value")),
        year_built=_safe_int(bldg.get("year_built")),
        bedrooms=_safe_int(bldg.get("bedrooms")),
        bathrooms=_safe_float(bldg.get("full_baths")),
        living_sqft=_safe_int(bldg.get("total_sqft")),
        lot_area=_safe_float(rec.get("land_area")),
        sale_date=str(rec.get("sale_date") or "")[:10] or None,
        sale_price=_safe_float(rec.get("sale_price")),
        owner_offsite=not _addresses_match(situs, mailing),
        is_residential=use_code.startswith(_POLARIS3G_RESIDENTIAL_PREFIXES),
        is_vacant_land=any(use_code.startswith(p) for p in _POLARIS3G_VACANT_PREFIXES),
        is_commercial=any(use_code.startswith(p) for p in _POLARIS3G_COMMERCIAL_PREFIXES),
        match_score=score,
        raw=rec,
    )


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _lookup_mecklenburg(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    """Find Mecklenburg parcels owned by the decedent via polaris3g name search.

    Strategy:
    1. Split name into (first, middle, last).
    2. Query polaris3g first with lastname+firstname (high precision).
    3. If <2 hits, broaden to lastname only and keep records where the
       first or middle initial matches the decedent's first/middle.
    4. Score every candidate by token overlap with the decedent name and
       drop anything below `min_score` (default 0.5 — at least 2 tokens
       overlap for a 3-token name).
    """
    first, middle, last = split_decedent_name(decedent_name)
    if not last:
        logger.info("polaris3g: no parseable lastname from %r", decedent_name)
        return []

    raw_rows = _polaris3g_search(lastname=last, firstname=first)
    if len(raw_rows) < 2 and first:
        # Broaden — drop firstname filter (sometimes owner is listed by middle)
        logger.info("polaris3g: precision search gave %d hits, broadening to lastname-only", len(raw_rows))
        broader = _polaris3g_search(lastname=last)
        # Dedup by pid
        seen_pids = {r.get("pid") for r in raw_rows}
        for r in broader:
            if r.get("pid") not in seen_pids:
                raw_rows.append(r)

    candidates: list[PropertyCandidate] = []
    for rec in raw_rows:
        c = _polaris3g_to_candidate(rec, "Mecklenburg", decedent_name)
        if not c:
            continue
        if c.match_score < min_score:
            continue
        candidates.append(c)
    # Sort by match score descending then market_value descending
    candidates.sort(key=lambda c: (-c.match_score, -(c.market_value or 0)))
    logger.info(
        "polaris3g: %r → %d raw rows → %d scoring matches",
        decedent_name, len(raw_rows), len(candidates),
    )
    return candidates


# ── ArcGIS REST search (other 6 NC counties) ─────────────────────────
#
# Cabarrus, Catawba, Gaston, Iredell, Lincoln, Rowan all expose standard
# Esri ArcGIS FeatureServer / MapServer endpoints. The query pattern is:
#   {base}/query?where=<OWNER_FIELD> LIKE 'NAME%'&outFields=*&f=json
# Each county uses different field names — captured in _ARCGIS_CONFIG below.


_ARCGIS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
}


# Per-county config: how to query + which fields to read.
# - url:        FeatureServer/MapServer layer URL ending in /<layer_index>
# - owner_fields: list of fields to OR-search on (some counties have OWNNAME + OWN2)
# - mailing_fields: ordered list of fields composing the mailing address
#                  (line1, line2, city, state, zip)
# - situs_fields: ordered list of fields composing the property address.
#                If multiple, they're concatenated with spaces. None means
#                the county doesn't expose a single situs field (Cabarrus).
# - parcel_field: the parcel ID field
# - use_field:    the use-code/description field (None means use vacant
#                inference from total value)
# - use_desc_field: optional secondary descriptive field
_ARCGIS_CONFIG: dict[str, dict] = {
    "rowan": {
        "url": "https://gis.rowancountync.gov/arcgis/rest/services/Public/MapViewer/MapServer/9",
        "owner_fields": ["OWNNAME", "OWN2"],
        "mailing_fields": ["TAXADD1", None, "CITY", "STATE", "ZIPCODE"],
        "situs_fields": ["PROP_ADDRESS"],
        "parcel_field": "PARCEL_ID",
        "use_field": None,
        "use_desc_field": "NEIGCLAS",
    },
    "cabarrus": {
        "url": "https://location.cabarruscounty.us/arcgisservices/rest/services/Tax_Parcels_Full/MapServer/0",
        "owner_fields": ["AcctName1", "AcctName2"],
        "mailing_fields": ["MailAddr1", "MailAddr2", "MailCity", "MailState", "MailZipCode"],
        # Cabarrus doesn't expose a situs/property address — best we have is
        # LegalDesc (e.g. "112 ST MARY ST N W (LT 4 BLK P)") which loosely
        # contains the street. We surface it as the address.
        "situs_fields": ["LegalDesc"],
        "parcel_field": "PIN",
        "use_field": "VacantOrImproved",  # 'V' or 'I'
        "use_desc_field": None,
    },
    "gaston": {
        "url": "https://services6.arcgis.com/2mzSgEVuNJwBvEDM/arcgis/rest/services/Gaston_County_Parcels/FeatureServer/0",
        "owner_fields": ["CURR_NAME1", "CURR_NAME2"],
        "mailing_fields": ["CURR_ADDR1", "CURR_ADDR2", "CURR_CITY", "CURR_STATE", "CURR_ZIPCO"],
        "situs_fields": ["PHYSSTRADD"],
        "parcel_field": "PIN",
        "use_field": "DESC1_DESC",
        "use_desc_field": None,
    },
    "catawba": {
        "url": "https://services1.arcgis.com/aT1T0pU1ZdpuDk1t/arcgis/rest/services/PP3_Q1_Map_WFL1/FeatureServer/5",
        "owner_fields": ["owner", "owner2"],
        "mailing_fields": ["address", "address2", "city", "state", "zip"],
        "situs_fields": ["paddress"],
        "parcel_field": "PIN",
        "use_field": "zoning",
        "use_desc_field": None,
    },
    "iredell": {
        "url": "https://maps.iredellcountync.gov/server/rest/services/Data/TaxSQL_Parcels/FeatureServer/0",
        "owner_fields": ["Name", "Jan1Own2"],
        "mailing_fields": ["ADD1", "ADD2", "CITY", "STATE", "ZIP"],
        "situs_fields": ["HouseNumber", "SDIR", "STREET", "STYPE", "ST_SUFFIX"],
        "parcel_field": "PIN",
        "use_field": "Land_Use_Code",
        "use_desc_field": "Building_Use",
    },
    "lincoln": {
        "url": "https://arcgisserver.lincolncountync.gov/arcgis/rest/services/Server_TaxParcelViewerSP/MapServer/0",
        "owner_fields": ["NAME1", "NAME2"],
        "mailing_fields": ["ADDRESS1", "ADDRESS2", "CITY", "STATE", "ZIP"],
        "situs_fields": ["PHYSICALADDR"],
        "parcel_field": "PIN",
        "use_field": "ZONING",
        "use_desc_field": "VACANT",  # "YES"/"NO"
    },
}


def _compose_address(rec: dict, fields: list[str | None]) -> str:
    """Compose a single address line from a list of field names (None = skip)."""
    parts: list[str] = []
    for f in fields:
        if not f:
            continue
        val = rec.get(f)
        if val is None:
            continue
        s = str(val).strip()
        if s and s.lower() != "null":
            parts.append(s)
    return " ".join(parts).strip()


def _arcgis_query(
    url: str,
    owner_field: str,
    name_token: str,
    *,
    record_limit: int = 100,
) -> list[dict]:
    """Run a single ArcGIS REST query and return the attribute dicts.

    Uses LIKE 'NAME%' to match owners whose names start with the token.
    """
    if not name_token:
        return []
    where = f"UPPER({owner_field}) LIKE '{name_token.upper()}%'"
    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": str(record_limit),
    }
    try:
        r = requests.get(url + "/query", params=params, headers=_ARCGIS_HEADERS, timeout=30)
    except requests.RequestException as e:
        logger.warning("ArcGIS: query failed at %s: %s", url, e)
        return []
    if r.status_code != 200:
        logger.warning("ArcGIS: HTTP %d at %s", r.status_code, url)
        return []
    try:
        data = r.json()
    except ValueError:
        logger.warning("ArcGIS: invalid JSON at %s", url)
        return []
    if "error" in data:
        logger.warning("ArcGIS error at %s: %s", url, data["error"])
        return []
    return [f.get("attributes") or {} for f in (data.get("features") or [])]


_CABARRUS_ADDR_URL = (
    "https://location.cabarruscounty.us/arcgisservices/rest/services/"
    "DataExplorerSearch/FeatureServer/0"
)


def _cabarrus_lookup_situs(pin: str) -> tuple[str, str, str]:
    """Look up real situs address for a Cabarrus parcel by PIN.

    The Tax_Parcels_Full layer only has LegalDesc; this DataExplorerSearch
    layer joins NG911 addresses to parcels via PIN14 and returns con_cat
    (e.g. "16627 HOPEWELL CHURCH RD") + City + Zip.
    Returns (street, city, zip) — empties when no match.
    """
    if not pin:
        return ("", "", "")
    # Normalize PIN — Cabarrus stores both 10-digit dotted (5552060223.00000000)
    # and 14-char (55520602230000). Try the longer form first, then strip dots.
    pin_clean = pin.replace(".", "").strip()
    if not pin_clean.isdigit():
        return ("", "", "")
    # PIN14 is 14 chars, padded with trailing zeros
    pin14 = (pin_clean + "00000000")[:14]
    where = f"PIN14='{pin14}'"
    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = requests.get(_CABARRUS_ADDR_URL + "/query", params=params,
                         headers=_ARCGIS_HEADERS, timeout=20)
    except requests.RequestException:
        return ("", "", "")
    if r.status_code != 200:
        return ("", "", "")
    try:
        data = r.json()
    except ValueError:
        return ("", "", "")
    feats = data.get("features") or []
    if not feats:
        return ("", "", "")
    a = feats[0].get("attributes") or {}
    street = (a.get("con_cat") or "").strip()
    city = (a.get("City") or "").strip()
    zipc = (a.get("Zip") or "").strip()
    return (street, city, zipc)


def _arcgis_to_candidate(
    rec: dict, county: str, decedent_name: str, cfg: dict,
) -> PropertyCandidate | None:
    """Convert one ArcGIS attribute dict → PropertyCandidate. None if unusable."""
    # Owner string — concatenate all owner fields
    owner_parts: list[str] = []
    for f in cfg["owner_fields"]:
        v = rec.get(f)
        if v:
            owner_parts.append(str(v).strip())
    owner_full = " | ".join(owner_parts).strip()
    if not owner_full:
        return None

    score = _name_match_score(decedent_name, owner_full.replace(" | ", " "))
    if score == 0.0:
        return None

    # Mailing address (single line composed)
    mailing = _compose_address(rec, cfg["mailing_fields"])

    # Situs (property address) — may be None (Cabarrus). For multi-field
    # compositions like Iredell (HouseNumber + SDIR + STREET + STYPE), join with spaces.
    situs = _compose_address(rec, cfg["situs_fields"])

    # Parcel ID
    pid = str(rec.get(cfg["parcel_field"]) or "").strip()

    # Cabarrus situs override — Tax_Parcels_Full has only LegalDesc which is
    # garbage as an address ("Lt 138" / "N/O Earnhardt Lake"). Replace with
    # a real street address from the DataExplorerSearch address-points layer.
    situs_city_override = ""
    situs_zip_override = ""
    if county.lower() == "cabarrus" and pid:
        c_street, c_city, c_zip = _cabarrus_lookup_situs(pid)
        if c_street:
            situs = c_street
            situs_city_override = c_city.title()
            situs_zip_override = c_zip
        else:
            # No address-point match — situs is LegalDesc-style garbage.
            # Blank it out so the FTM CSV doesn't show a fake address.
            situs = ""

    # Use code + description
    use_code = str(rec.get(cfg["use_field"]) or "").strip().upper() if cfg.get("use_field") else ""
    use_desc = str(rec.get(cfg["use_desc_field"]) or "").strip() if cfg.get("use_desc_field") else ""

    # Cabarrus special: VacantOrImproved is "V"/"I"
    is_vacant = False
    is_residential = False
    is_commercial = False
    if county.lower() == "cabarrus":
        is_vacant = use_code == "V"
        is_residential = use_code == "I"  # everything else is "improved" — assumed residential
    elif county.lower() == "lincoln":
        # VACANT field is "YES"/"NO"
        is_vacant = use_desc.upper() == "YES"
        is_residential = use_code.startswith("R")
    else:
        # General Esri counties — use description-keyword matching
        desc_upper = (use_desc + " " + use_code).upper()
        is_vacant = "VACANT" in desc_upper or "VAC" in desc_upper
        is_residential = (
            "RESIDENTIAL" in desc_upper or "SINGLE FAMILY" in desc_upper
            or use_code.startswith("R") or "DWELL" in desc_upper
        )
        is_commercial = "COMMERCIAL" in desc_upper or "OFFICE" in desc_upper or "INDUSTRIAL" in desc_upper

    return PropertyCandidate(
        county=county,
        pid=pid,
        owner_name=owner_full,
        situs_address=situs,
        mailing_address=mailing,
        use_code=use_code,
        use_description=use_desc,
        market_value=None,  # ArcGIS counties don't standardize value fields
        year_built=None,
        bedrooms=None,
        bathrooms=None,
        living_sqft=None,
        lot_area=None,
        sale_date=None,
        sale_price=None,
        owner_offsite=not _addresses_match(situs, mailing),
        is_residential=is_residential,
        is_vacant_land=is_vacant,
        is_commercial=is_commercial,
        match_score=score,
        raw=rec,
        situs_city_override=situs_city_override,
        situs_zip_override=situs_zip_override,
    )


def _lookup_arcgis_county(
    decedent_name: str, county_key: str, min_score: float = 0.7,
) -> list[PropertyCandidate]:
    """Generic ArcGIS-backed search — works for the 5 standard-Esri counties."""
    cfg = _ARCGIS_CONFIG.get(county_key)
    if not cfg:
        return []
    first, _middle, last = split_decedent_name(decedent_name)
    if not last:
        return []
    # Search each owner field on lastname
    raw_rows: list[dict] = []
    seen_pids: set[str] = set()
    for owner_field in cfg["owner_fields"]:
        rows = _arcgis_query(cfg["url"], owner_field, last)
        for r in rows:
            pid = str(r.get(cfg["parcel_field"]) or "")
            if pid and pid in seen_pids:
                continue
            seen_pids.add(pid)
            raw_rows.append(r)
    candidates: list[PropertyCandidate] = []
    for rec in raw_rows:
        c = _arcgis_to_candidate(rec, county_key.title(), decedent_name, cfg)
        if not c:
            continue
        if c.match_score < min_score:
            continue
        candidates.append(c)
    candidates.sort(key=lambda c: -c.match_score)
    logger.info(
        "%s GIS: %r → %d raw rows → %d scoring matches",
        county_key.title(), decedent_name, len(raw_rows), len(candidates),
    )
    return candidates


# Per-county adapter functions to register in _LOOKUP_BY_COUNTY
def _lookup_rowan(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "rowan", min_score)


def _lookup_cabarrus(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "cabarrus", min_score)


def _lookup_gaston(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "gaston", min_score)


def _lookup_catawba(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "catawba", min_score)


def _lookup_iredell(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "iredell", min_score)


def _lookup_lincoln(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "lincoln", min_score)


# ── Public entry ─────────────────────────────────────────────────────


# County → backend function. Add new counties here as they're built.
_LOOKUP_BY_COUNTY = {
    "mecklenburg": _lookup_mecklenburg,
    "rowan":       _lookup_rowan,
    "cabarrus":    _lookup_cabarrus,
    "gaston":      _lookup_gaston,
    "catawba":     _lookup_catawba,
    "iredell":     _lookup_iredell,
    "lincoln":     _lookup_lincoln,
}


def lookup_properties(
    decedent_name: str,
    county: str,
    *,
    min_score: float = 0.7,
) -> list[PropertyCandidate]:
    """Return parcels owned by the decedent in the given county.

    Returns [] when the county isn't yet supported (graceful no-op so the
    pipeline keeps moving while we roll out more counties).
    """
    if not decedent_name or not county:
        return []
    fn = _LOOKUP_BY_COUNTY.get(county.strip().lower())
    if fn is None:
        logger.debug("nc_gis_lookup: county %r not yet supported", county)
        return []
    try:
        return fn(decedent_name, min_score=min_score)
    except Exception:
        logger.exception("nc_gis_lookup: %s search for %r failed", county, decedent_name)
        return []


def filter_for_lead_quality(
    candidates: list[PropertyCandidate],
    *,
    drop_heir_occupied: bool = True,
    drop_commercial: bool = True,
    decedent_match_threshold: float = 0.9,
) -> list[PropertyCandidate]:
    """Apply user's heir-occupancy + buy-box filters to a candidate list.

    Heir-occupancy heuristic (the key probate signal):

      KEEP when:
        - The GIS owner is still the decedent (probate-in-progress; title
          hasn't transferred yet). Identified by `match_score >= 0.9`,
          meaning both first and last name match. These are the highest-
          value leads — the decedent lived there, now vacant. Mailing-vs-
          situs match doesn't disqualify them.
        - The GIS owner is someone else AND mailing address differs from
          the property address (offsite owner — could be heir who already
          inherited but lives elsewhere, or a renter situation).

      DROP when:
        - The GIS owner is someone else AND mailing matches property
          address — that someone is living in the property (likely heir
          who already inherited and moved in; they won't sell).
        - Commercial / office / industrial use codes (out of buy box).

    Buy box note: vacant land IS kept (user's NC buy box includes land).
    """
    keep: list[PropertyCandidate] = []
    for c in candidates:
        if drop_commercial and c.is_commercial:
            continue
        # If GIS owner is still the decedent, this IS the probate lead — keep
        if c.match_score >= decedent_match_threshold:
            keep.append(c)
            continue
        # Otherwise (owner differs from decedent), only keep offsite owners
        if drop_heir_occupied and not c.owner_offsite:
            continue
        keep.append(c)
    return keep


# ── Pipeline integration ─────────────────────────────────────────────


# Cache GIS lookups within a single run so we don't re-query for the
# same decedent twice (a name might appear in multiple notice rows).
_LOOKUP_CACHE: dict[tuple[str, str], list["PropertyCandidate"]] = {}


_TWO_WORD_NC_CITIES = {
    "MINT HILL", "MOUNT HOLLY", "HIGH POINT", "WINSTON SALEM",
    "ROCKY MOUNT", "CHINA GROVE", "HOPE MILLS", "GOLD HILL",
    "SCOTLAND NECK", "PINE LEVEL", "OAK ISLAND", "OAK RIDGE",
}


def _candidate_to_address_parts(c: PropertyCandidate) -> tuple[str, str, str]:
    """Split a 'STREET CITY NC ZIP' situs string into (street, city, zip).

    Polaris3g situs strings don't include ZIP. We backfill ZIP from the
    mailing address when the situs city matches the mailing city — for
    owner-occupied properties this is always true; for offsite owners
    we leave ZIP empty (Smarty fills it later in the pipeline).
    """
    s = (c.situs_address or "").strip()
    if not s:
        return ("", "", "")
    # If county lookup provided explicit overrides (e.g. Cabarrus pulls
    # street from one layer and city/zip from another), trust them.
    if c.situs_city_override or c.situs_zip_override:
        return (s.title() if s.isupper() else s, c.situs_city_override, c.situs_zip_override)
    # Pull a trailing ZIP if present in situs (rare on polaris3g)
    zip_m = re.search(r"\b(\d{5}(?:-\d{4})?)\b", s)
    zipc = zip_m.group(1) if zip_m else ""
    s_no_zip = s[: zip_m.start()].strip() if zip_m else s
    # Pull state suffix
    s_no_state = re.sub(r"\s+NC\s*$", "", s_no_zip, flags=re.IGNORECASE).strip()
    tokens = s_no_state.split()
    if len(tokens) >= 3:
        city = tokens[-1]
        street = " ".join(tokens[:-1])
        last_two = " ".join(tokens[-2:]).upper()
        if last_two in _TWO_WORD_NC_CITIES:
            city = " ".join(tokens[-2:])
            street = " ".join(tokens[:-2])
    else:
        street, city = s_no_state, ""

    # ZIP backfill from mailing address when cities match
    if not zipc and c.mailing_address:
        m_zip = re.search(r"\b(\d{5}(?:-\d{4})?)\b", c.mailing_address)
        if m_zip:
            # Extract the mailing city by stripping ZIP, state, then taking
            # the trailing token(s) before state.
            m = c.mailing_address.upper()
            m_no_zip = m[: m_zip.start()].strip()
            m_no_state = re.sub(r"\s+NC\s*$", "", m_no_zip).strip()
            m_tokens = m_no_state.split()
            if m_tokens:
                mailing_city = m_tokens[-1]
                if " ".join(m_tokens[-2:]) in _TWO_WORD_NC_CITIES:
                    mailing_city = " ".join(m_tokens[-2:])
                if city.upper() == mailing_city:
                    zipc = m_zip.group(1)

    return (street.title(), city.title(), zipc)


def expand_notices_with_gis(
    notices: list,
    *,
    notice_types: tuple[str, ...] = ("probate",),
    drop_unmatched: bool = True,
    min_score: float = 0.7,
) -> tuple[list, dict[str, int]]:
    """For each notice with a `decedent_name`, look up parcels and expand.

    Returns (new_notices, stats). Stats has keys: input, expanded_in,
    expanded_out, dropped_no_match, dropped_heir_occupied,
    counties_supported, counties_unsupported.

    Behavior:
    - Probate notices (decedent_name set) in supported counties → run GIS
      lookup → apply heir-occupancy filter → produce 1 output notice per
      qualified parcel (with property address + parcel_id + market value).
    - Notices in unsupported counties pass through unchanged.
    - Notices with no decedent_name pass through unchanged.
    - With `drop_unmatched=True`, probate notices whose GIS lookup
      returned zero qualified parcels are DROPPED (no address → not a lead).
    """
    from copy import copy as _copy  # local import to avoid hard dep at module load

    stats = {
        "input": len(notices),
        "expanded_in": 0,
        "expanded_out": 0,
        "dropped_no_match": 0,
        "dropped_heir_occupied": 0,
        "counties_supported": 0,
        "counties_unsupported": 0,
    }
    out: list = []

    for n in notices:
        county = (getattr(n, "county", "") or "").strip()
        ntype = (getattr(n, "notice_type", "") or "").strip().lower()
        decedent = (getattr(n, "decedent_name", "") or "").strip()
        if not county or ntype not in notice_types or not decedent:
            out.append(n)
            continue
        if county.lower() not in _LOOKUP_BY_COUNTY:
            stats["counties_unsupported"] += 1
            out.append(n)
            continue

        stats["counties_supported"] += 1
        stats["expanded_in"] += 1

        cache_key = (county.lower(), decedent.upper())
        if cache_key in _LOOKUP_CACHE:
            candidates = _LOOKUP_CACHE[cache_key]
        else:
            candidates = lookup_properties(decedent, county, min_score=min_score)
            _LOOKUP_CACHE[cache_key] = candidates

        raw_count = len(candidates)
        kept = filter_for_lead_quality(candidates)
        dropped = raw_count - len(kept)
        stats["dropped_heir_occupied"] += dropped

        if not kept:
            if drop_unmatched:
                stats["dropped_no_match"] += 1
                continue
            out.append(n)
            continue

        for c in kept:
            new_n = _copy(n)
            street, city, zipc = _candidate_to_address_parts(c)
            new_n.address = street
            new_n.city = city
            new_n.zip = zipc
            new_n.state = "NC"
            new_n.parcel_id = c.pid
            new_n.property_use_simple = simplify_use_code(c.use_code, c.use_description, c.county)
            if c.market_value is not None:
                new_n.estimated_value = f"{c.market_value:.0f}"
            if c.year_built is not None:
                new_n.year_built = str(c.year_built)
            if c.bedrooms is not None:
                new_n.bedrooms = str(c.bedrooms)
            if c.bathrooms is not None:
                new_n.bathrooms = str(c.bathrooms)
            if c.living_sqft is not None:
                new_n.sqft = str(c.living_sqft)
            if c.lot_area is not None:
                new_n.lot_size = f"{c.lot_area:.0f}"
            if c.sale_date:
                new_n.mls_last_sold_date = c.sale_date
            if c.sale_price is not None:
                new_n.mls_last_sold_price = f"{c.sale_price:.0f}"
            # For probate notices, DO NOT overwrite owner_* fields here —
            # the executor's mailing (set upstream by ecourts_scraper from
            # the Parties API) is the canonical primary contact. Only
            # populate owner_* when it's empty (e.g. foreclosures from GIS).
            if c.mailing_address and not _addresses_match(c.situs_address, c.mailing_address):
                if not (new_n.owner_street or new_n.owner_name):
                    _populate_mailing(new_n, c.mailing_address)
            out.append(new_n)
            stats["expanded_out"] += 1

    return out, stats


def _populate_mailing(notice, mailing_address: str) -> None:
    """Best-effort parse of 'STREET CITY ST ZIP' → notice.owner_* fields."""
    s = mailing_address.strip()
    zip_m = re.search(r"\b(\d{5}(?:-\d{4})?)\b", s)
    zipc = zip_m.group(1) if zip_m else ""
    s_no_zip = s[: zip_m.start()].strip() if zip_m else s
    # Trailing state
    state_m = re.search(r"\b(NC|SC|GA|TN|VA|FL|NY|TX|CA)\s*$", s_no_zip, re.IGNORECASE)
    state = state_m.group(1).upper() if state_m else ""
    s_no_state = s_no_zip[: state_m.start()].strip() if state_m else s_no_zip
    tokens = s_no_state.split()
    if len(tokens) >= 2:
        city = tokens[-1]
        street = " ".join(tokens[:-1])
    else:
        street, city = s_no_state, ""
    notice.owner_street = street.title()
    notice.owner_city = city.title()
    notice.owner_state = state or "NC"
    notice.owner_zip = zipc
