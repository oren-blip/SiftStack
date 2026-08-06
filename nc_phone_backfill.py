"""Bounded weekly PR-phone backfill from NC eCourts case PDFs.

Fills the FTM `Phone 1` (and `DM Email`) column for the current week's rows by
reading the Estates Action Cover Sheet / Family History Affidavit / Paid Funeral
Bill attached to each case — the three docs that actually carry the personal
representative's phone (validated Week 29: 3 of 5 cases hit).

Why a bounded per-week script and not the nightly drain: Odyssey throttles
document fetches to ~1/minute per IP (see [[project_case_doc_pdf_waf_fail]]).
The nightly drain already spends that quota on no-PR cases. A week has ~10-60
rows, so a dedicated pass over just the rows still missing a phone stays inside
the budget while the nightly drain keeps doing its job.

Usage:
    python nc_phone_backfill.py                       # latest *_dm_enriched.csv
    python nc_phone_backfill.py --csv output/....csv  # a specific file
    python nc_phone_backfill.py --limit 20            # cap doc fetches this run
    python nc_phone_backfill.py --dry-run             # find phones, don't write

Reads the WAF token from ecourts_waf_cookies.json (same one the scraper caches)
and the case_id_hex for each row from output/pending_case_docs.json. Rows whose
case_id_hex isn't cached are reported and skipped (re-run the scraper first).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import logging
import os
import re
import sys
import time

sys.path.insert(0, "src")

from case_pdf_extractor import (  # noqa: E402
    DocRateLimited,
    download_document_by_displaydoc,
    extract_text_with_ocr,
    list_case_documents,
)
from nc_pdf_phone_extractor import (  # noqa: E402
    PHONE_DOC_PATTERNS,
    extract_contacts,
    extract_pr_address,
)
from llm_client import vision_json  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("nc_phone_backfill")

WAF_PATH = "ecourts_waf_cookies.json"
PENDING_PATH = "output/pending_case_docs.json"
MIN_ADDR_SCORE = 5  # min score to accept a PR mailing address from a case PDF
MIN_SCORE = 3      # min score to FILL a blank Phone 1
PROMOTE_SCORE = 6  # min score to PROMOTE a court number to primary (Phone 1)
                   # when Phone 1 is already filled. Per Oren (2026-07-20): a
                   # court-verified number is authoritative, so it becomes the
                   # primary — but nothing is discarded. The prior Phone 1 slides
                   # down to Phone 2 (DM Phone); any number already in Phone 2
                   # slides into Notes. Skip-trace numbers are preserved, just
                   # re-ranked below the court number. Both cases tag the row
                   # court-verified-phone at export.


def _latest_enriched_csv() -> str:
    files = glob.glob("output/*_dm_enriched.csv")
    if not files:
        raise SystemExit("No *_dm_enriched.csv found in output/")
    return max(files, key=os.path.getmtime)


def _load_case_hex_map() -> dict:
    """case_number -> case_id_hex, from the scraper's pending-docs cache."""
    if not os.path.exists(PENDING_PATH):
        return {}
    entries = json.load(open(PENDING_PATH, encoding="utf-8")).get("entries", {})
    return {e["case_number"]: hexid for hexid, e in entries.items()
            if e.get("case_number")}


