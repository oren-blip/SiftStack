"""DP 26E002931-590 step 2: decedent-side Enformion search + free obituary search.

Looking for John Patrick Thompson (DOD 2023-03-17, Mecklenburg) whose relatives
include sons Chase and/or Chandler. Also Serper obit search (free tier of our
existing key) to ground the family before any more paid person searches.
"""
import json
import os
import re

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


def dod_text(p):
    parts = []
    if p.get("dod"):
        parts.append(str(p["dod"]))
    for d in p.get("datesOfDeath") or []:
        parts.append(str(d))
    return " ".join(parts)


def enformion_decedent():
    body = {"FirstName": "John", "MiddleName": "Patrick", "LastName": "Thompson",
            "Addresses": [{"AddressLine2": "Charlotte, NC"}]}
    resp = requests.post(URL, headers=HEADERS, json=body, timeout=60)
    print(f"# decedent search -> HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:300])
        return
    persons = resp.json().get("persons") or []
    print(f"  {len(persons)} candidates")
    keep = []
    for p in persons:
        n = p.get("name") or {}
        full = " ".join(filter(None, [n.get("firstName"), n.get("middleName"), n.get("lastName")]))
        dod = dod_text(p)
        rels = [(rel_name(r), r.get("relativeLevel"), bool(r.get("isDeceased")), r.get("dob"))
                for r in (p.get("relativesSummary") or [])]
        relstr = " | ".join(n for n, *_ in rels).lower()
        son_link = ("chase" in relstr) or ("chandler" in relstr)
        deceased = bool(p.get("isDeceased")) or bool(re.search(r"202[2-4]", dod))
        marker = ("SON-LINK " if son_link else "") + ("DECEASED" if deceased else "")
        print(f"  cand: {full}  age={p.get('age')}  dod={dod or '-'}  {marker}")
        for a in (p.get("addresses") or [])[:3]:
            print(f"        addr: {a.get('fullAddress')}")
        if son_link or deceased:
            keep.append(p)
            for nm, lvl, dec, dob in rels:
                print(f"        rel({lvl},{'DEC' if dec else 'liv'},{dob}): {nm}")
    out = os.path.join(ROOT, "output", "reports", "dp_thompson_decedent_20260817.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=1, default=str)
    print(f"  kept {len(keep)} -> {out}")


def serper_obit():
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        print("# no SERPER_API_KEY")
        return
    for q in ('"John Patrick Thompson" obituary Charlotte NC 2023',
              '"John Patrick Thompson" obituary "Chase" OR "Chandler"'):
        resp = requests.post("https://google.serper.dev/search",
                             headers={"X-API-KEY": key, "Content-Type": "application/json"},
                             json={"q": q, "num": 10}, timeout=30)
        print(f"# serper {q!r} -> HTTP {resp.status_code}")
        if resp.status_code != 200:
            continue
        for item in (resp.json().get("organic") or [])[:8]:
            print(f"  {item.get('title')}\n    {item.get('link')}\n    {item.get('snippet','')[:200]}")


if __name__ == "__main__":
    serper_obit()
    enformion_decedent()
