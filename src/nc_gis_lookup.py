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

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
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
    # TRUE when parcel has multiple owners (e.g. AcctName1 + AcctName2 in
    # Cabarrus, or "|" / "&" separator in single-field counties). Jointly-
    # owned property typically transfers by right of survivorship and isn't
    # part of the probate estate — solely-owned parcels are the real probate
    # leads. Used by main-parcel selection to prefer sole over joint.
    is_jointly_owned: bool = False
    # Score 0.0-1.0 — how confidently the parcel owner matches the decedent name
    match_score: float = 0.0
    # TRUE when the GIS owner shares first+middle+last with the decedent but
    # uses a LATER generational suffix (decedent JR -> deed III, etc.). This
    # is the post-probate transfer pattern: father died, deed updated to the
    # son with the same name + next generation marker. Polish flags these
    # so the user knows the deed already moved to the heir but the property
    # is still a real lead (the heir owns it, may or may not live there).
    is_heir_transferred: bool = False
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
    - "Barlow, Helen Barbara"       → ("HELEN", "BARBARA", "BARLOW")  (Odyssey API)
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
            # Comma was a suffix separator (e.g. "EDWARD EUGENE TAYLOR, II"
            # where _normalize_name dropped the post-comma "II"). Fall back
            # to treating the pre-comma chunk as "First Middle Last".
            parts = last.split()
            if len(parts) == 1:
                return ("", "", parts[0])
            if len(parts) == 2:
                return (parts[0], "", parts[1])
            return (parts[0], " ".join(parts[1:-1]), parts[-1])
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


_MIDDLE_NOISE_TOKENS = {
    "JR", "SR", "II", "III", "IV", "V", "WF", "HSB", "AND", "OR",
    "MR", "MRS", "MS", "DR", "MD", "PHD", "ESQ", "REV",
}


_GENERATIONAL_SUFFIXES = {"SR", "JR", "II", "III", "IV", "V"}
_HEIRS_MARKERS = {"HEIRS", "ESTATE", "ESTATEOF"}


def _extract_suffix(name: str) -> str:
    """Return the generational suffix (SR/JR/II/III/IV/V) in a name, or ''."""
    if not name:
        return ""
    s = re.sub(r"[^\w\s'-]", " ", name.upper())
    for token in s.split():
        if token in _GENERATIONAL_SUFFIXES:
            return token
    return ""


def _split_owner_segments(owner: str) -> list[tuple[str, bool]]:
    """Split a multi-owner GIS string into individual person/entity segments.

    Returns list of (segment, surname_inherited) tuples.
    surname_inherited=True means we faked a surname on a short trailing
    segment — caller should treat that segment with extra suspicion (the
    deed only carried a bare first name and we can't be sure of the
    surname; could be the spouse the surname implies, or someone else
    entirely if the decedent shares a first name with a real co-owner).

    Handles every joint-owner convention we have seen in the 7 NC county
    GIS endpoints:
      - "RUSSELL WILLIAM JR | RUSSELL SYLVANIA WF"   (Cabarrus, polaris3g)
      - "FOX PRESTON R+MARY"                          (Gaston live endpoint)
      - "SMITH JOHN A & SMITH JANE B"                 (most counties)
      - "SMITH JOHN; SMITH JANE"                      (rare, but seen)
      - "SMITH JOHN / SMITH JANE"                     (rare)

    Comma is NOT a separator here — single-owner strings like "SMITH, JOHN
    A" use comma. The decedent-name caller handles comma format separately.
    """
    if not owner:
        return []
    raw = [s.strip() for s in re.split(r"\s*[+&|/;]\s*", owner) if s.strip()]
    if len(raw) < 2:
        return [(r, False) for r in raw]
    first_tokens = raw[0].split()
    if not first_tokens:
        return [(r, False) for r in raw]
    presumed_surname = first_tokens[0].upper()
    out: list[tuple[str, bool]] = [(raw[0], False)]
    for seg in raw[1:]:
        seg_tokens = seg.split()
        has_surname = any(t.upper() == presumed_surname for t in seg_tokens)
        if not has_surname and 1 <= len(seg_tokens) <= 3:
            out.append((f"{first_tokens[0]} {seg}", True))
        else:
            out.append((seg, False))
    return out


def _name_match_score(decedent: str, owner_fullname: str) -> float:
    """Score how confidently the owner name matches the decedent.

    CRITICAL: When BOTH decedent and owner have a middle name/initial,
    they MUST share at least the first letter — otherwise we treat it
    as a different person. This prevents homonym false positives like
    "James Lee Osborne" matching "JAMES D OSBORNE". Exception: when
    the owner string contains "HEIRS" or "ESTATE", relax middle-match
    requirement (data inconsistencies in old probate-tagged records).

    Suffix disambiguation: if decedent has "Sr" and owner has "Jr"
    (or any generational mismatch), return 0 — they're different people
    (Leonard Kinney Sr's parcel vs his son Leonard Jr's parcel).

    Owner strings often contain joint owners separated by "|", "&", "+",
    "/", or ";". We split via _split_owner_segments (which also handles
    surname inheritance for short trailing segments), then score each
    segment independently and take the BEST score. The decedent matching
    ANY individual co-owner is a valid hit; matching scattered tokens
    across multiple co-owners is NOT.
    """
    if not decedent:
        return 0.0
    dec_suffix = _extract_suffix(decedent)
    sub_names = _split_owner_segments(owner_fullname or "")
    best = 0.0
    for sub, surname_inherited in sub_names:
        s = _name_match_score_one(decedent, sub, dec_suffix=dec_suffix)
        # Surname-inheritance guard: when we faked a surname onto a bare
        # first-name trailing segment (e.g. "+MARY" -> "FOX MARY"), the
        # deed only actually said "MARY" — we don't truly know it's the
        # surname. Cap at 0.6 (below typical min_score=0.7) so the match
        # gets treated as "candidate worth a human look" rather than
        # confirmed. Prevents the "Mary, Fox" -> "FOX PRESTON R+MARY"
        # false-positive class flagged in the audit.
        if surname_inherited and s >= 0.9:
            s = 0.6
        if s > best:
            best = s
        if best >= 1.0:
            break
    return best


_GENERATIONAL_ORDER = {"SR": 0, "JR": 1, "II": 2, "III": 3, "IV": 4, "V": 5}


def is_generational_heir_transfer(decedent: str, owner_fullname: str) -> bool:
    """True when the owner name matches the decedent's first+last but uses
    a STRICTLY LATER generational suffix (decedent JR -> deed III). Per-
    segment aware: splits joint-owner strings the same way the matcher
    does, returns True if any segment qualifies.
    """
    if not decedent or not owner_fullname:
        return False
    dec_suffix = _extract_suffix(decedent)
    if not dec_suffix:
        return False
    d_first, _d_middle, d_last = split_decedent_name(decedent)
    if not (d_first and d_last):
        return False
    for sub, _surname_inherited in _split_owner_segments(owner_fullname):
        o_suffix = _extract_suffix(sub)
        if not _is_later_generation(dec_suffix, o_suffix):
            continue
        o_tokens = _normalize_name(sub).split()
        if d_first in o_tokens and d_last in o_tokens:
            return True
    return False


def _is_later_generation(dec_suffix: str, owner_suffix: str) -> bool:
    """True when owner_suffix is strictly LATER in the generational chain
    than dec_suffix (e.g. dec=JR + owner=III = son inherited from father).
    Used by the generational heir-transfer matcher path.
    """
    if not dec_suffix or not owner_suffix:
        return False
    d = _GENERATIONAL_ORDER.get(dec_suffix.upper())
    o = _GENERATIONAL_ORDER.get(owner_suffix.upper())
    if d is None or o is None:
        return False
    return o > d


