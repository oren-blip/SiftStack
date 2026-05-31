r"""Pipeline run lock — prevent concurrent nc_*_run.bat invocations.

The TN/NC pipelines share output/, seen_ids, the WAF cookie, and the
manual archive index. Running two pipelines at once corrupts state
(seen examples: weekly re-scrape racing the 6pm daily run, both writing
Week-N merged files in parallel and tripping each other's polish steps).

Usage from a .bat:
    REM acquire
    "%PY%" scripts\pipeline_lock.py acquire weekly
    if errorlevel 1 exit /b 1
    REM ... run pipeline ...
    REM release at the end
    "%PY%" scripts\pipeline_lock.py release

Lock file: state\pipeline.lock (JSON with parent PID + label + start time).
A stale lock (parent PID no longer alive) is silently overwritten on
acquire — no manual cleanup needed after a crashed run.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

LOCK_PATH = Path("state") / "pipeline.lock"


def _is_pid_alive(pid: int) -> bool:
    """True if the given PID is currently running. Cross-platform.

    Windows quirk: OpenProcess can return a non-NULL handle for processes
    that have exited but whose kernel objects haven't been reaped yet —
    so we ALSO check GetExitCodeProcess and only treat STILL_ACTIVE (259)
    as alive. Without this check, stale locks from crashed/exited bats
    never get cleaned up.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h == 0:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            ok = kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(h)
    # Unix
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_lock() -> dict | None:
    if not LOCK_PATH.exists():
        return None
    try:
        return json.loads(LOCK_PATH.read_text())
    except (ValueError, OSError):
        return None


def _write_lock(label: str, parent_pid: int) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps({
        "label": label,
        "parent_pid": parent_pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }, indent=2))


def cmd_acquire(label: str) -> int:
    existing = _read_lock()
    if existing:
        pid = existing.get("parent_pid", 0)
        if _is_pid_alive(pid):
            print(
                f"ERROR: pipeline already running "
                f"(label={existing.get('label')!r}, "
                f"parent_pid={pid}, started_at={existing.get('started_at')}). "
                f"Wait for it to finish, or kill it and delete {LOCK_PATH}.",
                file=sys.stderr,
            )
            return 1
        print(
            f"NOTE: stale lock (label={existing.get('label')!r}, "
            f"dead pid={pid}) — overwriting.",
            file=sys.stderr,
        )
    parent_pid = os.getppid()
    _write_lock(label, parent_pid)
    print(f"acquired pipeline lock (label={label!r}, parent_pid={parent_pid})")
    return 0


def cmd_release() -> int:
    existing = _read_lock()
    if not existing:
        print("no lock to release (already gone)")
        return 0
    parent_pid = os.getppid()
    lock_pid = existing.get("parent_pid", 0)
    # Only release if we're the holder (or the holder is dead — stale lock).
    if lock_pid == parent_pid or not _is_pid_alive(lock_pid):
        try:
            LOCK_PATH.unlink()
            print(f"released pipeline lock (label={existing.get('label')!r})")
        except OSError as e:
            print(f"WARNING: failed to remove lock file: {e}", file=sys.stderr)
            return 1
        return 0
    print(
        f"WARNING: not releasing lock — held by different parent "
        f"(lock_pid={lock_pid}, my_parent={parent_pid}). "
        f"Manually delete {LOCK_PATH} if you're sure.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: pipeline_lock.py {acquire <label>|release|status}", file=sys.stderr)
        return 2
    cmd = sys.argv[1].lower()
    if cmd == "acquire":
        if len(sys.argv) < 3:
            print("usage: pipeline_lock.py acquire <label>", file=sys.stderr)
            return 2
        return cmd_acquire(sys.argv[2])
    if cmd == "release":
        return cmd_release()
    if cmd == "status":
        existing = _read_lock()
        if not existing:
            print("no lock")
            return 0
        pid = existing.get("parent_pid", 0)
        alive = _is_pid_alive(pid)
        print(json.dumps({**existing, "pid_alive": alive}, indent=2))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
