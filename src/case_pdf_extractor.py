"""Case PDF extractor — download Odyssey-attached case documents and
LLM-parse them into structured data (will item structure, executor chain,
heirs with relationships).

Pipeline shape:
    case_id (256-char hex) -> list_case_documents() -> [(doc_id, label, date), ...]
    doc_id                  -> download_document()    -> pdf bytes
    pdf bytes               -> extract_text()         -> str (pypdfium2 native;
                                                        OCR fallback TBD)
    will text               -> parse_will()           -> structured dict

The download_document() endpoint is verified working WITHOUT auth — see
Earney 26E000838-350 prototype. The list_case_documents() endpoint is
not yet wired (TODO: discover Tyler Tech's "Events" or "Documents" API).
For now callers can supply a known doc_id directly.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Doc-fetch batch instrumentation (diagnose HTTP 602 staleness): timestamp of
# the first ViewDocument fetch this process, and whether we've logged the first
# success. Lets each 602 report how many seconds into the batch it fired.
_BATCH_FIRST_TS: float | None = None
_BATCH_LOGGED_FIRST_OK: bool = False


class DocRateLimited(RuntimeError):
    """Odyssey is throttling document downloads.

    The DocumentViewer/Embedded endpoint answers HTTP 202 with an empty
    body once the caller is over quota. Measured 2026-07-08: the bucket
    holds ~6 documents and refills at roughly one per 50s. It is keyed on
    client IP, not on the WAF token — a stale token behaves identically to
    a fresh one, and re-solving the WAF does not reset it.

    This is NOT a per-document failure: the same fragment returns a real
    PDF once the bucket refills. So never fall through to api/ViewDocument
    on this (that endpoint always 602s) and never mark the doc as missing.
    """


# Backoff applied when Odyssey throttles a document fetch. One refill token
# lands roughly every 50s, so 60s is a little over one token.
DOC_BACKOFF_SECONDS = int(os.environ.get("NC_DOC_BACKOFF_SECONDS", "60"))
DOC_MAX_RETRIES = int(os.environ.get("NC_DOC_MAX_RETRIES", "2"))


# ── HTTP layer ────────────────────────────────────────────────────────


_PORTAL_BASE = "https://portal-nc.tylertech.cloud"
_DOC_VIEWER_LONGHEX_URL = _PORTAL_BASE + "/Portal/DocumentViewer/Embedded/{doc_id}"
_DOC_VIEWER_API_URL = _PORTAL_BASE + "/app/RegisterOfActionsService/api/ViewDocument"
_CASE_EVENTS_URL = _PORTAL_BASE + "/app/RegisterOfActionsService/CaseEvents('{case_id}')"
_REFERER = _PORTAL_BASE + "/"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": _REFERER,
    "Accept": "application/pdf, application/json, */*",
}

# Will-document type detection. Tyler Tech populates Event.TypeId.Description
# (and DocumentTypeID.Description) with values like these. We match on the
# description with a flexible regex so future variants don't slip through.
# Examples seen in the wild:
#   "Will Recorded -Not Probated"
#   "Last Will and Testament"
#   "Will Filed"
_WILL_DESCRIPTION_RE = re.compile(r"\b(will|testament)\b", re.IGNORECASE)

# Application form type detection. Variants seen so far per Oren 2026-06-23:
#   "Application for Probate and Letters Testamentary"
#   "Application for Letters of Administration"
#   "Application for Letters" (generic)
# Also matches the AOC form number directly (AOC-E-201 = Application).
_APPLICATION_DESCRIPTION_RE = re.compile(
    r"\b(application\s+for\s+(probate|letters?)|AOC-?E-?201)\b",
    re.IGNORECASE,
)


def download_document_by_longhex(long_hex: str, case_no: str = "", *, timeout: int = 30) -> bytes:
    """Fetch PDF using the unauthenticated /Portal/DocumentViewer/Embedded/
    {long_hex} endpoint. The long_hex is a 256-char token minted by the
    portal SPA for a specific document — no auth needed once you have it.

    Use this when a long_hex has already been obtained (e.g. from a copied
    browser URL). For programmatic fetching from a case_id + fragmentId,
    use download_document_by_fragment() instead — long_hex minting is not
    yet discovered.
    """
    if not long_hex:
        raise ValueError("long_hex is required")
    url = _DOC_VIEWER_LONGHEX_URL.format(doc_id=long_hex)
    params = {"p": "0"}
    if case_no:
        params["caseNum"] = case_no
    r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype:
        raise RuntimeError(f"Expected PDF, got Content-Type={ctype!r}")
    return r.content


def download_document_by_fragment(
    case_id_hex: str, fragment_id: str, waf_token: str, *, timeout: int = 30,
    all_cookies: dict | None = None,
) -> bytes:
    """Fetch PDF using the WAF-protected api/ViewDocument endpoint.

    `all_cookies` (optional): full cookie jar from the Playwright session
    (e.g. AWSALB, AWSALBCORS in addition to aws-waf-token). Tyler Tech's
    ViewDocument endpoint requires ALB stickiness cookies to be routed to
    the backend that recognizes the WAF token — without them, HTTP 602
    fires even when the WAF token itself is fresh (Week 26 audit: 156
    cases queued, 0 fetched until we plumbed all_cookies through).

    Returns the PDF binary on success. Raises RuntimeError with the
    Odyssey error message on session-invalid (HTTP 602).
    """
    if not case_id_hex or not fragment_id:
        raise ValueError("case_id_hex and fragment_id are required")
    if not waf_token:
        raise ValueError("waf_token is required for api/ViewDocument")
    # Track elapsed time since the first fetch of this batch so a 602 reveals
    # whether the token is stale from the start (+0s) or expires mid-batch.
    global _BATCH_FIRST_TS, _BATCH_LOGGED_FIRST_OK
    _now = time.monotonic()
    if _BATCH_FIRST_TS is None:
        _BATCH_FIRST_TS = _now
    _elapsed = _now - _BATCH_FIRST_TS
    params = {"caseId": case_id_hex, "fragmentId": fragment_id}
    # Build cookie jar — full jar from Playwright if available, else
    # fall back to just the WAF token (legacy behavior).
    if all_cookies:
        cookies = dict(all_cookies)
        cookies["aws-waf-token"] = waf_token  # ensure latest WAF token
    else:
        cookies = {"aws-waf-token": waf_token}
    r = requests.get(_DOC_VIEWER_API_URL, params=params, headers=_HEADERS,
                     cookies=cookies, timeout=timeout)
    if r.status_code == 602:
        # Tyler Tech's "session invalid" — happens when the WAF cookie expired
        body = r.text[:300] if r.text else ""
        raise RuntimeError(
            f"WAF session invalid (HTTP 602) at +{_elapsed:.0f}s into doc-fetch batch. "
            f"Cookie may have expired. {body}")
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype:
        raise RuntimeError(f"Expected PDF, got Content-Type={ctype!r}, body[:200]={r.content[:200]!r}")
    if not _BATCH_LOGGED_FIRST_OK:
        _BATCH_LOGGED_FIRST_OK = True
        logger.info("case_pdf_extractor: first successful doc fetch at +%.0fs into batch", _elapsed)
    return r.content


_DISPLAYDOC_URL = _PORTAL_BASE + "/Portal/DocumentViewer/DisplayDoc"


def download_document_by_displaydoc(
    *, fragment_id: str, case_num: str, location_id: str, case_id_num: str,
    doc_type_id: str, waf_token: str, all_cookies: dict | None = None,
    timeout: int = 40,
) -> bytes:
    """Fetch a document PDF via the portal's DisplayDoc viewer URL — the path
    the SPA's makeDocumentViewerUrl() actually uses.

    DisplayDoc mints the long_hex server-side and 302-redirects to the
    UNAUTHENTICATED /Portal/DocumentViewer/Embedded/{long_hex} viewer, which
    returns the PDF. This needs only the WAF cookie — NOT the Odyssey
    application "viewer session" that api/ViewDocument demands (that endpoint
    returns HTTP 602 "Odyssey Request Security: Session is invalid" even from
    inside a fully-authenticated browser, so cookie freshness was never the
    real fix). Verified 2026-07-01: returns a real PDF; bypasses the 602 that
    left ~271 cases queued with 0 fetched.

    All params come from list_case_documents(): documentID=fragment_id,
    locationId + numeric caseId from the ParentTypeID==1 link, docTypeId from
    the DocumentType CodeID. caseNum is the human case number.
    """
    if not fragment_id:
        raise ValueError("fragment_id (documentID) is required")
    params = {
        "documentID": fragment_id,
        "caseNum": case_num or "",
        "locationId": location_id or "",
        "caseId": case_id_num or "",
        "docTypeId": doc_type_id or "",
        "isVersionId": "false",
    }
    cookies = dict(all_cookies) if all_cookies else {}
    if waf_token:
        cookies["aws-waf-token"] = waf_token
    r = requests.get(_DISPLAYDOC_URL, params=params, headers=_HEADERS,
                     cookies=cookies, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    # DisplayDoc 302s to DocumentViewer/Embedded; that endpoint answers 202 +
    # empty body when we're over the per-IP document quota. Distinguish it from
    # a genuine "this document is unreadable" so callers can back off instead
    # of burning the doc's retry budget.
    if r.status_code == 202 and not r.content:
        raise DocRateLimited(
            f"throttled by Odyssey (HTTP 202, empty body) on fragment {fragment_id}")
    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype:
        raise RuntimeError(
            f"DisplayDoc: expected PDF, got Content-Type={ctype!r} "
            f"(status {r.status_code}), body[:150]={r.content[:150]!r}")
    return r.content


def _displaydoc_with_backoff(**kwargs) -> bytes:
    """download_document_by_displaydoc, retrying while Odyssey throttles us.

    Raises DocRateLimited if the quota never frees up within the retry budget —
    the caller should stop the batch and leave the doc queued rather than grind
    through hundreds of guaranteed-202 fetches (which is what produced the
    190-218 nightly "failures" before 2026-07-08).
    """
    for attempt in range(1, DOC_MAX_RETRIES + 2):
        try:
            return download_document_by_displaydoc(**kwargs)
        except DocRateLimited:
            if attempt > DOC_MAX_RETRIES:
                raise
            logger.info("Doc fetch throttled — backing off %ds (attempt %d/%d)",
                        DOC_BACKOFF_SECONDS, attempt, DOC_MAX_RETRIES + 1)
            time.sleep(DOC_BACKOFF_SECONDS)
    raise DocRateLimited("unreachable")  # pragma: no cover


def list_case_documents(case_id_hex: str, *, timeout: int = 30) -> list[dict[str, Any]]:
    """Return the docket entries for a case along with attached document IDs.

    Hits the public OData endpoint /CaseEvents('{case_id}') (no WAF cookie
    needed — verified 2026-06-23). Note: must NOT pass mode=portalembed,
    or the DocumentViewerIntents array comes back empty.

    Returns a list of dicts shaped:
      {
        "event_id": int,
        "filing_date": "MM/DD/YYYY",
        "event_label": str,            # e.g. "Last Will and Testament of ..."
        "event_type_code": str,        # e.g. "WLNP"
        "event_type_desc": str,        # e.g. "Will Recorded -Not Probated"
        "documents": [                  # one or more attached PDFs per event
            {
                "document_id": str,    # internal DocumentID
                "document_name": str,  # e.g. "Will Recorded -Not Probated"
                "fragment_id": str,    # the URI used by api/ViewDocument
            },
            ...
        ]
      }
    """
    url = _CASE_EVENTS_URL.format(case_id=case_id_hex)
    # NO mode param — that's what gates DocumentViewerIntents population.
    params = {"$top": "200", "$skip": "0"}
    r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    # The docket listing shares the per-IP document quota (measured 2026-08-22:
    # ~5 listings, then HTTP 202 + empty body — same throttle the PDF fetch
    # hits). 202 is NOT an error status, so raise_for_status() sails past it and
    # r.json() dies with "Expecting value: line 1 column 1". Callers must be able
    # to tell "throttled, retry later" from "this case has no docket" — that
    # confusion silently killed court-phone extraction for 515 cases (Aug 5-21).
    if r.status_code == 202 and not r.content:
        raise DocRateLimited(
            f"throttled by Odyssey (HTTP 202, empty body) listing case {case_id_hex[:16]}...")
    data = r.json()
    out: list[dict[str, Any]] = []
    for raw_ev in (data.get("Events") or []):
        ev = raw_ev.get("Event") or {}
        type_id = ev.get("TypeId") or {}
        entry: dict[str, Any] = {
            "event_id": raw_ev.get("EventId"),
            "filing_date": raw_ev.get("SortEventDate") or ev.get("Date") or "",
            "event_label": (ev.get("Comment") or "").strip(),
            "event_type_code": (type_id.get("Word") or "").strip(),
            "event_type_desc": (type_id.get("Description") or "").strip(),
            "documents": [],
        }
        for doc in (ev.get("Documents") or []):
            doc_type = doc.get("DocumentTypeID") or {}
            # The "URI" we need for api/ViewDocument lives in
            # DocumentViewer Intents (when mode is omitted). Find the
            # PDF-viewing intent.
            fragment_id = ""
            for version in (doc.get("DocumentVersions") or []):
                for frag in (version.get("DocumentFragments") or []):
                    for intent in (frag.get("DocumentViewerIntents") or []):
                        uri = intent.get("URI")
                        if uri:
                            fragment_id = str(uri)
                            break
                    if fragment_id:
                        break
                if fragment_id:
                    break
            # Extra fields for the DisplayDoc viewer URL (the working
            # doc-fetch path — see download_document_by_displaydoc). The SPA's
            # makeDocumentViewerUrl() reads locationId (NodeID) and the numeric
            # caseId from the ParentLink whose ParentTypeID == "1", plus the
            # DocumentType CodeID.
            location_id = ""
            case_id_num = ""
            for pl in (doc.get("ParentLinks") or []):
                if str(pl.get("ParentTypeID")) == "1":
                    location_id = str(pl.get("NodeID") or "")
                    case_id_num = str(pl.get("ParentID") or "")
                    break
            entry["documents"].append({
                "document_id": str(doc.get("DocumentID") or ""),
                "document_name": (doc.get("DocumentName") or "").strip(),
                "document_type_desc": (doc_type.get("Description") or "").strip(),
                "fragment_id": fragment_id,
                "location_id": location_id,
                "case_id_num": case_id_num,
                "doc_type_id": str(doc_type.get("CodeID") or ""),
            })
        out.append(entry)
    return out


def _find_documents_matching(events: list[dict[str, Any]], pattern: re.Pattern) -> list[dict[str, Any]]:
    """Filter docket events by matching `pattern` against event_label,
    event_type_desc, and individual document_name fields.
    """
    out: list[dict[str, Any]] = []
    for ev in events:
        if (pattern.search(ev.get("event_label", ""))
                or pattern.search(ev.get("event_type_desc", ""))):
            out.append(ev)
            continue
        for doc in ev.get("documents", []):
            if (pattern.search(doc.get("document_name", ""))
                    or pattern.search(doc.get("document_type_desc", ""))):
                out.append(ev)
                break
    return out


def find_will_documents(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events that look like a Last Will and Testament."""
    return _find_documents_matching(events, _WILL_DESCRIPTION_RE)


