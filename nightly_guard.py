"""Is the nightly build running right now?

Any script that talks to eCourts or writes the weekly CSVs must refuse to run
while nc_daily_run.bat is up. Learned 2026-09-03: a hex backfill launched at
17:00:02 -- the exact minute the nightly starts -- and Odyssey stopped rendering
Smart Search after 4 attempts, because the portal is IP-throttled and the
nightly owned the session. Both processes also write the same picked weekly
CSVs, so a concurrent run can silently lose edits.

Do NOT use scripts/pipeline_lock.py's `pid_alive` for this. nc_daily_run.bat
re-execs itself under scripts/keep_awake.py, so the pid recorded in the lock is
the ORIGINAL cmd.exe, which exits immediately -- the lock reads pid_alive=false
for the entire run. The log is authoritative instead: a "Daily run started" line
with no matching "done"/"aborted"/"skipped" after it means still running.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, time
from pathlib import Path

REPO = Path(__file__).parent
LOG = REPO / "logs" / "nc_daily_run.log"

# nc_daily_run.bat is scheduled for 17:00 on workdays. "No run in the log yet"
# is NOT a safe green light just before that: the check-then-launch window is
# wide enough to lose. Today's first collision was exactly this -- a job started
# at 17:00:02, the same second as the nightly. A peer session hit the identical
# race on a shared browser profile the same night. So treat the minutes around
# the start time as closed, whatever the log says.
_BLACKOUT_START = time(16, 50)
_BLACKOUT_END = time(17, 10)


def _in_start_blackout() -> str:
    now = datetime.now()
    if now.weekday() >= 5:          # nightly skips weekends
        return ""
    if _BLACKOUT_START <= now.time() <= _BLACKOUT_END:
        return (f"nightly build is due to start at 17:00 (now {now:%H:%M}) -- "
                f"inside the {_BLACKOUT_START:%H:%M}-{_BLACKOUT_END:%H:%M} blackout")
    return ""


_STALE_AFTER_HOURS = float(os.environ.get("NC_NIGHTLY_STALE_HOURS", "14") or 14)

_MARKER_TS = re.compile(r"(\d{2}/\d{2}/\d{4})\s+([\d:.]+)")


def _marker_time(line: str) -> datetime | None:
    """Parse the `MM/DD/YYYY HH:MM:SS.ss` stamp cmd.exe writes into a marker."""
    m = _MARKER_TS.search(line or "")
    if not m:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", fmt)
        except ValueError:
            continue
    return None


def nightly_running() -> str:
    """Return a human-readable reason string if the nightly is up, else ''."""
    blackout = _in_start_blackout()
    if blackout:
        return blackout
    if not LOG.exists():
        return ""
    try:
        # Mixed-encoding log (see project_geocode_cache_blank_cityzip) -- decode
        # defensively, we only need to find ASCII markers.
        text = LOG.read_bytes()[-400_000:].decode("ascii", "replace")
    except OSError:
        return ""
    last_start = text.rfind("=== Daily run started")
    if last_start < 0:
        return ""
    tail = text[last_start:]
    # "Back-half resume done" is a real ending: when the 4.5h budget killer
    # chops the back half, nc_backhalf_resume.bat finishes the run and writes
    # ITS OWN marker -- nc_daily_run.bat never reaches its "Daily run done".
    # Without this the guard read the 9/9 run as still running all through 9/10
    # and every guarded job (cold-case parties, hex backfill) refused silently
    # on exactly the mornings after a run that overran, which are the mornings
    # with the most left undone.
    for marker in ("=== Daily run done", "Daily run aborted", "Daily run skipped",
                   "=== Back-half resume done"):
        if marker in tail:
            return ""
    # A run that was killed outright (machine slept, power cut) writes no marker
    # at all, and "still running" would then be permanent. The nightly starts at
    # 17:00 and the budget killer caps it at 4.5h, so anything still unmarked the
    # next morning is over. The start blackout above and the pipeline lock remain
    # the real mutex.
    started = _marker_time(tail.split(chr(10), 1)[0])
    if started and (datetime.now() - started).total_seconds() > _STALE_AFTER_HOURS * 3600:
        return ""
    return f"nightly build still running -- {tail.split(chr(10), 1)[0].strip()}"


def refuse_if_nightly(force: bool = False) -> bool:
    """Print and return True when the caller should abort."""
    busy = nightly_running()
    if busy and not force:
        print(f"REFUSING TO RUN: {busy}")
        print("The nightly owns the eCourts session and rewrites these same "
              "CSVs.\nWait for it to finish, or pass --force.")
        return True
    return False
