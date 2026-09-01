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

import atexit
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


# Odyssey sometimes returns a caption name rather than a bare person name:
#   "Dorothy Lee Cline Pierce, The Estate of Dorothy L. Pierce aka"
# Left alone, split_decedent_name() reads that as first="THE",
# last="DOROTHY LEE CLINE PIERCE" and every score collapses to 0.00 — the
# decedent becomes unfindable. Week 28: Pierce 26E000799-170 was dropped for
# "no parcel" even though her deed ("PIERCE DOROTHY L TRUSTEE") scores 1.00
# against the cleaned name.
_ESTATE_TAIL_RE = re.compile(r",?\s*\bthe\s+estate\s+of\b.*$", re.I)
_ESTATE_LEAD_RE = re.compile(r"^\s*(?:the\s+)?estate\s+of\s+", re.I)
_AKA_TAIL_RE = re.compile(
    r"[,;]?\s*\b(?:a[./]?k[./]?a[./]?|f[./]?k[./]?a[./]?|n[./]?k[./]?a[./]?|formerly)(?:\b|\s|$).*$",
    re.I,
)


def collapse_repeated_phrases(name: str) -> str:
    """Collapse an immediately-repeated multi-word phrase in a name.

    Court clerks sometimes enter maiden+married surnames into both the middle
    and last name fields, e.g. Cabarrus 26E000834-120 whose FormattedName
    yields "Ann Barnhardt Ridenhour Barnhardt Ridenhour" in natural order.
    The doubled phrase finds nothing in GIS/obituary searches and breaks
    cross-run cache keying. Only phrases of >= 2 words are collapsed —
    single-token repeats ("James James") can be legitimate names.

    Handles "Last, First Middle" comma form by flipping to natural order
    internally (the repeat is only adjacent there) and restoring the comma
    form on output. Returns the input unchanged when nothing repeats.
    """
    if not name or not name.strip():
        return name
    last_part, comma, first_part = name.partition(",")
    if comma:
        last_tokens = last_part.split()
        tokens = first_part.split() + last_tokens
    else:
        last_tokens = []
        tokens = name.split()

    def _norm(t: str) -> str:
        return t.lower().rstrip(".")

    changed_any = False
    changed = True
    while changed:
        changed = False
        n_tok = len(tokens)
        for size in range(n_tok // 2, 1, -1):
            for i in range(0, n_tok - 2 * size + 1):
                if [_norm(t) for t in tokens[i:i + size]] == [
                    _norm(t) for t in tokens[i + size:i + 2 * size]
                ]:
                    tokens = tokens[:i + size] + tokens[i + 2 * size:]
                    changed = changed_any = True
                    break
            if changed:
                break
    if not changed_any:
        return name
    if comma and len(tokens) > len(last_tokens):
        n_last = len(last_tokens)
        return f"{' '.join(tokens[-n_last:])}, {' '.join(tokens[:-n_last])}"
    return " ".join(tokens)


def clean_decedent_name(name: str) -> str:
    """Strip 'Estate of' captions and aka/fka tails from a decedent name."""
    if not name:
        return ""
    # Lead first: "The Estate of John Smith" -> "John Smith". If the tail rule
    # ran first it would swallow the whole string.
    s = _ESTATE_LEAD_RE.sub("", name)
    s = _ESTATE_TAIL_RE.sub("", s)
    s = _AKA_TAIL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().strip(",").strip()
    s = collapse_repeated_phrases(s)
    # Never return empty — a caption we don't understand is better than nothing.
    return s or name.strip()


def split_decedent_name(name: str) -> tuple[str, str, str]:
    """Best-effort split into (first, middle, last).

    Handles BOTH formats:
    - "Helen Barbara Barlow"        → ("HELEN", "BARBARA", "BARLOW")
    - "Barlow, Helen Barbara"       → ("HELEN", "BARBARA", "BARLOW")  (Odyssey API)
    - "Thrower, James W Jr."        → ("JAMES", "W", "THROWER")        (suffix stripped first)
    Single-token names → ("", "", name).

    Estate-of captions and aka tails are stripped first (clean_decedent_name).
    """
    if not name:
        return ("", "", "")
    # Comma format: "Last, First Middle" — split on comma BEFORE normalizing
    raw = clean_decedent_name(name)
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
    # No comma — treat as "First Middle Last". Must use the CLEANED string:
    # stripping an estate caption often removes the only comma, so this branch
    # is exactly where a polluted name lands.
    norm = _normalize_name(raw)
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
# Short business-entity suffixes. These are 1-2 characters, so the first-initial
# matcher would otherwise read them as a person's initials: "BEAVER LP" (a
# limited partnership) scored 0.70 against decedent "Beaver, Linda Gale" because
# "LP" starts with L — outranking the four REAL Linda Beavers in Rowan at 0.60
# and attaching six of the partnership's parcels to her estate
# (26E000762-790 Week 30). Longer forms (LLC, INC, CORP) already fail the
# 2-char test; these are the ones that slipped through.
_ENTITY_ABBREVS = {"LP", "LP.", "PA", "PC", "CO", "LC", "PL"}


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


# ── Decedent alias registry ──────────────────────────────────────────
# Odyssey often lists a decedent under several names — Dozier, Patricia H /
# Patricia Hardy / Patricia Ann (26E002608-590). The deed may be recorded under
# a NON-primary one ("PATRICIA A DOZIER"), which scores only 0.40 against the
# primary "Patricia H" and gets dropped — even though "Patricia Ann" scores 1.00.
# The scraper registers every decedent-party name here so _name_match_score
# scores an owner against ALL of the decedent's known names and keeps the best.
# Persisted to disk so the polish process (a separate process from the scraper)
# sees the same aliases.
_ALIAS_REGISTRY_PATH = Path("output") / ".nc_decedent_aliases.json"
_ALIAS_REGISTRY: "dict[str, list[str]] | None" = None


def _alias_key(name: str) -> str:
    return _normalize_name(name or "").upper().strip()


def _load_alias_registry() -> "dict[str, list[str]]":
    global _ALIAS_REGISTRY
    if _ALIAS_REGISTRY is None:
        try:
            data = json.loads(_ALIAS_REGISTRY_PATH.read_text(encoding="utf-8"))
            _ALIAS_REGISTRY = data if isinstance(data, dict) else {}
        except Exception:
            _ALIAS_REGISTRY = {}
    return _ALIAS_REGISTRY


def register_decedent_aliases(primary_name: str, alias_names: "list[str]") -> None:
    """Persist a decedent's alternate court-listed names so the matcher can
    score deeds recorded under any of them. Keyed by the primary name. Safe to
    call repeatedly — idempotent, merges new aliases in."""
    if not primary_name or not alias_names:
        return
    reg = _load_alias_registry()
    key = _alias_key(primary_name)
    if not key:
        return
    have = set(reg.get(key, []))
    added = False
    for a in alias_names:
        a = (a or "").strip()
        if a and _alias_key(a) != key and a not in have:
            have.add(a)
            added = True
    if added:
        reg[key] = sorted(have)
        try:
            _ALIAS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _ALIAS_REGISTRY_PATH.write_text(
                json.dumps(reg, ensure_ascii=False, indent=0), encoding="utf-8")
        except Exception as e:
            logger.warning("could not persist decedent alias registry: %s", e)


def _decedent_name_variants(decedent: str) -> "list[str]":
    """The decedent name plus any registered court aliases."""
    if not decedent:
        return []
    reg = _load_alias_registry()
    return [decedent] + list(reg.get(_alias_key(decedent), []))


def _name_match_score(decedent: str, owner_fullname: str) -> float:
    """Alias-aware wrapper: score the owner against the decedent AND every
    registered court alias, keeping the best. Falls straight through to the
    core scorer when the decedent has no aliases (the common case)."""
    variants = _decedent_name_variants(decedent)
    if len(variants) <= 1:
        return _name_match_score_core(decedent, owner_fullname)
    return max(_name_match_score_core(v, owner_fullname) for v in variants)


def _name_match_score_core(decedent: str, owner_fullname: str) -> float:
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


def _normalize_compound_first(d_first: str, d_middle: str,
                              o_tokens: list[str]) -> list[str]:
    """Reconcile compound first names written as ONE token on one side and
    TWO on the other, in either direction:

      * Deed fused:  court "Irish, Jo Ann Scott" vs deed "IRISH JOANN SCOTT
        TRUSTEE" (Cabarrus 26E000837-120 — scored 0.4 and the case shipped
        parcel-less). When a deed token exactly equals d_first + the first
        middle word, split it back into the two court tokens.
      * Deed split:  court "Smith, Joann B" vs deed "SMITH JO ANN B". When
        two ADJACENT deed tokens concatenate exactly to d_first, merge them.

    Exact-concatenation equality is the whole guard: a genuinely different
    "JOANN" can only fuse when the court name is literally JO + ANN, and the
    surname gate has already passed before this runs. Middle names are left
    to the existing middle-check, which sees the rewritten token list.
    """
    mid_words = [w for w in (d_middle or "").split() if w]
    if mid_words:
        fused = d_first + mid_words[0]
        if fused in o_tokens:
            out: list[str] = []
            for t in o_tokens:
                if t == fused:
                    out.extend((d_first, mid_words[0]))
                else:
                    out.append(t)
            return out
    for i in range(len(o_tokens) - 1):
        if o_tokens[i] + o_tokens[i + 1] == d_first:
            return o_tokens[:i] + [d_first] + o_tokens[i + 2:]
    return o_tokens


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
    if d_first not in o_set:
        o_tokens = _normalize_compound_first(d_first, d_middle, o_tokens)
        o_set = set(o_tokens)

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
            # estate (contains HEIRS/ESTATE) AND a competing token is a
            # spelling variant of d_first (shares both 4-char PREFIX and
            # 2-char SUFFIX), treat as the same person. Catches Cabarrus
            # 26E000656-120 / Sega: "HUNTER VERNICE SR | SEGA PAULINE E
            # ESTATE" (Paulene vs Pauline — share PAUL prefix and NE suffix).
            #
            # The suffix requirement blocks false positives like Hannah
            # 26E000841-350 Week 26: decedent DAVID, owner "HANNAH DAVIS
            # ROWE HEIRS". DAVID and DAVIS share prefix DAVI but suffix
            # D vs S — different person, not a spelling variant. Prefix-
            # only matching was returning 0.7 and pulling in the wrong
            # estate's parcel via swap-on-DQ.
            if (
                o_set & _HEIRS_MARKERS
                and d_first
                and len(d_first) >= 4
            ):
                d_prefix = d_first[:4]
                d_suffix = d_first[-2:]
                for cf in competing_first_names:
                    if (
                        len(cf) >= 4
                        and cf[:4] == d_prefix
                        and len(cf) >= 2
                        and cf[-2:] == d_suffix
                    ):
                        return 0.7
            return 0.4  # owner has its own first name, ours isn't it

        d_first_initial = d_first[0]
        for t in o_tokens:
            if t in _ENTITY_ABBREVS:
                continue  # "LP"/"PA"/"CO" are entity suffixes, not initials
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
                # "V" is ambiguous. As a lone token between first and last it
                # is a middle initial ("MILLER DAVID V") far more often than
                # the generational suffix "the Fifth". Only swallow it as a
                # suffix when the decedent actually carries one. Week 28 audit:
                # decedent "Miller, David Allen" scored 1.00 against a stranger,
                # "MILLER DAVID V", because V was dropped here and the owner
                # then looked like it had no middle name at all.
                # II/III/IV/JR/SR are never middle initials — leave them noise.
                if t != "V" or dec_suffix == "V":
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
                # Full first name + full last name, but the middles disagree.
                # That is much stronger evidence than a bare surname hit, yet
                # 0.4 rated it identically — so the parcel sank into the pool of
                # every same-surname stranger in the county and could never be
                # surfaced, even when the first+last pair was unique.
                # Lackey 26E000718-480 Week 30: court "Lackey, Donnie Church"
                # vs deed "LACKEY DONNIE P" (Church is almost certainly the
                # mother's maiden name; a Church family owns the adjacent
                # parcel). Only two DONNIE LACKEY parcels exist in Iredell and
                # both are his — Oren pulled 262 Halyburton Rd by hand while the
                # pipeline dropped the case for having no parcel at all.
                # 0.6 lands in the existing review band (_LOWCONF_MIN 0.55 <=
                # s < _LOWCONF_MAX 0.70), so Step 3.7 attaches it FLAGGED for
                # verification and it still cannot clear the 0.7 confident-accept
                # gate or the 0.9 address-corroboration gate on its own.
                # A first-INITIAL-only match keeps 0.4 — too weak to bother.
                if first_full_match:
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


# Polaris rate-limits bursts (connection reset / 429). Since the 2026-07-12 name
# search rewrite fetches lastname-only for EVERY Meck decedent (higher volume),
# one transient failure must not silently zero out a decedent — retry with
# exponential backoff instead of returning empty.
_POLARIS3G_MAX_RETRIES = 4
_POLARIS3G_BACKOFF_BASE = 2.0        # seconds; 2,4,8,16
_POLARIS3G_RETRY_STATUS = {429, 500, 502, 503, 504}


def _polaris3g_get_page(session: "requests.Session", params: dict) -> list[dict]:
    """GET one bolt page, retrying transient failures (reset / timeout / 429 /
    5xx) with exponential backoff. Returns the parsed list. Raises RuntimeError
    on a permanent 4xx or after exhausting retries — the caller decides whether
    a partial result is usable, but a transient blip no longer looks like
    'this owner has no parcels'."""
    last_err: Any = None
    for attempt in range(_POLARIS3G_MAX_RETRIES):
        try:
            r = session.get(_POLARIS3G_BASE, params=params,
                            headers=_POLARIS3G_HEADERS, timeout=30)
        except requests.RequestException as e:
            last_err = e
        else:
            if r.status_code == 200:
                try:
                    data = r.json()
                except ValueError:
                    last_err = "invalid JSON"
                else:
                    return data if isinstance(data, list) else []
            elif r.status_code in _POLARIS3G_RETRY_STATUS:
                last_err = f"HTTP {r.status_code}"
            else:
                raise RuntimeError(f"polaris3g permanent HTTP {r.status_code}")
        sleep = _POLARIS3G_BACKOFF_BASE * (2 ** attempt)
        logger.warning("polaris3g: %s (attempt %d/%d) — backoff %.0fs",
                       last_err, attempt + 1, _POLARIS3G_MAX_RETRIES, sleep)
        time.sleep(sleep)
    raise RuntimeError(f"polaris3g: retries exhausted ({last_err})")


def _polaris3g_search(
    *,
    lastname: str,
    firstname: str = "",
    max_pages: int = 20,
    page_size: int = 20,
) -> list[dict]:
    """Page through /api/bolt for an owner name. Returns raw parcel dicts.

    A page that keeps failing after retries aborts the whole fetch by raising —
    partial-then-silent-empty is the dangerous mode (it would drop the
    decedent's real parcel if it's on a later page). Callers already treat a
    thrown lookup as "GIS unavailable", not "no parcels".
    """
    if not lastname:
        return []
    out: list[dict] = []
    session = requests.Session()
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {"lastname": lastname, "page": page}
        if firstname:
            params["firstname"] = firstname
        rows = _polaris3g_get_page(session, params)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page_size:
            break
        time.sleep(0.7)
    return out


# Street-suffix abbreviations Mecklenburg's polaris3g `situs` field uses. Odyssey
# sometimes spells the suffix out ("DRIVE", "COURT"); bolt situs is exact-match,
# so we must abbreviate before querying. Verified 2026-07-11: normalizing lifted
# the Week 28 Meck decedent-address hit rate from 2/7 to 5/7.
_SITUS_SUFFIX_ABBR = {
    "DRIVE": "DR", "COURT": "CT", "PLACE": "PL", "LANE": "LN", "ROAD": "RD",
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "CIRCLE": "CIR",
    "TERRACE": "TER", "TRAIL": "TRL", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "COVE": "CV", "SQUARE": "SQ",
}
# Mecklenburg municipalities to try when the row's city is unknown/wrong.
# Charlotte first (the overwhelming majority of parcels).
_MECK_MUNICIPALITIES = (
    "CHARLOTTE", "HUNTERSVILLE", "MATTHEWS", "MINT HILL", "CORNELIUS",
    "DAVIDSON", "PINEVILLE",
)


def _polaris3g_address_search(address: str, city_hint: str = "") -> list[dict]:
    """Mecklenburg address lookup via polaris3g bolt's `situs` param.

    bolt has no fuzzy address search — `situs` is an EXACT match on the full
    "NUM STREET SUFFIX CITY STATE" string. So reconstruct that string from the
    decedent's Odyssey address (uppercase, suffix abbreviated) and try each
    plausible municipality until one hits. Returns FLAT dicts shaped for
    _ARCGIS_CONFIG["mecklenburg"] (owner / pin / situs_street / situs_city /
    land_use_desc / market_value).
    """
    if not address:
        return []
    toks = [_SITUS_SUFFIX_ABBR.get(t, t)
            for t in re.sub(r"[^\w\s]", " ", address.upper()).split()]
    street = " ".join(toks).strip()
    if not street:
        return []
    cities: list[str] = []
    for c in [city_hint, *_MECK_MUNICIPALITIES]:
        c = (c or "").upper().strip()
        if c and c not in cities:
            cities.append(c)

    session = requests.Session()
    for city in cities:
        try:
            r = session.get(_POLARIS3G_BASE, params={"situs": f"{street} {city} NC", "page": 1},
                            headers=_POLARIS3G_HEADERS, timeout=30)
        except requests.RequestException as e:
            logger.warning("polaris3g situs: request failed (%s): %s", city, e)
            continue
        if r.status_code != 200:
            continue
        try:
            recs = r.json()
        except ValueError:
            continue
        if not isinstance(recs, list) or not recs:
            continue
        out: list[dict] = []
        for rec in recs:
            owners = rec.get("owner") or []
            owner_str = " | ".join(
                str(o.get("fullname") or "").strip() for o in owners if o.get("fullname")
            ) if isinstance(owners, list) else str(owners)
            situs_full = rec.get("situs")
            situs_full = situs_full[0] if isinstance(situs_full, list) and situs_full else (situs_full or "")
            # Strip the trailing "CITY NC [zip]" so situs_street is just the street.
            m = re.match(r"(.*?)\s+" + re.escape(city) + r"\s+NC\b", str(situs_full))
            situs_street = (m.group(1).strip() if m else str(situs_full)).strip()
            out.append({
                "owner": owner_str,
                "pin": str(rec.get("pid") or rec.get("gisid") or ""),
                "situs_street": situs_street,
                "situs_city": (rec.get("municipality") or city).title(),
                "land_use_desc": rec.get("land_use_desc") or "",
                "market_value": rec.get("market_value"),
            })
        return out
    return []


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
        # Legacy V/I flags (old Tax_Parcels_Full layer — kept for cache-hit
        # safety on entries from before 2026-05-31 layer switch).
        if code == "V":
            return "Vacant Land"
        if code == "I":
            return "SFR"
        # New Parcels-layer CODE values (most common are KA=959, CN=627,
        # CO=343, KT=64, HB=7 in a 2000-parcel sample). CN/HB confirmed;
        # KA/KT/CO ambiguous — leave blank so address heuristics handle.
        if code == "CN":
            return "Condo"   # Needham Mark Lindsay 26E000661-120 leaked through Week 26
        if code == "HB":
            return "SFR"     # "Home Built" per Cabarrus comment
        # Note: removed CO -> Vacant Land (shipped 2026-06-22, reverted
        # 2026-06-24). The code comment claimed "Country/vacant" but Week 26
        # audit found CO applied to BOTH true vacant lots AND residences on
        # country/rural land (Honeycutt Ralph A 26E000664-120: residence at
        # 26 Mary Cir $336K marked CO; adjacent lot at 28 Mary Cir $24K
        # also CO). The address heuristic in _arcgis_to_candidate ("0 STREET"
        # = vacant) handles the true-vacant case more reliably.
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
            # Gaston RES covers ALL residential — SFR, townhouse, condo, MH.
            # Check the detailed desc to route to the right bucket. Without
            # this, townhouses + condos were defaulting to SFR and slipping
            # past the condo/townhouse drop (Reid 26E000854-350 Week 26).
            if "MOBILE HOME" in desc or "MANUFACTURED" in desc:
                return "MH"
            if "TOWNHOUSE" in desc or "TOWN HOUSE" in desc:
                return "Townhouse"
            if "CONDO" in desc:
                return "Condo"
            # Gaston tags a vacant residential lot as code=RES, desc='Vacant'.
            # Without this it fell through to SFR — which not only mislabels
            # the row but disables the vacant-land exemption inside the
            # heir-occupancy filter. Week 28: Hutchins 26E000897-350, a $400
            # landlocked strip on Wellington Dr, was published as SFR.
            if "VACANT" in desc:
                return "Vacant Land"
            # RES + 'Auxiliary Improvement' = a lot whose only structure is a
            # shed/garage (no dwelling). Treat as vacant: the SFR label blocked
            # BOTH the Step 1.5 house-promotion swap AND the "0 <street>"
            # vacant prefix on Putnam 26E001064-350 (Week 33 Belton Ave).
            if "AUXILIARY" in desc:
                return "Vacant Land"
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
        if "VACANT" in desc or "AUXILIARY" in desc:
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

    situs = ((rec.get("situs") or [""])[0] or "").strip()
    use_code = (rec.get("land_use_code") or "").strip().upper()
    use_desc = (rec.get("land_use_desc") or "").strip()

    # Drop parcels with no usable property address (some condo/vacant entries
    # have only an owner mailing and no situs)
    if not situs:
        return None

    bldg = (rec.get("bldg") or [{}])[0] or {}

    # Score against EVERY owner, not just owner[0]. On a jointly-owned parcel
    # the decedent is often NOT listed first (Norman 26E...: owner list is
    # ['WILLIE J NORMAN', 'JACQUELINE NORMAN'] — scoring only owner[0] gave the
    # husband 0.40 and dropped Jacqueline's real parcel). Pick the best-matching
    # owner, and also score the combined "OWNER1 | OWNER2" string the way the
    # ArcGIS counties do. owner_name becomes the piped list so downstream
    # matchers / display see the joint ownership.
    owner_names = [(o.get("fullname") or "").strip() for o in owners
                   if (o.get("fullname") or "").strip()]
    combined_owner = " | ".join(owner_names) if owner_names else (primary.get("fullname") or "").strip()
    best = primary
    score = _name_match_score(decedent_name, (primary.get("fullname") or "").strip())
    for o in owners:
        s = _name_match_score(decedent_name, (o.get("fullname") or "").strip())
        if s > score:
            best, score = o, s
    s_combined = _name_match_score(decedent_name, combined_owner)
    if s_combined > score:
        score = s_combined

    fullname = combined_owner
    mailing = (best.get("mailing_address") or primary.get("mailing_address") or "").strip()
    heir_xfer = is_generational_heir_transfer(decedent_name, (best.get("fullname") or "").strip())

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

    # Fetch by LAST NAME ONLY and score client-side — exactly like the ArcGIS
    # counties. The bolt `firstname` filter is unreliable: it exact-matches the
    # whole first field, so compound firsts ('ELOISE LITAKER') and second-listed
    # joint owners are missed, and the old broaden gate (`< 2 hits`) skipped the
    # lastname-only fetch whenever firstname returned >=2 junk rows — silently
    # dropping findable parcels (Norman, Ryan, Kerns...). Also search the middle
    # token as a surname to catch maiden names (Rencher, Rebecca Nisbet -> deed
    # recorded under NISBET).
    def _candidates_for(surname: str) -> tuple[int, list[PropertyCandidate]]:
        seen: set[str] = set()
        cands: list[PropertyCandidate] = []
        raw = _polaris3g_search(lastname=surname)
        for rec in raw:
            pid = rec.get("pid")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            c = _polaris3g_to_candidate(rec, "Mecklenburg", decedent_name)
            if c and c.match_score >= min_score:
                cands.append(c)
        return len(raw), cands

    n_raw, candidates = _candidates_for(last)
    surnames = [last]

    # When the last-name fetch hits the hard page cap (400 rows = 20 pages of
    # 20), the surname is common enough that the decedent's parcel may be past
    # the cap and got silently truncated (Harris, Barbara Joyce 26E002623-590:
    # 400 HARRIS rows, hers was #400+). Retry narrowed by firstname. Polaris
    # exact-matches the whole `firstname` field, which for anyone with a middle
    # name is stored as "FIRST M" (first + middle INITIAL) — so "BARBARA" misses
    # her but "BARBARA J" finds her exactly. Try both. Only fires on the capped
    # case, so it costs nothing for the common (uncommon-surname) lookup.
    # Narrow by firstname whenever the surname fetch hit the page cap — NOT only
    # when we found nothing. A MULTI-PARCEL decedent may have one parcel inside
    # the 400 (e.g. their home) and others truncated past it. Smith, William
    # Edward 26E002657-590: surname search returned 400 SMITHs incl. his home
    # (10304 Shelter Rock, score 1.0), so the old `not target_found` gate skipped
    # the narrow search — and his OTHER properties (3642 Delgany + Park Ave lots)
    # were never fetched, so swap-on-DQ (his home is executor-occupied) had no
    # sibling to move to and the lead was lost. Polaris exact-matches the whole
    # firstname field, stored as "FIRST M" (first + middle INITIAL): "WILLIAM"
    # returns 2 unrelated rows, "WILLIAM E" returns exactly his 5 parcels.
    _POLARIS_PAGE_CAP = 400
    if n_raw >= _POLARIS_PAGE_CAP and first:
        seen_pids = {c.pid for c in candidates if c.pid}
        narrow_firsts = [first.upper()]
        if middle:
            narrow_firsts.append(f"{first} {middle[0]}".upper())
        for fn in narrow_firsts:
            raw = _polaris3g_search(lastname=last, firstname=fn)
            n_raw += len(raw)
            for rec in raw:
                pid = rec.get("pid")
                if pid and pid in seen_pids:
                    continue
                c = _polaris3g_to_candidate(rec, "Mecklenburg", decedent_name)
                if c and c.match_score >= min_score:
                    candidates.append(c)
                    if pid:
                        seen_pids.add(pid)

    # Only pay for the maiden-name (middle-token) search when the primary
    # surname found nothing acceptable — halves Polaris request volume in the
    # common case, which matters for the nightly's rate-limit exposure. The
    # Week-28 recoveries were all found under the primary surname.
    if not candidates and middle and middle.upper() != last.upper() and len(middle) > 1:
        surnames.append(middle)
        n2, c2 = _candidates_for(middle)
        n_raw += n2
        candidates = c2

    candidates.sort(key=lambda c: (-c.match_score, -(c.market_value or 0)))
    logger.info(
        "polaris3g: %r → %d raw rows (surnames=%s) → %d scoring matches",
        decedent_name, n_raw, surnames, len(candidates),
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

# Transient-failure retries for ArcGIS Server queries (connection reset, 5xx,
# {"status":"error"}). Cabarrus is the flaky one. A 200 + zero features is NOT
# a transient failure and is never retried.
_ARCGIS_QUERY_RETRIES = int(os.environ.get("NC_ARCGIS_RETRIES", "2"))
_ARCGIS_QUERY_BACKOFF = float(os.environ.get("NC_ARCGIS_BACKOFF", "2.0"))

# ── County GIS outage detection ───────────────────────────────────────
#
# A county server that is DOWN and a decedent who owns NOTHING both come back
# as zero rows. That equivalence costs both time and leads:
#
#   * Time. Gaston died at 19:29 on 2026-07-16 and every lookup afterwards
#     burned ~97s (3 tries x 30s timeout + backoff) before giving up empty --
#     ~35 min of one night spent waiting on a server returning Cloudflare 525s.
#   * Leads. The empty result flows into the has-parcel filter, which drops the
#     row. Silently. Cabarrus did exactly this on 2026-07-09.
#
# So: count CONSECUTIVE failures per endpoint. Any success -- including a
# legitimate 200 + zero features -- resets the count, because that proves the
# server is answering. After _OUTAGE_THRESHOLD consecutive failures, declare
# the endpoint down and fast-fail every later query against it for the rest of
# the process: no network, no wait.
#
# Callers use downed_counties() / is_county_down() to tell "server broken" from
# "owns nothing" and refuse to drop rows on the former. Nothing is cached from
# a downed county (_persist_put already skips empty results), so tomorrow's run
# re-fetches cleanly.
_OUTAGE_THRESHOLD = int(os.environ.get("NC_GIS_OUTAGE_THRESHOLD", "3"))
_outage_fails: dict[str, int] = {}
_outage_down: set[str] = set()


def _endpoint_key(url: str) -> str:
    """Group failures by host — one county's layers share a server."""
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower() if m else (url or "?")


def _outage_note_failure(url: str, why: str) -> None:
    key = _endpoint_key(url)
    if key in _outage_down:
        return
    _outage_fails[key] = _outage_fails.get(key, 0) + 1
    if _outage_fails[key] >= _OUTAGE_THRESHOLD:
        _outage_down.add(key)
        logger.error(
            "GIS OUTAGE: %s failed %d consecutive queries (%s). Marking it DOWN "
            "for the rest of this run — further lookups fast-fail instead of "
            "waiting. Rows for this county are INCOMPLETE and must NOT be "
            "treated as 'no parcels found'.", key, _outage_fails[key], why)


def _outage_note_success(url: str) -> None:
    """A server that answers at all is up — even with zero features."""
    _outage_fails.pop(_endpoint_key(url), None)


def is_endpoint_down(url: str) -> bool:
    return _endpoint_key(url) in _outage_down


def downed_counties() -> set[str]:
    """County keys (as used in _ARCGIS_CONFIG) whose GIS went down this run."""
    return {county for county, cfg in _ARCGIS_CONFIG.items()
            if cfg.get("url") and _endpoint_key(cfg["url"]) in _outage_down}


def is_county_down(county: str) -> bool:
    cfg = _ARCGIS_CONFIG.get((county or "").strip().lower())
    return bool(cfg and cfg.get("url") and is_endpoint_down(cfg["url"]))


def reset_outage_state() -> None:
    """Clear outage bookkeeping (tests, or a caller retrying a later phase)."""
    _outage_fails.clear()
    _outage_down.clear()


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
        # STATE + ZIP are per-parcel situs values (verified via two-parcel
        # A/B for same owner — Hannah David Jon's two parcels show ZIP=28056
        # for 3307 Sand Post Oak Ct and ZIP=28016 for 208 Park St while the
        # owner mailing CURR_ZIPCODE is FL=325703762 on both). Without these,
        # swap-on-DQ rewrites Property Address but leaves City/Zip blank.
        "situs_zip_field": "ZIP",
        # Gaston exposes BOTH: PIN is the 10-digit dashed grid id
        # ("3539-83-1095"); PID is the 6-digit parcel/account number
        # ("167236") that appears on the county's own property card and is
        # what Oren records by hand. Per his Week 28 audit answer, PID is
        # canonical. Changing this rewrites the Parcel ID on every Gaston row.
        "parcel_field": "PID",
        "use_field": "property_use",
        "use_desc_field": "DESC1_DESC",
    },
    "catawba": {
        # NOTE: Catawba does NOT use ArcGIS. Name search goes through the PHP
        # endpoint (_lookup_catawba) and address search + valuation through
        # GeoServer WFS (_catawba_wfs_query). No `url` here on purpose — the old
        # services1.arcgis.com/PP3_Q1_Map_WFL1 snapshot is dead, and leaving it
        # in place invited callers to query it. The remaining keys describe the
        # WFS `catawba:parcels_plus` field names, which is what
        # lookup_by_address() hands back for this county.
        "url": None,
        "owner_fields": ["owner", "owner2"],
        "mailing_fields": ["oaddress", "ocity", "ozip"],
        "situs_fields": ["paddress"],
        "parcel_field": "pin",   # GeoServer returns lowercase
        "use_field": None,       # no use code; vacancy comes from bldg_value == 0
        "use_desc_field": None,
    },
    "mecklenburg": {
        # Name search uses polaris3g bolt directly (_lookup_mecklenburg, NOT this
        # config). This entry only describes the FLAT dicts _polaris3g_address_search
        # returns, so lookup_by_address-based steps (0.64 fallback, 0.68 cross-check)
        # can read owner / pin / situs for Mecklenburg. url: None — no ArcGIS here.
        "url": None,
        "owner_fields": ["owner"],
        "mailing_fields": [],
        "situs_fields": ["situs_street"],
        "situs_city_field": "situs_city",
        "parcel_field": "pin",
        "use_field": None,
        "use_desc_field": "land_use_desc",
    },
    "iredell": {
        # FeatureServer/0 started returning HTTP 200 + {"error": 400 "Unable to
        # perform query operation"} on EVERY query (even where=1=1) around
        # 2026-07-01 — the layer's query op is broken server-side though it still
        # advertises the Query capability. The parallel MapServer/0 serves the
        # same TaxSQL_Parcels data with identical fields and queries fine
        # (109k parcels, UPPER(Name) LIKE works). Swap back if the FeatureServer
        # recovers. (MapServer is a touch flaky under rapid-fire requests — the
        # retry/pagination in _arcgis_query absorbs the occasional 500.)
        "url": "https://maps.iredellcountync.gov/server/rest/services/Data/TaxSQL_Parcels/MapServer/0",
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
        # Changed PIN -> PARCELID 2026-07-23 per Oren: his hand-entered APN for
        # Francis 26E000455-540 was 88873, which is this parcel's PARCELID; the
        # 10-digit PIN (3684513243) is the ArcGIS grid id. Same call as Gaston's
        # PIN -> PID switch on 2026-07-09. Coverage is identical (2 nulls in
        # 56,966 parcels for either field). Rewrites every Lincoln row once.
        # The PIN is still published, in Notes — see alt_parcel_field.
        "parcel_field": "PARCELID",
        "alt_parcel_field": "PIN",
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
    # Server already declared down this run — don't spend another ~97s proving
    # it. Returns empty like any other failure; is_county_down() is how callers
    # tell this apart from a genuine "owns nothing".
    if is_endpoint_down(url):
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
        # Cabarrus (and other ArcGIS Server counties) flake intermittently:
        # a connection reset, a 5xx, or a {"status":"error"} on one call, then
        # a clean result on the next. Retry transient failures with backoff so
        # a single bad response doesn't drop a real lead (Barbee 26E000709-120
        # kept vanishing on empty Cabarrus responses). A genuine 200 + zero
        # features is NOT retried — that's a real "no such owner".
        data = None
        for attempt in range(_ARCGIS_QUERY_RETRIES + 1):
            try:
                r = requests.get(url + "/query", params=params,
                                 headers=_ARCGIS_HEADERS, timeout=30)
            except requests.RequestException as e:
                if attempt < _ARCGIS_QUERY_RETRIES:
                    time.sleep(_ARCGIS_QUERY_BACKOFF * (attempt + 1))
                    continue
                logger.warning("ArcGIS: query failed at %s after %d tries: %s",
                               url, attempt + 1, e)
                _outage_note_failure(url, f"request failed: {e}")
                break
            if r.status_code != 200:
                if r.status_code >= 500 and attempt < _ARCGIS_QUERY_RETRIES:
                    time.sleep(_ARCGIS_QUERY_BACKOFF * (attempt + 1))
                    continue
                logger.warning("ArcGIS: HTTP %d at %s", r.status_code, url)
                _outage_note_failure(url, f"HTTP {r.status_code}")
                break
            try:
                parsed = r.json()
            except ValueError:
                if attempt < _ARCGIS_QUERY_RETRIES:
                    time.sleep(_ARCGIS_QUERY_BACKOFF * (attempt + 1))
                    continue
                logger.warning("ArcGIS: invalid JSON at %s", url)
                _outage_note_failure(url, "invalid JSON")
                break
            # Dead backend: HTTP 200 with {"status":"error",...} and no "error"
            # key — indistinguishable from "no parcels" without this check.
            # Cabarrus was fully down like this on 2026-07-09.
            if parsed.get("status") == "error":
                if attempt < _ARCGIS_QUERY_RETRIES:
                    time.sleep(_ARCGIS_QUERY_BACKOFF * (attempt + 1))
                    continue
                logger.error("ArcGIS SERVER DOWN at %s: %s — results empty; do "
                             "NOT treat as 'no parcels found'",
                             url, "; ".join(parsed.get("messages") or []))
                _outage_note_failure(url, "status=error")
                break
            # HTTP 200 carrying {"error": {...}} — an ArcGIS Server still
            # coming up answers every query with 500 9017$SITE_NOT_INITIALIZED
            # (Gaston, 2026-07-16 21:06). Previously this fell straight through
            # to `break` with no retry and no outage note, so a flapping server
            # read as "nobody in this county owns anything". Retry it like any
            # other transient, then count it.
            if "error" in parsed:
                if attempt < _ARCGIS_QUERY_RETRIES:
                    time.sleep(_ARCGIS_QUERY_BACKOFF * (attempt + 1))
                    continue
                logger.warning("ArcGIS error at %s: %s", url, parsed["error"])
                _outage_note_failure(url, str(parsed["error"])[:80])
                break
            data = parsed
            break
        if data is None:
            break
        _outage_note_success(url)  # answered — zero features here means zero
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


_CATAWBA_PARCEL_REPORT_URL = "https://gis.catawbacountync.gov/_ws/v2/ws_ims_attribute_query.php"


def _catawba_parcel_report(pid: str) -> dict | None:
    """Fetch the bitek_parcel_report_view record for a Catawba parcel.

    The PHP-based GIS layer we use for name search exposes only 8 fields
    (no value, no use, no sale data). This endpoint backs the "Parcel Report"
    UI link on gis.catawbacountync.gov and returns the full assessor record:
    total_value, bldg_value, land_value, yr_built, sale_date, sale_amount,
    legal description, etc. Used by populate_property_values to plug the
    Catawba value-blind gap (see project_catawba_value_field_missing.md).
    """
    if not pid:
        return None
    params = {
        "table": "bitek_parcel_report_view",
        "fields": "*",
        "where": f"where pinc like '{pid}%'",
    }
    headers = dict(_ARCGIS_HEADERS)
    headers["Referer"] = f"https://gis.catawbacountync.gov/nomap/parcel_report_h.php?key={pid}&typ=P"
    try:
        r = requests.get(_CATAWBA_PARCEL_REPORT_URL, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
    except (requests.RequestException, ValueError):
        return None
    return None


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


# Lot acreage field names, in priority order. Same story as market_value —
# every county returns acreage (we already query outFields=*), but under its
# own field name, so _arcgis_to_candidate hardcoded lot_area=None and the
# polish's >2-acre subdivide exemption had nothing to read. Names verified
# live against each layer's ?f=json on 2026-07-16.
#
# Deed/tax acreage first (what the county bills on and what prints on the
# property card), then GIS-geometry-calculated acreage as fallback — the deed
# field is absent or zero on a minority of parcels.
_ACRE_FIELDS = (
    # Deed / tax: Rowan DEEDACRE, Gaston DEEDAC, Iredell TaxAcres, Lincoln ACRE.
    "DEEDACRE", "DEEDAC", "TaxAcres", "ACRE",
    # Calculated: Cabarrus CALCULATED_ACREAGE (its only acreage field),
    # Rowan CALCACRE, Gaston CALCAC, Lincoln MAPPEDACRE.
    "CALCULATED_ACREAGE", "CALCACRE", "CALCAC", "MAPPEDACRE",
)

# No NC residential parcel approaches this. A field carrying square feet under
# a name we scan would blow past it and be rejected, rather than silently
# exempting a row from the buy-box cap by looking like a huge tract.
_MAX_PLAUSIBLE_ACRES = 50_000


def acres_from_arcgis_attrs(rec: dict) -> float | None:
    """Lot acreage from a raw ArcGIS attribute dict, or None if unavailable.

    Shared by _arcgis_to_candidate and the polish steps that attach a parcel
    straight from query attributes without building a PropertyCandidate.
    """
    for acre_field in _ACRE_FIELDS:
        v = rec.get(acre_field)
        if v in (None, "", 0, 0.0):
            continue
        try:
            v_f = float(v)
        except (TypeError, ValueError):
            continue
        if 0 < v_f < _MAX_PLAUSIBLE_ACRES:
            return v_f
    return None


def _arcgis_to_candidate(
    rec: dict, county: str, decedent_name: str, cfg: dict,
    *, force_score: float | None = None,
) -> PropertyCandidate | None:
    """Convert one ArcGIS attribute dict → PropertyCandidate. None if unusable.

    force_score: when set, bypass person-name scoring and stamp this score on
    the candidate. Used by the trust/LLC fallback, where the owner is an
    entity with no person first/middle name to match against — the caller
    supplies a capped "worth a human look" score instead.
    """
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

    # Score the PIPED owner string. Flattening " | " to " " merged co-owners
    # into a single bag of tokens, so "BARBEE DONALD RAY | BARBEE LORETTA B"
    # scored 1.00 against decedent "Barbee, Ray Buford" — BARBEE and RAY are
    # both present, but they come from different people. _split_owner_segments
    # needs the separator to tell the owners apart. Week 28 audit: this put
    # Barbee on a stranger's parcel and the row was dropped.
    if force_score is not None:
        score = force_score
    else:
        score = _name_match_score(decedent_name, owner_full)
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

    # Per-county explicit situs city/zip fields (when GIS exposes them
    # separately from the owner-mailing city/zip). Without these, swap-on-DQ
    # leaves Property City/Zip blank when the new parcel's owner mails out
    # of state — Hannah David Jon swap to 208 Park St lost ZIP 28016 because
    # owner mailing was MILTON FL 325703762.
    sf_city = cfg.get("situs_city_field")
    sf_zip = cfg.get("situs_zip_field")
    if sf_city and not situs_city_override:
        v = rec.get(sf_city)
        if v not in (None, "", 0):
            situs_city_override = str(v).strip().title()
    if sf_zip and not situs_zip_override:
        v = rec.get(sf_zip)
        if v not in (None, "", 0):
            situs_zip_override = str(v).strip()

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
        # Gaston codes a lot whose only structure is an outbuilding as
        # property_use=RES + DESC1_DESC='Auxiliary Improvement' (no dwelling:
        # YEARBLT=0, SQFT=0). Functionally vacant land. Putnam 26E001064-350
        # Week 33: the $32K 0.99-ac aux lot on Belton Ave carried
        # is_residential=True, so nothing ever demoted it below the $233K
        # house next door at 423 Belton Ave.
        if "AUXILIARY IMPROVEMENT" in desc_upper:
            is_vacant = True
            is_residential = False

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
                        "AppraisedValue",
                        # County-specific names discovered Week 26 audit:
                        # Gaston exposes TOTVAL, Iredell Total_Value,
                        # Lincoln TOTALVALUE, Rowan TOT_VAL. Without these,
                        # the $500K drop filter only fired in Cabarrus +
                        # Mecklenburg (2 of 7 counties).
                        "TOTVAL", "Total_Value", "TOTALVALUE", "TOT_VAL"):
        v = rec.get(value_field)
        if v not in (None, "", 0, 0.0):
            try:
                market_value = float(v)
                break
            except (TypeError, ValueError):
                continue

    lot_area = acres_from_arcgis_attrs(rec)

    # Sale date + price: each county uses its own field names and date
    # format. Helpers below normalize into ISO 'YYYY-MM-DD' + float.
    # Used by drop_recently_sold polish step (24-month window) to filter
    # out properties already sold post-decedent's death (or pre-listed/
    # under-contract via county records).
    sale_date = _parse_arcgis_sale_date(rec)
    sale_price = _parse_arcgis_sale_price(rec)

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
        lot_area=lot_area,
        sale_date=sale_date,
        sale_price=sale_price,
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


def _parse_arcgis_sale_date(rec: dict) -> str | None:
    """Normalize ArcGIS sale-date variants into ISO 'YYYY-MM-DD' or None.

    Counties expose sale dates in 3 distinct formats:
      - Epoch milliseconds (Gaston SALEDATE = 1730782800000)
      - 'MM/DD/YYYY' strings (Iredell Sale_Date = '05/13/2014')
      - ISO 'YYYY-MM-DD' strings (Catawba deed_date = '2021-09-30')

    For year-only fields (Lincoln DEEDYR=1997, Rowan DEEDYEAR=2010.0),
    we synthesize 'YYYY-01-01' so the 24-month cutoff has SOMETHING to
    work with — slightly pessimistic (treats sales as Jan 1) which
    means a property sold late in 2024 reads as 2024-01-01, but for
    the 24-month-cutoff use case that's safer than dropping the field.
    """
    from datetime import datetime, timezone
    # Priority 1: full date fields
    for field in ("SaleDate", "SALEDATE", "Sale_Date", "sale_date",
                  "DeedDate", "deed_date", "LastSaleDate", "SaleDt"):
        v = rec.get(field)
        if v in (None, "", " ", 0):
            continue
        # Epoch ms (integer or float)
        if isinstance(v, (int, float)):
            try:
                dt = datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d")
            except (OSError, ValueError, OverflowError):
                continue
        s = str(v).strip()
        if not s:
            continue
        # ISO format already?
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        # MM/DD/YYYY
        if "/" in s:
            for fmt in ("%m/%d/%Y", "%m/%d/%y"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
    # Priority 1.5: year + month (Cabarrus OpenData/Tax_Parcels publishes
    # SaleYear/SaleMonth and no day) — synthesize the 1st of that month.
    yr_v, mo_v = rec.get("SaleYear"), rec.get("SaleMonth")
    if yr_v not in (None, "", 0, 0.0):
        try:
            yr = int(float(yr_v))
            mo = int(float(mo_v)) if mo_v not in (None, "", 0, 0.0) else 1
            if 1900 <= yr <= 2100 and 1 <= mo <= 12:
                return f"{yr:04d}-{mo:02d}-01"
        except (TypeError, ValueError):
            pass
    # Priority 2: year-only fallback — synthesize Jan 1
    for field in ("Sale_Yr", "SALE_YEAR", "DEEDYR", "DEEDYEAR"):
        v = rec.get(field)
        if v in (None, "", 0, 0.0):
            continue
        try:
            yr = int(float(v))
            if 1900 <= yr <= 2100:
                return f"{yr:04d}-01-01"
        except (TypeError, ValueError):
            continue
    return None


def _parse_arcgis_sale_price(rec: dict) -> float | None:
    """Read sale price from any of the variant ArcGIS field names."""
    for field in ("SalePrice", "SALEPRICE", "Sales_Price", "sale_amoun",
                  "SALESAMT", "SALE_AMT", "Sale_Price", "LastSalePrice"):
        v = rec.get(field)
        if v in (None, "", 0, 0.0):
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


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
    if not candidates:
        # Nothing titled in the decedent's own name — the property is
        # sometimes held by a family trust or LLC (e.g. "THE PIERCE FAMILY
        # TRUST"). Try surname-anchored entity patterns before giving up.
        candidates = _lookup_trust_variants(decedent_name, county_key, min_score)
    logger.info(
        "%s GIS: %r → %d raw rows → %d scoring matches",
        county_key.title(), decedent_name, len(raw_rows), len(candidates),
    )
    return candidates


# ── Trust / LLC ownership fallback ───────────────────────────────────
# When a decedent's regular name search returns 0 accepted candidates, the
# property is sometimes titled to a family trust or LLC rather than the
# person (e.g. "THE PIERCE SR FAMILY TRUST", "SMITH FAMILY LLC"). The
# regular search (LIKE 'PIERCE%') misses these when the entity name doesn't
# START with the surname, and _arcgis_to_candidate score-rejects them when
# it does (an entity has no first/middle name to match). This fallback runs
# a small set of surname-ANCHORED entity patterns and accepts hits at a
# capped 0.75 "worth a human look" score — a FAMILY trust could belong to a
# relative, not this decedent's estate, so it's a lead to verify, not a
# confirmed parcel.
#
# Deliberately NARROW to avoid the junk-parcel blow-up that made
# find_heir_transfer_candidates skip trusts entirely: every query pattern is
# anchored on the decedent's actual surname, AND every hit is re-checked for
# a trust/LLC marker + the surname as a token before it's accepted.
#
# ArcGIS counties only (Cabarrus, Gaston, Iredell, Lincoln, Rowan). Catawba
# (PHP) and Mecklenburg (polaris3g) are out of scope — Catawba's trust gap
# needs the separate GeoServer WFS route. Off-switch: NC_TRUST_FALLBACK=0.

_TRUST_MARKER_RE = re.compile(
    r"\b(TRUSTEE|TRUST|REVOCABLE|IRREVOCABLE|LIVING|FAMILY|PROPERTIES|"
    r"L\.?L\.?C\.?|ESTATE)\b",
    re.IGNORECASE,
)

_TRUST_FALLBACK_SCORE = 0.75


def _lookup_trust_variants(
    decedent_name: str, county_key: str, min_score: float = 0.7,
    *, max_rows: int = 300,
) -> list[PropertyCandidate]:
    """Surname-anchored trust/LLC fallback for ArcGIS counties. Fires only
    when the regular decedent-name search found nothing. Returns candidates
    stamped at the capped _TRUST_FALLBACK_SCORE."""
    if os.environ.get("NC_TRUST_FALLBACK", "1") == "0":
        return []
    # Capped score must still clear the caller's threshold to be worth querying.
    if _TRUST_FALLBACK_SCORE < min_score:
        return []
    if county_key in {"catawba", "mecklenburg"}:
        return []
    _first, _middle, last = split_decedent_name(decedent_name)
    if not last or len(last) < 3:
        return []
    last_upper = last.upper()
    # Don't run on decedents who are THEMSELVES entities — the regular search
    # already handled them and these patterns would be nonsense.
    if last_upper in {"TRUST", "ESTATE", "LLC", "INC", "CORP", "FUND", "BENEFIT"}:
        return []
    cfg = _ARCGIS_CONFIG.get(county_key)
    if not cfg:
        return []
    if is_endpoint_down(cfg["url"]):
        return []
    esc = last_upper.replace("'", "''")
    # Every pattern carries the surname; the marker re-check below rejects
    # coincidental hits like "THE <LAST> COMPANY" (no trust/LLC/family word).
    patterns = [
        f"{esc} FAMILY%",   # SMITH FAMILY TRUST / SMITH FAMILY LLC
        f"{esc}%TRUST",     # SMITH TRUST, SMITH REVOCABLE TRUST
        f"{esc}%LLC",       # SMITH PROPERTIES LLC
        f"THE {esc}%",      # THE SMITH FAMILY TRUST
        f"% {esc} %TRUST",  # <first> <LAST> LIVING TRUST (surname mid-string)
    ]
    seen_pids: set[str] = set()
    candidates: list[PropertyCandidate] = []
    for owner_field in cfg["owner_fields"]:
        for pat in patterns:
            where = f"UPPER({owner_field}) LIKE '{pat}'"
            try:
                r = requests.get(cfg["url"] + "/query", params={
                    "where": where, "outFields": "*", "returnGeometry": "false",
                    "f": "json", "resultRecordCount": max_rows,
                }, headers=_ARCGIS_HEADERS, timeout=30)
            except requests.RequestException as e:
                logger.warning("trust-fallback: query failed at %s: %s",
                               cfg["url"], e)
                continue
            if r.status_code != 200:
                continue
            try:
                feats = r.json().get("features") or []
            except ValueError:
                continue
            for feat in feats:
                rec = feat.get("attributes", {})
                pid = str(rec.get(cfg["parcel_field"]) or "")
                if not pid or pid in seen_pids:
                    continue
                owner_join = " ".join(
                    str(rec.get(fld) or "") for fld in cfg["owner_fields"]).upper()
                # Re-verify: must carry a trust/LLC marker AND the surname as
                # a whole token (guards "THE <LAST> COMPANY", stranger LLCs).
                if not _TRUST_MARKER_RE.search(owner_join):
                    continue
                if last_upper not in re.findall(r"[A-Z']+", owner_join):
                    continue
                c = _arcgis_to_candidate(
                    rec, county_key.title(), decedent_name, cfg,
                    force_score=_TRUST_FALLBACK_SCORE)
                if not c:
                    continue
                seen_pids.add(pid)
                candidates.append(c)
    if candidates:
        logger.info(
            "%s GIS trust-fallback: %r → %d entity parcel(s) at capped %.2f",
            county_key.title(), decedent_name, len(candidates),
            _TRUST_FALLBACK_SCORE,
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

    # Score the PIPED owner string. Flattening " | " to " " merged co-owners
    # into a single bag of tokens, so "BARBEE DONALD RAY | BARBEE LORETTA B"
    # scored 1.00 against decedent "Barbee, Ray Buford" — BARBEE and RAY are
    # both present, but they come from different people. _split_owner_segments
    # needs the separator to tell the owners apart. Week 28 audit: this put
    # Barbee on a stranger's parcel and the row was dropped.
    score = _name_match_score(decedent_name, owner_full)
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
    # The PHP owner table carries no valuation, so every Catawba candidate used
    # to arrive with market_value=None — which silently disabled BOTH the $500K
    # buy-box cap and the $10K standalone floor for the entire county. Enrich
    # from the county's GeoServer parcel layer.
    _catawba_enrich_values(candidates)
    logger.info(
        "Catawba GIS (PHP): %r → %d raw rows → %d unique parcels matching (min_score=%.2f)",
        decedent_name, len(rows), len(candidates), min_score,
    )
    return candidates


# Catawba's public viewer is OpenLayers over GeoServer — there is no ArcGIS
# REST here (/arcgis/rest/services 404s). `catawba:parcels_plus` is the only
# layer carrying owner + property address + mailing + valuation.
_CATAWBA_WFS_URL = "https://gis.catawbacountync.gov/geoserver/wfs"
_CATAWBA_WFS_LAYER = "catawba:parcels_plus"
_CATAWBA_WFS_FIELDS = (
    "pin,paddress,pcity,pzip,owner,oaddress,ocity,ozip,"
    "bldg_value,land_value,total_valu"
)


def _catawba_wfs_query(cql: str, *, max_features: int = 200) -> list[dict]:
    """Run a CQL query against Catawba's GeoServer WFS. Returns property dicts.

    GeoServer speaks `cql_filter` (not ArcGIS `where`) and returns GeoJSON
    `features[].properties` (not `features[].attributes`), so this cannot reuse
    _arcgis_query.
    """
    if not cql:
        return []
    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "typeName": _CATAWBA_WFS_LAYER, "outputFormat": "application/json",
        "propertyName": _CATAWBA_WFS_FIELDS, "cql_filter": cql,
        "maxFeatures": str(max_features),
    }
    try:
        r = requests.get(_CATAWBA_WFS_URL, params=params, headers=_ARCGIS_HEADERS, timeout=45)
    except requests.RequestException as e:
        logger.warning("Catawba WFS: query failed: %s", e)
        return []
    if r.status_code != 200:
        logger.warning("Catawba WFS: HTTP %d", r.status_code)
        return []
    try:
        data = r.json()
    except ValueError:
        logger.warning("Catawba WFS: invalid JSON")
        return []
    return [f.get("properties", {}) for f in (data.get("features") or [])]


def _catawba_enrich_values(candidates: list[PropertyCandidate]) -> None:
    """Fill market_value + vacancy on Catawba candidates, in place.

    Vacancy: `bldg_value == 0`. Catawba exposes no use code (zoning R-* maps
    everything to SFR today), so this is the only reliable vacant signal.
    Verified on Titterington's $2,000 lot at Forrest Creek Dr vs his two
    improved parcels.
    """
    pins = [c.pid for c in candidates if c.pid]
    if not pins:
        return
    by_pin: dict[str, dict] = {}
    for i in range(0, len(pins), 50):  # keep the CQL IN() list sane
        chunk = pins[i:i + 50]
        cql = "pin IN (" + ",".join(f"'{p}'" for p in chunk) + ")"
        for props in _catawba_wfs_query(cql, max_features=len(chunk)):
            if props.get("pin"):
                by_pin[str(props["pin"])] = props
    if not by_pin:
        logger.warning("Catawba WFS: no valuation returned for %d parcel(s) — "
                       "buy-box cap and value floor will not apply", len(pins))
        return
    for c in candidates:
        props = by_pin.get(c.pid)
        if not props:
            continue
        c.market_value = _safe_float(props.get("total_valu"))
        bldg = _safe_float(props.get("bldg_value")) or 0.0
        if bldg == 0.0:
            c.is_vacant_land = True
            c.is_residential = False
            if not c.use_description:
                c.use_description = "Vacant"


def _lookup_iredell(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "iredell", min_score)


def _lookup_lincoln(decedent_name: str, min_score: float = 0.7) -> list[PropertyCandidate]:
    return _lookup_arcgis_county(decedent_name, "lincoln", min_score)


# Lincoln's parcel-viewer query (ZONING) carries no structure type, so a condo
# or townhouse reads as SFR. The real dwelling style lives in the Property
# Record Card's backing tables: MainInfoLive links PIN -> AKPAR_ (account no.),
# and Major_Improvement_View.AHDESC holds the style ('TOWNHOUSE', 'CONDOMINIUM',
# 'SINGLE FAMILY', 'MOBILE HOME', ...). Compessi 26E000418-540 (PIN 4603760575
# -> AKPAR_ 79206 -> AHDESC 'TOWNHOUSE') was the trigger.
_LINCOLN_TABLES = ("https://arcgisserver.lincolncountync.gov/arcgis/rest/"
                   "services/Server_Tables/MapServer")
_lincoln_structure_cache: dict[str, str] = {}


def _lincoln_ahdesc_to_bucket(ahdesc: str) -> str:
    d = (ahdesc or "").strip().upper()
    if not d:
        return ""
    if "TOWNHOUSE" in d or "TOWN HOUSE" in d or "ROW" in d:
        return "Townhouse"
    if "CONDO" in d:
        return "Condo"
    if "MOBILE" in d or "MANUFACTURED" in d or "MODULAR" in d:
        return "MH"
    if "SINGLE" in d or "CONVENTIONAL" in d or "RANCH" in d or "CAPE" in d \
            or "SPLIT" in d or "COLONIAL" in d or "DWELLING" in d:
        return "SFR"
    return ""


def lincoln_structure_type(pin: str) -> str:
    """Return our use-bucket for a Lincoln parcel's dwelling style, or "".

    Two-step: PIN -> AKPAR_ (MainInfoLive), AKPAR_ -> AHDESC
    (Major_Improvement_View). Vacant parcels have no improvement row and
    return "". Results cached per-process. Never raises — on any error the
    caller keeps its existing classification.
    """
    pin = (pin or "").strip()
    if not pin:
        return ""
    if pin in _lincoln_structure_cache:
        return _lincoln_structure_cache[pin]
    result = ""
    try:
        r = requests.get(f"{_LINCOLN_TABLES}/1/query", params={
            "where": f"PIN='{pin}'", "outFields": "AKPAR_",
            "returnGeometry": "false", "f": "json"},
            headers=_ARCGIS_HEADERS, timeout=20)
        feats = (r.json() or {}).get("features", [])
        akpar = str(feats[0]["attributes"].get("AKPAR_") or "").strip() if feats else ""
        if akpar:
            r2 = requests.get(f"{_LINCOLN_TABLES}/8/query", params={
                "where": f"AGPAR_='{akpar}'", "outFields": "AHDESC",
                "returnGeometry": "false", "f": "json"},
                headers=_ARCGIS_HEADERS, timeout=20)
            ifeats = (r2.json() or {}).get("features", [])
            ahdesc = str(ifeats[0]["attributes"].get("AHDESC") or "").strip() if ifeats else ""
            result = _lincoln_ahdesc_to_bucket(ahdesc)
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        logger.debug("lincoln_structure_type(%s) failed: %s", pin, e)
        return ""   # transient — don't poison the cache
    _lincoln_structure_cache[pin] = result
    return result


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


# Counties whose parcel layer stores the situs as SEPARATE component columns
# (house number + street name) instead of one combined string. A LIKE on any
# single column can never match a full "156 MANOR CIR" address — the house
# number lives in one field and the street name in another — so lookup_by_address
# must build a composite WHERE for these. Iredell: HouseNumber + STREET (its
# ADD1 holds the MAILING address, and PHYSADDR isn't populated — which is why
# every situs address lookup silently returned nothing; Barnett/Barnette
# 26E002615-590 156 Manor Cir was invisible).
_COMPONENT_SITUS_FIELDS: dict[str, tuple[str, str]] = {
    "iredell": ("HouseNumber", "STREET"),
}

_STREET_SUFFIX_TOKENS = {
    "DR", "DRIVE", "CT", "COURT", "PL", "PLACE", "LN", "LANE", "RD", "ROAD",
    "ST", "STREET", "AVE", "AVENUE", "BLVD", "BOULEVARD", "CIR", "CIRCLE",
    "TER", "TERRACE", "TRL", "TRAIL", "PKWY", "PARKWAY", "HWY", "HIGHWAY",
    "CV", "COVE", "SQ", "SQUARE", "WAY", "LOOP", "RUN", "PATH", "XING", "PT", "POINT",
}


def _split_house_street(address: str) -> tuple[str, str]:
    """('156 Manor Cir') -> ('156', 'MANOR'); drops the trailing street
    suffix so a component-field query matches. ('','') when unparseable.
    Takes only the street portion (before the first comma) so a full
    '156 Manor Circle, Mooresville, NC 28115' still parses to house+street."""
    address = (address or "").split(",")[0]
    parts = _normalize_address_for_query(address).split()
    if not parts or not parts[0].isdigit():
        return "", ""
    house = parts[0]
    street_tokens = parts[1:]
    while street_tokens and street_tokens[-1].upper() in _STREET_SUFFIX_TOKENS:
        street_tokens = street_tokens[:-1]
    return house, " ".join(street_tokens).upper()


def parcel_centroid(county: str, situs_address: str = "",
                    pid: str = "") -> tuple[float, float] | None:
    """(lat, lon) of a parcel's centroid, for reverse-geocoding its city/zip.

    The county GIS has no reliable situs CITY/ZIP field (Iredell's is often
    "00"; CITY tracks OWNER mailing — wrong for absentee owners). The parcel's
    map location does not lie, so we take the polygon centroid and reverse-
    geocode it. Requests geometry in WGS84 (outSR=4326) so no reprojection is
    needed. Matches by Parcel ID first (works for vacant "0 <street>" and
    number-less situs like "WELLINGTON DR"), then by street prefix. ArcGIS
    counties only (Cabarrus/Catawba/Mecklenburg use other APIs).
    """
    cfg = _ARCGIS_CONFIG.get(county.lower())
    if not cfg or not cfg.get("url"):
        return None

    wheres: list[str] = []
    if pid:
        pf = cfg.get("parcel_field") or "PIN"
        wheres.append(f"{pf}='{pid}'")
    pattern = _street_token_pattern(situs_address)
    if pattern:
        for fld in (_ADDRESS_FIELDS_BY_COUNTY.get(county.lower())
                    or cfg.get("situs_fields") or []):
            wheres.append(f"UPPER({fld}) LIKE '{pattern}%'")

    for where in wheres:
        try:
            r = requests.get(cfg["url"] + "/query", params={
                "where": where, "returnGeometry": "true", "outSR": "4326",
                "f": "json", "resultRecordCount": 1,
            }, headers=_ARCGIS_HEADERS, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            feats = r.json().get("features") or []
        except ValueError:
            continue
        if not feats:
            continue
        rings = (feats[0].get("geometry") or {}).get("rings")
        if not rings or not rings[0]:
            continue
        pts = rings[0]
        n = len(pts)
        lat = sum(p[1] for p in pts) / n
        lon = sum(p[0] for p in pts) / n
        if -90 < lat < 90 and -180 < lon < 0:
            return (lat, lon)
    return None


def lookup_by_address(address: str, county: str, city_hint: str = "") -> list[dict]:
    """Find parcels in `county` whose situs starts with the given address
    prefix. Useful as a fallback when name-search fails — e.g. a beneficiary
    in the case data lives at the inherited property, or the user has the
    decedent's last-known address from Odyssey Party Information.

    `city_hint` — optional municipality, used only by Mecklenburg (polaris3g's
    situs search is exact-match and needs the city). Ignored elsewhere.

    Returns raw attribute dicts (caller chooses how to score / present).

    Catawba goes through GeoServer WFS (`catawba:parcels_plus`), whose property
    names match _ARCGIS_CONFIG["catawba"] (owner / paddress / pin), so callers
    need no special-casing. Mecklenburg (polaris3g) and Cabarrus still have no
    address path — Cabarrus's parcel layer exposes only MailAddr1, no situs.
    """
    if not address:
        return []
    county_key = county.lower()
    if county_key == "catawba":
        prefix = _street_token_pattern(address)
        if not prefix:
            return []
        return _catawba_wfs_query(f"paddress LIKE '{prefix}%'", max_features=50)
    if county_key == "mecklenburg":
        return _polaris3g_address_search(address, city_hint=city_hint)
    cfg = _ARCGIS_CONFIG.get(county_key)
    if not cfg or not cfg.get("url") or county_key == "mecklenburg":
        return []
    out: list[dict] = []
    seen_pids: set[str] = set()
    pid_field = cfg.get("parcel_field") or "PIN"

    # Component-situs counties (Iredell): house number + street name in
    # separate columns — build one composite WHERE instead of a per-field LIKE.
    if county_key in _COMPONENT_SITUS_FIELDS:
        num_field, street_field = _COMPONENT_SITUS_FIELDS[county_key]
        house, street = _split_house_street(address)
        if not house or not street:
            return []
        where = f"{num_field}='{house}' AND UPPER({street_field}) LIKE '{street}%'"
        try:
            r = requests.get(cfg["url"] + "/query", params={
                "where": where, "outFields": "*", "returnGeometry": "false",
                "f": "json", "resultRecordCount": 50,
            }, headers=_ARCGIS_HEADERS, timeout=30)
            if r.status_code == 200:
                for feat in r.json().get("features", []):
                    attrs = feat.get("attributes", {})
                    pid = str(attrs.get(pid_field) or "")
                    if pid and pid in seen_pids:
                        continue
                    seen_pids.add(pid)
                    out.append(attrs)
        except (requests.RequestException, ValueError) as e:
            logger.warning("lookup_by_address: component query failed at %s: %s", cfg["url"], e)
        return out

    pattern = _street_token_pattern(address)
    if not pattern:
        return []
    fields = _ADDRESS_FIELDS_BY_COUNTY.get(county_key) or cfg.get("situs_fields") or []
    if not fields:
        return []
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
_PERSIST_VERSION = 20  # bumped 2026-08-13 (2nd bump today). v20: compound-first-name
# normalization in _name_match_score_one — "IRISH JOANN SCOTT TRUSTEE" now scores
# 1.00 against court "Irish, Jo Ann Scott" (was 0.4; Cabarrus 26E000837-120 shipped
# parcel-less). Cached candidates carry old scores baked in, so bump per precedent.
# Prior: v19: Gaston RES + 'Auxiliary Improvement' (lot with shed/garage, no dwelling) now is_vacant_land=True / is_residential=False + simplify_use_code -> Vacant Land. Cached candidates carry the old flags baked in (Putnam 26E001064-350's $32K aux lot was cached is_residential=True), so bump per the v13 precedent. Prior: v18 2026-07-23. v17: _name_match_score_one scores a full-first+full-last match with a CONFLICTING middle at 0.6 (review band) instead of 0.4, so cases like Lackey 26E000718-480 surface for verification instead of dropping parcel-less. v18: short entity suffixes (LP/PA/CO/PC/LC/PL) no longer count as a first initial — "BEAVER LP" was scoring 0.70 against "Beaver, Linda Gale" and outranking four real Linda Beavers (26E000762-790). Cached candidates carry the old scores baked in, so each change needs its own bump. Gaston RES + 'Auxiliary Improvement' (lot with shed/garage, no dwelling) now is_vacant_land=True / is_residential=False + simplify_use_code -> Vacant Land. Cached candidates carry the old flags baked in (Putnam 26E001064-350's $32K aux lot was cached is_residential=True), so bump per the v13 precedent. Prior: v18 2026-07-23. v17: _name_match_score_one scores a full-first+full-last match with a CONFLICTING middle at 0.6 (review band) instead of 0.4, so cases like Lackey 26E000718-480 surface for verification instead of dropping parcel-less. v18: short entity suffixes (LP/PA/CO/PC/LC/PL) no longer count as a first initial — "BEAVER LP" was scoring 0.70 against "Beaver, Linda Gale" and outranking four real Linda Beavers (26E000762-790). Cached candidates carry the old scores baked in, so each change needs its own bump.
# v13 (same day, earlier pass): stopped flattening " | " between co-owners before
# scoring; stopped treating a lone "V" as a generational suffix; graded
# _middle_match_strength; Gaston code=RES + desc='Vacant' -> Vacant Land.
_PERSIST_TTL_DAYS = int(os.environ.get("NC_GIS_CACHE_TTL_DAYS", "14"))
_PERSIST_DISABLED = os.environ.get("NC_GIS_CACHE_DISABLE", "") == "1"
_persist_store: dict[str, dict] | None = None  # None = not yet loaded

# ── Cache size control (2026-08-06) ──────────────────────────────────
# The file had grown to 403 MB / 1,278 entries (avg 128 candidates each,
# worst 1,104 — Iredell prefix-LIKE searches return most of the county).
# Because _persist_put write-throughs the WHOLE store on every successful
# lookup, a normal night rewrote tens of GB. Two fixes, neither of which
# changes matching behaviour (so NO _PERSIST_VERSION bump — bumping would
# throw away 1,278 good lookups and re-hit the slow county GIS):
#
#   1. `raw` (the unparsed GIS record) is NOT persisted. It is 81% of every
#      entry and is write-only — nothing in the codebase ever reads
#      PropertyCandidate.raw after construction (verified 2026-08-06). Live
#      in-process objects still carry it; only the disk copy drops it.
#   2. Candidates per entry are capped. EVERY candidate scoring >= 0.7 (the
#      "strong match" band) is always kept no matter how many, so a genuine
#      multi-parcel estate is never truncated (biggest real one seen:
#      Holbrook 26E002916-590, 9 parcels). Only the weak-scoring tail —
#      same-surname strangers that every caller's min_score filters out
#      anyway — is trimmed.
#
# Flushes are batched (dirty flag + every _PERSIST_FLUSH_EVERY puts + at
# process exit) instead of once per put. A crash loses at most a few cached
# lookups, which simply get re-fetched — a cache miss is safe, never wrong.
_MAX_CACHED_CANDIDATES = int(os.environ.get("NC_GIS_CACHE_MAX_CANDIDATES", "60"))
_STRONG_SCORE_KEEP_ALL = 0.7
_PERSIST_FLUSH_EVERY = int(os.environ.get("NC_GIS_CACHE_FLUSH_EVERY", "25"))
_persist_dirty = 0  # puts since last flush


def _trim_for_cache(candidates: list[PropertyCandidate]) -> list[dict]:
    """Serialize candidates for disk: drop `raw`, cap the weak-scoring tail.

    Keeps every strong (>= 0.7) match plus the highest-scoring remainder up
    to _MAX_CACHED_CANDIDATES total.
    """
    strong = [c for c in candidates if (c.match_score or 0) >= _STRONG_SCORE_KEEP_ALL]
    weak = sorted(
        (c for c in candidates if (c.match_score or 0) < _STRONG_SCORE_KEEP_ALL),
        key=lambda c: c.match_score or 0, reverse=True,
    )
    room = max(0, _MAX_CACHED_CANDIDATES - len(strong))
    out = []
    for c in [*strong, *weak[:room]]:
        d = asdict(c)
        d.pop("raw", None)  # write-only field — never read back
        out.append(d)
    return out


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
    global _persist_dirty
    for k, v in entries.items():
        try:
            if datetime.fromisoformat(v.get("ts", "")) < cutoff:
                continue
        except (ValueError, AttributeError):
            continue
        # Compact legacy entries in place: older files carry the write-only
        # `raw` blob (81% of their size) and an uncapped candidate tail.
        # Rewriting them here means the next flush shrinks the file without
        # invalidating anything (scores are untouched).
        cands = v.get("candidates")
        if isinstance(cands, list) and cands:
            has_raw = any(c.get("raw") for c in cands if isinstance(c, dict))
            strong = [c for c in cands
                      if isinstance(c, dict) and (c.get("match_score") or 0) >= _STRONG_SCORE_KEEP_ALL]
            weak = sorted(
                (c for c in cands
                 if isinstance(c, dict) and (c.get("match_score") or 0) < _STRONG_SCORE_KEEP_ALL),
                key=lambda c: c.get("match_score") or 0, reverse=True,
            )
            room = max(0, _MAX_CACHED_CANDIDATES - len(strong))
            keep = [*strong, *weak[:room]]
            # Only rewrite when something actually changes — an entry whose
            # strong matches alone exceed the cap is already minimal, and
            # re-flagging it would rewrite the file every single run.
            if has_raw or len(keep) != len(cands):
                trimmed = []
                for c in keep:
                    c = dict(c)
                    c.pop("raw", None)
                    trimmed.append(c)
                v["candidates"] = trimmed
                _persist_dirty += 1
        _persist_store[k] = v
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


def _persist_flush() -> None:
    """Write the store to disk atomically. No-op when nothing is pending."""
    global _persist_dirty
    if _PERSIST_DISABLED or _persist_store is None or not _persist_dirty:
        return
    try:
        _PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PERSIST_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"_version": _PERSIST_VERSION, "entries": _persist_store}),
            encoding="utf-8",
        )
        tmp.replace(_PERSIST_PATH)  # atomic on Windows + POSIX
        _persist_dirty = 0
    except OSError as e:
        logger.warning("nc_gis_lookup: could not write persistent cache: %s", e)


atexit.register(_persist_flush)


def _persist_put(decedent_name: str, county: str, candidates: list[PropertyCandidate]) -> None:
    """Persist a SUCCESSFUL lookup. Empties skipped; flush is batched."""
    global _persist_dirty
    if _PERSIST_DISABLED or not candidates:
        return
    store = _persist_load()
    store[_persist_key(decedent_name, county)] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "candidates": _trim_for_cache(candidates),
    }
    _persist_dirty += 1
    if _persist_dirty >= _PERSIST_FLUSH_EVERY:
        _persist_flush()


