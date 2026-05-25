"""Standalone validation of the DM-wiring fix.

Picks the 9 known regressions from the last A/B (rows where manual pull
had a named heir but pipeline output said "Heirs of [Decedent]"),
reconstructs them as NoticeData, runs the state-aware obituary enricher
with `--nc-obituary` semantics (NC mode, Tier 2 only, no Knox Tax), and
reports whether `notice.decision_maker_name` got populated.

This validates two things end-to-end without burning ~50 min on a full
weekly run:
  1. obituary_enricher correctly sets decision_maker_name for NC notices
  2. nc_ftm_writer reads decision_maker_* into the DM columns

Step 4 DM-promotion logic is already unit-tested separately.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402
from notice_parser import NoticeData  # noqa: E402
from obituary_enricher import enrich_obituary_data  # noqa: E402
from nc_ftm_writer import notice_to_ftm_row, FTM_COLUMNS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("validate_dm")


# The 9 regressions from the previous A/B comparison
REGRESSIONS = [
    # (county, decedent, expected_manual_heir, property_city)
    ("Catawba",      "McCachren, Clifford Mitchell", "Shane McCachren",     "Conover"),
    ("Catawba",      "Isaac, Brenda Joyce Stafford", "Christopher Isaac",   "Conover"),
    ("Gaston",       "Weiden, Mary",                 "Gregory A Germain",   "Gastonia"),
    ("Gaston",       "Deviney, Raymond Ray",         "Christopher Deviney", "Gastonia"),
    ("Iredell",      "Moore, Robert Burl",           "David Moore",         "Statesville"),
    ("Mecklenburg",  "Cook, Joel Wayne",             "Joel Cook",           "Charlotte"),
    ("Mecklenburg",  "Malone, Philip Morris",        "Rachel M Clark",      "Charlotte"),
    ("Rowan",        "Floyd David Long, Jr",         "Donald Long",         "Salisbury"),
    ("Rowan",        "Hildebrand, Shirley H",        "Ricky Hildebrand",    "Salisbury"),
]


def build_notice(county: str, decedent: str, property_city: str) -> NoticeData:
    return NoticeData(
        notice_type="probate",
        county=county,
        state="NC",
        date_added=datetime.now().strftime("%Y-%m-%d"),
        decedent_name=decedent,
        city=property_city,
        owner_deceased="yes",
    )


def main() -> None:
    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — aborting")
        sys.exit(1)

    notices = [build_notice(c, d, city) for (c, d, _expected, city) in REGRESSIONS]
    logger.info("Built %d test NoticeData (state=NC) for the 9 known regressions",
                len(notices))

    # Run the state-aware obituary enricher. Same flags the --nc-obituary
    # opt-in uses: ancestry off (Knox-only), tracerfy_tier1 off, all
    # other defaults.
    logger.info("Running enrich_obituary_data (state-aware path)...")
    enrich_obituary_data(
        notices,
        config.ANTHROPIC_API_KEY,
        skip_heir_verification=False,
        max_heir_depth=2,
        skip_dm_address=False,
        tracerfy_tier1=False,
        skip_ancestry=True,
    )

    # Report per-row outcomes
    print()
    print("=" * 90)
    print(f"{'Decedent':<35} {'Expected manual heir':<22} {'Obituary enricher DM':<22} {'Match?'}")
    print("-" * 90)
    matched = 0
    found_any_dm = 0
    for n, (_c, dec, expected, _city) in zip(notices, REGRESSIONS, strict=True):
        dm = (n.decision_maker_name or "").strip()
        if dm:
            found_any_dm += 1
        # Loose match: any token from expected last name appears in DM name
        expected_last = expected.strip().split()[-1].lower()
        is_match = expected_last and expected_last in dm.lower()
        if is_match:
            matched += 1
        print(f"{dec[:34]:<35} {expected[:21]:<22} {(dm or '(empty)')[:21]:<22} "
              f"{'YES' if is_match else 'no'}")
    print("-" * 90)
    print(f"DM Name populated: {found_any_dm}/{len(notices)}  "
          f"Matched expected heir: {matched}/{len(notices)}")
    print()

    # Also write the FTM XLSX using the NEW nc_ftm_writer wiring so we
    # can verify DM Name actually lands in the workbook column.
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_csv = Path("output") / f"validate_dm_wiring_{ts}.csv"
    rows = [notice_to_ftm_row(n) for n in notices]
    import csv as _csv
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=FTM_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    logger.info("Wrote validation CSV: %s", out_csv)

    dm_cells = sum(1 for r in rows if (r.get("DM Name") or "").strip())
    logger.info("DM Name column populated in output CSV: %d/%d", dm_cells, len(rows))


if __name__ == "__main__":
    main()
