r"""Run one nightly-pipeline step under the run's global time budget.

nc_daily_run.bat computes a wall-clock deadline at start (default 4.5h,
NC_RUN_MAX_MINS to change, 0 to disable) and exports NC_RUN_DEADLINE_EPOCH.
Each heavy step is launched through this wrapper:

    step_timeout.py -- <command ...>

Behavior:
  - No deadline in the environment -> run the command unbounded (manual
    nc_weekly_run.bat invocations are unaffected).
  - Deadline already passed -> SKIP the step (exit 0) so the cheap back
    half (consolidate + daily report) still runs and the workbook lands.
  - Step still running at the deadline -> kill its whole process tree
    (taskkill /T /F, catches Playwright browser children) and exit 0.

Why exit 0 on kill/skip: the bat must CONTINUE. A partial night is fine —
raw scrape rows already on disk survive, the polish re-runs every night,
and a week with no fresh polished file consolidates from the prior run's.
The *** BUDGET lines in the log are the audit trail.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


def _say(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        _say("usage: step_timeout.py -- <command ...>")
        return 2

    raw = os.environ.get("NC_RUN_DEADLINE_EPOCH", "").strip()
    try:
        deadline = float(raw) if raw else 0.0
    except ValueError:
        deadline = 0.0

    if deadline <= 0:
        return subprocess.call(argv)

    remaining = deadline - time.time()
    label = " ".join(argv[:4])
    if remaining <= 60:
        _say(f"*** BUDGET: run is past its deadline — SKIPPING step: {label} ***")
        return 0

    _say(f"[budget] {remaining / 60:.0f} min left for: {label}")
    proc = subprocess.Popen(argv)
    try:
        return proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        _say(f"*** BUDGET: step hit the nightly deadline after "
             f"{remaining / 60:.0f} min — killing its process tree and moving "
             f"on so consolidate + report still run: {label} ***")
        subprocess.call(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _say("*** BUDGET: process tree did not exit within 30s of taskkill ***")
        return 0


if __name__ == "__main__":
    sys.exit(main())