def _iso_date(s: str | None) -> str | None:
    """Normalize a date string to ISO 'YYYY-MM-DD'. Accepts ISO,
    'M/D/YYYY' / 'MM/DD/YYYY' (eCourts File Date), and 'Month D, YYYY'
    (OCR'd DOD). Returns None when unparseable — callers treat that as
    'no anchor', never as an error."""
    from datetime import datetime
    s = (s or "").strip()
    if not s:
        return None
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        return s[:10]
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def drop_posthumous_acquisitions(
    candidates: list[PropertyCandidate],
    anchor_date: str | None,
    *,
    context: str = "",
) -> list[PropertyCandidate]:
    """Drop candidates whose sale/deed date is AFTER the anchor date
    (decedent's DOD, or the estate filing date as a conservative stand-in).
    A dead person cannot acquire property — a post-anchor acquisition means
    the parcel belongs to a same-name STRANGER, not the decedent.

    Motivating case: Baker 26E002844-590 (Week 32) — 4 of 5 attached
    Mecklenburg parcels belonged to other living Joseph Bakers, one bought
    2026-04-02, two months after the decedent's 2026-02-05 death. A
    post-DOD purchase date is the fastest disqualifier for common-surname
    parcel clusters.

    Exemptions (kept even with a post-anchor date):
    - is_heir_transferred: the same-name-later-suffix post-probate transfer
      pattern — the deed moving to the heir AFTER death is exactly what the
      flag means, and those are deliberately kept as leads.
    - No sale_date on the candidate (no signal — never reject on absence).

    Year-only counties (Lincoln DEEDYR, Rowan DEEDYEAR) synthesize
    'YYYY-01-01', so this only rejects there when the deed YEAR is strictly
    after the anchor year — imprecise but never wrong in the reject
    direction.
    """
    anchor = _iso_date(anchor_date)
    if not anchor or not candidates:
        return list(candidates)
    kept: list[PropertyCandidate] = []
    for c in candidates:
        sd = _iso_date(c.sale_date)
        if sd and sd > anchor and not c.is_heir_transferred:
            logger.info(
                "POSTHUMOUS-ACQ rejected %s/%s pid=%s (%s): sale %s > anchor %s "
                "owner=%r", c.county, context, c.pid, c.situs_address, sd,
                anchor, c.owner_name)
            continue
        kept.append(c)
    return kept


