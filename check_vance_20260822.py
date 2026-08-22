import sys, json, requests
from pathlib import Path
REPO = Path(r"d:\SiftStack"); sys.path.insert(0, str(REPO))
from audit_rename_gap_20260822 import token, search
tok = token()
h = {"accept": "application/json", "origin": "https://app.reisift.io",
     "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
     "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
     "content-type": "application/json"}
for q in ("Brevard Place Rd", "Vance"):
    print("=" * 70)
    print("query:", q)
    for x in search(h, q):
        a = x.get("address") or {}
        o = x.get("owner") or {}
        st = (a.get("street") or "")
        if q == "Vance" and "brevard" not in st.lower():
            continue
        tg = [t.get("title") if isinstance(t, dict) else str(t) for t in (x.get("tags") or [])]
        print(f"  {st:34s} | {a.get('city')} | owner={(o.get('first_name') or '')} "
              f"{(o.get('last_name') or '')} | uuid={x.get('uuid') or x.get('id')}")
        print(f"      tags: {', '.join(sorted(tg))}")
