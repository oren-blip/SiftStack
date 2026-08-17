"""DP 26E002931-590 step 4: resolve PR William Chase Thompson (b.2001) + mother
Heather Roe Thompson (b.1969), Canton GA household (122 Gold Bridge Xing)."""
import json
import os

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

HEADERS = {
    "galaxy-ap-name": os.environ["ENFORMION_AP_NAME"],
    "galaxy-ap-password": os.environ["ENFORMION_AP_PASSWORD"],
    "galaxy-search-type": "Person",
    "Content-Type": "application/json",
}
URL = "https://devapi.enformion.com/PersonSearch"

SEARCHES = [
    {"FirstName": "William", "MiddleName": "Chase", "LastName": "Thompson", "Dob": "2001"},
    {"FirstName": "Heather", "MiddleName": "Roe", "LastName": "Thompson", "Dob": "1969"},
]


def main():
    keep = []
    for body in SEARCHES:
        resp = requests.post(URL, headers=HEADERS, json=body, timeout=60)
        label = f"{body['FirstName']} {body.get('MiddleName','')} {body['LastName']} {body['Dob']}"
        print(f"# {label} -> HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text[:300])
            continue
        persons = resp.json().get("persons") or []
        print(f"  {len(persons)} candidates")
        for p in persons:
            n = p.get("name") or {}
            full = " ".join(filter(None, [n.get("firstName"), n.get("middleName"), n.get("lastName")]))
            addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])]
            blob = " ".join(addrs).lower()
            family = any(t in blob for t in ("canton", "gold bridge", "gold mill", "river green",
                                             "charlotte", "huntersville", "woodstock"))
            print(f"  cand: {full}  age={p.get('age')}  familyaddr={family}")
            for a in addrs[:5]:
                print(f"        addr: {a}")
            for ph in (p.get("phoneNumbers") or [])[:8]:
                print(f"        phone: {ph.get('phoneNumber')} {ph.get('phoneType')} conn={ph.get('isConnected')}")
            for e in (p.get("emailAddresses") or [])[:5]:
                em = e.get("emailAddress") if isinstance(e, dict) else e
                print(f"        email: {em}")
            rels = [" ".join(filter(None, [r.get("firstName"), r.get("middleName"), r.get("lastName")]))
                    for r in (p.get("relativesSummary") or [])]
            fam_rels = [r for r in rels if any(t in r.lower() for t in ("chandler", "chase", "heather", "john"))]
            if fam_rels:
                print(f"        family-rels: {', '.join(fam_rels[:6])}")
            if family or fam_rels:
                keep.append(p)
    out = os.path.join(ROOT, "output", "reports", "dp_thompson_pr_20260817.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1, default=str)
    print(f"\nkept {len(keep)} -> {out}")


if __name__ == "__main__":
    main()
