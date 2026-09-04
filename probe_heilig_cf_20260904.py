"""READ-ONLY: dump the custom-field values on the Adolphus Rd / Heiligh record."""
from __future__ import annotations
import sys
from pathlib import Path
import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "src"))
from audit_rename_gap_20260822 import API, token  # noqa: E402

UUID = "d0d0be79-f2ae-4918-bcff-738a896b1b48"

tok = token()
h = {"accept": "application/json", "origin": "https://app.reisift.io",
     "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
     "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
     "content-type": "application/json"}
r = requests.get(f"{API}/api/internal/property/{UUID}/custom-field/?offset=0&limit=1000",
                 headers=h, timeout=30)
print("HTTP", r.status_code)
d = r.json()
rows = d.get("results") or d.get("data") or []
print(f"{len(rows)} custom-field rows\n")
for e in rows:
    lab = ((e.get("custom_field") or {}).get("label") or "").strip()
    val = e.get("value")
    if val not in (None, "", []):
        print(f"  {lab:<34} = {val}")
print("\n--- empty ones ---")
print(", ".join(sorted(((e.get("custom_field") or {}).get("label") or "").strip()
                       for e in rows if e.get("value") in (None, "", []))))