def _name_match_score_one(decedent: str, owner_fullname: str, dec_suffix: str = "") -> float:
    """Score a single (non-joint) owner name against the decedent."""
    # Suffix disambiguation: Sr vs Jr (or any generational difference)
    # means different people, even if the rest of the name matches.
    o_suffix = _extract_suffix(owner_fullname)
    if dec_suffix and o_suffix and dec_suffix != o_suffix:
        # Generational heir-transfer escape: when the owner is strictly
        # LATER in the generational chain (decedent JR, deed III; or
        # decedent SR, deed JR) AND first + last names match exactly,
        # treat as a post-probate transfer to the next-generation heir.
        # Score 0.75 so it passes min_score=0.7 but stays below an exact
        # match. The caller is expected to set is_heir_transferred=True
        # on the resulting PropertyCandidate via _name_match_score's
        # heir-transfer companion helper.
        if _is_later_generation(dec_suffix, o_suffix):
            d_first, _d_middle, d_last = split_decedent_name(decedent)
            o_tokens = _normalize_name(owner_fullname).split()
            if (
                d_first and d_last
                and d_last in o_tokens
                and d_first in o_tokens
            ):
                return 0.75
        return 0.0

    d_first, d_middle, d_last = split_decedent_name(decedent)
    if not d_last:
        return 0.0
    o_tokens = _normalize_name(owner_fullname).split()
    if not o_tokens:
        return 0.0
    o_set = set(o_tokens)
    if d_last not in o_set:
        return 0.0
    if not d_first:
        return 0.6

    first_full_match = d_first in o_set
    first_initial_match = False
    if not first_full_match:
        # Guard against the "JOANIE D matches Doris J" false positive:
        # if the owner has a LONGER alphabetic token that's clearly the
        # actual first name (and it's not ours), the bare-initial match
        # on a separate single-char token is meaningless.
        competing_first_names = [
            t for t in o_tokens
            if t != d_last and len(t) > 2 and t.isalpha()
            and t not in _MIDDLE_NOISE_TOKENS
            and t not in _HEIRS_MARKERS
            and t not in {"TRUST", "TRUSTEE", "LIVING", "REVOC", "REVOCABLE"}
        ]
        if competing_first_names:
            # Estate-marker escape: when owner is clearly the decedent's
            # estate (contains HEIRS/ESTATE) AND a competing token shares
            # the 4-char prefix of d_first, treat as a spelling variant
            # of the decedent. Catches Cabarrus 26E000656-120 / Sega
            # Paulene: owner "HUNTER VERNICE SR | SEGA PAULINE E ESTATE"
            # — Paulene vs Pauline is a deed-spelling drift on the same
            # person. Accept with confidence 0.7 (above min_score, below
            # exact-match 1.0).
            if (
                o_set & _HEIRS_MARKERS
                and d_first
                and len(d_first) >= 4
            ):
                d_prefix = d_first[:4]
                for cf in competing_first_names:
                    if len(cf) >= 4 and cf[:4] == d_prefix:
                        return 0.7
            return 0.4  # owner has its own first name, ours isn't it

        d_first_initial = d_first[0]
        for t in o_tokens:
            if t == d_first_initial or (len(t) <= 2 and t[0] == d_first_initial):
                first_initial_match = True
                break
    if not first_full_match and not first_initial_match:
        return 0.4

    # MIDDLE-NAME CHECK — when both sides have a middle, they must share
    # at least the first letter of ANY decedent middle word. Compound
    # middles like "Joyce Stafford" must match owner "S" (= Stafford
    # initial) — common pattern where maiden name is used as middle.
    if d_middle:
        d_middle_words = [w for w in d_middle.split() if w]
        d_middle_initials = {w[0] for w in d_middle_words}
        owner_middle_tokens: list[str] = []
        first_seen = False
        last_seen = False
        for t in o_tokens:
            if t == d_last and not last_seen:
                last_seen = True
                continue
            if t == d_first and not first_seen and first_full_match:
                first_seen = True
                continue
            if first_initial_match and not first_full_match and not first_seen:
                d_first_initial = d_first[0]
                if t == d_first_initial or (len(t) <= 2 and t[0] == d_first_initial):
                    first_seen = True
                    continue
            if t in _MIDDLE_NOISE_TOKENS:
                continue
            # HEIRS/ESTATE/ESTATEOF aren't middle names — they're trust-
            # status markers. Skip so they don't get scored as a
            # competing middle (e.g. "SMITH JOHN HEIRS" for decedent
            # "Smith, John A" should NOT treat "HEIRS" as a clashing
            # middle and downgrade the match).
            if t in _HEIRS_MARKERS:
                continue
            owner_middle_tokens.append(t)
        if owner_middle_tokens:
            owner_middle_matches = False
            for t in owner_middle_tokens:
                # Owner has full middle name matching any decedent middle word
                if t in d_middle_words:
                    owner_middle_matches = True
                    break
                # Owner has single-letter initial matching any decedent middle word's first letter
                if len(t) == 1 and t in d_middle_initials:
                    owner_middle_matches = True
                    break
                # Decedent has single-letter middle matching owner full middle's first letter
                if any(len(w) == 1 and t[0] == w for w in d_middle_words):
                    owner_middle_matches = True
                    break
            if not owner_middle_matches:
                # HEIRS / ESTATE marker partial-accept: when the owner
                # string contains HEIRS/ESTATE the parcel is held in
                # an estate, but the middle name we have for the
                # current decedent doesn't match the deed -- could be
                # the right family (e.g. deed never updated after a
                # prior generation's probate) OR a different "John
                # Cowan" in the same county. Score below min_score so
                # the polish step drops the row. Per Oren's audit of
                # Cowan 26E000686-170 (Catawba: COWAN JOHN B HEIRS vs
                # court decedent "Cowan, John Williams Jr."), the
                # false-positive risk on these is high enough that
                # auto-dropping is the right call. Loses ~5% of real
                # deed-never-updated inheritance cases.
                if o_set & _HEIRS_MARKERS:
                    return 0.6
                return 0.4

    if first_full_match:
        return 1.0
    return 0.7


# ── Co-owner vs beneficiary cross-reference ───────────────────────────


def extract_co_owner_names(owner_full: str, decedent_name: str) -> list[str]:
    """From a parcel's joined owner string (e.g. "BONDS BOBBY R | BONDS ELSIE WF"),
    extract the OTHER owner names (not the decedent). Returns a list of
    normalized name strings for downstream matching.

    Drops obvious noise tokens ("WF" = wife, "HB" = husband, "ETUX",
    "& WF", "TRUSTEE", etc.) that some county GIS systems append.

    Suffix-aware: if the decedent is "Kinney, Leonard Sr." and the owner
    string contains "KINNEY LEONARD JR", that entry is the SON (not the
    decedent's own listing), so DON'T skip it — it's a real co-owner.
    """
    if not owner_full:
        return []
    parts = re.split(r"\s*[|&]\s*", owner_full)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return []
    _f, _m, dec_last = split_decedent_name(decedent_name)
    dec_first, _, _ = split_decedent_name(decedent_name)
    dec_suffix = _extract_suffix(decedent_name)
    co_owners: list[str] = []
    for p in parts:
        p_suffix = _extract_suffix(p)
        n = _normalize_name(p)
        tokens = set(n.split()) - _MIDDLE_NOISE_TOKENS - {"WF", "HB", "ETUX", "ETAL", "TRUSTEE", "TR"}
        if not tokens:
            continue
        # Skip if this is the decedent (same last+first AND same/empty suffix).
        # A Jr/Sr suffix difference means it's a relative, NOT the decedent.
        looks_like_decedent = (
            dec_last and dec_first
            and dec_last in tokens and dec_first in tokens
            and (not dec_suffix or not p_suffix or dec_suffix == p_suffix)
        )
        if looks_like_decedent:
            continue
        co_owners.append(n)
    return co_owners


def co_owner_is_beneficiary(co_owner_normalized: str, beneficiaries_json: str) -> bool:
    """Return True when the co-owner's name overlaps a beneficiary in the
    estate's Parties API output. Match logic: both must share the same
    last name AND at least one other token (first name or middle).

    Beneficiaries_json is a JSON list of {name, street, city, state, zip}
    from ecourts_case_api.CaseParty.
    """
    if not co_owner_normalized or not beneficiaries_json:
        return False
    co_tokens = set(co_owner_normalized.split())
    if len(co_tokens) < 2:
        return False
    try:
        bens = json.loads(beneficiaries_json)
    except (ValueError, TypeError):
        return False
    for b in bens:
        bname = _normalize_name(b.get("name") or "")
        if not bname:
            continue
        b_tokens = set(bname.split()) - _MIDDLE_NOISE_TOKENS
        # Last name must appear in both
        overlap = co_tokens & b_tokens
        if len(overlap) >= 2:
            return True
    return False