def _pick_phone_docs(events: list[dict]) -> list[tuple[str, dict]]:
    """Return (doc_type_key, doc) for each phone-bearing doc, priority-ordered."""
    picks: list[tuple[str, dict]] = []
    for key, pat in PHONE_DOC_PATTERNS:
        for ev in events:
            label = f"{ev.get('event_label','')} {ev.get('event_type_desc','')}"
            for doc in ev.get("documents", []):
                hay = f"{label} {doc.get('document_name','')}"
                if pat.search(hay) and doc.get("fragment_id"):
                    picks.append((key, doc))
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--limit", type=int, default=40, help="max doc fetches this run")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(WAF_PATH):
        raise SystemExit(f"No {WAF_PATH} — run the scraper first to cache a WAF token.")
    waf = json.load(open(WAF_PATH, encoding="utf-8"))["aws_waf_token"]
    hex_map = _load_case_hex_map()
    csv_path = args.csv or _latest_enriched_csv()
    logger.info("Backfilling phones for: %s", csv_path)

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    fieldnames = rows[0].keys() if rows else []
    # Process every row with a case number. Blank-Phone-1 rows first (a fill is
    # always a win), then filled rows (only upgraded when the court doc yields a
    # high-confidence PR number that beats the skip-trace one). --limit bounds
    # the throttled fetches; blanks-first ordering means the cheapest wins land
    # before the cap is hit.
    have_case = [r for r in rows if (r.get("Case No.") or "").strip()]
    todo = sorted(have_case, key=lambda r: bool((r.get("Phone 1") or "").strip()))
    n_blank = sum(1 for r in todo if not (r.get("Phone 1") or "").strip())
    logger.info("%d rows total, %d missing Phone 1, %d with a phone to verify",
                len(rows), n_blank, len(todo) - n_blank)

    fetched = 0
    found = 0
    found_addr = 0
    vision_heirs = 0
    benef_found = 0
    for r in todo:
        if fetched >= args.limit:
            logger.info("Hit --limit %d doc fetches; stopping (rerun to continue).", args.limit)
            break
        case = r["Case No."].strip()
        hexid = hex_map.get(case)
        name = r.get("Deceased Owner", "")
        if not hexid:
            logger.info("  SKIP %s (%s): no cached case_id_hex — rescrape needed", case, name)
            continue
        try:
            events = list_case_documents(hexid)
        except Exception as e:
            logger.info("  SKIP %s: docket list failed: %s", case, e)
            continue
        picks = _pick_phone_docs(events)
        if not picks:
            logger.info("  MISS %s (%s): no cover-sheet/family-history/funeral doc filed", case, name)
            continue

        best = None
        best_addr = None
        for key, doc in picks:
            if fetched >= args.limit:
                break
            try:
                pdf = download_document_by_displaydoc(
                    fragment_id=doc["fragment_id"], case_num=case,
                    location_id=doc.get("location_id", ""),
                    case_id_num=doc.get("case_id_num", ""),
                    doc_type_id=doc.get("doc_type_id", ""), waf_token=waf,
                )
            except DocRateLimited:
                logger.info("  THROTTLED at %s — stopping; rerun later.", case)
                _write(csv_path, rows, fieldnames, args.dry_run, found, found_addr, benef_found)
                return
            except Exception as e:
                logger.info("  fetch fail %s/%s: %s", case, key, str(e)[:80])
                continue
            fetched += 1
            txt = extract_text_with_ocr(pdf)
            c = extract_contacts(txt, r.get("First Name", ""), r.get("Last Name", ""))
            # Call vision when the text path can't answer what this row still
            # needs: no phone (answers are probably handwritten — Tesseract
            # can't read those), OR no Beneficiaries and this is the cover
            # sheet, which carries the "entitled to share" list the OData
            # Parties feed often lacks. Skipped entirely when the row already
            # has both, so we never pay for a call with nothing to gain.
            needs_benef = (key == "cover_sheet"
                           and not (r.get("Beneficiaries") or "").strip())
            if not c["phone_digits"] or needs_benef:
                v = _vision_contacts(
                    pdf, r.get("First Name", ""), r.get("Last Name", ""),
                    cache_key=f"{case}|{doc.get('fragment_id', '')}")
                if v:
                    # Beneficiaries: the cover sheet's numbered list is the
                    # court's own statement of who may share in the estate.
                    if needs_benef and v.get("entitled"):
                        blob = _format_beneficiaries(v["entitled"])
                        if blob:
                            logger.info("  BENEFICIARIES %s (%s): %d from cover sheet",
                                        case, name, len(v["entitled"]))
                            if not args.dry_run:
                                r["Beneficiaries"] = blob
                                r["Match Reason"] = ((r.get("Match Reason") or "")
                                                     + " | cover-sheet-beneficiaries").strip(" |")
                            benef_found += 1
                    # A second fiduciary is a CO-EXECUTOR: they must also sign,
                    # and their phone is on the same sheet. No DM 2 Phone
                    # column exists, so it goes in Notes where the caller sees it.
                    extra = [f for f in (v.get("fiduciaries") or [])[1:]
                             if (f.get("phone") or "").strip()]
                    if extra and not args.dry_run:
                        who = "; ".join(f"{f['name']} {f['phone']}".strip()
                                        for f in extra)
                        note = (r.get("Notes") or "").strip()
                        blk = f"[co-fiduciary from cover sheet: {who}]"
                        if blk not in note:
                            r["Notes"] = f"{note}\n{blk}".strip() if note else blk
                            logger.info("  CO-FIDUCIARY %s: %s", case, who)
                    if v["phone_digits"]:
                        logger.info("  VISION %s (%s): read %s off the handwriting [%s]",
                                    case, name, v["phone"], v["context"])
                        c = v
                    if v.get("heirs"):
                        names = "; ".join(
                            f"{h.get('name','')} - {h.get('address','')}".strip(" -")
                            for h in v["heirs"])
                        logger.info("  VISION %s: children on form -> %s", case, names)
                        if not args.dry_run and names:
                            note = (r.get("Notes") or "").strip()
                            blk = f"[court form children: {names}]"
                            if blk not in note:
                                r["Notes"] = f"{note}\n{blk}".strip() if note else blk
                        vision_heirs += 1
            if c["phone_digits"] and c["score"] >= MIN_SCORE and (best is None or c["score"] > best["score"]):
                best = {**c, "doc": key}
            # Same OCR'd text, no extra (throttled) fetch: the PR's own mailing
            # address. Lambert 26E002739-590 Week 30 — the funeral bill carried
            # "Reid Carter / 9001 Carindale Rd. / Waxhaw, NC 28173" while the
            # workbook was mailing the decedent's house.
            a = extract_pr_address(txt, r.get("First Name", ""), r.get("Last Name", ""))
            if a["street"] and a["score"] >= MIN_ADDR_SCORE and (
                    best_addr is None or a["score"] > best_addr["score"]):
                best_addr = {**a, "doc": key}
            if best and best["score"] >= 7 and best_addr:
                break  # strong hit on both — stop spending quota on this case

        existing = (r.get("Phone 1") or "").strip()
        existing_digits = "".join(ch for ch in existing if ch.isdigit())
        dm_existing = (r.get("DM Phone") or "").strip()
        dm_existing_digits = "".join(ch for ch in dm_existing if ch.isdigit())
        if best and not existing:
            # Phone 1 is empty — the court number becomes the primary contact.
            found += 1
            logger.info("  FILL  %s (%s): %s  [%s, score %d]  email=%s",
                        case, name, best["phone"], best["doc"], best["score"], best["email"] or "-")
            if not args.dry_run:
                r["Phone 1"] = best["phone"]
                if best["email"] and not (r.get("DM Email") or "").strip():
                    r["DM Email"] = best["email"]
                r["Match Reason"] = ((r.get("Match Reason") or "") + " | pdf-phone").strip(" |")
        elif (best and best["score"] >= PROMOTE_SCORE
              and best["phone_digits"] not in (existing_digits, dm_existing_digits)):
            # Phone 1 already has a number — PROMOTE the court number to primary
            # (it's authoritative) but keep everything: the prior Phone 1 slides
            # to Phone 2 (DM Phone); any number already in Phone 2 slides into
            # Notes. Nothing is discarded. Row is tagged court-verified-phone.
            found += 1
            logger.info("  PROMOTE %s (%s): %s (court, score %d) → Phone 1; %s → Phone 2%s",
                        case, name, best["phone"], best["score"], existing,
                        f"; {dm_existing} → Notes" if dm_existing else "")
            if not args.dry_run:
                if dm_existing and dm_existing_digits != existing_digits:
                    note = (r.get("Notes") or "").strip()
                    alt = f"[alt phone: {dm_existing}]"
                    r["Notes"] = f"{note}\n{alt}".strip() if note else alt
                r["Phone 1"] = best["phone"]
                r["DM Phone"] = existing
                if best["email"] and not (r.get("DM Email") or "").strip():
                    r["DM Email"] = best["email"]
                r["Match Reason"] = ((r.get("Match Reason") or "") + " | pdf-phone").strip(" |")
        elif best:
            logger.info("  KEEP  %s (%s): existing %s stands (court score %d, dup or low)",
                        case, name, existing, best["score"])
        else:
            logger.info("  MISS  %s (%s): docs filed but no PR phone in them", case, name)

        if best_addr:
            found_addr += _apply_pr_address(r, best_addr, case, name, args.dry_run)

    _write(csv_path, rows, fieldnames, args.dry_run, found, found_addr, benef_found)


