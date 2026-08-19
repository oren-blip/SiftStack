"""Scan cached Enformion responses: find the Charlotte William Gregory, and
dump full relative lists / extra matches for overcash + archie."""
import json
import re
from pathlib import Path

CACHE = Path(r"d:\SiftStack\output\dp_enformion_20260819")


def yr(v):
    if isinstance(v, dict):
        v = " ".join(str(x) for x in v.values())
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return m.group(0) if m else "?"


def persons(tag):
    d = json.loads((CACHE / f"{tag}.json").read_text(encoding="utf-8"))
    return d.get("persons") or d.get("people") or []


print("### gregory_william — all matches, Charlotte filter")
for i, p in enumerate(persons("gregory_william")):
    n = p.get("name") or {}
    full = f"{n.get('firstName','')} {n.get('middleName','')} {n.get('lastName','')}".strip()
    addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])]
    blob = " | ".join(addrs)
    hit = ("Mcclure" in blob or "McClure" in blob or "Bonaire" in blob
           or "28208" in blob or "Charlotte" in blob)
    dods = p.get("datesOfDeath") or []
    print(f"[{i}] {full} deceased={p.get('isDeceased')} dod={yr(dods[0] if dods else p.get('dod'))} charlotte_hit={hit}")
    if hit:
        for a in addrs[:6]:
            print("    ", a)

for tag, idx in (("overcash_jessie", 1), ("archie_james", 1)):
    ps = persons(tag)
    if len(ps) <= idx:
        continue
    p = ps[idx]
    n = p.get("name") or {}
    print(f"\n### {tag}[{idx}] {n.get('firstName')} {n.get('middleName')} {n.get('lastName')}"
          f" deceased={p.get('isDeceased')} dod={yr((p.get('datesOfDeath') or [None])[0] or p.get('dod'))}")
    for a in (p.get("addresses") or [])[:6]:
        print("  addr:", a.get("fullAddress"))
    rels = p.get("relativesSummary") or []
    print(f"  relatives ({len(rels)}):")
    for rl in rels:
        ln = f"{rl.get('firstName','')} {rl.get('middleName','')} {rl.get('lastName','')}".strip()
        print(f"    {rl.get('relativeLevel','?'):>2} {rl.get('relativeType') or 'Family':<10} {ln:<32} b.{yr(rl.get('dob'))} dead={rl.get('isDeceased')} score={rl.get('score')}")

# Eboni check in archie match 1's relatives + overcash match 0 full list
for tag in ("archie_james", "overcash_jessie"):
    print(f"\n### {tag}: any Eboni/Dixon/Jordan/Kathryn/Judy across ALL matches")
    for i, p in enumerate(persons(tag)):
        for rl in (p.get("relativesSummary") or []):
            ln = f"{rl.get('firstName','')} {rl.get('middleName','')} {rl.get('lastName','')}"
            if re.search(r"eboni|dixon|jordan|kathryn|judy", ln, re.I):
                print(f"  match[{i}] rel: {rl.get('relativeLevel')} {rl.get('relativeType') or 'Family'} {ln.strip()} b.{yr(rl.get('dob'))} dead={rl.get('isDeceased')} score={rl.get('score')}")
