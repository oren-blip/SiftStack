"""Heir prospecting for FTM rows missing executor / personal representative data.

When NC eCourts hasn't yet captured a court-named executor (case just
opened, small estate affidavit not filed yet, or executor never recorded),
the FTM row sits with blank `Personal Representative`. These are NOT dead
leads — the property is still in probate, just without a formally-filed
contact. To turn them into actionable leads, we run the existing
4-level deep-prospecting waterfall:

  L1 (Court record)  → already done by reenrich_ftm_executors.py
  L2 (Obituary)      → search obituary for survivors, rank heirs
  L3 (Skip trace)    → Tracerfy phone numbers for top heirs
  L4 (DM address)    → multi-tier mailing-address lookup

The script reads the latest FTM CSV, finds rows with blank executor,
reconstructs NoticeData objects, runs obituary_enricher + batch_skip_trace
(both already wired in the main pipeline), and merges the resulting
decision-maker fields back into 8 new DM columns on the FTM CSV.

Usage:
    python heir_prospect_no_executor.py
    python heir_prospect_no_executor.py --csv output/nc_estates_ftm_X.csv
    python heir_prospect_no_executor.py --max-heir-depth 1   # quicker
    python heir_prospect_no_executor.py --skip-skip-trace    # no Tracerfy
    python heir_prospect_no_executor.py --max-rows 5         # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402
from notice_parser import NoticeData  # noqa: E402
from obituary_enricher import enrich_obituary_data  # noqa: E402
from tracerfy_skip_tracer import batch_skip_trace  # noqa: E402
from reenrich_ftm_executors import write_csv, write_xlsx  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("heir_prospect")


def parse_file_date(s: str) -> str:
    """Normalize '5/11/2026' or '2026-05-11' to YYYY-MM-DD for NoticeData.date_added."""
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def row_to_notice(row: dict) -> NoticeData:
    """Rebuild a NoticeData from an FTM CSV row.

    Only populates the fields obituary_enricher + batch_skip_trace need:
    decedent_name, county, state, date_added, address (for context), and
    owner_deceased="yes" (triggers obituary search path).
    """
    return NoticeData(
        notice_type="probate",
        county=row.get("County", ""),
        state="NC",
        date_added=parse_file_date(row.get("File Date", "")),
        decedent_name=row.get("Deceased Owner", ""),
        address=row.get("Property Address", ""),
        city=row.get("Property City", ""),
        zip=row.get("Property Zip", ""),
        owner_deceased="yes",  # signals obituary enricher to process
        source_url=row.get("Case No.", ""),
    )


def apply_notice_dm_to_row(row: dict, n: NoticeData) -> bool:
    """Copy enriched NoticeData DM/phone/email fields onto the CSV row.

    Returns True if any non-empty DM data was written.
    """
    wrote_anything = False

    def setf(col: str, val: str) -> None:
        nonlocal wrote_anything
        val = (val or "").strip()
        if val:
            row[col] = val
            wrote_anything = True

    setf("DM Name", n.decision_maker_name)
    setf("DM Relationship", n.decision_maker_relationship)
    setf("DM 2 Name", n.decision_maker_2_name)
    setf("DM 2 Relationship", n.decision_maker_2_relationship)
    setf("DM 3 Name", n.decision_maker_3_name)
    setf("DM 3 Relationship", n.decision_maker_3_relationship)

    # Phone: prefer primary_phone (skip-traced top heir), then mobile_1, then landline_1
    phone = (
        getattr(n, "primary_phone", "")
        or getattr(n, "mobile_1", "")
        or getattr(n, "landline_1", "")
    )
    setf("DM Phone", phone)

    # Email: email_1 if present
    setf("DM Email", getattr(n, "email_1", ""))

    return wrote_anything


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None,
                    help="FTM CSV path (default: latest in output/)")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="Cap rows processed (0 = all). Use small N for smoke testing.")
    ap.add_argument("--max-heir-depth", type=int, default=2,
                    help="Obituary enricher max heir verification depth (default 2)")
    ap.add_argument("--skip-heir-verification", action="store_true",
                    help="Skip living-status verification for heirs (faster, less accurate)")
    ap.add_argument("--skip-dm-address", action="store_true",
                    help="Skip DM mailing-address lookup (saves Firecrawl calls)")
    ap.add_argument("--skip-skip-trace", action="store_true",
                    help="Skip Tracerfy skip-trace step (no phone numbers, no cost)")
    args = ap.parse_args()

    src_csv = Path(args.csv) if args.csv else max(Path("output").glob("nc_estates_ftm_*.csv"))
    logger.info("Source CSV: %s", src_csv)
    with src_csv.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    logger.info("Loaded %d rows", len(rows))

    target = [
        r for r in rows
        if not (r.get("Personal Representative") or "").strip()
        and (r.get("Deceased Owner") or "").strip()
        and "IN THE MATTER" not in (r.get("Deceased Owner") or "").upper()
    ]
    logger.info("Targets (no executor + valid decedent): %d", len(target))

    if args.max_rows and args.max_rows < len(target):
        target = target[:args.max_rows]
        logger.info("--max-rows: capped to %d rows", len(target))

    if not target:
        logger.info("Nothing to do")
        return

    # Build NoticeData list
    notices = [row_to_notice(r) for r in target]
    notice_to_row = {id(n): r for n, r in zip(notices, target, strict=True)}

    # ── Stage 1: obituary enrichment (populates DM fields + heir_map_json) ──
    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set in .env — aborting (needed for "
                     "obituary enricher LLM extraction)")
        sys.exit(1)
    logger.info("Stage 1/2: obituary enrichment (max_heir_depth=%d, skip_verification=%s, "
                "skip_dm_address=%s)",
                args.max_heir_depth, args.skip_heir_verification, args.skip_dm_address)
    enrich_obituary_data(
        notices,
        config.ANTHROPIC_API_KEY,
        skip_heir_verification=args.skip_heir_verification,
        max_heir_depth=args.max_heir_depth,
        skip_dm_address=args.skip_dm_address,
        tracerfy_tier1=False,  # don't burn Tracerfy in tier-1 address; let stage 2 handle phones
        skip_ancestry=False,
    )

    obit_hits = sum(1 for n in notices if (n.decision_maker_name or "").strip())
    logger.info("Obituary stage: %d/%d rows now have a DM name", obit_hits, len(notices))

    # ── Stage 2: Tracerfy skip trace (populates phones + emails) ──
    if not args.skip_skip_trace:
        if not config.TRACERFY_API_KEY:
            logger.warning("TRACERFY_API_KEY not set — skipping skip-trace stage")
        else:
            logger.info("Stage 2/2: Tracerfy skip trace (max_signing_traces=5)")
            stats = batch_skip_trace(
                notices,
                max_signing_traces=5,
                lookup_heir_addresses=True,
                address_lookup_api_key=config.ANTHROPIC_API_KEY,
            )
            logger.info("Skip-trace stats: %s", stats)
    else:
        logger.info("--skip-skip-trace: skipping Tracerfy stage")

    # ── Merge enriched fields back into CSV rows ──
    rows_filled = 0
    for n in notices:
        row = notice_to_row[id(n)]
        if apply_notice_dm_to_row(row, n):
            rows_filled += 1

    # ── Write outputs ──
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_csv = Path("output") / f"nc_estates_ftm_{ts}.csv"
    out_xlsx = Path("output") / f"nc_estates_ftm_{ts}.xlsx"
    write_csv(rows, out_csv)
    write_xlsx(rows, out_xlsx)

    logger.info("=" * 60)
    logger.info("Heir prospecting complete")
    logger.info("Targets processed: %d", len(target))
    logger.info("DM data written: %d rows", rows_filled)
    logger.info("Output: %s", out_csv)


if __name__ == "__main__":
    main()