_VISION_SCORE = 8   # a hand-filled court form beats any skip-trace number

# ── Persistent vision-read cache ─────────────────────────────────────
# Court documents are immutable, but the nightly build re-fetched and
# re-vision-read (Sonnet — the priciest model in the pipeline) the SAME
# docs every night for rows still missing a phone. Cache the vision result
# per (case, fragment_id) so each document is paid for once, ever. A
# genuine "form has no phone" read is cached too — that was the case that
# re-billed nightly. API failures are deliberately NOT cached, so a credits
# outage never poisons the cache. NC_VISION_CACHE_DISABLE=1 bypasses;
# delete output/.nc_vision_cache.json to clear.
_VISION_CACHE_PATH = "output/.nc_vision_cache.json"
_VISION_CACHE_VERSION = 1
_VISION_CACHE_TTL_DAYS = int(os.environ.get("NC_VISION_CACHE_TTL_DAYS", "90"))
_VISION_CACHE_DISABLED = os.environ.get("NC_VISION_CACHE_DISABLE", "") == "1"
_vision_cache_store: dict | None = None  # None = not yet loaded


def _vision_cache_load() -> dict:
    global _vision_cache_store
    if _vision_cache_store is not None:
        return _vision_cache_store
    _vision_cache_store = {}
    if _VISION_CACHE_DISABLED:
        return _vision_cache_store
    try:
        with open(_VISION_CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _vision_cache_store
    if not isinstance(data, dict) or data.get("_version") != _VISION_CACHE_VERSION:
        return _vision_cache_store
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=_VISION_CACHE_TTL_DAYS)
    for k, v in (data.get("entries") or {}).items():
        try:
            if datetime.fromisoformat(v.get("ts", "")) >= cutoff:
                _vision_cache_store[k] = v
        except (ValueError, AttributeError):
            continue
    return _vision_cache_store