def find_application_documents(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events that look like an Application for Probate / Letters Test. /
    Letters of Administration (AOC-E-201)."""
    return _find_documents_matching(events, _APPLICATION_DESCRIPTION_RE)


# ── Text extraction ───────────────────────────────────────────────────


def extract_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using pypdfium2 (native text layer).

    Returns "" when the PDF has no recoverable text layer (scanned image).
    Caller should treat empty/very-short results as a signal to fall back
    to OCR (not yet wired here).
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise RuntimeError("pypdfium2 not installed — pip install pypdfium2") from e

    chunks: list[str] = []
    pdf = pdfium.PdfDocument(BytesIO(pdf_bytes))
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            try:
                chunks.append(tp.get_text_range())
            finally:
                tp.close()
                page.close()
    finally:
        pdf.close()
    return "\n\n".join(chunks).strip()


def needs_ocr(text: str) -> bool:
    """Heuristic — short or empty text after native extraction means the
    PDF is scanned and an OCR pass is needed."""
    return len(text.strip()) < 100


def ocr_pdf_bytes(pdf_bytes: bytes, *, dpi: int = 200, max_pages: int = 8) -> str:
    """Render a PDF's pages to images and OCR them with Tesseract.

    For the scanned applications/wills that have no native text layer — the
    majority of the fetchable case-doc backlog (2026-07-12: the top no-PR
    cases with a fragment all returned empty because they're scanned images).
    Reuses the same pypdfium2 render + image_utils.ocr_page path as the PDF
    import pipeline. Caps pages so a long filing with attachments doesn't
    stall the drain.
    """
    try:
        import pypdfium2 as pdfium
        from image_utils import ocr_page, fix_rotation
    except ImportError as e:
        logger.warning("OCR unavailable (%s) — cannot read scanned PDF", e)
        return ""
    out: list[str] = []
    try:
        pdf = pdfium.PdfDocument(BytesIO(pdf_bytes))
    except Exception as e:  # noqa: BLE001
        logger.warning("OCR: could not open PDF: %s", e)
        return ""
    try:
        for i in range(min(len(pdf), max_pages)):
            try:
                img = pdf[i].render(scale=dpi / 72).to_pil()
                try:
                    img = fix_rotation(img)
                except Exception:  # noqa: BLE001
                    pass  # OSD is flaky; OCR the un-rotated page rather than fail
                out.append(ocr_page(img, psm=3))
            except Exception as e:  # noqa: BLE001
                logger.debug("OCR: page %d failed: %s", i, e)
    finally:
        pdf.close()
    return "\n".join(out)


def extract_text_with_ocr(pdf_bytes: bytes) -> str:
    """Native text layer, falling back to Tesseract OCR for scanned PDFs.

    Returns the OCR text only when it recovers more than the native layer, so
    a partial native layer is never replaced by worse OCR.
    """
    text = extract_text(pdf_bytes)
    if not needs_ocr(text):
        return text
    ocr = ocr_pdf_bytes(pdf_bytes)
    return ocr if len(ocr.strip()) > len(text.strip()) else text


# ── LLM parsing ───────────────────────────────────────────────────────


_WILL_EXTRACT_PROMPT = """\
You are reading a North Carolina Last Will and Testament. Extract structured
information about the executor chain and beneficiaries.

Wills typically have an "ITEM" (Roman-numeral) structure: ITEM I, ITEM II, etc.
- One item names beneficiaries who get the residuary estate (usually "all the
  rest, residue and remainder")
- A subsequent item appoints the Executor / Executrix (primary) with an
  Alternate Executor named in case the primary predeceases or declines

For EACH person mentioned, extract:
- "full_name": full legal name as written, including middle name(s)
- "relationship": to the testator (spouse, brother-in-law, daughter, etc.) if stated
- "role": one of "primary_executor", "alternate_executor", "residue_beneficiary",
  "conditional_beneficiary", "specific_beneficiary"
- "condition": if conditional, describe the trigger (e.g. "wife predeceased or
  joint disaster"). Empty string if unconditional.

Return ONLY valid JSON with this exact shape:
{{
  "testator_name": "<full name of testator, if stated in the will header>",
  "testator_spouse": "<full name of spouse, if mentioned — they are often the primary executor>",
  "people": [
    {{
      "full_name": "...",
      "relationship": "...",
      "role": "...",
      "condition": "..."
    }}
  ]
}}

Return an empty "people" array if this document is NOT a will (e.g. it's an
Application for Probate, an Affidavit, or some other case-attached form).

Will text:
{will_text}
"""


_APPLICATION_EXTRACT_PROMPT = """\
You are reading a North Carolina Application for Probate / Letters Testamentary /
Letters of Administration (AOC-E-201 or similar). Extract structured data.

The application typically contains:
- The DECEDENT's name, date of death, and last domicile address
- The APPLICANT (who is acting as Personal Representative) — name + address +
  relationship to decedent (spouse / child / sibling / etc.)
- A list of HEIRS / persons entitled to share in the estate — each with their
  name, age indicator (e.g. "18+" or actual age), relationship, mailing address
- The ATTORNEY representing the estate (when one is listed)
- A preliminary estate value (Part I total of the Preliminary Inventory)
- REAL ESTATE the decedent owned, listed in the Preliminary Inventory: Part I
  ("Real property solely owned by decedent" / jointly owned) and Part II item 4
  ("Real estate owned by decedent and not listed elsewhere"). These fields are
  OFTEN BLANK — only capture a street address when one is actually written in.

OCR / form extraction is messy — field labels and values get jumbled. Do your
best to associate each value with the right field by context.

Return ONLY valid JSON with this exact shape (use empty strings/arrays when
data is missing — DO NOT invent):

{{
  "decedent_name": "<full legal name>",
  "decedent_address": "<street, city, state, zip>",
  "date_of_death": "<MM/DD/YYYY>",
  "applicant": {{
    "full_name": "<full legal name including middle if shown>",
    "street": "...",
    "city": "...",
    "state": "...",
    "zip": "...",
    "relationship_to_decedent": "<spouse / child / sibling / etc., if stated>"
  }},
  "heirs": [
    {{
      "full_name": "...",
      "age": "<age or '18+' or empty>",
      "relationship": "<spouse / child / parent / sibling / niece / etc.>",
      "street": "...",
      "city": "...",
      "state": "...",
      "zip": "..."
    }}
  ],
  "attorney_name": "<full name, empty if pro se>",
  "preliminary_estate_value_usd": <number or null>,
  "real_estate_owned": [
    "<full street address (street, city, state, zip) of each parcel of real
     estate the decedent owned, exactly as written in the Preliminary Inventory
     Part I / Part II item 4. Empty list if none is listed — this is common.>"
  ]
}}

If this document is NOT an Application form (e.g. it's a death certificate or
some unrelated affidavit), return:
{{ "decedent_name": "", "applicant": {{"full_name": ""}}, "heirs": [] }}

Application text:
{app_text}
"""


def parse_application(text: str, *, api_key: str = "", max_chars: int = 30000) -> dict[str, Any]:
    """LLM-parse Application for Probate / Letters into structured data.

    Captures applicant (acting PR), heirs (often missing from OData
    Parties API — see [[project_odata_misses_pdf_heirs]]), date of death,
    attorney, and preliminary estate value. Returns empty dict on LLM
    failure or when the doc isn't an Application.
    """
    if not text or not text.strip():
        return {}
    try:
        import llm_client  # type: ignore
        import config as cfg  # type: ignore
    except Exception as e:
        logger.warning("LLM client unavailable: %s", e)
        return {}
    api_key = api_key or getattr(cfg, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY configured for application parser")
        return {}
    prompt = _APPLICATION_EXTRACT_PROMPT.format(app_text=text[:max_chars])
    return llm_client.chat_json(
        prompt,
        system="You extract structured data from legal forms. Return only valid JSON.",
        max_tokens=2048,
        api_key=api_key,
    ) or {}


def parse_will(text: str, *, api_key: str = "", max_chars: int = 30000) -> dict[str, Any]:
    """LLM-parse will text into structured executor/beneficiary data.

    Uses the project's llm_client (Claude Haiku). Returns empty dict on
    LLM failure; caller should treat that as "couldn't parse, skip".
    """
    if not text or not text.strip():
        return {}
    try:
        import llm_client  # type: ignore
        import config as cfg  # type: ignore
    except Exception as e:
        logger.warning("LLM client unavailable: %s", e)
        return {}
    api_key = api_key or getattr(cfg, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY configured for will parser")
        return {}
    prompt = _WILL_EXTRACT_PROMPT.format(will_text=text[:max_chars])
    return llm_client.chat_json(
        prompt,
        system="You extract structured data from legal documents. Return only valid JSON.",
        max_tokens=2048,
        api_key=api_key,
    ) or {}


# ── Convenience ───────────────────────────────────────────────────────


def fetch_and_parse_will_by_longhex(
    long_hex: str, case_no: str = "", *, api_key: str = "",
) -> dict[str, Any]:
    """End-to-end with a known long_hex token (unauthenticated). Use this
    when a long_hex has already been minted (e.g. copied from a browser).
    Returns the structured dict from parse_will() or {} on any failure.
    """
    try:
        pdf_bytes = download_document_by_longhex(long_hex, case_no=case_no)
    except Exception as e:
        logger.warning("PDF download failed for long_hex %s...: %s", long_hex[:16], e)
        return {}
    text = extract_text_with_ocr(pdf_bytes)
    if needs_ocr(text):
        logger.info("long_hex %s...: no usable text even after OCR (%d chars)",
                    long_hex[:16], len(text))
        return {}
    return parse_will(text, api_key=api_key)


def fetch_and_parse_case_docs(
    case_id_hex: str, waf_token: str, doc_types: list[str], *, api_key: str = "",
    all_cookies: dict | None = None, case_number: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch + LLM-parse multiple registered doc types from a case in one
    docket round-trip.

    Returns {doc_type: [parsed_dict, ...]}. Doc types with no matching
    document in the docket OR whose document couldn't be fetched/parsed
    map to an empty list — caller can use that to decide whether to queue
    the doc type for retry.

    Requires waf_token because the api/ViewDocument endpoint is auth-gated.
    `all_cookies` (optional): full Playwright cookie jar for ALB
    stickiness — see download_document_by_fragment.
    """
    import case_doc_queue as cdq
    out: dict[str, list[dict[str, Any]]] = {dt: [] for dt in doc_types}
    try:
        events = list_case_documents(case_id_hex)
    except Exception as e:
        logger.warning("list_case_documents failed for case %s...: %s", case_id_hex[:16], e)
        return out

    for doc_type in doc_types:
        spec = cdq.get_doc_type(doc_type)
        if not spec:
            logger.debug("Unknown doc_type %r — skipping", doc_type)
            continue
        matching = _find_documents_matching(events, spec.label_regex)
        if not matching:
            continue
        for ev in matching:
            for doc in ev.get("documents", []):
                fragment_id = doc.get("fragment_id", "")
                if not fragment_id:
                    continue
                # Primary: DisplayDoc viewer URL (WAF-cookie only, bypasses the
                # api/ViewDocument 602). Fall back to api/ViewDocument only if
                # DisplayDoc fails for some doc.
                try:
                    pdf_bytes = _displaydoc_with_backoff(
                        fragment_id=fragment_id, case_num=case_number,
                        location_id=doc.get("location_id", ""),
                        case_id_num=doc.get("case_id_num", ""),
                        doc_type_id=doc.get("doc_type_id", ""),
                        waf_token=waf_token, all_cookies=all_cookies,
                    )
                except DocRateLimited:
                    # Quota exhausted. The doc is fine — we're not allowed to
                    # read it right now. Propagate so the batch stops; the doc
                    # stays queued for the next run.
                    raise
                except Exception as e:
                    logger.warning("DisplayDoc fetch failed for %s fragment %s: %s "
                                   "— trying api/ViewDocument", doc_type, fragment_id, e)
                    try:
                        pdf_bytes = download_document_by_fragment(
                            case_id_hex, fragment_id, waf_token=waf_token,
                            all_cookies=all_cookies,
                        )
                    except Exception as e2:
                        logger.warning("api/ViewDocument also failed for %s fragment %s: %s",
                                       doc_type, fragment_id, e2)
                        continue
                text = extract_text_with_ocr(pdf_bytes)
                if needs_ocr(text):
                    logger.info("%s fragment %s: no usable text even after OCR",
                                doc_type, fragment_id)
                    continue
                parsed = spec.parser(text, api_key=api_key)
                if parsed:
                    parsed["_meta"] = {
                        "event_label": ev.get("event_label", ""),
                        "filing_date": ev.get("filing_date", ""),
                        "fragment_id": fragment_id,
                    }
                    out[doc_type].append(parsed)
    return out


def fetch_and_parse_case_wills(
    case_id_hex: str, waf_token: str, *, api_key: str = "",
) -> list[dict[str, Any]]:
    """End-to-end for a probate case: list the docket, find any will
    documents, download + LLM-parse each one. Returns a list of structured
    dicts (one per will found).

    Requires waf_token because we use the api/ViewDocument endpoint (the
    unauthenticated /Portal/DocumentViewer/Embedded endpoint needs a
    pre-minted long_hex token which we can't programmatically generate).

    Empty list = no will found OR fetch/parse failed for all wills.
    """
    results: list[dict[str, Any]] = []
    try:
        events = list_case_documents(case_id_hex)
    except Exception as e:
        logger.warning("list_case_documents failed for case %s...: %s", case_id_hex[:16], e)
        return results
    wills = find_will_documents(events)
    if not wills:
        return results
    for ev in wills:
        for doc in ev.get("documents", []):
            fragment_id = doc.get("fragment_id", "")
            if not fragment_id:
                continue
            try:
                pdf_bytes = download_document_by_fragment(
                    case_id_hex, fragment_id, waf_token=waf_token,
                )
            except Exception as e:
                logger.warning("Will fetch failed for fragment %s: %s", fragment_id, e)
                continue
            text = extract_text_with_ocr(pdf_bytes)
            if needs_ocr(text):
                logger.info("Will fragment %s: no usable text even after OCR", fragment_id)
                continue
            parsed = parse_will(text, api_key=api_key)
            if parsed:
                parsed["_meta"] = {
                    "event_label": ev.get("event_label", ""),
                    "filing_date": ev.get("filing_date", ""),
                    "fragment_id": fragment_id,
                }
                results.append(parsed)
    return results


# ── Doc type registration ────────────────────────────────────────────


def _register_known_doc_types() -> None:
    """Register the doc types this module knows how to parse with the
    case_doc_queue registry. Idempotent."""
    import case_doc_queue as cdq
    cdq.register_doc_type(cdq.DocTypeSpec(
        key="will",
        label_regex=_WILL_DESCRIPTION_RE,
        parser=parse_will,
    ))
    cdq.register_doc_type(cdq.DocTypeSpec(
        key="application",
        label_regex=_APPLICATION_DESCRIPTION_RE,
        parser=parse_application,
    ))


_register_known_doc_types()