def is_likely_survivorship(
    owner_full: str, decedent_name: str, beneficiaries_json: str,
) -> bool:
    """True when the parcel's joint co-owner(s) appear in the estate's
    beneficiary list — strong signal the deed is JTWROS and the property
    transfers by survivorship (NOT in probate).

    Returns True (= NOT in probate) for sole-owned parcels too — sole means
    no joint-survivorship concern; the main-parcel sorter treats this as
    "already-in-probate" via the is_jointly_owned flag instead.

    Defaults to True when we can't determine (e.g. blank beneficiary list).
    """
    co_owners = extract_co_owner_names(owner_full, decedent_name)
    if not co_owners:
        return True  # sole owned (no joint-survivorship concern)
    if not beneficiaries_json:
        return True  # can't verify — default to "transfers" (safer to skip)
    for co in co_owners:
        if co_owner_is_beneficiary(co, beneficiaries_json):
            return True  # at least one co-owner IS a beneficiary → likely survivorship
    return False  # no co-owner is a beneficiary → likely TIC, IN probate


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
        # Live endpoint (2026-06-13+) exposes property_use as a short code:
        #   RES (residential), COM (commercial), IND (industrial),
        #   EXEMPT, OTHER. DESC1_DESC carries the detailed text we
        #   previously matched against.
        if code == "RES":
            if "MOBILE HOME" in desc or "MANUFACTURED" in desc:
                return "MH"
            return "SFR"
        if code in ("COM", "IND"):
            return "Commercial"
        if code == "EXEMPT":
            return ""  # churches, gov, etc — drop via use_desc
        # Fall through to the legacy text-based matching for OTHER /
        # missing code, and for any pre-switch cached candidates.
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

    # Joint ownership = parcel has multiple distinct owner records.
    # Mecklenburg polaris3g returns owner[] as a list; len > 1 = joint.
    distinct_owner_names = {
        (o.get("fullname") or "").strip().upper()
        for o in owners if (o.get("fullname") or "").strip()
    }
    is_jointly_owned = len(distinct_owner_names) > 1

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
    heir_xfer = is_generational_heir_transfer(decedent_name, fullname)

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
        is_jointly_owned=is_jointly_owned,
        match_score=score,
        is_heir_transferred=heir_xfer,
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
        # Switched from Tax_Parcels_Full -> Parcels (2026-05-31). Audit
        # caught Tax_Parcels_Full as stale by ~4+ years for ownership
        # (parcel 46928353840000 still showed previous owner "WHITE
        # NELLIE S" instead of current "BAILEY JERRY ALLEN | JOHNSON
        # TAMIKA FIELDS" who bought in 11/2021). The Parcels layer is
        # the same one MapCabarrus (the public-facing viewer) uses and
        # matches current tax/deed records.
        # Tradeoff: Parcels lacks the VacantOrImproved V/I flag that
        # Tax_Parcels_Full had — we now rely on the "0 STREET" address
        # heuristic in _arcgis_to_candidate to detect vacant lots.
        "url": "https://location.cabarruscounty.us/arcgisservices/rest/services/Parcels/MapServer/0",
        "owner_fields": ["AcctName1", "AcctName2"],
        "mailing_fields": ["MailAddr1", "MailAddr2", "MailCity", "MailState", "MailZipCode"],
        # Parcels layer DOES expose situs addresses (the old layer only had
        # LegalDesc and we had to second-hop through DataExplorerSearch).
        # Use the real situs field directly — much faster and more accurate.
        "situs_fields": ["PropAddr"],
        "parcel_field": "PIN14",  # 14-digit human-friendly form (matches tax bills/deeds)
        "use_field": "CODE",  # HB=Home Built, CO=Country/vacant, etc.
        "use_desc_field": None,
    },
    "gaston": {
        # Switched 2026-06-13 from services6.arcgis.com/.../Gaston_County_Parcels
        # snapshot to the live Gaston public GIS. The snapshot was stale by 13+
        # months — owner of 2511 Mary Ave still showed pre-May-2024 owner
        # HENSON BRENDA C; live endpoint correctly shows YOUNG CARL L (decedent
        # in case 26E000789-350 Week 24). Field names align with the previous
        # config except CURR_ZIPCO -> CURR_ZIPCODE. See project_gaston_gis_stale.
        "url": "https://gis.gastoncountync.gov/publicgis/rest/services/PublicGIS/Parcels/MapServer/11",
        "owner_fields": ["CURR_NAME1", "CURR_NAME2"],
        "mailing_fields": ["CURR_ADDR1", "CURR_ADDR2", "CURR_CITY", "CURR_STATE", "CURR_ZIPCODE"],
        "situs_fields": ["PHYSSTRADD"],
        "parcel_field": "PIN",
        "use_field": "property_use",
        "use_desc_field": "DESC1_DESC",
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
    record_limit: int = 5000,
    page_size: int = 1000,
) -> list[dict]:
    """Run an ArcGIS REST query and return all matching attribute dicts.

    Uses LIKE 'NAME%' to match owners whose names start with the token.
    Paginates via resultOffset until either exhausted or record_limit
    rows have been collected. This catches common last names like SMITH
    or THOMPSON where the parcel we need is beyond the first 100 hits.
    """
    if not name_token:
        return []
    where = f"UPPER({owner_field}) LIKE '{name_token.upper()}%'"
    all_rows: list[dict] = []
    offset = 0
    while len(all_rows) < record_limit:
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        try:
            r = requests.get(url + "/query", params=params, headers=_ARCGIS_HEADERS, timeout=30)
        except requests.RequestException as e:
            logger.warning("ArcGIS: query failed at %s: %s", url, e)
            break
        if r.status_code != 200:
            logger.warning("ArcGIS: HTTP %d at %s", r.status_code, url)
            break
        try:
            data = r.json()
        except ValueError:
            logger.warning("ArcGIS: invalid JSON at %s", url)
            break
        if "error" in data:
            logger.warning("ArcGIS error at %s: %s", url, data["error"])
            break
        feats = data.get("features") or []
        if not feats:
            break
        all_rows.extend(a.get("attributes", {}) for a in feats)
        # Stop if server says no more, or page was short
        if not data.get("exceededTransferLimit") and len(feats) < page_size:
            break
        offset += len(feats)
        if offset >= record_limit:
            break
    return all_rows[:record_limit]


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

    # Joint ownership detection: either multiple owner fields populated
    # (Cabarrus's AcctName1 + AcctName2), or "|"/"&" separators inside a
    # single owner string (e.g. "BOB & ALICE SMITH").
    joint_parts = [p for p in re.split(r"\s*[|&]\s*", owner_full) if p.strip()]
    is_jointly_owned = len(joint_parts) > 1

    score = _name_match_score(decedent_name, owner_full.replace(" | ", " "))
    if score == 0.0:
        return None

    # Mailing address (single line composed)
    mailing = _compose_address(rec, cfg["mailing_fields"])

    # Situs (property address) — may be None (Cabarrus). For multi-field
    # compositions like Iredell (HouseNumber + SDIR + STREET + STYPE), join with spaces.
    situs = _compose_address(rec, cfg["situs_fields"])

    # Parcel ID. Several counties (notably Iredell) return PIN as a JSON
    # number — Python str() of those produces "4666780132.0" or
    # "4666780132.000" depending on serialization, which then leaks into
    # the CSV. Coerce to integer string when the value is whole-number-
    # shaped; otherwise leave the string as-is (dashed PIDs like
    # Gaston "3535-59-6052" must be preserved).
    _pid_raw = rec.get(cfg["parcel_field"])
    if isinstance(_pid_raw, (int, float)):
        try:
            if float(_pid_raw).is_integer():
                pid = str(int(_pid_raw))
            else:
                pid = str(_pid_raw)
        except (TypeError, ValueError):
            pid = str(_pid_raw or "")
    else:
        pid = str(_pid_raw or "").strip()
        # Strip trailing-zero-only decimal portion ("X.0", "X.000") on
        # strings that pass through requests' JSON decoder as floats and
        # then get str-cast upstream.
        if re.fullmatch(r"\d+\.0+", pid):
            pid = pid.split(".", 1)[0]

    # Cabarrus situs enrichment — the Parcels layer's PropAddr has the
    # street (e.g. "2626 BARR RD") but no city/zip. Use DataExplorerSearch
    # to fill in city/zip from the NG911 address-points layer. Don't blank
    # situs on lookup failure — PropAddr from the parcel layer is already
    # accurate; the secondary lookup just adds city/zip metadata.
    situs_city_override = ""
    situs_zip_override = ""
    if county.lower() == "cabarrus" and pid:
        c_street, c_city, c_zip = _cabarrus_lookup_situs(pid)
        if c_street:
            # Prefer the address-points street if available (more standardized)
            situs = c_street
            situs_city_override = c_city.title()
            situs_zip_override = c_zip
        # else: leave PropAddr as-is — it's valid in the new Parcels layer

    # If situs is blank (vacant lots in Cabarrus / unimproved parcels in
    # other counties often have no NG911 address), fall back to the
    # owner's MailAddr — matches Oren's manual convention of using the
    # owner's mailing address as the property reference when the parcel
    # itself has no street number assigned.
    if not situs:
        # mailing_fields convention: [street, street2, city, state, zip]
        mf = cfg.get("mailing_fields") or []
        mail_street = str(rec.get(mf[0]) or "").strip() if mf and mf[0] else ""
        if mail_street:
            situs = mail_street
            if not situs_city_override and len(mf) >= 3 and mf[2] and rec.get(mf[2]):
                situs_city_override = str(rec.get(mf[2])).strip().title()
            if not situs_zip_override and len(mf) >= 5 and mf[4] and rec.get(mf[4]):
                situs_zip_override = str(rec.get(mf[4])).strip()

    # Use code + description
    use_code = str(rec.get(cfg["use_field"]) or "").strip().upper() if cfg.get("use_field") else ""
    use_desc = str(rec.get(cfg["use_desc_field"]) or "").strip() if cfg.get("use_desc_field") else ""

    # Cabarrus: the new Parcels layer's CODE field hasn't been fully
    # mapped yet (observed values include "HB" = Home Built). For now use
    # an address heuristic: a real street number = residential, "0 STREET"
    # = vacant (handled by the 0-prefix heuristic below). No commercial
    # detection here — would need to discover the CODE values for that.
    is_vacant = False
    is_residential = False
    is_commercial = False
    if county.lower() == "cabarrus":
        situs_check = (situs or "").strip().upper()
        if situs_check and not (situs_check.startswith("0 ") or situs_check == "0"):
            is_residential = True
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

    # Vacant-by-address heuristic: when use codes aren't classified (common
    # in Rowan / Catawba / Iredell which don't expose detailed use codes
    # in the layer we query). Two signals indicate a vacant lot:
    #   1. situs starts with "0 " or is just "0" — county assigns "0 STREET"
    #      to unimproved parcels because no street number has been assigned
    #   2. situs starts with a letter (e.g. "CARRIAGE RD" with no house
    #      number prefix) — composed-address fields where the house-number
    #      field was empty, also signals an unimproved parcel
    # Only mark vacant when we couldn't classify any other way.
    if not (is_vacant or is_residential or is_commercial):
        situs_check = (situs or "").strip().upper()
        if not situs_check:
            pass  # blank, no signal
        elif situs_check.startswith("0 ") or situs_check == "0":
            is_vacant = True
        elif situs_check[0].isalpha():
            is_vacant = True

    # Market value: counties don't standardize the field name. Try the
    # common ones in priority order. Cabarrus exposes "MarketValue"
    # directly (and so do several other Tyler/ArcGIS layers). Without
    # this read, the polish's drop_over_500k filter (Step 1.8) never
    # fires on ArcGIS counties — Watts Mitchell W's $1.7M commercial
    # estate leaked through Week 25 audit because market_value was
    # hardcoded None.
    market_value = None
    for value_field in ("MarketValue", "TotalValue", "AssessedValue",
                        "Market_Value", "TOTAL_VALUE", "MKT_VALUE",
                        "AppraisedValue"):
        v = rec.get(value_field)
        if v not in (None, "", 0, 0.0):
            try:
                market_value = float(v)
                break
            except (TypeError, ValueError):
                continue

    return PropertyCandidate(
        county=county,
        pid=pid,
        owner_name=owner_full,
        situs_address=situs,
        mailing_address=mailing,
        use_code=use_code,
        use_description=use_desc,
        market_value=market_value,
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
        is_jointly_owned=is_jointly_owned,
        match_score=score,
        is_heir_transferred=is_generational_heir_transfer(decedent_name, owner_full),
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


# Catawba uses its own PHP web service (Bitek IMS on top of GeoServer), NOT
# standard Esri ArcGIS REST. The ArcGIS endpoint we previously queried was a
# stale Q1 snapshot uploaded to ArcGIS Online — missing recent HEIRS entries
# (e.g. Mauser Sarah K HEIRS, 9 parcels confirmed in 2026-06-03 audit). The
# live owner-search endpoint is reverse-engineered from the public parcel
# search at https://gis.catawbacountync.gov/parcel/_js/parcel_h.js (lines
# 780-800). It uses LIKE 'PREFIX%' semantics and returns JSON.
_CATAWBA_PHP_URL = "https://gis.catawbacountync.gov/_ws/v3/ws_ims_attribute_query.php"


def _catawba_php_query(name_prefix: str) -> list[dict]:
    """Live Catawba owner search. Returns list of dicts with fields
    address, city, zip, pinc, owner, owner2, lrk, calcac.

    Important: the `where` parameter has a TRAILING SPACE — the server
    appends "'<PREFIX>%'" to it.
    """
    if not name_prefix:
        return []
    params = {
        "table": "bitek_owner_all",
        "fields": "distinct address,city,zip,pinc,owner,owner2,lrk,calcac",
        "where": "where owner like ",
        "parameters": name_prefix.upper(),
        "orderby": "order by owner",
    }
    try:
        r = requests.get(
            _CATAWBA_PHP_URL, params=params, headers=_ARCGIS_HEADERS, timeout=30,
        )
    except requests.RequestException as e:
        logger.warning("Catawba PHP: query failed: %s", e)
        return []
    if r.status_code != 200:
        logger.warning("Catawba PHP: HTTP %d", r.status_code)
        return []
    try:
        data = r.json()
    except ValueError:
        logger.warning("Catawba PHP: invalid JSON")
        return []
    if not isinstance(data, list):
        return []
    # The server returns a single "OWNER NOT FOUND" sentinel when nothing
    # matches — filter it out.
    out: list[dict] = []
    for row in data:
        if row.get("owner") == "" and row.get("pinc") == "000000000000":
            continue
        out.append(row)
    return out


def _catawba_php_to_candidate(
    rec: dict, decedent_name: str,
) -> PropertyCandidate | None:
    """Convert one Catawba PHP attribute dict → PropertyCandidate."""
    owner_parts = [
        str(rec.get(f) or "").strip()
        for f in ("owner", "owner2")
    ]
    owner_parts = [p for p in owner_parts if p]
    owner_full = " | ".join(owner_parts)
    if not owner_full:
        return None

    joint_parts = [p for p in re.split(r"\s*[|&]\s*", owner_full) if p.strip()]
    is_jointly_owned = len(joint_parts) > 1

    score = _name_match_score(decedent_name, owner_full.replace(" | ", " "))
    if score == 0.0:
        return None

    pid = str(rec.get("pinc") or "").strip()
    street = str(rec.get("address") or "").strip()
    city = str(rec.get("city") or "").strip().title()
    zipc = str(rec.get("zip") or "").strip()

    # Vacant detection (2026-06-12 audit fix): PHP returns empty `address`
    # for fully-vacant parcels with no civic address at all (e.g. Mauser HEIRS
    # forest tracts), but ALSO returns just-the-street for sibling lots that
    # share a street with the primary house (e.g. Wilson Wilma T HEIRS had
    # one parcel at "1688 17TH AVE CT NE" and a sibling at bare "17TH ST NE"
    # with no house number). Both pattern-types are vacant — without a house
    # number there's no occupancy. Detect both as vacant so the smart picker
    # demotes them below true residential parcels.
    first_token = street.split(maxsplit=1)[0] if street.strip() else ""
    has_house_number = first_token.isdigit() and 1 <= len(first_token) <= 6
    is_vacant = not has_house_number
    is_residential = has_house_number

    # Workbook display: vacant lots get "0 <street>" prefix per Oren's
    # convention (see feedback_vacant_lot_zero_prefix memory). Iredell GIS
    # uses this natively (e.g. "0 CARRIAGE RD"); Catawba PHP doesn't, so
    # synthesize the prefix here when we have a street but no house number.
    if is_vacant and street and not street.lstrip().startswith("0 "):
        street = f"0 {street.lstrip()}"

    # Catawba PHP endpoint exposes only the property address — no separate
    # mailing address. Use property address as mailing fallback (matches the
    # convention applied elsewhere when situs and mailing collapse).
    situs = street
    mailing_bits = [b for b in (street, city, "NC" if street or city else "", zipc) if b]
    mailing = " ".join(mailing_bits).strip()

    return PropertyCandidate(
        county="Catawba",
        pid=pid,
        owner_name=owner_full,
        situs_address=situs,
        mailing_address=mailing,
        use_code="",
        use_description="",
        market_value=None,
        year_built=None,
        bedrooms=None,
        bathrooms=None,
        living_sqft=None,
        lot_area=_safe_float(rec.get("calcac")),
        sale_date=None,
        sale_price=None,
        owner_offsite=False,  # no separate mailing — can't compare
        is_residential=is_residential,
        is_vacant_land=is_vacant,
        is_commercial=False,
        is_jointly_owned=is_jointly_owned,
        match_score=score,
        is_heir_transferred=is_generational_heir_transfer(decedent_name, owner_full),
        raw=rec,
        situs_city_override=city,
        situs_zip_override=zipc,
    )


def _lookup_catawba(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    """Catawba live PHP-endpoint lookup. See _catawba_php_query for the
    endpoint details and why we don't use the ArcGIS path here."""
    first, _middle, last = split_decedent_name(decedent_name)
    if not last:
        return []
    rows = _catawba_php_query(last)
    # The PHP endpoint returns one row per (parcel × historical owner)
    # combination — a single parcel often shows up 4-6 times (Joel B, Joel B
    # Trustee, Jonathan T, Robert Thomas Trust, Sarah K HEIRS, etc.). We
    # must score EVERY row, then dedup by PID keeping the highest score per
    # parcel — otherwise dedup-first would silently drop the Sarah K HEIRS
    # row in favor of an alphabetically earlier non-decedent owner.
    best_by_pid: dict[str, PropertyCandidate] = {}
    for rec in rows:
        c = _catawba_php_to_candidate(rec, decedent_name)
        if not c or c.match_score < min_score:
            continue
        pid = c.pid or rec.get("pinc") or ""
        existing = best_by_pid.get(pid)
        if existing is None or c.match_score > existing.match_score:
            best_by_pid[pid] = c
    candidates = sorted(best_by_pid.values(), key=lambda c: -c.match_score)
    logger.info(
        "Catawba GIS (PHP): %r → %d raw rows → %d unique parcels matching (min_score=%.2f)",
        decedent_name, len(rows), len(candidates), min_score,
    )
    return candidates


def _lookup_iredell(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "iredell", min_score)


def _lookup_lincoln(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "lincoln", min_score)


# ── Heir-transfer fallback ───────────────────────────────────────────
# When a decedent's regular name search returns 0 high-score matches, the
# property has often already transferred to heirs whose owner-of-record name
# embeds the decedent's surname (e.g. "HOVIS SHARON SAIN" — Geraldine Sain's
# married daughter). The regular query (LIKE 'SAIN%') won't find this because
# the owner doesn't START with SAIN. The query below finds these cases by
# matching the decedent's lastname as a non-prefix token in NAME1/NAME2.


# Field names where each ArcGIS county stores the property's street address.
# These are the situs fields we already declared in _ARCGIS_CONFIG, just
# flattened here so lookup_by_address can scan all of them per county.
_ADDRESS_FIELDS_BY_COUNTY: dict[str, list[str]] = {
    "cabarrus":  ["PropAddr", "PHYSSTRADD", "WHOLE_ADDRESS"],
    "catawba":   [],  # PHP path — handled separately if we extend later
    "gaston":    ["PHYSSTRADD", "WHOLE_ADDRESS"],
    "iredell":   ["ADD1", "PHYSADDR"],
    "lincoln":   ["PHYSICALADDR"],
    "rowan":     ["PHYSADDR", "PROP_ADDRESS"],
}


def _normalize_address_for_query(addr: str) -> str:
    """Strip to upper + alphanumeric + spaces (collapsed). Lets us send
    cleaner LIKE patterns to ArcGIS WHERE-clauses without breaking on
    apostrophes, periods, multiple spaces, etc."""
    if not addr:
        return ""
    s = re.sub(r"[^\w\s]", " ", addr.upper())
    return re.sub(r"\s+", " ", s).strip()


def _street_token_pattern(addr: str) -> str | None:
    """Build a LIKE-friendly substring pattern from an address. Pulls the
    house number + first 1-2 street words so '1234 OAK CHURCH HILL RD'
    becomes '1234 OAK CHURCH%' — restrictive enough to avoid spurious
    matches but tolerant of trailing variation (street suffix abbreviation,
    direction, unit number)."""
    parts = _normalize_address_for_query(addr).split()
    if not parts:
        return None
    # Need at least: house# + 1 street word
    if not parts[0].isdigit():
        return None
    take = min(3, len(parts))
    return " ".join(parts[:take])


def lookup_by_address(address: str, county: str) -> list[dict]:
    """Find parcels in `county` whose situs starts with the given address
    prefix. Useful as a fallback when name-search fails — e.g. a beneficiary
    in the case data lives at the inherited property, or the user has the
    decedent's last-known address from Odyssey Party Information.

    Returns raw attribute dicts (caller chooses how to score / present).
    Only supports ArcGIS counties for now; Catawba PHP / Mecklenburg
    polaris3g would need separate paths.
    """
    if not address:
        return []
    county_key = county.lower()
    cfg = _ARCGIS_CONFIG.get(county_key)
    if not cfg or county_key in {"catawba", "mecklenburg"}:
        return []
    pattern = _street_token_pattern(address)
    if not pattern:
        return []
    fields = _ADDRESS_FIELDS_BY_COUNTY.get(county_key) or cfg.get("situs_fields") or []
    if not fields:
        return []
    out: list[dict] = []
    seen_pids: set[str] = set()
    pid_field = cfg.get("parcel_field") or "PIN"
    for f in fields:
        where = f"UPPER({f}) LIKE '{pattern}%'"
        try:
            r = requests.get(cfg["url"] + "/query", params={
                "where": where, "outFields": "*", "returnGeometry": "false",
                "f": "json", "resultRecordCount": 50,
            }, headers=_ARCGIS_HEADERS, timeout=30)
        except requests.RequestException as e:
            logger.warning("lookup_by_address: query failed at %s: %s", cfg["url"], e)
            continue
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        for feat in data.get("features", []):
            attrs = feat.get("attributes", {})
            pid = str(attrs.get(pid_field) or "")
            if pid and pid in seen_pids:
                continue
            seen_pids.add(pid)
            out.append(attrs)
    return out


def find_heir_transfer_candidates(
    decedent_name: str, county: str, *, max_per_field: int = 200,
) -> list[dict]:
    """Return raw parcel dicts where the decedent's lastname appears as the
    LAST whitespace-token of NAME1 or NAME2 (married-name pattern).

    This is intentionally narrower than the regular search — we only flag
    the married-name pattern, which is the highest-precision signal of
    "property transferred to a daughter/granddaughter who took her
    husband's surname." Other patterns (lastname as middle token, lastname
    elsewhere) generate too many false positives for surface-to-user.

    Each returned dict has: pid, name1, name2, situs, county. Caller is
    expected to write these to a review-me XLSX for manual audit.

    Only supports ArcGIS counties (Cabarrus, Gaston, Iredell, Lincoln, Rowan).
    Catawba (PHP) and Mecklenburg (polaris3g) return [].
    """
    _first, _middle, last = split_decedent_name(decedent_name)
    if not last:
        return []
    county_key = county.lower()
    # Catawba's ArcGIS endpoint is stale (we use PHP for regular lookups)
    # and Mecklenburg uses polaris3g with a different API. Both bypass.
    if county_key in {"catawba", "mecklenburg"}:
        return []
    # Skip non-person decedents — trust / IN THE MATTER / corporate names
    # blow up the result set (e.g. "TRUST" as a surname token returns
    # thousands of irrelevant parcels) and there's no human to match against.
    upper = decedent_name.upper()
    if last.upper() in {"TRUST", "ESTATE", "LLC", "INC", "CORP", "FUND", "BENEFIT"}:
        return []
    if any(marker in upper for marker in ("IN THE MATTER", "TRUSTEE", " TRUST ", "RETIREMENT", "BENEFIT TRUST", "F/B/O")):
        return []
    cfg = _ARCGIS_CONFIG.get(county_key)
    if not cfg:
        return []
    last_upper = last.upper()
    results: list[dict] = []
    seen_pids: set[str] = set()
    for owner_field in cfg["owner_fields"]:
        # Match "% <LASTNAME>" — last token is the decedent's surname.
        # Single-token LIKE 'LASTNAME' is already covered by regular search.
        where = f"UPPER({owner_field}) LIKE '% {last_upper}'"
        offset = 0
        while True:
            try:
                r = requests.get(cfg["url"] + "/query", params={
                    "where": where, "outFields": "*", "returnGeometry": "false",
                    "f": "json", "resultRecordCount": 1000, "resultOffset": offset,
                }, headers=_ARCGIS_HEADERS, timeout=30)
            except requests.RequestException as e:
                logger.warning("heir-transfer: query failed at %s: %s", cfg["url"], e)
                break
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except ValueError:
                break
            feats = data.get("features") or []
            if not feats:
                break
            for f in feats:
                a = f.get("attributes", {})
                pid = str(a.get(cfg["parcel_field"]) or "")
                if not pid or pid in seen_pids:
                    continue
                # Compose situs the same way the regular flow does
                situs = _compose_address(a, cfg["situs_fields"])
                results.append({
                    "pid": pid,
                    "name1": str(a.get(cfg["owner_fields"][0]) or "").strip(),
                    "name2": str(a.get(cfg["owner_fields"][1]) or "").strip() if len(cfg["owner_fields"]) > 1 else "",
                    "situs": situs,
                    "matched_field": owner_field,
                    "raw": a,
                })
                seen_pids.add(pid)
                if len(seen_pids) >= max_per_field * len(cfg["owner_fields"]):
                    break
            if len(feats) < 1000:
                break
            offset += len(feats)
    return results


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


# ── Cross-run persistent cache ───────────────────────────────────────
#
# The in-memory _LOOKUP_CACHE (below) only lives for one Python process,
# so a NEW process (e.g. the nightly daily-build run) re-hits the county
# GIS for every decedent — including ones already looked up earlier in the
# week. That makes Cabarrus (~1 min/call) the dominant cost when the same
# in-progress week is rebuilt each day.
#
# This disk cache remembers SUCCESSFUL lookups across runs so repeat
# decedents are served instantly. Not-yet-found decedents are deliberately
# NOT persisted — they retry every run, which is what we want for cases
# Odyssey/GIS indexes a day or two late. Bump _PERSIST_VERSION whenever a
# county endpoint or the candidate schema changes (invalidates old entries).
#
# Disable with NC_GIS_CACHE_DISABLE=1; tune lifetime with NC_GIS_CACHE_TTL_DAYS.
# To clear by hand, delete output/.nc_gis_cache.json.
_PERSIST_PATH = Path("output") / ".nc_gis_cache.json"
_PERSIST_VERSION = 6  # bumped 2026-06-20 — matcher tightening: HEIRS-marker escape now scores 0.6 (below min_score) when middle name doesn't match, instead of accepting at 1.0. Catches Cowan-class false positives (COWAN JOHN B HEIRS vs court "Cowan John Williams Jr.")
_PERSIST_TTL_DAYS = int(os.environ.get("NC_GIS_CACHE_TTL_DAYS", "14"))
_PERSIST_DISABLED = os.environ.get("NC_GIS_CACHE_DISABLE", "") == "1"
_persist_store: dict[str, dict] | None = None  # None = not yet loaded


def _persist_key(decedent_name: str, county: str) -> str:
    return f"{county.strip().upper()}|{decedent_name.strip().upper()}"


def _persist_load() -> dict[str, dict]:
    """Load (once) the on-disk cache, pruning expired/foreign-version entries."""
    global _persist_store
    if _persist_store is not None:
        return _persist_store
    _persist_store = {}
    if _PERSIST_DISABLED:
        return _persist_store
    try:
        data = json.loads(_PERSIST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _persist_store
    if not isinstance(data, dict) or data.get("_version") != _PERSIST_VERSION:
        return _persist_store  # schema changed → start fresh
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return _persist_store
    cutoff = datetime.now() - timedelta(days=_PERSIST_TTL_DAYS)
    for k, v in entries.items():
        try:
            if datetime.fromisoformat(v.get("ts", "")) >= cutoff:
                _persist_store[k] = v
        except (ValueError, AttributeError):
            continue
    return _persist_store


def _persist_get(decedent_name: str, county: str) -> list[PropertyCandidate] | None:
    """Return cached candidates for a decedent, or None on miss/expired."""
    if _PERSIST_DISABLED:
        return None
    entry = _persist_load().get(_persist_key(decedent_name, county))
    if not entry:
        return None
    try:
        if datetime.fromisoformat(entry.get("ts", "")) < datetime.now() - timedelta(days=_PERSIST_TTL_DAYS):
            return None
        return [PropertyCandidate(**c) for c in entry.get("candidates", [])]
    except (ValueError, TypeError):
        return None  # corrupt/old-schema entry → treat as miss, re-fetch


def _persist_put(decedent_name: str, county: str, candidates: list[PropertyCandidate]) -> None:
    """Persist a SUCCESSFUL lookup (write-through, crash-safe). Empties skipped."""
    if _PERSIST_DISABLED or not candidates:
        return
    store = _persist_load()
    store[_persist_key(decedent_name, county)] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "candidates": [asdict(c) for c in candidates],
    }
    try:
        _PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PERSIST_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"_version": _PERSIST_VERSION, "entries": store}),
            encoding="utf-8",
        )
        tmp.replace(_PERSIST_PATH)  # atomic on Windows + POSIX
    except OSError as e:
        logger.warning("nc_gis_lookup: could not write persistent cache: %s", e)