def _vision_cache_get(key: str) -> dict | None:
    """Return {"empty": True} or {"v": {...}} for a cached read, else None."""
    if _VISION_CACHE_DISABLED or not key:
        return None
    return _vision_cache_load().get(key)


def _vision_cache_put(key: str, v: dict | None) -> None:
    """Persist a completed vision read (v=None means form had no contacts)."""
    if _VISION_CACHE_DISABLED or not key:
        return
    from datetime import datetime
    store = _vision_cache_load()
    entry: dict = {"ts": datetime.now().isoformat(timespec="seconds")}
    if v is None:
        entry["empty"] = True
    else:
        entry["v"] = v
    store[key] = entry
    try:
        os.makedirs(os.path.dirname(_VISION_CACHE_PATH), exist_ok=True)
        tmp = _VISION_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"_version": _VISION_CACHE_VERSION, "entries": store}, f)
        os.replace(tmp, _VISION_CACHE_PATH)
    except (OSError, TypeError) as e:
        logger.info("  vision cache: could not write (%s)", e)


def _render_pdf_pages(pdf: bytes, max_pages: int = 2, scale: float = 2.0) -> list[bytes]:
    """Render the first `max_pages` PDF pages to PNG bytes for a vision call."""
    import io
    try:
        import pypdfium2 as pdfium
    except Exception as e:  # noqa: BLE001
        logger.info("  vision: pypdfium2 unavailable (%s)", e)
        return []
    out: list[bytes] = []
    try:
        doc = pdfium.PdfDocument(pdf)
        for i in range(min(len(doc), max_pages)):
            buf = io.BytesIO()
            doc[i].render(scale=scale).to_pil().save(buf, format="PNG")
            out.append(buf.getvalue())
    except Exception as e:  # noqa: BLE001
        logger.info("  vision: render failed (%s)", e)
        return []
    return out


