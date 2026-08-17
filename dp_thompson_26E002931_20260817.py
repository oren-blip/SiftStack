"""DP run 2026-08-17 - case 26E002931-590 (Thompson, Mecklenburg Week 32).

Court facts: decedent John Patrick Thompson (DOD 03/17/2023 per application),
PR Chase Thompson (son), DM2 Chandler Thompson (son). Estate parcels:
0 Mt Holly-Huntersville Rd 28216 (lot), 9720 Southampton Commons Dr 28277,
6721 Bevington Brook Ln 28277.

Step: list ALL Enformion candidates for Chase + Chandler Thompson (Charlotte NC,
then no-state retry per the 8/14 gotcha) and cross-identify via relatives:
right person's graph should contain the brother and/or deceased father John.
Prints candidate summaries only; full JSON saved for the chosen ones.
"""
import json
import os
import re
import sys

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


def rel_name(r):
    return " ".join(filter(None, [r.get("firstName"), r.get("middleName"), r.get("lastName")]))


def candidates(first, last, addr2=None):
    body = {"FirstName": first, "LastName": last}
    if addr2:
        body["Addresses"] = [{"AddressLine2": addr2}]
    resp = requests.post(URL, headers=HEADERS, json=body, timeout=60)
    print(f"# search {first} {last} anchor={addr2!r} -> HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:300])
        return []
    return resp.json().get("persons") or []


def brief(p):
    name = p.get("name") or {}
    full = " ".join(filter(None, [name.get("firstName"), name.get("middleName"), name.get("lastName")])) or "?"
    age = p.get("age")
    addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])[:3]]
    rels = [(rel_name(r), r.get("relativeLevel"), "DEC" if r.get("isDeceased") else "liv")
            for r in (p.get("relativesSummary") or [])]
    flag = ""
    relnames = " | ".join(n for n, _, _ in rels).lower()
    if "chandler" in relnames or "chase" in relnames:
        flag += " [BROTHER-LINK]"
    if re.search(r"john\b.*thompson", relnames):
        flag += " [JOHN-LINK]"
    print(f"  cand: {full}  age={age}{flag}")
    for a in addrs:
        print(f"        addr: {a}")
    for n, lvl, st in rels[:12]:
        print(f"        rel({lvl},{st}): {n}")
    return flag


def main():
    picked = []
    for first in ("Chase", "Chandler"):
        found = []
        for anchor in ("Charlotte, NC", None):
            persons = candidates(first, "Thompson", anchor)
            print(f"  -> {len(persons)} candidates")
            for p in persons:
                flag = brief(p)
                if flag:
                    found.append(p)
            if found:
                break
        picked.extend(found)
    out = os.path.join(ROOT, "output", "reports", "dp_thompson_candidates_20260817.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(picked, fh, indent=1, default=str)
    print(f"\nflagged candidates saved: {len(picked)} -> {out}")


if __name__ == "__main__":
    main()
