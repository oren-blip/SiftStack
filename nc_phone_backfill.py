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
from nc_pdf_phone_extractor import PHONE_DOC_PATTERNS, extract_contacts  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("nc_phone_backfill")

WAF_PATH = "ecourts_waf_cookies.json"
PENDING_PATH = "output/pending_case_docs.json"
MIN_SCORE = 3  # don't write a phone that only scored on position (avoid noise)


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
    todo = [r for r in rows if not (r.get("Phone 1") or "").strip()
            and (r.get("Case No.") or "").strip()]
    logger.info("%d rows total, %d missing Phone 1", len(rows), len(todo))

    fetched = 0
    found = 0
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
                _write(csv_path, rows, fieldnames, args.dry_run, found)
                return
            except Exception as e:
                logger.info("  fetch fail %s/%s: %s", case, key, str(e)[:80])
                continue
            fetched += 1
            txt = extract_text_with_ocr(pdf)
            c = extract_contacts(txt, r.get("First Name", ""), r.get("Last Name", ""))
            if c["phone_digits"] and c["score"] >= MIN_SCORE and (best is None or c["score"] > best["score"]):
                best = {**c, "doc": key}
            if best and best["score"] >= 7:
                break  # strong hit — stop spending quota on this case

        if best:
            found += 1
            logger.info("  FOUND %s (%s): %s  [%s, score %d]  email=%s",
                        case, name, best["phone"], best["doc"], best["score"], best["email"] or "-")
            if not args.dry_run:
                r["Phone 1"] = best["phone"]
                if best["email"] and not (r.get("DM Email") or "").strip():
                    r["DM Email"] = best["email"]
                r["Match Reason"] = ((r.get("Match Reason") or "") + " | pdf-phone").strip(" |")
        else:
            logger.info("  MISS %s (%s): docs filed but no PR phone in them", case, name)

    _write(csv_path, rows, fieldnames, args.dry_run, found)


def _write(csv_path, rows, fieldnames, dry_run, found) -> None:
    if dry_run:
        logger.info("DRY RUN — found %d phone(s), nothing written.", found)
        return
    if not found:
        logger.info("No phones found; %s unchanged.", csv_path)
        return
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        w.writerows(rows)
    logger.info("Wrote %d PR phone(s) into %s", found, csv_path)


if __name__ == "__main__":
    main()
