"""ISO-week archive helper.

A week is "archived" when output/archive_week<N>_done/ exists. Archived
weeks are skipped by the pipeline scripts (prepare_weekly_input.py,
fix_addresses_and_prep.py, consolidate_weeks.py) so we don't keep
re-processing weeks the user has already audited and finalized.

To archive a week: create output/archive_week<N>_done/ and move its
*_week<N>_*.csv / *_week<N>_*.xlsx files into it.
"""
from __future__ import annotations
import re
from pathlib import Path


_ARCHIVE_DIR_RE = re.compile(r"^archive_week(\d+)_done$")


def get_archived_weeks(output_dir: str | Path = "output") -> set[int]:
    """Return ISO week numbers archived under output/archive_week<N>_done/."""
    out = Path(output_dir)
    if not out.is_dir():
        return set()
    archived: set[int] = set()
    for d in out.iterdir():
        if d.is_dir():
            m = _ARCHIVE_DIR_RE.match(d.name)
            if m:
                archived.add(int(m.group(1)))
    return archived


def is_archived(iso_week: int, output_dir: str | Path = "output") -> bool:
    return iso_week in get_archived_weeks(output_dir)
