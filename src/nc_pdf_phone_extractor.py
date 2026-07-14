"""Extract a personal-representative phone (and email) from a NC eCourts
case's attached PDFs.

Validated 2026-07-13 (Week 29 audit) against 5 live cases: 3 of 5 carried an
extractable PR phone in a filed PDF — a much higher hit rate than the original
"few and far between" guess. See [[project_estate_cover_sheet_phones]].

Which documents carry a phone (in priority order):
  1. Estates Action Cover Sheet (AOC-E-650) — applicant/attorney phone field.
  2. Family History Affidavit / Documentation — the affiant (usually the PR or
     a close relative) lists a contact phone.
  3. Paid Funeral Bill — the purchaser/informant (usually the PR) with a
     "(mobile)/(preferred)" cell AND an email.

The Application (AOC-E-201) and the Will never carry a phone — they are skipped
so the throttled document quota isn't spent on guaranteed misses.

This module only parses text; fetching the PDF bytes (WAF-gated, rate-limited)
is the caller's job via case_pdf_extractor.download_document_by_displaydoc.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Label patterns for the three productive doc types, most-likely-to-hit first.
# Matched against event_label / event_type_desc / document_name.
PHONE_DOC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cover_sheet", re.compile(r"cover\s*sheet", re.I)),
    ("family_history", re.compile(r"family\s*history", re.I)),
    ("funeral_bill", re.compile(r"funeral", re.I)),
]

_PHONE_RE = re.compile(r"(?<!\d)(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Numbers that are never a lead's personal contact — attorney firms, clerks,
# fax lines, toll-free. Detected by nearby context words.
_SKIP_CONTEXT = re.compile(
    r"fax|elder\s*law|law\s*(firm|office|group|pllc|pa\b)|attorney|clerk\s+of|"
    r"superior\s+court|toll[\s\-]?free|funeral\s+home|mortuary|crematory",
    re.I,
)
_TOLLFREE = re.compile(r"^(?:800|833|844|855|866|877|888)")

# Context words that raise confidence a number is the filer's personal contact.
_GOOD_CONTEXT = re.compile(
    r"mobile|cell|preferred|home\s*(phone|no)|telephone|applicant|petitioner|"
    r"executor|administrat|personal\s+rep|affiant|purchaser|informant",
    re.I,
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def extract_contacts(text: str, pr_first: str = "", pr_last: str = "") -> dict:
    """Score every phone/email in `text`; return the best PR contact.

    Returns {"phone": pretty, "phone_digits": "##########", "email": str,
    "score": int, "context": str}. Empty phone/email when nothing scores.

    Scoring per phone (line-scoped context = the ±1 line window):
      +4 the PR's last name appears in the window
      +3 a "mobile/cell/preferred/executor/applicant/..." cue word is present
      +1 the phone is on page 1 / early in the doc
      −5 a skip cue (fax / attorney firm / clerk / funeral home) is present
      toll-free numbers are dropped outright.
    """
    if not text:
        return {"phone": "", "phone_digits": "", "email": "", "score": 0, "context": ""}
    lines = text.splitlines()
    last = (pr_last or "").strip().lower()
    first = (pr_first or "").strip().lower()

    best = None  # (score, pretty, digits, context)
    for i, line in enumerate(lines):
        for m in _PHONE_RE.finditer(line):
            pretty = m.group(0).strip()
            digits = _digits(pretty)
            if len(digits) != 10 or _TOLLFREE.match(digits):
                continue
            window = " ".join(lines[max(0, i - 1): i + 2])
            score = 0
            if last and last in window.lower():
                score += 4
            if first and first in window.lower():
                score += 1
            if _GOOD_CONTEXT.search(window):
                score += 3
            frac = i / max(1, len(lines))
            if frac < 0.25:
                score += 1
            if _SKIP_CONTEXT.search(window):
                score -= 5
            cand = (score, pretty, digits, window.strip()[:80])
            if best is None or cand[0] > best[0]:
                best = cand

    # Email: prefer one on a line whose context isn't an attorney/firm line.
    email = ""
    for m in _EMAIL_RE.finditer(text):
        e = m.group(0)
        i = text.rfind("\n", 0, m.start())
        j = text.find("\n", m.end())
        ctx = text[max(0, i): j if j != -1 else len(text)]
        if _SKIP_CONTEXT.search(ctx):
            continue
        email = e
        if last and last in e.lower():
            break  # a personal-looking email wins

    if best is None or best[0] <= 0:
        return {"phone": "", "phone_digits": "", "email": email, "score": 0, "context": ""}
    return {
        "phone": best[1], "phone_digits": best[2], "email": email,
        "score": best[0], "context": best[3],
    }
