"""READ-ONLY: confirm each pass-1 GAP against the record detail endpoint.

The /property/ SEARCH index lags behind writes (Punch 26E000919-170 was renamed
at 12:52 today and still searched as "Heirs Punch" at 13:06), so a GAP verdict
from search alone is not trustworthy. This refetches each UUID directly.
"""
import csv, sys, requests
from pathlib import Path
REPO = Path(r"d:\SiftStack"); sys.path.insert(0, str(REPO))
from audit_rename_gap_20260822 import token

tok = token()
h = {"accept": "application/json", "origin": "https://app.reisift.io",
     "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
     "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
     "content-type": "application/json"}

gaps = [r for r in csv.DictReader(
    open(REPO / "output" / "dp_resolved_heirs_audit_20260822.csv", encoding="utf-8-sig"))
    if r["Status"] == "GAP"]

out, real = [], []
for g in gaps:
    u = g["UUID"]
    r = requests.get(f"https://apiv2.reisift.io/api/internal/property/{u}/",
                     headers=h, timeout=30)
    if r.status_code != 200:
        print(f"{g['Case No.']:20s} HTTP {r.status_code}")
        continue
    d = r.json(); d = d.get("data") or d.get("result") or d
    o = d.get("owner") or {}
    fn = (o.get("first_name") or "").strip(); ln = (o.get("last_name") or "").strip()
    live = f"{fn} {ln}".strip()
    tags = sorted(t.get("title") if isinstance(t, dict) else str(t) for t in (d.get("tags") or []))
    still = fn.lower().startswith(("heir", "estate"))
    mail = " / ".join(x for x in [o.get("mailing_street"), o.get("mailing_city"),
                                  o.get("mailing_state"), o.get("mailing_zip")] if x) or "(blank)"
    flag = "STILL HEIRS" if still else "OK - renamed"
    spouse = "Surviving Spouse" in tags
    print(f"{g['Case No.']:20s} {flag:12s} live={live!r:34s} want={g['Wanted Owner'] or '?'!r:22s}"
          f" {'[SurvSpouse]' if spouse else ''} {'[DPComplete]' if 'DP Complete' in tags else ''}")
    print(f"    mailing: {mail}")
    print(f"    tags   : {', '.join(tags)}")
    out.append({**g, "Live Owner (detail)": live, "Confirmed": flag,
                "Owner Mailing": mail, "Surviving Spouse tag": "yes" if spouse else "no",
                "All Tags": "; ".join(tags)})
    if still:
        real.append(out[-1])

p = REPO / "output" / "dp_gap_confirmed_20260822.csv"
with p.open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print(f"\nCONFIRMED still-Heirs: {len(real)} of {len(gaps)} search-flagged")
for r in real:
    print(f"  {r['Case No.']:20s} {r['Live Owner (detail)']!r} -> {r['Wanted Owner'] or '?'!r}"
          f"   {r['Property']}   spouse={r['Surviving Spouse tag']}")
print(f"wrote {p}")
