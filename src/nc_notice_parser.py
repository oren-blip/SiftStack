"""Parse individual notice pages from ncnotices.com.

Mirrors notice_parser.py but tuned to NC notice wording, NC case-number
formats, and NC county/state references. Produces the same NoticeData
dataclass so downstream enrichment + DataSift export are unchanged.

NC notice formats observed during recon (2026-05-16):

  Foreclosure:
    "NOTICE OF FORECLOSURE SALE 26SP000061-800 Under and by virtue of the
     power of sale contained in a certain Deed of Trust made by Bryanna P.
     Nelsen (PRESENT RECORD OWNER(S): Bryanna P. Nelsen) to ..."
    Also: "IN THE MATTER OF THE FORECLOSURE OF A DEED OF TRUST EXECUTED BY
           DEBORAH W. HONEYCUTT ..."
    Also: "AMENDED NOTICE OF TAX FORECLOSURE SALE ... action entitled
           COUNTY OF PERQUIMANS vs. CYNTHIA ROBERTS ..."

  Probate (NCGS 28A-14-1):
    "NOTICE TO CREDITORS Having qualified as Executor for the Estate of
     Jack William Dull (a/k/a Jack W. Dull) late of Forsyth County, NC ..."
    "Having qualified as Administrator of the Estate of Ava Lynn Burkard,
     deceased, Dare County, NC ..."
    "All persons, firms, and corporations having claims against Edward
     Henry Conklin, deceased of Rowan County, North Carolina ..."

Address indicator phrases ("commonly known as", "property address is", etc.)
behave the same in NC, so we reuse most of the TN _PROP_INDICATOR pattern.
"""

import logging
import re
from datetime import datetime

from playwright.async_api import Page

from notice_parser import NoticeData

logger = logging.getLogger(__name__)


# ── Reusable street-suffix pattern ───────────────────────────────────
_SUFFIX = (
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|"
    r"Boulevard|Blvd|Way|Circle|Cir|Court|Ct|Place|Pl|"
    r"Pike|Highway|Hwy|Trail|Trl|Terrace|Ter|Parkway|Pkwy|"
    r"Cove|Cv|Loop|Run|Path|Ridge|Rdg|Crossing|Xing|"
    r"Bend|Point|Pt|Pass|Hollow|Holw|Glen|Glenn|View|"
    r"Landing|Lndg|Row|Trace|Walk|Knoll|Overlook|Crest|Spur|Commons)\b"
)

_ADDR_PART = (
    r"(\d{1,5}\s+"
    r"(?:[NSEW]\.?\s+)?"
    r"(?:[\w'-]+\s+)+?"
    + _SUFFIX
    + r"\.?)"
)

_PROP_INDICATOR = (
    r"(?:"
    r"commonly\s+known\s+as"
    r"|property\s+known\s+as"
    r"|property\s+address\s*(?:is|of|:)"
    r"|(?:real\s+)?property\s+(?:located|situated)\s+at"
    r"|said\s+property\s+(?:being|is)"
    r"|hereinafter\s+(?:known|described)\s+as"
    r"|also\s+known\s+as"
    r"|a/?k/?a"
    r"|known\s+as"
    r"|bearing\s+the\s+address\s+(?:of\s+)?"
    r"|having\s+(?:the\s+)?address\s+(?:of\s+)?"
    r"|street\s+address\s*(?:is|of|:)?"
    r"|property\s+at"
    r"|with\s+(?:the|an)\s+address\s+(?:of\s+)?"
    r"|the\s+address\s+of\s+(?:which|said\s+property|the\s+property)\s+(?:is|being)"
    r")"
)

# NC ZIP range: 27006-28909 (27xxx and 28xxx prefixes)
_NC_STATE = r"(?:North\s+Carolina|N\.?\s*C\.?|NC)"

FULL_PROPERTY_RE = re.compile(
    _PROP_INDICATOR
    + r"\s*[:.,\s]*"
    + _ADDR_PART
    + r"(?:\s*[,.]?\s*(?:Suite|Ste|Apt|Unit|#)\s*\w+)?"
    + r"\s*[,.]\s*"
    + r"([\w][\w\s]*?)"                       # city
    + r"(?:\s*[,.]\s*\w+\s+County)?"
    + r"\s*[,.]\s*"
    + _NC_STATE
    + r"\s*[,.\s]*"
    + r"(\d{5}(?:-\d{4})?)?",
    re.IGNORECASE,
)

