"""Extract phone numbers from probate court PDFs (e.g. Estate Cover Sheet).

Odyssey case pages link to a Documents section that includes the
PR's filing forms — most importantly the Estate Cover Sheet (filed
by the executor) and Family History form. Both routinely carry the
PR's phone number.

This module is the EXTRACTOR. The Odyssey-side document-fetch wiring
is deferred (needs WAF-token-authenticated download support in the
scraper). See README and the project_estate_cover_sheet_phones memory
for the wiring plan.

Usage:
    from estate_cover_sheet_phones import (
        extract_phones_from_pdf, pick_pr_phone,
    )
    phones = extract_phones_from_pdf(Path("estate_cover_sheet.pdf").read_bytes())
    best = pick_pr_phone(phones, pr_first="Jane", pr_last="Smith")
"""
from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)


# Phone number formats we see on NC court forms:
#   (704) 555-1234
#   704-555-1234
#   704.555.1234
#   7045551234
#   +1 (704) 555-1234
_PHONE_RE = re.compile(
    r"""
    (?:\+?1[\s.\-]?)?              # optional country code
    \(?(\d{3})\)?                  # area code
    [\s.\-]?
    (\d{3})                        # exchange
    [\s.\-]?
    (\d{4})                        # subscriber
    """,
    re.VERBOSE,
)

# Phone numbers we DO NOT want to capture — these appear as boilerplate on
# every court form (clerk of court, hotline numbers, etc.).
_BOILERPLATE_PREFIXES = {
    # NC State Bar / Clerk hotlines
    "800-662-7660", "8006627660",
    # Generic toll-free dummy numbers sometimes pre-printed
    "800-555-0000", "8005550000",
    # AOC public information line
    "919-890-1000", "9198901000",
}


def _normalize_phone(raw: str) -> str:
    """Strip non-digits and return a 10-digit phone or empty if invalid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return ""
    # NANP area codes can't start with 0 or 1
    if digits[0] in "01":
        return ""
    return digits


def _is_boilerplate(digits: str) -> bool:
    if digits in {p.replace("-", "") for p in _BOILERPLATE_PREFIXES}:
        return True
    return False


def _format_pretty(digits: str) -> str:
    """10 digits → '(704) 555-1234'."""
    if len(digits) != 10:
        return digits
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"


def extract_text_from_pdf(pdf_bytes: bytes) -> list[str]:
    """Return per-page text. Uses pypdfium2 (already a project dep)."""
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "pypdfium2 is required for PDF phone extraction (already a project dep)"
        ) from e
    out: list[str] = []
    doc = pdfium.PdfDocument(BytesIO(pdf_bytes))
    try:
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            try:
                out.append(textpage.get_text_range())
            finally:
                textpage.close()
            page.close()
    finally:
        doc.close()
    return out


def extract_phones_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Return a list of phone-occurrence dicts:
        {"digits": "7045551234", "pretty": "(704) 555-1234",
         "context": "...the line of text containing the match...",
         "page": 1}

    Empty list if PDF has no extractable text or no phone-shaped tokens.
    Skips boilerplate court / clerk numbers via _is_boilerplate.
    """
    pages = extract_text_from_pdf(pdf_bytes)
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for pno, text in enumerate(pages, start=1):
        for line in text.splitlines():
            for m in _PHONE_RE.finditer(line):
                digits = _normalize_phone(m.group(0))
                if not digits or _is_boilerplate(digits):
                    continue
                key = (pno, digits)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "digits": digits,
                    "pretty": _format_pretty(digits),
                    "context": line.strip()[:200],
                    "page": pno,
                })
    return out


# Cue words that appear NEAR the PR's phone on Estate Cover Sheets and
# Family History forms. Used to score candidate phones in pick_pr_phone.
_PR_CUE_WORDS = (
    "applicant", "petitioner", "executor", "executrix",
    "administrator", "administratrix",
    "personal representative", "personal rep",
    "next of kin", "interested person",
    "telephone", "phone", "phone number", "daytime",
)


def pick_pr_phone(
    phones: list[dict[str, Any]],
    *,
    pr_first: str = "",
    pr_last: str = "",
) -> str:
    """Pick the most likely PR phone from extracted candidates.

    Scoring:
      +3  context contains PR first or last name (strongest signal — the
          phone is on the same line as the PR's name).
      +2  context contains a PR cue word (executor/applicant/petitioner/
          telephone/etc).
      +1  it's the FIRST phone on the FIRST page (Estate Cover Sheets
          put the applicant's contact at the top).

    Returns the pretty-formatted phone, or empty string if no candidate.
    """
    if not phones:
        return ""
    pr_first_l = (pr_first or "").lower().strip()
    pr_last_l = (pr_last or "").lower().strip()
    best_score = -1
    best_pretty = ""
    for i, p in enumerate(phones):
        ctx = p["context"].lower()
        score = 0
        if pr_first_l and pr_first_l in ctx:
            score += 3
        if pr_last_l and pr_last_l in ctx:
            score += 3
        if any(cue in ctx for cue in _PR_CUE_WORDS):
            score += 2
        if i == 0 and p["page"] == 1:
            score += 1
        if score > best_score:
            best_score = score
            best_pretty = p["pretty"]
    # Require ANY signal (score > 0). Pure first-phone-no-context wins
    # via the +1 page-1 rule, so a zero-score fallthrough means we
    # didn't find any plausible PR phone.
    return best_pretty if best_score > 0 else ""