def lookup_properties(
    decedent_name: str,
    county: str,
    *,
    min_score: float = 0.7,
) -> list[PropertyCandidate]:
    """Return parcels owned by the decedent in the given county.

    Returns [] when the county isn't yet supported (graceful no-op so the
    pipeline keeps moving while we roll out more counties).

    Two cache layers, both keyed on (decedent, county) and both holding the
    broadest min_score=0.4 result so any caller's threshold is served by
    in-memory filtering:
      1. _LOOKUP_CACHE — per-process; collapses the many calls the
         fix_addresses_and_prep pipeline makes per decedent across its steps.
      2. _persist_* (output/.nc_gis_cache.json) — across processes; so the
         nightly daily-build doesn't re-hit the slow county GIS (esp.
         Cabarrus ~1 min/call) for decedents already resolved earlier in the
         week. Only successful lookups are persisted; misses retry each run.
    """
    if not decedent_name or not county:
        return []
    fn = _LOOKUP_BY_COUNTY.get(county.strip().lower())
    if fn is None:
        logger.debug("nc_gis_lookup: county %r not yet supported", county)
        return []
    cache_key = (decedent_name.strip().upper(), county.strip().upper())
    candidates = _LOOKUP_CACHE.get(cache_key)
    if candidates is None:
        candidates = _persist_get(decedent_name, county)
        if candidates is None:
            try:
                # Fetch at the broadest threshold so the cached result can serve
                # any caller's min_score by in-memory filtering.
                candidates = fn(decedent_name, min_score=0.4)
            except Exception:
                logger.exception("nc_gis_lookup: %s search for %r failed", county, decedent_name)
                candidates = []
            _persist_put(decedent_name, county, candidates)
        _LOOKUP_CACHE[cache_key] = candidates
    if min_score <= 0.4:
        return list(candidates)
    return [c for c in candidates if c.match_score >= min_score]


