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
_DOC_VIEWER_URL = _PORTAL_BASE + "/Portal/DocumentViewer/Embedded/{doc_id}"
_REFERER = _PORTAL_BASE + "/"

# Verified 2026-06-23: no WAF cookie needed for /Portal/DocumentViewer/
# Embedded/{doc_id}?caseNum={no}&p=0 — just User-Agent + Referer.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": _REFERER,
    "Accept": "application/pdf, */*",
}


def download_document(doc_id: str, case_no: str = "", *, timeout: int = 30) -> bytes:
    """Fetch the raw PDF bytes for an Odyssey document.

    Verified working without auth — the viewer URL serves the PDF binary
    directly (Content-Type: application/pdf). caseNum query param is
    optional for the request but accepted.

    Raises requests.HTTPError on non-200; RuntimeError on non-PDF content-type.
    """
    if not doc_id:
        raise ValueError("doc_id is required")
    url = _DOC_VIEWER_URL.format(doc_id=doc_id)
    params = {"p": "0"}
    if case_no:
        params["caseNum"] = case_no
    r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype:
        raise RuntimeError(f"Expected PDF, got Content-Type={ctype!r}")
    return r.content


def list_case_documents(case_id_hex: str, waf_token: str = "") -> list[dict[str, Any]]:
    """Return a list of document entries for a case from the Register of
    Actions service.

    Each entry: {doc_id, label, filing_date, doc_type}

    TODO: wire to Tyler Tech's actual docket endpoint. Common candidates:
      /app/RegisterOfActionsService/Events('{case_id_hex}')
      /app/RegisterOfActionsService/CaseEvents('{case_id_hex}')
      /app/RegisterOfActionsService/Documents('{case_id_hex}')
    Until verified, callers should supply doc_ids directly.
    """
    raise NotImplementedError(
        "list_case_documents() — docket-listing endpoint not yet discovered. "
        "Pass known doc_ids to download_document() directly for now."
    )


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


def fetch_and_parse_will(doc_id: str, case_no: str = "", *, api_key: str = "") -> dict[str, Any]:
    """End-to-end: download will PDF -> extract text -> LLM-parse.

    Returns the structured dict from parse_will() or {} on any failure.
    """
    try:
        pdf_bytes = download_document(doc_id, case_no=case_no)
    except Exception as e:
        logger.warning("PDF download failed for doc %s: %s", doc_id[:16], e)
        return {}
    text = extract_text(pdf_bytes)
    if needs_ocr(text):
        # OCR fallback not yet wired — return empty so caller treats as "no will"
        logger.info("doc %s: native extraction yielded %d chars; OCR fallback not yet wired",
                    doc_id[:16], len(text))
        return {}
    return parse_will(text, api_key=api_key)
