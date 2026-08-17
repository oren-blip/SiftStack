"""Pull the DataSift (app.reisift.io) rs_token from Chrome's Local Storage
on disk — no DevTools, no copy/paste (Oren couldn't paste into the console,
Chrome blocks console pastes by default).

Chrome stores localStorage in per-profile leveldb files. We copy them to a
temp dir (dodges file locks while Chrome is open), binary-scan for JWTs near
"rs_token" keys (UTF-8 and UTF-16 encodings), then validate each candidate
against the live API and return the first one that authenticates. Read-only.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import requests

API = "https://apiv2.reisift.io"
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")


def _leveldb_dirs():
    base = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    if not base.exists():
        return
    for prof in base.iterdir():
        lv = prof / "Local Storage" / "leveldb"
        if lv.is_dir():
            yield lv


def _candidates():
    seen = {}
    for lv in _leveldb_dirs():
        files = sorted(lv.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files:
            if f.suffix.lower() not in (".ldb", ".log"):
                continue
            try:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    shutil.copyfile(f, tmp.name)
                    data = Path(tmp.name).read_bytes()
                os.unlink(tmp.name)
            except OSError:
                continue
            if b"reisift" not in data and b"r\x00e\x00i\x00s\x00i\x00f\x00t" not in data:
                continue
            for m in JWT_RE.finditer(data):
                tok = m.group(0).decode("ascii")
                seen.setdefault(tok, f.stat().st_mtime)
            # UTF-16LE-stored values: strip interleaved NULs and rescan
            stripped = data.replace(b"\x00", b"")
            for m in JWT_RE.finditer(stripped):
                tok = m.group(0).decode("ascii")
                seen.setdefault(tok, f.stat().st_mtime)
    # newest file first
    return [t for t, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def _works(tok: str) -> bool:
    h = {"authorization": f"Bearer {tok}", "accept": "application/json",
         "origin": "https://app.reisift.io", "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0"}
    try:
        r = requests.get(f"{API}/api/internal/user/", headers=h, timeout=20)
        print(f"  candidate {tok[:18]}... -> user/ HTTP {r.status_code}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"  candidate {tok[:18]}... -> network error {e}")
        return False


def get_token() -> str | None:
    cands = _candidates()
    print(f"found {len(cands)} JWT candidate(s) in Chrome Local Storage")
    for tok in cands[:12]:
        if _works(tok):
            print("validated a working DataSift token from Chrome")
            return tok
    return None


if __name__ == "__main__":
    t = get_token()
    print(t[:40] + "..." if t else "NO WORKING TOKEN FOUND — log into app.reisift.io in Chrome, then rerun")
