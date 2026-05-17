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

    eCourts gives names like "Helen Barbara Barlow" → ("HELEN", "BARBARA", "BARLOW").
    Single-token names (rare) → ("", "", name).
    Two tokens → ("first", "", "last").
    """
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

    Returns:
      1.0  - first AND last token both appear in owner name (strong match)
      0.7  - last token + first initial (or initial only) match
      0.0  - lastname mismatch (we never call this with mismatched lastnames,
             but defensive)
    """
    d_tokens = _normalize_name(decedent).split()
    o_tokens = _normalize_name(owner_fullname).split()
    if not d_tokens or not o_tokens:
        return 0.0
    d_last = d_tokens[-1]
    d_first = d_tokens[0] if len(d_tokens) > 1 else ""
    o_set = set(o_tokens)
    if d_last not in o_set:
        return 0.0
    if not d_first:
        return 0.6  # lastname-only decedent; lower confidence
    if d_first in o_set:
        return 1.0
    # Initial match — owner has "B BELL" or "BRENDA J BELL" and decedent is "Brenda Bell"
    d_first_initial = d_first[0]
    for t in o_tokens:
        if t == d_first_initial or (len(t) >= 1 and t[0] == d_first_initial and len(t) <= 2):
            return 0.7
    return 0.0


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


# ── Public entry ─────────────────────────────────────────────────────


# County → backend function. Add new counties here as they're built.
_LOOKUP_BY_COUNTY = {
    "mecklenburg": _lookup_mecklenburg,
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
        # Check known 2-word Mecklenburg cities
        TWO_WORD_CITIES = {"MINT HILL"}
        last_two = " ".join(tokens[-2:]).upper()
        if last_two in TWO_WORD_CITIES:
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
                if " ".join(m_tokens[-2:]) in TWO_WORD_CITIES:
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
            # If we have a separate mailing address, route it into owner_*
            # so the contact-mailing path picks it up. (For probate the
            # PR's address is the contact target; if GIS owner mailing differs
            # from situs, it's likely the heir/PR's mailing.)
            if c.mailing_address and not _addresses_match(c.situs_address, c.mailing_address):
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
