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
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


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
        raise RuntimeError(f"WAF session invalid (HTTP 602). Cookie may have expired. {body}")
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype:
        raise RuntimeError(f"Expected PDF, got Content-Type={ctype!r}, body[:200]={r.content[:200]!r}")
    return r.content


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
            entry["documents"].append({
                "document_id": str(doc.get("DocumentID") or ""),
                "document_name": (doc.get("DocumentName") or "").strip(),
                "document_type_desc": (doc_type.get("Description") or "").strip(),
                "fragment_id": fragment_id,
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
    PDF is scanned and an OCR pass is needed (not yet wired here)."""
    return len(text.strip()) < 100


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
  "preliminary_estate_value_usd": <number or null>
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
    text = extract_text(pdf_bytes)
    if needs_ocr(text):
        logger.info("long_hex %s...: native extraction yielded %d chars; OCR fallback not yet wired",
                    long_hex[:16], len(text))
        return {}
    return parse_will(text, api_key=api_key)


def fetch_and_parse_case_docs(
    case_id_hex: str, waf_token: str, doc_types: list[str], *, api_key: str = "",
    all_cookies: dict | None = None,
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
                try:
                    pdf_bytes = download_document_by_fragment(
                        case_id_hex, fragment_id, waf_token=waf_token,
                        all_cookies=all_cookies,
                    )
                except Exception as e:
                    logger.warning("PDF fetch failed for %s fragment %s: %s",
                                   doc_type, fragment_id, e)
                    continue
                text = extract_text(pdf_bytes)
                if needs_ocr(text):
                    logger.info("%s fragment %s: needs OCR, skipping",
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
            text = extract_text(pdf_bytes)
            if needs_ocr(text):
                logger.info("Will fragment %s: needs OCR, skipping", fragment_id)
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
