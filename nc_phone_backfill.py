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
                _write(csv_path, rows, fieldnames, args.dry_run, found, found_addr)
                return
            except Exception as e:
                logger.info("  fetch fail %s/%s: %s", case, key, str(e)[:80])
                continue
            fetched += 1
            txt = extract_text_with_ocr(pdf)
            c = extract_contacts(txt, r.get("First Name", ""), r.get("Last Name", ""))
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

    _write(csv_path, rows, fieldnames, args.dry_run, found, found_addr)


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


def _write(csv_path, rows, fieldnames, dry_run, found, found_addr=0) -> None:
    if dry_run:
        logger.info("DRY RUN — found %d phone(s) and %d address(es), nothing written.",
                    found, found_addr)
        return
    if not found and not found_addr:
        logger.info("No phones or addresses found; %s unchanged.", csv_path)
        return
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        w.writerows(rows)
    logger.info("Wrote %d PR phone(s) and %d PR address(es) into %s",
                found, found_addr, csv_path)


if __name__ == "__main__":
    main()