_VISION_PROMPT = """This is a North Carolina court estate filing (Estates Action
Cover Sheet AOC-E-650, Family History Affidavit, funeral bill, or similar).
Parts may be PRINTED and parts HANDWRITTEN — read the handwriting carefully.

Return ONLY JSON:
{
  "applicant_name": "the primary fiduciary/petitioner/applicant/affiant, or ''",
  "phone": "that person's telephone number as written, or ''",
  "email": "that person's email address, or ''",
  "mailing_address": {"street": "", "city": "", "state": "", "zip": ""},
  "fiduciaries": [{"name": "", "phone": "", "email": ""}],
  "entitled_to_share": [{"name": "", "address": ""}],
  "children": [{"name": "", "address": "", "age": ""}],
  "confidence": "high|medium|low"
}

Rules:
- Transcribe ONLY what is actually written. Never invent or complete a value.
- Use '' for any field that is blank, illegible, or not on the form.
- "fiduciaries" = EVERY person in a "Name Of Fiduciary/Petitioner/Applicant"
  box, each with the telephone printed in that same box. A cover sheet often
  has TWO (co-executors) — return both, in order.
- "entitled_to_share" = the numbered list under wording like "All persons
  listed below may be entitled to share in the decedent's estate". Include an
  address only if one is written next to the name. Skip blank numbered rows.
- "children" = the decedent's children table, if the form has one.
- NEVER return the attorney, law firm, clerk, funeral home, fax or toll-free
  number as a person's phone. The attorney block is separate and is not a
  fiduciary — exclude it everywhere."""


