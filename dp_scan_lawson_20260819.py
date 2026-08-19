"""Scan cached keener_son_jeffrey matches for the real Jeffrey S Lawson
(kin of Barbara Keener / Julie Brookshire Lawson / Ted or James Lawson;
or Hickory-Granite Falls NC addresses)."""
import json
import re
from pathlib import Path

CACHE = Path(r"d:\SiftStack\output\dp_enformion_20260819")


def yr(v):
    if isinstance(v, dict):
        v = " ".join(str(x) for x in v.values())
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return m.group(0) if m else "?"


d = json.loads((CACHE / "keener_son_jeffrey.json").read_text(encoding="utf-8"))
for i, p in enumerate(d.get("persons") or []):
    n = p.get("name") or {}
    full = f"{n.get('firstName','')} {n.get('middleName','')} {n.get('lastName','')}".strip()
    addrs = [a.get("fullAddress", "") for a in (p.get("addresses") or [])]
    blob = " | ".join(addrs)
    rels = p.get("relativesSummary") or []
    relblob = " | ".join(f"{r.get('firstName','')} {r.get('lastName','')}" for r in rels)
    markers = []
    if re.search(r"keener", relblob, re.I):
        markers.append("REL:Keener")
    if re.search(r"julie\s+\w*\s*lawson|brookshire", relblob + blob, re.I):
        markers.append("REL:Julie/Brookshire")
    if re.search(r"Hickory|Granite Falls|28602|28630", blob):
        markers.append("ADDR:Hickory")
    if not markers:
        continue
    print(f"[{i}] {full}  markers={markers}")
    for a in addrs[:5]:
        print("   addr:", a)
    for ph in (p.get("phoneNumbers") or [])[:6]:
        print(f"   phone: {ph.get('phoneNumber')} {ph.get('phoneType')} connected={ph.get('isConnected')}")
    for r in rels:
        ln = f"{r.get('firstName','')} {r.get('middleName','')} {r.get('lastName','')}".strip()
        if re.search(r"keener|lawson|brookshire", ln, re.I):
            print(f"   rel: {r.get('relativeLevel')} {r.get('relativeType') or 'Family'} {ln} b.{yr(r.get('dob'))} dead={r.get('isDeceased')} score={r.get('score')}")