def _owner_has_suffix(owner_name: str, suffix: str) -> bool:
    """True if the owner_name token list includes the suffix marker."""
    if not suffix or not owner_name:
        return False
    tokens = re.sub(r"[^\w\s]", " ", owner_name.upper()).split()
    return suffix in tokens


def _use_tier(c: PropertyCandidate) -> int:
    """Use-class rank for picker: RES > unknown > vacant > commercial."""
    if c.is_commercial:
        return 0
    if c.is_residential and not c.is_vacant_land:
        return 3
    if c.is_vacant_land:
        return 1
    return 2  # unknown


def _owner_has_middle_match(owner_name: str, decedent_name: str) -> bool:
    """True when the owner string contains either the decedent's full
    middle word OR an initial that matches the decedent's middle's first
    letter. Used as a tiebreaker — when multiple parcels score equally
    on name+suffix+use, prefer the one whose deed actually carries the
    decedent's middle name (Gaither case: 'JAMES I GAITHER' at Seaman
    Dr beats 'JAMES GAITHER' at Chestnut Oak Ln because decedent is
    'James Israel' and 'I' matches Israel's initial).
    """
    if not owner_name or not decedent_name:
        return False
    _d_first, d_middle, _d_last = split_decedent_name(decedent_name)
    if not d_middle:
        return False
    d_middle_words = [w for w in d_middle.split() if w]
    d_middle_initials = {w[0] for w in d_middle_words}
    o_tokens = set(_normalize_name(owner_name).split())
    if any(w in o_tokens for w in d_middle_words):
        return True
    return any(len(t) == 1 and t in d_middle_initials for t in o_tokens)