PROPERTY_ADDR_RE = re.compile(
    _PROP_INDICATOR + r"\s*[:.,\s]*" + _ADDR_PART,
    re.IGNORECASE,
)

# NC ZIP detection — keep prefix loose, validate against county after
NC_ZIP_RE = re.compile(r"\b(2[78]\d{3})(?:-\d{4})?\b")


# ── Owner name patterns (NC foreclosure) ──────────────────────────────

# "made by NAME (PRESENT RECORD OWNER(S): NAME)" — canonical NC foreclosure.
# Closing paren is the reliable terminator; we deliberately do NOT use "\.\s"
# because middle initials ("P. Nelsen") would truncate the name to "P".
PRESENT_RECORD_OWNER_RE = re.compile(
    r"PRESENT\s+RECORD\s+OWNER\(?S?\)?\s*:\s*"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s*\)|\s*\n|\s*;)",
    re.IGNORECASE,
)

# "made by NAME ..." — typically followed by parenthesis or "to TRUSTEE"
MADE_BY_RE = re.compile(
    r"made\s+by\s+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s*\(PRESENT\s+RECORD"
    r"|\s+to\s+[\w\s&,]+?(?:Trustee|Trust\b)"
    r"|\s*,\s*(?:dated|conveying|a\s|an\s|as\s|husband|wife|unmarried|single))",
    re.IGNORECASE,
)

# "EXECUTED BY NAME" — uppercase variant in IN THE MATTER OF... notices
EXECUTED_BY_RE = re.compile(
    r"EXECUTED\s+BY\s+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s+(?:DATED|TO|AND\s+RECORDED|CONVEYING)"
    r"|,\s*(?:dated|husband|wife))",
    re.IGNORECASE,
)

# "COUNTY OF XXX vs. NAME" — tax-foreclosure plaintiff-vs-defendant pattern
COUNTY_VS_RE = re.compile(
    r"COUNTY\s+OF\s+\w+\s+vs?\.\s+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s*,|\s+(?:and|et\s+al|\d)|\.\s)",
    re.IGNORECASE,
)

FORECLOSURE_OWNER_PATTERNS = [
    PRESENT_RECORD_OWNER_RE,  # highest signal — explicit label
    MADE_BY_RE,
    EXECUTED_BY_RE,
    COUNTY_VS_RE,
]


# ── Decedent + PR patterns (NC probate) ───────────────────────────────

# "Estate of NAME, deceased" / "Estate of NAME (a/k/a ...)"
DECEDENT_NAME_RE = re.compile(
    r"Estate\s+of\s+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s*\(a/?k/?a"
    r"|\s*,\s*(?:Deceased|deceased|dec['’.]?\s*d|late\s+of|who\s+died)"
    r"|\s+(?:deceased|late\s+of)"
    r"|\s*–\s*\d"        # en-dash + case number
    r"|\s*-\s*\d{2}E\d"        # case # like "- 26E000..."
    r")",
    re.IGNORECASE,
)

# "claims against NAME, deceased" — alt decedent phrasing
CLAIMS_AGAINST_RE = re.compile(
    r"claims\s+against\s+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"\s*,?\s+(?:deceased|late\s+of)",
    re.IGNORECASE,
)

# PR/Executor name — appears in the closing signature block.
# Canonical NC pattern: "This the Nth day of MONTH, YYYY. NAME, Title"
# A few notices use "This the Nth day MONTH of YYYY." (word-order swap).
# Salisbury Post uses "Today's date MM/DD/YYYY. NAME, as Title for the estate"
# REQUIRE a date prefix — without it the regex matches lead-in junk like
# "Having qualified as Administrator..." instead of the real PR name.
PR_NAME_RE = re.compile(
    r"(?:"
    r"This\s+(?:the\s+)?\d+(?:st|nd|rd|th)?\s+day\s+"
    r"(?:of\s+\w+,?\s*\d{4}|\w+\s+of\s+\d{4})"
    r"|Today'?s?\s+date\s+\d{1,2}/\d{1,2}/\d{2,4}"
    r")"
    r"\.?\s+"
    r"([A-Z][A-Za-z.\s,'-]+?[A-Za-z.])"
    r"\s*,\s*"
    r"(?:as\s+)?"  # Salisbury Post wraps title with 'as'
    r"(?:Executor|Executrix|Administrator|Administratrix|Personal\s+Representative|Ancillary\s+(?:Co-)?(?:Executor|Executrix|Administrator|Administratrix)|Co[-\s]?Administrator(?:s|ix)?|Co[-\s]?Executor(?:s|ix)?)",
    re.IGNORECASE,
)

