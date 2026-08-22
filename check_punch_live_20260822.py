"""READ-ONLY: fetch the Punch record straight by UUID, not via search."""
import json, sys, requests
from pathlib import Path
REPO = Path(r"d:\SiftStack"); sys.path.insert(0, str(REPO))
from audit_rename_gap_20260822 import token, search
tok = token()
h = {"accept": "application/json", "origin": "https://app.reisift.io",
     "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
     "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
     "content-type": "application/json"}
UUID = "dbe5c215-c295-4cfd-b50b-4d693a236aa7"
for path in (f"/api/internal/property/{UUID}/", f"/api/internal/property/{UUID}"):
    r = requests.get(f"https://apiv2.reisift.io{path}", headers=h, timeout=30)
    print(path, r.status_code)
    if r.status_code == 200:
        d = r.json()
        d = d.get("data") or d.get("result") or d
        o = d.get("owner") or {}
        a = d.get("address") or {}
        print("  owner:", json.dumps({k: o.get(k) for k in
              ("first_name","last_name","mailing_street","mailing_city","mailing_state","mailing_zip")}, indent=2))
        print("  addr :", a.get("street"), "|", a.get("city"), a.get("state"), a.get("zip"))
        tags = [t.get("title") if isinstance(t, dict) else str(t) for t in (d.get("tags") or [])]
        print("  tags :", ", ".join(sorted(tags)))
        ph = d.get("phones") or d.get("phone_numbers") or []
        print("  phones:", len(ph))
        break
print("\n--- fresh search for '994 22Nd' ---")
for x in search(h, "994 22Nd St Pl Ne"):
    o = x.get("owner") or {}; a = x.get("address") or {}
    print(" ", (o.get("first_name") or "") , (o.get("last_name") or ""), "@", a.get("street"), "|", x.get("uuid") or x.get("id"))
