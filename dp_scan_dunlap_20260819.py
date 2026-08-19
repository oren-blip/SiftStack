"""Scan cached dunlap_stephen / dunlap_judy matches for the real Charlotte
signers (relatives include Query / Frances / each other; or Charlotte or
Richmond VA addresses — caller-tagged phone (804) 939-1120 is Richmond)."""
import json
import re
from pathlib import Path

CACHE = Path(r"d:\SiftStack\output\dp_enformion_20260819")


def yr(v):
    if isinstance(v, dict):
        v = " ".join(str(x) for x in v.values())
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return m.group(0) if m else "?"


for tag in ("dunlap_stephen", "dunlap_judy"):
    d = json.loads((CACHE / f"{tag}.json").read_text(encoding="utf-8"))
    people = d.get("persons") or d.get("people") or []
    print(f"### {tag}: {len(people)} matches")
    for i, p in enumerate(people):
        n = p.get("name") or {}
        full = f"{n.get('firstName','')} {n.get('middleName','')} {n.get('lastName','')}".strip()
        addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])]
        blob = " | ".join(addrs)
        rels = p.get("relativesSummary") or []
        relnames = " | ".join(
            f"{r.get('firstName','')} {r.get('middleName','')} {r.get('lastName','')}" for r in rels)
        markers = []
        if re.search(r"query|frances", relnames, re.I):
            markers.append("REL:Query/Frances")
        if re.search(r"judy\s+\w*\s*dunlap", relnames, re.I) and "judy" not in tag:
            markers.append("REL:Judy")
        if re.search(r"stephen\s+\w*\s*dunlap", relnames, re.I) and "stephen" not in tag:
            markers.append("REL:Stephen")
        if "Charlotte" in blob:
            markers.append("ADDR:Charlotte")
        if re.search(r"Richmond|VA 23", blob):
            markers.append("ADDR:RichmondVA")
        if not markers:
            continue
        print(f" [{i}] {full}  markers={markers}")
        for a in addrs[:5]:
            print("     addr:", a)
        for ph in (p.get("phoneNumbers") or [])[:6]:
            print(f"     phone: {ph.get('phoneNumber')} {ph.get('phoneType')} connected={ph.get('isConnected')}")
        for r in rels:
            ln = f"{r.get('firstName','')} {r.get('middleName','')} {r.get('lastName','')}".strip()
            if re.search(r"dunlap|query|frances", ln, re.I):
                print(f"     rel: {r.get('relativeLevel')} {r.get('relativeType') or 'Family'} {ln} b.{yr(r.get('dob'))} dead={r.get('isDeceased')} score={r.get('score')}")