# Alt: "qualified as Executor for the Estate of DEC. The Personal Rep is NAME"
# — fallback to labeled patterns when present
LABELED_PR_RE = re.compile(
    r"(?:Personal\s+Representative|Executor|Executrix|Administrator|Administratrix)"
    r"[:\s]+"
    r"([A-Z][A-Za-z\s.,'\-]+?)"
    r"(?:\s*,|\s*\(|\s+of\b|\s+for\b|\s+\d|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


# ── County extraction from notice body ────────────────────────────────

# "<County> County, North Carolina" / "<County> County, N.C." — strongest signal
COUNTY_FROM_BODY_RE = re.compile(
    r"\b([A-Z][A-Za-z]+)\s+County(?:\s*,\s*(?:North\s+Carolina|N\.?\s*C\.?|NC))",
    re.IGNORECASE,
)

# "late of <County> County, NC" — common NC probate phrasing.
# Require an NC state anchor to avoid grabbing out-of-state decedent counties
# (e.g. "late of Horry County, South Carolina" should NOT match).
LATE_OF_COUNTY_RE = re.compile(
    r"\blate\s+of\s+([A-Z][A-Za-z]+)\s+County\b\s*,?\s*"
    r"(?:North\s+Carolina|N\.?\s*C\.?|NC)\b",
    re.IGNORECASE,
)

# "NORTH CAROLINA <COUNTY> COUNTY" — uppercase header pattern
HEADER_COUNTY_RE = re.compile(
    r"NORTH\s+CAROLINA\s+([A-Z][A-Z]+)\s+COUNTY",
    re.IGNORECASE,
)


# ── Date patterns ─────────────────────────────────────────────────────

PUBLISH_DATE_RE = re.compile(
    r"Notice Publish Date:\s*\n?\s*(?:\w+day,\s*)?(\w+\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)

# Sale date — reuse TN patterns; NC foreclosure notices use the same vendor
# wording ("Sale Date:", "will be sold on", etc.)
_DATE_FRAGMENT = (
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s*)?"
    r"("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}\s*,?\s*\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r")"
)

AUCTION_DATE_PATTERNS = [
    re.compile(r"sale\s+will\s+be\s+(?:held\s+)?on\s+" + _DATE_FRAGMENT, re.IGNORECASE),
    re.compile(r"will\s+be\s+sold\b.{0,60}?\bon\s+" + _DATE_FRAGMENT, re.IGNORECASE | re.DOTALL),
    re.compile(r"Sale\s+Date\s*(?:and\s+\w+)?\s*:\s*" + _DATE_FRAGMENT, re.IGNORECASE),
    re.compile(r"public\s+auction\b.{0,80}?\bon\s+" + _DATE_FRAGMENT, re.IGNORECASE | re.DOTALL),
    re.compile(r",\s+on\s+" + _DATE_FRAGMENT + r"\s*,?\s+(?:at|on)\s+(?:or\s+about\s+)?\d{1,2}:\d{2}", re.IGNORECASE),
]


# ── Address validation ───────────────────────────────────────────────

_BAD_ADDR_WORDS = [
    "courthouse", "court house", "county building", "city building",
    "register", "office of", "entrance", "main entrance",
]


def _is_valid_address(addr: str) -> bool:
    if not addr or len(addr.strip()) < 5:
        return False
    low = addr.lower()
    if any(b in low for b in _BAD_ADDR_WORDS):
        return False
    m = re.match(r"(\d+)", addr)
    if m and (int(m.group(1)) < 1 or int(m.group(1)) > 99999):
        return False
    return True


_INVALID_NAMES = {
    "said property", "the grantor", "the grantors", "the creditor",
    "the creditors", "the respondent", "respondent", "the defendant",
    "defendant", "the borrower", "the mortgagor", "the debtor",
    "the estate", "the above", "the property", "the court",
    "all persons", "unknown heirs", "the undersigned",
    "the personal representative", "personal representative",
    "the executor", "the executrix", "the administrator",
}


