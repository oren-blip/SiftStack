"""READ-ONLY probe: dump the full DataSift record for the Adolphus Rd /
Heilig case Oren flagged (missing Case No., suspect parcel).

    python probe_heilig_20260904.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, search, token  # noqa: E402

UUID = "d0d0be79-f2ae-4918-bcff-738a896b1b48"


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    r = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    print("GET status", r.status_code)
    if r.status_code != 200:
        print(r.text[:2000])
        return 1
    d = r.json()
    rec = d.get("data") or d
    out = REPO / "output" / "heilig_record_20260904.json"
    out.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    print("wrote", out)

    def g(*path):
        cur = rec
        for p in path:
            cur = (cur or {}).get(p) if isinstance(cur, dict) else None
        return cur

    print("\n--- top-level keys ---")
    print(sorted(rec.keys()) if isinstance(rec, dict) else type(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
