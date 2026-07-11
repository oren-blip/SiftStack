"""Paced, resumable drain of the case-document backlog.

Odyssey throttles document downloads to a per-IP token bucket (~6, then ~1 per
50-60s — surfaced as an HTTP 202 with an empty body). The nightly run only
clears ~6-12 documents before it stops; the backlog is in the hundreds. This
runs for hours instead: it fetches ONE document at a time with a gap tuned to
the refill rate, works the highest-value blocked leads first, and re-mints the
WAF cookie as it ages out.

Each fetched will/application yields the executor's name (and, for an
application, address + heirs + date of death), which fills the "Heirs of" rows
the pipeline can't otherwise name.

Safe to Ctrl-C and re-run — results persist in output/fetched_case_docs.json and
already-fetched docs are skipped.

Usage:
    python drain_case_docs.py                  # until queue empty or 6h
    python drain_case_docs.py --hours 12
    python drain_case_docs.py --gap 55         # seconds between fetches
    python drain_case_docs.py --headed         # watch the WAF solve
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Pacing lives entirely in THIS runner (--gap / --cooldown). Disable the inner
# per-doc backoff so a throttled fetch raises DocRateLimited immediately instead
# of sleeping 60s x N inside case_pdf_extractor. Must be set BEFORE the import —
# DOC_MAX_RETRIES is read at module load.
os.environ.setdefault("NC_DOC_MAX_RETRIES", "0")

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402
import case_doc_queue as cdq  # noqa: E402
from case_pdf_extractor import (  # noqa: E402
    DocRateLimited, fetch_and_parse_case_docs,
)
from ecourts_scraper import cases_needing_docs, refresh_waf_cookie  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("drain")

# Odyssey app-session security means api/ViewDocument always 602s; only the WAF
# cookie matters, and it lasts ~4h. Re-mint a bit before that.
_WAF_MAX_AGE_S = 3.5 * 3600
# Fetch the application first (applicant + relationship + address + heirs + DOD);
# fall back to the will (executor name + relationship only).
_DOC_ORDER = {"application": 0, "will": 1}


def _ordered_targets() -> list[tuple[str, dict, tuple]]:
    """(case_hex, entry, priority) for pending no-PR cases, highest first."""
    needed = cases_needing_docs()          # case_no -> priority key
    pending = cdq.load_pending()
    out = []
    for case_hex, entry in pending.items():
        cn = (entry.get("case_number") or "").strip().upper()
        if cn in needed and entry.get("needs"):
            out.append((case_hex, entry, needed[cn]))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6.0, help="max wall-clock hours")
    ap.add_argument("--gap", type=float, default=55.0, help="seconds between fetches")
    ap.add_argument("--cooldown", type=float, default=180.0,
                    help="seconds to wait when the quota is exhausted")
    ap.add_argument("--headed", action="store_true", help="show the browser for the WAF solve")
    args = ap.parse_args()

    api_key = getattr(config, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot parse documents. Aborting.")
        return 2

    targets = _ordered_targets()
    if not targets:
        logger.info("Nothing to drain — no pending no-PR cases need a document.")
        return 0
    logger.info("Backlog: %d no-PR cases need a document. Highest-value first:", len(targets))
    for case_hex, entry, prio in targets[:5]:
        nc, val, _mt = prio
        logger.info("   %s  no_contact=%d  value=%s",
                    entry.get("case_number"), nc, f"${val:,.0f}")

    deadline = time.monotonic() + args.hours * 3600
    waf = asyncio.run(refresh_waf_cookie(headless=not args.headed))
    waf_minted = time.monotonic()
    if not waf.get("waf_token"):
        logger.error("Could not obtain a WAF cookie. Aborting.")
        return 2

    fetched = skipped = errors = no_doc = 0
    i = 0
    while i < len(targets):
        if i and i % 10 == 0:
            logger.info("progress: %d/%d cases — %d fetched, %d no-document, %d already-had",
                        i, len(targets), fetched, no_doc, skipped)
        if time.monotonic() > deadline:
            logger.info("Reached the %.1fh time budget — stopping.", args.hours)
            break

        # Re-mint the WAF cookie before it ages out.
        if time.monotonic() - waf_minted > _WAF_MAX_AGE_S:
            logger.info("WAF cookie aging — re-minting.")
            waf = asyncio.run(refresh_waf_cookie(force=True, headless=not args.headed))
            waf_minted = time.monotonic()

        case_hex, entry, _prio = targets[i]
        case_no = entry.get("case_number", "")

        # Skip doc types already in hand (resumability).
        needs = [dt for dt in entry.get("needs", [])
                 if not cdq.get_fetched(case_hex, dt)]
        needs.sort(key=lambda dt: _DOC_ORDER.get(dt, 9))
        if not needs:
            skipped += 1
            i += 1
            continue

        landed = False
        for dt in needs:
            try:
                got = fetch_and_parse_case_docs(
                    case_hex, waf_token=waf["waf_token"], doc_types=[dt],
                    api_key=api_key, all_cookies=waf.get("all_cookies"),
                    case_number=case_no,
                )
            except DocRateLimited:
                # Bucket empty. Wait out a longer cooldown and retry THIS case
                # (don't advance i).
                logger.info("Quota exhausted at %s — cooling down %.0fs "
                            "(%d fetched / %d done of %d)",
                            case_no, args.cooldown, fetched, i, len(targets))
                time.sleep(args.cooldown)
                break
            except Exception as e:  # noqa: BLE001
                logger.warning("fetch error for %s (%s): %s", case_no, dt, e)
                errors += 1
                continue
            results = got.get(dt) or []
            if not results:
                continue  # doc type absent from this docket — try the next
            parsed = results[0]
            cdq.record_fetched(case_hex, dt, parsed)
            cdq.mark_fetched(case_hex, dt)
            fetched += 1
            landed = True
            logger.info("LANDED %s -> %s (%s)  [%d fetched, %d/%d]",
                        case_no, dt, parsed.get("_meta", {}).get("event_label", ""),
                        fetched, i + 1, len(targets))
            break  # one good document is enough for this case

        else:
            # for-loop finished without break → no DocRateLimited. Either a doc
            # landed, or none of the needed types had a fetchable/parseable PDF
            # (fragments=0, or a scanned image that hits needs_ocr and is
            # skipped — the majority of the backlog).
            if not landed:
                no_doc += 1
                logger.debug("no fetchable document for %s (needs=%s)", case_no, needs)
            i += 1
            time.sleep(args.gap if landed else 0.2)
            continue

        # We hit the cooldown `break`. Only advance if the doc actually landed.
        if landed:
            i += 1
            time.sleep(args.gap)

    logger.info("Done. %d fetched, %d no-document, %d already-had, %d errors.",
                fetched, no_doc, skipped, errors)
    logger.info("Queue: %s", cdq.pending_summary())
    if no_doc and not fetched:
        logger.info("NOTE: every case tried had no fetchable/parseable PDF "
                    "(fragments=0 or scanned image needing OCR). These need OCR "
                    "or manual courthouse lookup, not a longer drain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