def lookup_properties(
    decedent_name: str,
    county: str,
    *,
    min_score: float = 0.7,
    acquired_by: str | None = None,
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
    # Post-cache filter (never mutates the cached list) — so cached entries
    # are served correctly and no _PERSIST_VERSION bump is needed.
    if acquired_by:
        candidates = drop_posthumous_acquisitions(
            candidates, acquired_by, context=decedent_name)
    if min_score <= 0.4:
        return list(candidates)
    return [c for c in candidates if c.match_score >= min_score]


def _owner_has_suffix(owner_name: str, suffix: str) -> bool:
    """True if the owner_name token list includes the suffix marker."""
    if not suffix or not owner_name:
        return False
    tokens = re.sub(r"[^\w\s]", " ", owner_name.upper()).split()
    return suffix in tokens


# Tokens that mark an owner segment as an organisation rather than a person.
# "TRUSTEE" is deliberately absent — "PIERCE DOROTHY L TRUSTEE" is a person.
_ENTITY_SEGMENT_TOKENS = {
    "TRUST", "LLC", "LLP", "INC", "CORP", "CORPORATION", "PARTNERSHIP",
    "FOUNDATION", "ASSOCIATION", "CHURCH", "MINISTRIES", "COMPANY",
}


def _person_tokens(owner_name: str) -> list[str]:
    """Uppercase tokens from the PERSON segments of an owner string.

    Segments naming an organisation are dropped, so a generational suffix
    can't be harvested out of "THE PIERCE SR FAMILY TRUST".
    """
    if not owner_name:
        return []
    out: list[str] = []
    for seg in re.split(r"\s*[|&]\s*", owner_name.upper()):
        toks = re.sub(r"[^\w\s]", " ", seg).split()
        if any(t in _ENTITY_SEGMENT_TOKENS for t in toks):
            continue
        out.extend(toks)
    # If EVERY segment is an organisation there is no person suffix to find.
    # Return nothing rather than falling back to the raw tokens — otherwise a
    # single-segment "SMITH JOHN SR FAMILY TRUST" still yields a bogus "SR".
    return out


def _suffix_match_score(owner_name: str, decedent_suffix: str) -> int:
    """3-way suffix preference for the picker tiebreaker. Higher = better.

      2 = exact match (both have same suffix, or both have none)
      1 = decedent has suffix, owner doesn't (deed may have omitted it)
      0 = decedent has NO suffix but owner has one (likely different person —
          e.g. decedent "James R Beaver" vs owner "BEAVER JAMES R JR")

    Resolves Beaver 26E000659-120 (Cabarrus): two candidates scored 1.0,
    one was "BEAVER JAMES R JR" (different person, Sr decedent or no-
    suffix decedent), the other "BEAVER JAMES R" (matches no-suffix
    decedent). Old _owner_has_suffix tiebreaker returned False for both
    when decedent had no suffix, so the picker fell through to value
    and picked the wrong one.

    Entity segments are excluded before looking for a suffix: "THE PIERCE SR
    FAMILY TRUST" is a trust name, not a man called Pierce Sr. Week 28: that
    stray "SR" scored Dorothy Pierce's real deed a 0 here, and since suffix is
    the TOP tiebreaker it sank the correct parcel beneath a namesake.
    """
    o_tokens = _person_tokens(owner_name)
    o_suffix = ""
    for t in o_tokens:
        if t in _GENERATIONAL_SUFFIXES:
            o_suffix = t
            break
    d = (decedent_suffix or "").upper()
    if d == o_suffix:
        return 2  # both none, or both same
    if d and not o_suffix:
        return 1  # decedent has suffix, deed omitted it
    return 0      # decedent no suffix but deed has one, or mismatched suffixes


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
    return _middle_match_strength(owner_name, decedent_name) > 0


def _middle_match_strength(owner_name: str, decedent_name: str) -> int:
    """Graded middle-name agreement between a deed and the decedent.

      2 = deed carries the decedent's FULL middle word ("JONES MICHAEL GREGORY")
      1 = deed carries only a matching initial          ("JONES MICHAEL G")
      0 = no middle information, or it disagrees

    A full middle name is far stronger evidence than a bare initial, and the
    boolean version couldn't say so. Week 28: decedent "Jones, Michael Gregory"
    (Catawba) matched THREE parcels at 1.00 — "JONES MICHAEL GREGORY | JONES
    SUSAN B" (his, with his wife/PR Susan), "JONES CHRISTY P | JONES MICHAEL G"
    (a different Michael, different spouse), and a bare "JONES MICHAEL". The
    boolean tiebreaker rated the first two equal, and the picker took the
    stranger's house at 1866 Fairway Dr.
    """
    if not owner_name or not decedent_name:
        return 0
    _d_first, d_middle, _d_last = split_decedent_name(decedent_name)
    if not d_middle:
        return 0
    d_middle_words = [w for w in d_middle.split() if w]
    d_middle_initials = {w[0] for w in d_middle_words}
    o_tokens = set(_normalize_name(owner_name).split())
    if any(len(w) > 1 and w in o_tokens for w in d_middle_words):
        return 2
    if any(len(t) == 1 and t in d_middle_initials for t in o_tokens):
        return 1
    # Decedent's middle is itself a single letter that matches a full owner word
    # ("Gaither, James I" vs deed "JAMES ISRAEL GAITHER").
    if any(len(w) == 1 and any(t[0] == w and len(t) > 1 for t in o_tokens)
           for w in d_middle_words):
        return 1
    return 0


def _situs_affinity(candidate: PropertyCandidate, decedent_address: str) -> int:
    """How well a parcel's situs matches the decedent's own known address.

      2 = same house number AND same street
      1 = same street, different number (lot clusters, adjacent parcels)
      0 = no address known, or no match

    POSITIVE SIGNAL ONLY — never a penalty. Measured 2026-07-09 against Oren's
    24 hand-verified Week-28 rows: only 15 decedents have an address on the
    Odyssey Parties response, and only 7 of those addresses equal the true
    property. Several point at the EXECUTOR's house instead (Gallimore's
    decedent address is 235 Noodle Way — Angela Kiser's — while the property is
    180 Noodle Way). So a match is near-proof; a non-match proves nothing, and
    must not push a candidate down.

    Ranked below match_score so a low-scoring stranger on the right street can
    never outrank a correctly-named deed.
    """
    if not decedent_address or not candidate.situs_address:
        return 0
    a = _street_tokens(decedent_address)
    b = _street_tokens(candidate.situs_address)
    if not a or not b:
        return 0
    a_num, a_street = a
    b_num, b_street = b
    if not a_street or a_street != b_street:
        return 0
    if a_num and b_num and a_num == b_num:
        return 2
    return 1


def _street_tokens(addr: str) -> tuple[str, str] | None:
    """('1433', 'POSTON') from '1433 Poston Dr'. Suffix + unit dropped so
    Odyssey's '3435 Huie S' still matches the deed's '3435 HUIE ST'."""
    if not addr:
        return None
    toks = re.sub(r"[^\w\s]", " ", addr.upper()).split()
    if not toks:
        return None
    num = toks[0] if toks[0].isdigit() else ""
    rest = toks[1:] if num else toks
    rest = [t for t in rest if t not in _STREET_SUFFIX_TOKENS and not t.isdigit()]
    if not rest:
        return None
    return (num, " ".join(rest))


# Suffixes and directionals stripped before comparing street names. Odyssey
# truncates ("Huie S" for "Huie St") and counties abbreviate inconsistently.
_STREET_SUFFIX_TOKENS = {
    "RD", "ROAD", "ST", "STREET", "DR", "DRIVE", "LN", "LANE", "CT", "COURT",
    "AVE", "AVENUE", "AV", "CIR", "CIRCLE", "HWY", "HIGHWAY", "WAY", "WY",
    "BLVD", "BOULEVARD", "PL", "PLACE", "TRL", "TRAIL", "PKWY", "TER", "TERRACE",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
}


def pick_best_candidate(
    candidates: list[PropertyCandidate],
    decedent_name: str = "",
    decedent_address: str = "",
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
            _suffix_match_score(c.owner_name, suffix),
            c.match_score,
            # Below match_score on purpose — see _situs_affinity's docstring.
            _situs_affinity(c, decedent_address),
            _middle_match_strength(c.owner_name, decedent_name),
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

        # A parcel acquired AFTER the estate was filed belongs to a
        # same-name stranger (dead people don't buy houses). Applied
        # OUTSIDE the cache so cached entries get filtered too.
        candidates = drop_posthumous_acquisitions(
            candidates, getattr(n, "date_added", None), context=decedent)

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
                # 2 decimals, NOT lot_size's :.0f — the buy-box exemption
                # turns on ">2 acres", and rounding to int would read 2.4ac
                # as 2 (no exemption) and 1.6ac as 2. Both wrong.
                new_n.lot_acres = f"{c.lot_area:.2f}"
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
