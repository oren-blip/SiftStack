r"""Hold the machine awake while a child command runs.

Windows Modern Standby killed two nightly runs in a row: the 8/3 run died
when the PC idle-slept at 23:41 mid-step, and the 8/4 run to a manual
restart. This wrapper takes a SYSTEM power request (the same mechanism
"powercfg /requests" reports) for the lifetime of the child command, so
idle timeout can never suspend a run. It does NOT keep the display on,
and it cannot survive a user-initiated restart -- nothing can.

Usage (from a .bat, re-exec pattern):
    keep_awake.py -- <command ...>

The request is per-process and auto-clears if this process dies, so a
crashed run leaves no lingering wake lock.
"""
from __future__ import annotations

import subprocess
import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _set_awake(enable: bool) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enable else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("usage: keep_awake.py -- <command ...>", file=sys.stderr)
        return 2
    _set_awake(True)
    try:
        return subprocess.call(argv)
    finally:
        _set_awake(False)


if __name__ == "__main__":
    sys.exit(main())