def pick_best_candidate(
    candidates: list[PropertyCandidate],
    decedent_name: str = "",
) -> PropertyCandidate | None:
    """Pick the best parcel for a decedent. Tiebreak order (descending):

      1. Suffix match — if the decedent has SR/JR/II/III/IV/V, parcels whose
         owner string explicitly carries that suffix marker win. Resolves the
         Kinney case (decedent "Leonard Sr." → KINNEY LEONARD SR HEIRS wins
         over KINNEY LEONARD HEIRS without suffix).
      2. match_score (already filtered, but kept here for sort stability).
      3. Middle-name match — prefer parcels whose deed carries the
         decedent's middle name/initial over deeds with no middle at
         all. Resolves Gaither 26E002300-590 (decedent "James Israel"
         → "JAMES I GAITHER" Seaman Dr wins over "JAMES GAITHER"
         Chestnut Oak Ln since 'I' matches Israel's initial).
      4. Use tier — residential > unknown > vacant > commercial. Resolves the
         Keller case (3820 Mt Hope SFR wins over 0 Mt Hope vacant).
      5. Market value — when both candidates have a value.
      6. Lot area — when market_value is unset (most ArcGIS counties), the
         bigger parcel wins. Resolves Mauser case (481-ac Rocky Ford wins
         over 1.45-ac Hickory among the 5 addressed HEIRS parcels).

    Returns None if candidates is empty.
    """
    if not candidates:
        return None
    suffix = _extract_suffix(decedent_name)

    def sort_key(c: PropertyCandidate) -> tuple:
        return (
            _owner_has_suffix(c.owner_name, suffix),
            c.match_score,
            _owner_has_middle_match(c.owner_name, decedent_name),
            _use_tier(c),
            float(c.market_value or 0),
            float(c.lot_area or 0),
        )

    return max(candidates, key=sort_key)