def _is_valid_name(name: str) -> bool:
    low = name.strip().lower()
    if low in _INVALID_NAMES:
        return False
    for bad in _INVALID_NAMES:
        if low.startswith(bad):
            return False
    if len(name) > 80 or len(name) < 3:
        return False
    return True


# ── Main parser entry ────────────────────────────────────────────────


def parse_nc_notice_text(
    raw_text: str,
    county: str,
    notice_type: str,
    source_url: str = "",
    date_added: str = "",
) -> NoticeData:
    """Parse NC notice fields from already-extracted text.

    Used by sources that surface the full notice body inline (e.g. column.us
    aggregator) where there's no detail page to navigate. Caller supplies the
    raw notice text, fallback county + notice_type, optional source_url, and
    optional pre-extracted date_added.
    """
    notice = NoticeData(
        county=county,
        notice_type=notice_type,
        source_url=source_url,
        state="NC",
        date_added=date_added,
    )

    notice.raw_text = (raw_text or "").replace("\xa0", " ").strip()
    if not notice.raw_text:
        return notice

    # County from body — overrides caller-supplied county when present
    body_county = _extract_county(notice.raw_text)
    if body_county:
        notice.county = body_county

    _parse_address(notice)

    if notice_type == "probate":
        _parse_probate_parties(notice)
    else:
        _parse_foreclosure_owner(notice)
        _parse_auction_date(notice)

    return notice


async def parse_nc_notice_page(
    page: Page, county: str, notice_type: str, llm_api_key: str | None = None,
) -> NoticeData:
    """Extract structured fields from an ncnotices.com detail page.

    Same contract as notice_parser.parse_notice_page but tuned for NC text.
    Sets state="NC" on the returned NoticeData.
    """
    full_text = await page.inner_text("body")
    full_text = full_text.replace("\xa0", " ")

    notice_content = _extract_notice_content(full_text)
    body_text = notice_content if notice_content else full_text

    notice = parse_nc_notice_text(
        raw_text=body_text,
        county=county,
        notice_type=notice_type,
        source_url=page.url,
        date_added=_extract_publish_date(full_text),
    )

    if llm_api_key and _needs_llm(notice):
        try:
            from llm_parser import extract_with_llm

            llm_result = await extract_with_llm(
                notice.raw_text, notice_type, county, llm_api_key,
            )
            _apply_llm_fallback(notice, llm_result)
        except Exception as e:
            logger.debug("LLM fallback failed for %s: %s", page.url, e)

    return notice


# ── Helpers ──────────────────────────────────────────────────────────


def _extract_notice_content(full_text: str) -> str:
    """Strip page chrome and return just the notice body."""
    marker = "Notice Content"
    idx = full_text.find(marker)
    if idx == -1:
        return ""
    body = full_text[idx + len(marker):]
    for end_marker in ["\nBack\n", "\nIf you have any questions", "\nSelect Language"]:
        end_idx = body.find(end_marker)
        if end_idx != -1:
            body = body[:end_idx]
            break
    return body.strip()


def _extract_publish_date(full_text: str) -> str:
    m = PUBLISH_DATE_RE.search(full_text)
    if m:
        return _normalize_date(m.group(1))
    return ""


def _normalize_date(raw: str) -> str:
    raw = raw.strip().rstrip(".")
    for fmt in ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _extract_county(text: str) -> str:
    """Pull the property county from notice body, normalized to title-case.

    Tries the labeled forms first ("X County, North Carolina"), then the
    uppercase header form ("NORTH CAROLINA X COUNTY").
    """
    m = COUNTY_FROM_BODY_RE.search(text)
    if m:
        return m.group(1).strip().title()
    m = LATE_OF_COUNTY_RE.search(text)
    if m:
        return m.group(1).strip().title()
    m = HEADER_COUNTY_RE.search(text)
    if m:
        return m.group(1).strip().title()
    return ""


