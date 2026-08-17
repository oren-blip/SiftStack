"""DP 26E002931-590 step 3: resolve twins Chase + Chandler Thompson (b. ~2001, Canton GA).

Court: Chase = PR, Chandler = DM2. Obit: identical twins of Canton GA (Kennesaw
State). Graph: Chandler Roe Thompson b. 7/2001; decedent addresses include
4163 Gold Mill Rdg + 249 River Green Ave, Canton GA 30114.
Person Search name+DOB(2001), no state anchor (state anchor can miss - 8/14
gotcha). Disambiguate by Canton/Kennesaw GA or Charlotte NC address overlap.
"""
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

FAMILY_TOKENS = ("canton", "kennesaw", "gold mill", "river green", "charlotte",
                 "mt holly", "huntersville", "woodstock, ga", "marietta")


def show(p):
    n = p.get("name") or {}
    full = " ".join(filter(None, [n.get("firstName"), n.get("middleName"), n.get("lastName")]))
    addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])]
    overlap = any(t in " ".join(addrs).lower() for t in FAMILY_TOKENS)
    rels = [" ".join(filter(None, [r.get("firstName"), r.get("middleName"), r.get("lastName")]))
            for r in (p.get("relativesSummary") or [])]
    fam = [r for r in rels if any(t in r.lower() for t in
           ("chase", "chandler", "heather", "nancy", "john", "jennifer", "matthew"))]
    print(f"  cand: {full}  age={p.get('age')}  dob={p.get('dob')}  familyaddr={overlap}")
    for a in addrs[:4]:
        print(f"        addr: {a}")
    for ph in (p.get("phoneNumbers") or [])[:8]:
        print(f"        phone: {ph.get('phoneNumber')} {ph.get('phoneType')} connected={ph.get('isConnected')}")
    for e in (p.get("emailAddresses") or [])[:5]:
        em = e.get("emailAddress") if isinstance(e, dict) else e
        print(f"        email: {em}")
    if fam:
        print(f"        family-rels: {', '.join(fam[:8])}")
    return overlap or bool(fam)


def main():
    keep = []
    for first in ("Chase", "Chandler"):
        body = {"FirstName": first, "LastName": "Thompson", "Dob": "2001"}
        resp = requests.post(URL, headers=HEADERS, json=body, timeout=60)
        print(f"# {first} Thompson Dob=2001 -> HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(resp.text[:300])
            continue
        persons = resp.json().get("persons") or []
        print(f"  {len(persons)} candidates")
        for p in persons:
            if show(p):
                keep.append(p)
    out = os.path.join(ROOT, "output", "reports", "dp_thompson_twins_20260817.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1, default=str)
    print(f"\nkept {len(keep)} -> {out}")


if __name__ == "__main__":
    main()