def parcel_quality_score(
    c: PropertyCandidate, simplified_use: str = "",
) -> tuple[int, str]:
    """Score a parcel 0-100 for probate-lead quality + return a tier label.

    Lets the multi-parcel-collapse Notes column rank siblings so Oren
    can scan a Stewart-Jimmy-Wayne-style 13-parcel estate and instantly
    see which 2-3 to chase first.

    Rubric (max 100):
      - Property type (40):  SFR/Condo/Townhouse=40, MH=30, Vacant
        depending on acreage, Commercial=0. (Condo/Townhouse get dropped
        upstream — see feedback_drop_condos_townhouses memory — so the
        40 they score here doesn't actually surface.)
      - Property value (30): sweet spot $100-300K=30, $300-500K=20,
        $50-100K=20, near-cap $500-700K=10, blank/unknown=15 (medium).
      - Address quality (20): has civic # = 20, bare street = 10,
        no address at all = 5.
      - Probate signal (10): HEIRS/ESTATE marker in owner = 10, sole = 8,
        joint = 5.

    Returns (score, tier) where tier is "T1" (80-100), "T2" (50-79),
    "T3" (30-49), or "T4" (0-29).
    """
    score = 0
    use = (simplified_use or "").upper()

    # 1. Property type
    if use in {"SFR", "RESIDENTIAL"}:
        score += 40
    elif use in {"CONDO", "TOWNHOUSE"}:
        score += 40  # will be dropped upstream
    elif use == "MH":
        score += 30
    elif "VACANT" in use or "LAND" in use:
        acres = float(c.lot_area or 0)
        if acres == 0:
            score += 15
        elif acres < 0.5:
            score += 10
        elif acres <= 5:
            score += 20
        else:
            score += 30  # development potential
    elif "COMMERCIAL" in use or "INDUSTRIAL" in use or "OFFICE" in use:
        score += 0
    else:
        score += 20  # unknown — give partial credit

    # 2. Property value
    mv = float(c.market_value or 0)
    if mv == 0:
        score += 15
    elif 100_000 <= mv <= 300_000:
        score += 30
    elif 300_000 < mv <= 500_000:
        score += 20
    elif 50_000 <= mv < 100_000:
        score += 20
    elif 500_000 < mv <= 700_000:
        score += 10
    else:
        score += 5

    # 3. Address quality
    situs = (c.situs_address or "").strip()
    if situs:
        first_token = situs.split(maxsplit=1)[0]
        if first_token.isdigit() and not first_token.startswith("0"):
            score += 20
        else:
            score += 10  # "0 Carriage Rd" or bare street
    else:
        score += 5

    # 4. Probate signal
    owner_upper = (c.owner_name or "").upper()
    if any(m in owner_upper for m in ("HEIRS", "ESTATE")):
        score += 10
    elif not c.is_jointly_owned:
        score += 8
    else:
        score += 5

    score = max(0, min(100, score))
    if score >= 80:
        tier = "T1"
    elif score >= 50:
        tier = "T2"
    elif score >= 30:
        tier = "T3"
    else:
        tier = "T4"
    return score, tier