def _parse_address(notice: NoticeData) -> None:
    text = notice.raw_text

    m = FULL_PROPERTY_RE.search(text)
    if m:
        addr = _clean_address(m.group(1))
        if _is_valid_address(addr):
            notice.address = addr
            notice.city = _clean_city(m.group(2))
            if m.group(3):
                notice.zip = m.group(3)
            return

    m = PROPERTY_ADDR_RE.search(text)
    if m:
        addr = _clean_address(m.group(1))
        if _is_valid_address(addr):
            notice.address = addr
            _extract_city_zip_near(notice, text, m.end())


def _extract_city_zip_near(notice: NoticeData, text: str, addr_end: int) -> None:
    window = text[addr_end:addr_end + 200]
    city_state_re = re.compile(
        r"[,.\s]+([\w][\w\s]*?)"
        r"(?:\s*[,.]\s*\w+\s+County)?"
        r"\s*[,.]\s*" + _NC_STATE
        + r"\s*[,.\s]*(\d{5}(?:-\d{4})?)?",
        re.IGNORECASE,
    )
    m = city_state_re.search(window)
    if m:
        notice.city = _clean_city(m.group(1))
        if m.group(2):
            notice.zip = m.group(2)
        return
    z = NC_ZIP_RE.search(window)
    if z:
        notice.zip = z.group(1)


def _parse_foreclosure_owner(notice: NoticeData) -> None:
    for pat in FORECLOSURE_OWNER_PATTERNS:
        m = pat.search(notice.raw_text)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                notice.owner_name = name
                return


def _parse_probate_parties(notice: NoticeData) -> None:
    text = notice.raw_text

    # Decedent
    m = DECEDENT_NAME_RE.search(text)
    if m:
        name = _clean_name(m.group(1))
        if _is_valid_name(name):
            notice.decedent_name = name
    if not notice.decedent_name:
        m = CLAIMS_AGAINST_RE.search(text)
        if m:
            name = _clean_name(m.group(1))
            if _is_valid_name(name):
                notice.decedent_name = name

    # PR / Executor — try signature-line pattern first, then labeled
    m = PR_NAME_RE.search(text)
    if m:
        name = _clean_name(m.group(1))
        if _is_valid_name(name):
            notice.owner_name = name
            return
    m = LABELED_PR_RE.search(text)
    if m:
        name = _clean_name(m.group(1))
        if _is_valid_name(name):
            notice.owner_name = name


def _parse_auction_date(notice: NoticeData) -> None:
    text = notice.raw_text
    for pat in AUCTION_DATE_PATTERNS:
        m = pat.search(text)
        if m:
            normalized = _normalize_date(m.group(1).strip())
            if normalized and len(normalized) >= 8:
                notice.auction_date = normalized
                return


def _clean_address(raw: str) -> str:
    addr = re.sub(r"\s+", " ", raw).strip()
    return addr.rstrip(",. ")


def _clean_city(raw: str) -> str:
    city = re.sub(r"\s+", " ", raw).strip().rstrip(",. ")
    if city.isupper():
        city = city.title()
    return city


def _clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"\s+,?\s*(?:AND|and)\s*$", "", name)
    name = name.rstrip(",. ")
    return name.title()


def _needs_llm(notice: NoticeData) -> bool:
    if notice.notice_type == "probate":
        return not (notice.owner_name and notice.decedent_name)
    return not (notice.address and notice.owner_name)


def _apply_llm_fallback(notice: NoticeData, llm_result: dict) -> None:
    if notice.notice_type == "probate":
        if not notice.decedent_name and llm_result.get("decedent_name"):
            notice.decedent_name = llm_result["decedent_name"]
        if not notice.owner_name and llm_result.get("owner_name"):
            notice.owner_name = llm_result["owner_name"]
        if not notice.owner_street and llm_result.get("owner_street"):
            notice.owner_street = llm_result["owner_street"]
            notice.owner_city = llm_result.get("owner_city") or notice.owner_city
            notice.owner_state = llm_result.get("owner_state") or "NC"
            notice.owner_zip = llm_result.get("owner_zip") or notice.owner_zip
    else:
        if not notice.address and llm_result.get("address"):
            notice.address = llm_result["address"]
            notice.city = llm_result.get("city") or notice.city
            notice.zip = llm_result.get("zip") or notice.zip
        if not notice.owner_name and llm_result.get("owner_name"):
            notice.owner_name = llm_result["owner_name"]
        if not notice.auction_date and llm_result.get("auction_date"):
            notice.auction_date = llm_result["auction_date"]
