"""Extract a personal-representative phone, email, and mailing address from a
NC eCourts case's attached PDFs.

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

The SAME documents also carry the PR's own mailing address — see
`extract_pr_address`. Surfaced Week 30 (Lambert 26E002739-590): the Paid Funeral
Bill reads "Customer Name: Reid Carter / Address: 9001 Carindale Rd. / Waxhaw,
NC 28173", which is exactly the address Oren found by hand, while the pipeline
had no PR address at all and fell back to mailing the decedent's house. We had
already downloaded and OCR'd that PDF for the phone and discarded the rest of
the text — so this costs no extra (throttled) document fetches.

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
# "att[o0][rm]ney" tolerates the OCR mangling seen on real cover sheets
# ("Attomey Bar No.", "Zip OfAlfomey") — without it the attorney's own office
# address reads as an unguarded candidate on the Estates Action Cover Sheet.
_SKIP_CONTEXT = re.compile(
    r"fax|elder\s*law|law\s*(firm|office|group|pllc|pa\b)|att[o0][rm]ney|"
    r"bar\s*no|esq\b|name\s*of\s*firm|clerk\s+of|"
    r"superior\s+court|toll[\s\-]?free|funeral\s+home|mortuary|crematory",
    re.I,
)
_TOLLFREE = re.compile(r"^(?:800|833|844|855|866|877|888)")
# Email domains that belong to the estate's ATTORNEY, never to the PR.
_FIRM_DOMAIN = re.compile(
    r"@[\w.-]*(law|attorney|legal|esq|firm)[\w.-]*\.", re.I)

# Context words that raise confidence a number is the filer's personal contact.
_GOOD_CONTEXT = re.compile(
    r"mobile|cell|preferred|home\s*(phone|no)|telephone|applicant|petitioner|"
    r"executor|administrat|personal\s+rep|affiant|purchaser|informant",
    re.I,
)


# ── PR mailing address ────────────────────────────────────────────────────
# Street suffixes as they appear in filed docs (abbreviated or spelled out).
_SUFFIX = (r"rd|road|st|street|dr|drive|ln|lane|ave|avenue|ct|court|blvd|"
           r"boulevard|way|cir|circle|trl|trail|pl|place|hwy|highway|pkwy|"
           r"parkway|ter|terrace|loop|run|path|xing|crossing|sq|square|pt|point")
# "9001 Carindale Rd." / "480 Phaniel Church Rd" / "301 S. McDowell St. #410"
_STREET_RE = re.compile(
    r"\b(\d{1,6}\s+(?:[A-Za-z0-9'&.\-]+\s+){0,4}?(?:" + _SUFFIX + r")\b\.?"
    r"(?:\s+(?:apt|unit|ste|suite|#)\s*[A-Za-z0-9\-]+)?)",
    re.I,
)
# "Waxhaw, NC 28173" — also tolerates the missing comma / glued ZIP OCR produces.
_CSZ_RE = re.compile(
    r"\b([A-Za-z][A-Za-z .'\-]{1,28}?)\s*,?\s*\b(NC|SC|VA|GA|TN|FL|TX|NY|OH|PA)\b\s*"
    r"(\d{5})(?:-\d{4})?\b"
)
# A PO Box is a perfectly good mailing address for direct mail.
_POBOX_RE = re.compile(r"\bP\.?\s?O\.?\s*BOX\s*\d+\b", re.I)
# Label cues that mark an address block as the filer's own.
_ADDR_LABEL = re.compile(
    r"address|mailing|residing|resides|of\s+record|customer|purchaser|informant|"
    r"applicant|petitioner|affiant", re.I,
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _window(lines: list[str], i: int, n: int = 1) -> str:
    """Line `i` plus its `n` nearest NON-BLANK neighbours on each side.

    OCR'd court PDFs come back double-spaced — a blank line between every line
    of real text — so a naive lines[i-1:i+2] window is just ['', line, ''] and
    never reaches the adjacent label or name. On the Lambert funeral bill that
    put "Customer Name: Reid Carter" two indices above "Address: 9001 Carindale
    Rd.", costing both the address gate and the phone scorer's name bonus.
    """
    out = [lines[i]]
    for step in (-1, 1):
        seen, j = 0, i + step
        while 0 <= j < len(lines) and seen < n:
            if lines[j].strip():
                out.append(lines[j])
                seen += 1
            j += step
    return " ".join(out)


def extract_pr_address(text: str, pr_first: str = "", pr_last: str = "") -> dict:
    """Pull the personal representative's OWN mailing address out of a filed
    case PDF.

    Returns {"street", "city", "state", "zip", "score", "context"} — street is
    "" when nothing clears the bar.

    Same line-window scoring shape as `extract_contacts`, because the failure
    mode is identical: these documents also carry the ATTORNEY's office address
    and the FUNERAL HOME's address, and mailing a lead letter to either is worse
    than mailing nothing. Gates, per candidate street (±1-line window):
      +4 the PR's last name appears in the window   <- required, not just scored
      +1 the PR's first name appears
      +3 an "Address:/Customer/Applicant/..." label is present
      -5 a skip cue (attorney / bar no / firm / funeral home / clerk) is present
    Accept at >= 5, i.e. the PR's name must be adjacent AND something else must
    corroborate. On the Lambert cover sheet the attorney block scores 0 (the
    beneficiary list naming "Reid W. Carter" is two lines further up, outside
    the window), while the funeral bill's "Customer Name: Reid Carter /
    Address: 9001 Carindale Rd." scores 8.
    """
    empty = {"street": "", "city": "", "state": "", "zip": "", "score": 0, "context": ""}
    if not text:
        return empty
    last = (pr_last or "").strip().lower()
    first = (pr_first or "").strip().lower()
    if not last:
        return empty  # without a name to anchor on, every address is a guess

    lines = text.splitlines()
    best = None  # (score, street, city, state, zip, context)
    for i, line in enumerate(lines):
        window = _window(lines, i)
        wl = window.lower()
        if last not in wl:
            continue  # hard gate: the PR must be named right here
        if _SKIP_CONTEXT.search(window):
            continue
        m = _STREET_RE.search(line) or _POBOX_RE.search(line)
        if not m:
            continue
        street = " ".join(m.group(0).split()).rstrip(".,")
        score = 4
        if first and first in wl:
            score += 1
        if _ADDR_LABEL.search(window):
            score += 3
        if score < 5:
            continue
        # City/state/ZIP: same line first (two-column OCR flattens the block
        # onto one line — "Address: 9001 Carindale Rd. Phone 1: ... Waxhaw, NC
        # 28173"), then the following line for a normal stacked address block.
        city = state = zipc = ""
        for hay in (line[m.end():], line, " ".join(lines[i + 1: i + 3])):
            cm = _CSZ_RE.search(hay)
            if cm:
                city, state, zipc = (cm.group(1).strip().title(),
                                     cm.group(2).upper(), cm.group(3))
                break
        cand = (score, street, city, state, zipc, window.strip()[:120])
        if best is None or cand[0] > best[0]:
            best = cand

    if not best:
        return empty
    return {"street": best[1], "city": best[2], "state": best[3],
            "zip": best[4], "score": best[0], "context": best[5]}


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
            window = _window(lines, i)
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

    # Email: prefer one whose context isn't an attorney/firm line.
    # The context window is ±1 LINE, not the single line the address sits on:
    # OCR frequently isolates an email onto its own line, which strands it from
    # the "Attorney Email Address" / "NC Attorney Bar No." label right above it.
    # Russell 26E001013-350 cover sheet: OCR emitted "\ndawn@parkswilsonlaw.com\r"
    # alone, so the single-line check passed and the ATTORNEY's address was
    # about to be written into the row as the PR's own email.
    email = ""
    for m in _EMAIL_RE.finditer(text):
        e = m.group(0)
        i = text.rfind("\n", 0, m.start())
        prev = text.rfind("\n", 0, max(0, i))
        j = text.find("\n", m.end())
        nxt = text.find("\n", j + 1) if j != -1 else -1
        ctx = text[max(0, prev): nxt if nxt != -1 else len(text)]
        if _SKIP_CONTEXT.search(ctx):
            continue
        # A law-firm domain is a firm address no matter what the label says.
        if _FIRM_DOMAIN.search(e):
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