def filter_for_lead_quality(
    candidates: list[PropertyCandidate],
    *,
    drop_heir_occupied: bool = True,
    drop_commercial: bool = True,
    decedent_match_threshold: float = 0.9,
    beneficiaries_json: str = "",
    decedent_name: str = "",
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
        - The parcel is SOLELY owned by someone listed as a beneficiary
          in the estate (it's the beneficiary's OWN property — not in
          probate). Catches cases like Kinney 145 Carriage owned by
          Leonard Kinney Jr who's a beneficiary in his father's estate.

    Buy box note: vacant land IS kept (user's NC buy box includes land).
    """
    keep: list[PropertyCandidate] = []
    for c in candidates:
        if drop_commercial and c.is_commercial:
            continue
        # Beneficiary-owns-this-parcel check: when sole-owned by a person
        # who's a beneficiary in the estate, the parcel is the beneficiary's
        # own pre-existing property, not part of the probate estate.
        if not c.is_jointly_owned and beneficiaries_json and decedent_name:
            # AcctName1 is the primary owner. Normalize and check if it
            # matches any beneficiary name (token overlap >= 2).
            primary = c.owner_name.split("|")[0].strip()
            primary_norm = _normalize_name(primary)
            # Don't drop if the primary owner IS the decedent (high score)
            if c.match_score < decedent_match_threshold and co_owner_is_beneficiary(primary_norm, beneficiaries_json):
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
    # NC towns observed in our 7-county data
    "IRON STATION", "EAST SPENCER", "GRANITE QUARRY", "GRANITE FALLS",
    "MOUNT ULLA", "MOUNT MOURNE", "SAINT STEPHENS", "LONG VIEW",
    "MOUNT PLEASANT",
}

# Tokens that look city-like (last token before state in a situs string)
# but are actually parts of the street: street types + directional
# suffixes. When the trailing token matches one of these, the situs has
# NO city — fall through to the mailing-address city backfill instead.
_NOT_A_CITY_TOKENS = {
    # Street type abbreviations (and the full words just in case)
    "DR", "DRIVE", "ST", "STREET", "RD", "ROAD", "LN", "LANE",
    "CT", "COURT", "AVE", "AVENUE", "BLVD", "BOULEVARD",
    "WAY", "CIR", "CIRCLE", "PL", "PLACE", "TC", "TER", "TERRACE",
    "TR", "TRL", "TRAIL", "PKWY", "PARKWAY", "HWY", "HIGHWAY",
    "ALY", "ALLEY", "PT", "POINT", "RDG", "RIDGE", "RUN", "ROW",
    "XING", "CROSSING", "LOOP", "PATH", "PLZ", "PLAZA",
    "SQ", "SQUARE", "EST", "ESTATES", "GLN", "GLEN",
    # Directional suffixes/prefixes (also not cities)
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    "NORTH", "SOUTH", "EAST", "WEST",
    # Unit / qualifiers sometimes left dangling
    "APT", "UNIT", "STE", "SUITE", "BLDG", "BUILDING", "FL", "FLOOR",
}


def _looks_like_street_suffix(token: str) -> bool:
    """True when a token is a street type or directional, not a city."""
    return token.upper().strip(".") in _NOT_A_CITY_TOKENS


_US_STATE_CODES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC",
}


def _extract_city_from_mailing(mailing: str) -> str:
    """Pull the city out of a 'STREET CITY NC ZIP' mailing address.
    Returns "" if mailing is offsite (state != NC), looks like a street
    fragment, or the trailing token isn't a plausible city name.
    """
    if not mailing:
        return ""
    m = mailing.upper()
    # Strip trailing ZIP — accept 5, 5-4 with dash, or 9-no-dash format
    # (Gaston tax records sometimes store ZIP+4 without the dash).
    zip_m = re.search(r"\b(\d{5}(?:-?\d{4})?)\s*$", m)
    if zip_m:
        m = m[: zip_m.start()].strip()
    # Only trust mailing for property city when STATE is NC.
    # Offsite owners in GA/SC/etc. have city = their out-of-state city,
    # which is NOT the property's city. Bail in that case.
    if not re.search(r"\bNC\b\s*$", m):
        return ""
    m = re.sub(r"\s+NC\s*$", "", m).strip()
    # Mailings often abbreviate "Mount" as "Mt" (e.g., "Mt Holly", "Mt Ulla").
    # Normalize for 2-word city detection.
    m = re.sub(r"\bMT\b", "MOUNT", m)
    tokens = m.split()
    if not tokens:
        return ""
    # Two-word city (Mount Holly, Iron Station, etc.) takes precedence
    if len(tokens) >= 2:
        last_two = " ".join(tokens[-2:])
        if last_two in _TWO_WORD_NC_CITIES:
            return last_two
    last = tokens[-1]
    # Reject street-type suffixes (Dr, Rd, Ln, ...)
    if _looks_like_street_suffix(last):
        return ""
    # Reject US state codes left over from malformed mailings (Ga, Ny, etc.)
    if last in _US_STATE_CODES:
        return ""
    # Reject mostly-digit tokens (e.g., a ZIP that escaped the regex strip)
    if last.replace("-", "").isdigit():
        return ""
    return last


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
    # Pull a trailing ZIP if present in situs (rare on polaris3g).
    # MUST anchor to end-of-string — otherwise a 5-digit street number at
    # the start (e.g. "15679 KNOLL OAK CT HUNTERSVILLE NC") gets captured
    # as the "ZIP" and the actual street + city are discarded.
    zip_m = re.search(r"\b(\d{5}(?:-?\d{4})?)\s*$", s)
    zipc = zip_m.group(1) if zip_m else ""
    s_no_zip = s[: zip_m.start()].strip() if zip_m else s
    # Pull state suffix
    s_no_state = re.sub(r"\s+NC\s*$", "", s_no_zip, flags=re.IGNORECASE).strip()
    tokens = s_no_state.split()
    city = ""
    if len(tokens) >= 3:
        # Common case: "STREET... CITY"  — take last token as city.
        # BUT if the last token is actually a street-type suffix (Dr, St,
        # Rd, Ave, etc.) or a directional (Se, Nw, etc.), the situs has
        # NO city — keep the whole thing as street.
        last_two_upper = " ".join(tokens[-2:]).upper()
        if last_two_upper in _TWO_WORD_NC_CITIES:
            city = " ".join(tokens[-2:])
            street = " ".join(tokens[:-2])
        elif _looks_like_street_suffix(tokens[-1]):
            # No city in situs (e.g. "3429 ROCK CREEK DR")
            street = s_no_state
            city = ""
        else:
            city = tokens[-1]
            street = " ".join(tokens[:-1])
    else:
        street, city = s_no_state, ""

    situs_had_no_city = (not city)  # remember this before backfill mutates city

    # City backfill from mailing address when situs had no city
    if situs_had_no_city and c.mailing_address:
        mailing_city = _extract_city_from_mailing(c.mailing_address)
        if mailing_city:
            # When situs explicitly lacked a city (last token was a street
            # type like Dr/Rd/Ln), the mailing address IS the property
            # mailing — trust it for the city regardless of match_score.
            # For other low-confidence cases, fall back to the score gate.
            city = mailing_city

    # ZIP backfill from mailing address. Anchor to end-of-string —
    # same street-number-as-ZIP trap. Reject offsite-state mailings —
    # an Atlanta GA owner's ZIP is NOT the NC property's ZIP.
    mailing_is_nc = False
    if c.mailing_address:
        mailing_up = c.mailing_address.upper()
        # Strip trailing ZIP to check state at the end
        _zm = re.search(r"\b(\d{5}(?:-?\d{4})?)\s*$", mailing_up)
        if _zm:
            stripped = mailing_up[: _zm.start()].rstrip()
            if re.search(r"\bNC\s*$", stripped):
                mailing_is_nc = True
        elif re.search(r"\bNC\s*$", mailing_up):
            mailing_is_nc = True
    if not zipc and c.mailing_address and mailing_is_nc:
        m_zip = re.search(r"\b(\d{5}(?:-?\d{4})?)\s*$", c.mailing_address)
        if m_zip:
            # Three conditions under which mailing ZIP IS the property ZIP:
            #   1. GIS owner == decedent (probate-in-progress, same person)
            #   2. Situs had no recognizable city — mailing is authoritative
            #      anyway (e.g. ArcGIS counties return just "STREET DR")
            #   3. Lower-score match where situs city == mailing city
            #      (offsite-owner safety check)
            if c.match_score >= 0.9 or situs_had_no_city:
                zipc = m_zip.group(1)
            else:
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

    # Normalize 9-digit-no-dash ZIPs to proper "XXXXX-XXXX" format
    if zipc and len(zipc) == 9 and zipc.isdigit():
        zipc = f"{zipc[:5]}-{zipc[5:]}"
        # If the +4 portion is all zeros, drop it (use 5-digit form)
        if zipc.endswith("-0000"):
            zipc = zipc[:5]
    # Final safety: a city that's all digits is junk leftover from a
    # malformed mailing — clear it rather than letting it land in CSV.
    if city and city.replace("-", "").isdigit():
        city = ""
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
        kept = filter_for_lead_quality(
            candidates,
            beneficiaries_json=getattr(n, "beneficiaries_json", "") or "",
            decedent_name=decedent,
        )
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
            # Vacant-detection heuristic in _arcgis_to_candidate may flag a
            # parcel as vacant via situs-prefix even when use_code maps to
            # something else (e.g. Rowan defaults all parcels to "SFR").
            # When the heuristic says vacant, that's stronger evidence than
            # the default mapping — override.
            if c.is_vacant_land and "VACANT" not in (new_n.property_use_simple or "").upper():
                new_n.property_use_simple = "Vacant Land"
            new_n.is_jointly_owned = c.is_jointly_owned
            # Cross-reference parcel co-owners against the case's beneficiary
            # list. If a co-owner is also a court-recognized beneficiary, the
            # deed is likely JTWROS (transfers automatically — not in probate).
            # If no co-owner is in the case, it's likely TIC (decedent's share
            # IS in probate). See is_likely_survivorship for details.
            co_owners_list = extract_co_owner_names(c.owner_name, decedent)
            new_n.joint_co_owners = " | ".join(co_owners_list)
            new_n.is_likely_survivorship = is_likely_survivorship(
                c.owner_name, decedent, getattr(n, "beneficiaries_json", "") or "",
            )
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
