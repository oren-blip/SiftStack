#!/usr/bin/env python
"""Archive finished ISO weeks. A closed week stays live Mon+Tue, goes Wednesday.

Oren's rule (2026-07-16): a week that has closed stays on the workbook for the
Monday and Tuesday runs, then gets put away.

Why not archive the instant the week closes (the first plan): Friday's cases
would get exactly ONE polish pass, and one pass is provably not enough --

  * Several enrichment steps are rationed per night ON PURPOSE: LandPortal's
    property-data quota (a global exhausted-flag; leftovers wait for tomorrow),
    nc_phone_backfill --limit 25, nc_deep_prospect max-rows 50, ~15 Odyssey doc
    fetches. A week's enrichment is MEANT to spread over several nights.
    Evidence: re-polishing week 28 on 2026-07-16 -- four days after it closed --
    recovered 26E000805-170 (Catawba, Barnes) via `landportal-reval`, and
    26E002514-590 (Mecklenburg, Davis). One pass would have dropped both.
  * County GIS outages. Gaston was down the evening of 2026-07-16; a lookup
    during an outage returns zero rows, indistinguishable from "owns nothing",
    and the row is dropped at the has-parcel filter. Only a later night's
    re-polish recovers it.
  * Friday's cases first appear in Friday night's workbook, and no runs happen
    at the weekend -- so Mon+Tue is the window to actually work them.

Weeks older than the previous one are archived regardless of weekday: their
enrichment is long finished and each one costs ~1h45m per night.

Why this is automated rather than left as a habit: an un-archived week is
re-polished from scratch EVERY night, forever. prepare_weekly_input.py stops
emitting new merged files for it after 14 days, but the old merged file stays
in output/ and fix_addresses_and_prep.py globs the lot with no date window --
so nothing ages out on its own. Week 24's merged files were still sitting there
a month later; only its archive marker stopped the rebuild. Each forgotten week
is a permanent ~1h45m added to every future run, and at 4-5 of them the nightly
build would still be going when the next one fires and die on the pipeline lock.
The failure is silent and cumulative, which is exactly what a guard is for.

Archiving is just the marker directory output/archive_week<N>_done/ existing --
prepare_weekly_input, fix_addresses_and_prep and consolidate_weeks all check it
(see iso_week_archive.py). Moving the CSVs in is optional housekeeping, so this
script doesn't bother: week 24's files never moved and it archives correctly.

Nothing is lost by archiving:
  * cases_needing_docs() keeps hunting an archived week's Wills/Applications
    for a full 30 days -- it deliberately walks archived weeks.
  * apply_late_docs.py applies anything that lands and the daily report
    surfaces it.
To un-archive, delete the marker directory.

Usage:
    python scripts/auto_archive_weeks.py            # archive stale weeks
    python scripts/auto_archive_weeks.py --dry-run  # show what would happen
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from iso_week_archive import get_archived_weeks  # noqa: E402

OUTPUT_DIR = Path("output")
# Only weeks that actually produced a polished sheet are worth a marker.
_POLISHED_RE = re.compile(
    r"^nc_estates_ftm_(\d{4})-\d{2}-\d{2}_\d{6}_week(\d+)_"
    r"(datasift|dm_enriched|ecourts_backfilled)\.csv$")


_ARCHIVE_FROM_ISOWEEKDAY = 3  # Wednesday — the previous week goes away today


def _is_due(yw: tuple[int, int], now: datetime) -> bool:
    """Is this (year, week) finished enough to archive today?

    Compared as (year, week) tuples rather than bare week numbers, and the
    previous week is derived by subtracting 7 days rather than 1 from the week
    number, so the turn of the year can't archive week 52 of the new year on
    1 January.
    """
    cur = now.isocalendar()
    if yw >= (cur.year, cur.week):
        return False  # the live week (or a future-dated file) — never
    prev = (now - timedelta(days=7)).isocalendar()
    if yw == (prev.year, prev.week):
        return now.isoweekday() >= _ARCHIVE_FROM_ISOWEEKDAY  # Mon+Tue: keep live
    return True  # older than last week — enrichment long finished


def stale_weeks(now: datetime) -> list[tuple[int, int]]:
    """(year, week) pairs that are due for archiving and not yet archived."""
    archived = get_archived_weeks()
    seen: set[tuple[int, int]] = set()
    for fp in OUTPUT_DIR.glob("nc_estates_ftm_*.csv"):
        m = _POLISHED_RE.match(fp.name)
        if not m:
            continue
        yw = (int(m.group(1)), int(m.group(2)))
        if yw[1] not in archived and _is_due(yw, now):
            seen.add(yw)
    return sorted(seen)


# A week is frozen forever once archived, so never freeze one whose last polish
# ran against a dead county GIS -- those rows lost their parcel to an outage and
# were dropped, and only another polish brings them back. Deferring costs one
# night; archiving anyway costs the leads permanently.
_OUTAGE_PATH = OUTPUT_DIR / ".gis_outage_last_run.json"
# ...but a county that stays dead must not defer archiving forever, or the
# runtime creep this script exists to prevent comes back. Past this, archive and
# say so.
_OUTAGE_DEFER_MAX_DAYS = 4


def outage_block(now: datetime) -> tuple[list[str], bool]:
    """(counties down in the last run, whether the note is too old to honour)."""
    try:
        data = json.loads(_OUTAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], False  # no note = no known outage
    counties = data.get("counties") or []
    if not counties:
        return [], False
    try:
        age = now - datetime.fromisoformat(data.get("ts", ""))
    except (ValueError, TypeError):
        return [], False
    return list(counties), age > timedelta(days=_OUTAGE_DEFER_MAX_DAYS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be archived; create nothing")
    args = ap.parse_args()

    now = datetime.now()
    stale = stale_weeks(now)
    if not stale:
        print(f"auto-archive: nothing to do "
              f"(live week = {now.isocalendar().week}, all older weeks archived)")
        return

    down, expired = outage_block(now)
    if down and not expired:
        print(f"auto-archive: DEFERRED for week(s) {[w for _, w in stale]} — "
              f"last run hit a GIS outage ({', '.join(down)}), so those rows are "
              f"incomplete. Will archive after a clean run.")
        return
    if down and expired:
        print(f"auto-archive: {', '.join(down)} has been down for over "
              f"{_OUTAGE_DEFER_MAX_DAYS} days — archiving anyway so the nightly "
              f"run doesn't creep. {', '.join(down)} rows in these weeks may be "
              f"incomplete.")

    for year, wk in stale:
        marker = OUTPUT_DIR / f"archive_week{wk}_done"
        if args.dry_run:
            print(f"auto-archive: WOULD archive week {wk} {year} -> {marker}/")
            continue
        marker.mkdir(parents=True, exist_ok=True)
        print(f"auto-archive: archived week {wk} {year} "
              f"(saves ~1h45m/night; un-archive by deleting {marker}/)")


if __name__ == "__main__":
    main()
