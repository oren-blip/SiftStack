"""READ-ONLY: what else does the CRM hold on Adolphus Rd / the TR7 tract?"""
from __future__ import annotations
import sys
from pathlib import Path
import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "src"))
from audit_rename_gap_20260822 import search, token  # noqa: E402

tok = token()
h = {"accept": "application/json", "origin": "https://app.reisift.io",
     "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
     "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
     "content-type": "application/json"}

for q in ("Adolphus Rd", "Heiligh", "Pabon", "Dubose"):
    hits = search(h, q)
    print(f"\n=== {q!r}: {len(hits)} hit(s) ===")
    for r in hits[:25]:
        a = r.get("address") or {}
        o = r.get("owner") or {}
        oa = o.get("address") or {}
        if q == "Adolphus Rd" and "adolphus" not in (a.get("street") or "").lower():
            continue
        print(f"  {a.get('street')}, {a.get('city')} {a.get('postal_code')} | parcel={r.get('parcel_id')}")
        print(f"     owner: {o.get('first_name')} {o.get('last_name')} / {o.get('company')}")
        print(f"     mail : {oa.get('street')}, {oa.get('city')} {oa.get('state')} {oa.get('postal_code')}")
        print(f"     lists={r.get('lists')} phones={o.get('total_phones')} uuid={r.get('uuid')}")
