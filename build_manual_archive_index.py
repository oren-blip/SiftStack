"""Build a persistent index of the user's manual FTM XLSX archive.

The user maintains a master workbook (`FTM_2026_NC Estates (N).xlsx` in
their Downloads folder) with one tab per ISO week. Each tab contains
their manually-pulled probate cases with verified case numbers + PR
mailings. As newspaper-published notices (which lack case numbers) flow
into our weekly scraper, we want to automatically match them against
this manual archive — the case was almost certainly filed weeks earlier
and the user already pulled it.

This script:
  1. Finds the latest FTM XLSX in `C:\\Users\\omark\\Downloads\\`
  2. Walks every "Week N" tab, extracts rows with a non-blank Case No.
  3. Builds a JSON index keyed by (county, normalized-decedent-tokens)
  4. Writes to `output/.manual_archive_index.json` for use by
     `fix_addresses_and_prep.py:backfill_from_manual_archive`.

Re-run any time you update the manual workbook.

Usage:
    python build_manual_archive_index.py
    python build_manual_archive_index.py --xlsx "C:\\path\\to\\file.xlsx"
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger("manual_index")


INDEX_PATH = Path("output") / ".manual_archive_index.json"
DOWNLOADS_DIR = Path(r"C:\Users\omark\Downloads")
XLSX_GLOB = "FTM*NC*Estates*.xlsx"


def find_latest_xlsx() -> Path:
    candidates = sorted(DOWNLOADS_DIR.glob(XLSX_GLOB),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No {XLSX_GLOB} in {DOWNLOADS_DIR}")
    return candidates[0]


def name_token_key(name: str) -> str:
    """Order-independent name key — covers 'Last, First Middle' / 'First
    Middle Last' / 'AKA <alt>' variations by sorting normalized tokens.
    """
    s = (name or "").upper()
    s = re.sub(r"\bAKA\b.*", "", s)
    s = re.sub(r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR)\.?\b", "", s)
    tokens = sorted(t for t in re.findall(r"[A-Z]+", s) if len(t) >= 3)
    return " ".join(tokens)


def cell(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=None, help="Path to the manual XLSX file")
    args = ap.parse_args()

    xlsx_path = Path(args.xlsx) if args.xlsx else find_latest_xlsx()
    logger.info("Reading manual archive: %s", xlsx_path)
    wb = load_workbook(xlsx_path, data_only=True)

    week_tabs = [s for s in wb.sheetnames if s.lower().startswith("week ")]
    logger.info("Found %d week tabs", len(week_tabs))

    index: dict[str, dict] = {}  # key: "COUNTY||sorted-name-tokens"
    skipped_no_case = 0
    by_week_counts: dict[str, int] = {}

    for tab in week_tabs:
        ws = wb[tab]
        headers = [cell(c.value) for c in ws[1]]
        try:
            col_county = headers.index("County")
            col_case = headers.index("Case No.")
            col_dec = headers.index("Deceased Owner")
        except ValueError:
            logger.warning("Skipping tab %s (missing required column)", tab)
            continue

        # Optional columns — best effort
        def maybe(name: str) -> int | None:
            return headers.index(name) if name in headers else None
        col_first = maybe("First Name")
        col_last = maybe("Last Name")
        col_mail_addr = maybe("Mailing Address")
        col_mail_city = maybe("Mailing City")
        col_mail_state = maybe("Mailing State")
        col_mail_zip = maybe("Mailing Zip")
        col_parcel = maybe("Parcel ID")
        col_prop_addr = maybe("Property Address")
        col_prop_city = maybe("Property City")
        col_prop_zip = maybe("Property Zip")

        added_this_tab = 0
        for r in ws.iter_rows(min_row=2, values_only=True):
            county = cell(r[col_county]) if col_county < len(r) else ""
            case_no = cell(r[col_case]) if col_case < len(r) else ""
            dec = cell(r[col_dec]) if col_dec < len(r) else ""
            if not dec:
                continue
            if not case_no:
                skipped_no_case += 1
                continue
            key = f"{county.upper()}||{name_token_key(dec)}"
            entry = {
                "case_no": case_no,
                "week": tab,
                "deceased_owner": dec,
                "county": county,
            }
            for name, idx in [
                ("first_name", col_first), ("last_name", col_last),
                ("mailing_address", col_mail_addr), ("mailing_city", col_mail_city),
                ("mailing_state", col_mail_state), ("mailing_zip", col_mail_zip),
                ("parcel_id", col_parcel),
                ("property_address", col_prop_addr), ("property_city", col_prop_city),
                ("property_zip", col_prop_zip),
            ]:
                if idx is not None and idx < len(r):
                    val = cell(r[idx])
                    if val:
                        entry[name] = val
            # First occurrence wins (oldest week — closer to file date)
            if key not in index:
                index[key] = entry
                added_this_tab += 1
        by_week_counts[tab] = added_this_tab

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump({"_source_xlsx": str(xlsx_path), "_entries": index}, f,
                  separators=(",", ":"), ensure_ascii=False)

    logger.info("Wrote index: %s", INDEX_PATH)
    logger.info("  Total unique (county, decedent) entries: %d", len(index))
    logger.info("  Skipped rows without Case No.: %d", skipped_no_case)
    logger.info("Per-week additions (new unique decedents per tab):")
    for tab in week_tabs:
        n = by_week_counts.get(tab, 0)
        logger.info("  %s: %d", tab, n)


if __name__ == "__main__":
    main()