def _vision_contacts(pdf: bytes, first: str, last: str,
                     cache_key: str = "") -> dict | None:
    """Read a hand-filled court form with Claude vision.

    WHY: Tesseract cannot read handwriting. These forms are printed templates
    filled in by hand, so OCR returns the field LABELS and drops every answer —
    which looks downstream like "this doc has no phone number". Walsh
    26E002826-590 (2026-08-02): OCR found 0 phones; the form clearly shows
    "(704) 564-0605", an email, and three children with addresses and ages.

    Returns an extract_contacts-shaped dict (plus "heirs"), or None.
    """
    cached = _vision_cache_get(cache_key)
    if cached is not None:
        logger.info("  vision cache hit for %s%s", cache_key,
                    " (empty form)" if cached.get("empty") else "")
        return None if cached.get("empty") else cached.get("v")
    images = _render_pdf_pages(pdf)
    if not images:
        return None
    data = vision_json(_VISION_PROMPT, images, max_tokens=2048)
    if not data:
        return None  # API failure / no answer — transient, do NOT cache
    phone = (data.get("phone") or "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        digits, phone = "", ""
    def _people(key):
        return [h for h in (data.get(key) or [])
                if isinstance(h, dict) and (h.get("name") or "").strip()]

    heirs = _people("children")
    entitled = _people("entitled_to_share")
    fiduciaries = _people("fiduciaries")
    if not phone and not (data.get("email") or "").strip() and not (heirs or entitled):
        _vision_cache_put(cache_key, None)  # genuine read, nothing on the form
        return None
    result = {
        "phone": phone, "phone_digits": digits,
        "email": (data.get("email") or "").strip(),
        "score": _VISION_SCORE if phone else 0,
        "context": f"vision/{data.get('confidence', '?')}",
        "heirs": heirs,
        "entitled": entitled,
        "fiduciaries": fiduciaries,
        "applicant": (data.get("applicant_name") or "").strip(),
    }
    _vision_cache_put(cache_key, result)
    return result


def _format_beneficiaries(entitled: list[dict]) -> str:
    """Render the cover sheet's 'entitled to share' list into the workbook's
    Beneficiaries format: one person per line, 'Name - address' when known."""
    lines = []
    for p in entitled:
        name = (p.get("name") or "").strip()
        addr = (p.get("address") or "").strip()
        if not name:
            continue
        lines.append(f"{name} - {addr}" if addr else name)
    return "\n".join(lines)


def _norm_addr(s: str) -> str:
    """Suffix-normalized, alphanumeric-only form for address equality.

    The suffix rewrite has to happen BEFORE the alphanumeric strip, or
    "3432 Back Creek Church Road" (PDF) and "3432 Back Creek Church Rd"
    (GIS situs) compare as different addresses and the "this is just the
    property address again" guard never fires.
    """
    try:
        from fix_addresses_and_prep import _STREET_SUFFIX_NORMALIZE as SUF
    except Exception:  # pragma: no cover
        SUF = {}
    toks = [SUF.get(t, t) for t in
            (t.strip(".,").lower() for t in (s or "").split()) if t]
    return "".join(ch for ch in " ".join(toks) if ch.isalnum())


def _apply_pr_address(r: dict, addr: dict, case: str, name: str, dry_run: bool) -> int:
    """Write a PDF-sourced PR mailing address onto the row when it beats what's
    already there. Returns 1 if applied, 0 otherwise.

    Only overwrites a mailing we ourselves synthesized or guessed:
      * blank
      * `mailing-from-property` — the "mail to the decedent's house" backstop
      * `pr-people-search` / `pr-tracerfy` — third-party guesses
    A mailing that came from Odyssey's Parties API with no tag is court-supplied
    already and is left alone. A PDF address identical to the property address
    is no better than the fallback, so it's skipped too.
    """
    reason = r.get("Match Reason") or ""
    existing = (r.get("Mailing Address") or "").strip()
    synthesized = any(t in reason for t in
                      ("mailing-from-property", "pr-people-search", "pr-tracerfy"))
    if existing and not synthesized:
        return 0
    if _norm_addr(addr["street"]) == _norm_addr(r.get("Property Address")):
        return 0
    if existing and _norm_addr(addr["street"]) == _norm_addr(existing):
        return 0
    logger.info("  ADDR  %s (%s): %s, %s %s  [%s, score %d]%s",
                case, name, addr["street"], addr.get("city", ""), addr.get("zip", ""),
                addr["doc"], addr["score"],
                f"  (was {existing})" if existing else "")
    if dry_run:
        return 1
    r["Mailing Address"] = addr["street"]
    if addr.get("city"):
        r["Mailing City"] = addr["city"]
    if addr.get("state"):
        r["Mailing State"] = addr["state"]
    if addr.get("zip"):
        r["Mailing Zip"] = addr["zip"]
    # The property fallback / people-search guess is no longer what's on the row.
    kept = [p.strip() for p in reason.split("|") if p.strip() and p.strip() not in
            ("mailing-from-property", "pr-people-search", "pr-tracerfy")]
    kept.append("pdf-pr-address")
    r["Match Reason"] = " | ".join(kept)
    # Step 1.95 tags these rows for manual address hunting; we just found it.
    tags = [t.strip() for t in (r.get("Tags") or "").split(",")
            if t.strip() and t.strip() != "Verify: No PR Address"]
    r["Tags"] = ", ".join(tags)
    return 1


def _write(csv_path, rows, fieldnames, dry_run, found, found_addr=0, found_benef=0) -> None:
    # found_benef must be part of the "is there anything to save" test: a run
    # that filled ONLY Beneficiaries (cover sheet) but no phone would otherwise
    # hit the early return and silently throw the heir list away.
    if dry_run:
        logger.info("DRY RUN — found %d phone(s), %d address(es), %d beneficiary "
                    "list(s); nothing written.", found, found_addr, found_benef)
        return
    if not found and not found_addr and not found_benef:
        logger.info("No phones, addresses or beneficiaries found; %s unchanged.", csv_path)
        return
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        w.writerows(rows)
    logger.info("Wrote %d PR phone(s), %d PR address(es) and %d beneficiary list(s) into %s",
                found, found_addr, found_benef, csv_path)
    _refresh_datasift_upload(csv_path, rows)


def _refresh_datasift_upload(enriched_csv: str, rows: list[dict]) -> None:
    """Push these court-verified phones into the week's DataSift upload CSV.

    The polish wrote that file before this step ran, so without this the numbers
    reach the workbook but never the CRM. Same filename the polish used, so
    upload_netnew_datasift.py picks up the refreshed one. See the twin refresh
    in nc_deep_prospect.py.
    """
    stem = os.path.basename(enriched_csv)[: -len("_dm_enriched.csv")]
    upload = os.path.join(os.path.dirname(enriched_csv), f"{stem}_datasift_upload.csv")
    if not os.path.exists(upload):
        logger.info("No %s to refresh — skipping DataSift upload refresh.",
                    os.path.basename(upload))
        return
    try:
        from nc_datasift_export import write_datasift_upload_csv
        wk = re.search(r"week(\d+)", stem)
        write_datasift_upload_csv(rows, upload,
                                  week=int(wk.group(1)) if wk else None)
        logger.info("Refreshed DataSift upload CSV -> %s", os.path.basename(upload))
    except Exception as e:  # never sink an otherwise-good backfill run
        logger.warning("Could not refresh DataSift upload CSV: %s", e)


if __name__ == "__main__":
    main()
