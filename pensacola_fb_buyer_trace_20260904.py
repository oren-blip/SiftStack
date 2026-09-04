"""Trace the top Facebook-harvested Pensacola buyers for phones + a home address (2026-09-04).

Oren's go (9/4 ~02:45): "trace the top 20" at ~$0.35/Enformion hit + Trestle scoring.

Targets come from output/pensacola_fb_cash_buyers_2026-09-04.csv: buyer-side classes,
no phone in their own words, not a company inbox, ranked by score (email holders first
because an email is an identity anchor). Search order per person:
  1. Enformion PersonSearch by EMAIL (+ name)  -> accept when the returned record carries
     that email, or the surname matches.
  2. Otherwise by name anchored to "Pensacola, FL" -> accept only if the surname matches
     AND the address history touches the Pensacola area (a same-named stranger elsewhere
     must not get on the sheet).
Every number is Trestle-scored (cache first). Results land back in the SAME CSV as
Phones / Phone Tiers / Traced Address / Trace Note, plus a JSON audit file.
Hard spend ceiling: $8.00 Enformion this run. Nothing touches DataSift.

    .venv\\Scripts\\python.exe pensacola_fb_buyer_trace_20260904.py --dry-run   # targets + cost, $0
    .venv\\Scripts\\python.exe pensacola_fb_buyer_trace_20260904.py             # do it
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from phone_validator import clean_phone, process_phones  # noqa: E402

CSV_PATH = REPO / "output" / "pensacola_fb_cash_buyers_2026-09-04.csv"
AUDIT_PATH = REPO / "output" / "pensacola_fb_buyer_trace_2026-09-04.json"
CACHE_PATH = REPO / "output" / ".trestle_score_cache.json"
ENF_CACHE = REPO / "output" / ".fb_buyer_enformion_20260904.json"

PERSON_SEARCH_URL = "https://devapi.enformion.com/PersonSearch"
COST_PER_MATCH = 0.35
MAX_SPEND = 8.00
N_TARGETS = 20
BUYER_CLASSES = ("CASH BUYER", "BUYER who also wholesales", "DEAL RESPONDER (asked about a deal)")
AREA = ("pensacola", "milton", "pace", "cantonment", "gulf breeze", "navarre", "pensacola beach",
        "escambia", "santa rosa", "ferry pass", "brent", "bellview", "warrington", "myrtle grove")
PAGE_LIKE = re.compile(r"(cash buyers|lawncare|handy|contracting|realty|properties|homes|llc|group|solutions|services|"
                       r"buyers|investments|company|inc\b)", re.I)
DRY = "--dry-run" in sys.argv
_spend = 0.0


def hdrs() -> dict:
    return {"galaxy-ap-name": os.environ["ENFORMION_AP_NAME"],
            "galaxy-ap-password": os.environ["ENFORMION_AP_PASSWORD"],
            "galaxy-search-type": "Person", "Content-Type": "application/json",
            "Accept": "application/json"}


def load_enf_cache() -> dict:
    try:
        return json.loads(ENF_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_enf_cache(c: dict) -> None:
    ENF_CACHE.write_text(json.dumps(c, indent=1), encoding="utf-8")


def enf_search(body: dict, key: str, cache: dict) -> list[dict]:
    """POST one PersonSearch; returns the persons list. Cached by key; billed only when
    persons come back (a miss is free)."""
    global _spend
    if key in cache:
        return cache[key]
    if _spend + COST_PER_MATCH > MAX_SPEND:
        print("  spend ceiling reached - no more lookups")
        return []
    try:
        r = requests.post(PERSON_SEARCH_URL, headers=hdrs(), json=body, timeout=45)
    except Exception as e:  # noqa: BLE001
        print(f"  request failed: {e}")
        return []
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return []
    try:
        resp = r.json()
    except ValueError:
        return []
    persons = [p for p in (resp.get("persons") or resp.get("people") or resp.get("results") or []) if isinstance(p, dict)]
    if persons:
        _spend += COST_PER_MATCH
    cache[key] = persons
    save_enf_cache(cache)
    return persons


def surname(p: dict) -> str:
    return ((p.get("name") or {}).get("lastName") or "").strip().split()[-1].lower() if (p.get("name") or {}).get("lastName") else ""


def person_emails(p: dict) -> set[str]:
    out = set()
    for e in p.get("emailAddresses") or p.get("emails") or []:
        v = e.get("emailAddress") if isinstance(e, dict) else e
        if v:
            out.add(str(v).strip().lower())
    return out


def addr_blob(p: dict) -> str:
    return " ".join((a.get("fullAddress") or "").lower() for a in (p.get("addresses") or []) if isinstance(a, dict))


def best_address(p: dict) -> dict:
    addrs = [a for a in (p.get("addresses") or []) if isinstance(a, dict) and a.get("fullAddress")]
    if not addrs:
        return {}
    addrs.sort(key=lambda a: (a.get("lastReportedDate") or a.get("lastSeen") or ""), reverse=True)
    # prefer a Pensacola-area address if one exists in the top 3
    for a in addrs[:3]:
        if any(c in (a.get("fullAddress") or "").lower() for c in AREA):
            return a
    return addrs[0]


def phones_of(p: dict) -> list[tuple[str, str, bool]]:
    out, seen = [], set()
    entries = [e for e in (p.get("phoneNumbers") or []) if isinstance(e, dict)]
    entries.sort(key=lambda e: bool(e.get("isConnected")), reverse=True)
    for e in entries:
        d = clean_phone(e.get("phoneNumber") or "")
        if not d or d in seen:
            continue
        seen.add(d)
        out.append((d, (e.get("phoneType") or "").lower(), bool(e.get("isConnected"))))
        if len(out) >= 6:
            break
    return out


def is_deceased(p: dict) -> bool:
    v = p.get("isDeceased")
    return v if isinstance(v, bool) else str(v or "").lower() in ("true", "yes", "1")


def pick_targets(rows: list[dict]) -> list[dict]:
    cands = []
    for r in rows:
        if r["Class"] not in BUYER_CLASSES or r["Phones"].strip():
            continue
        if "company inbox" in r.get("Flags", ""):
            continue
        name = re.sub(r"\s*[-–].*$", "", r["Name"]).strip()      # "Elaijuah Staten - Realtor" -> name only
        toks = name.split()
        if len(toks) < 2 or len(toks) > 4 or re.search(r"\d", name) or PAGE_LIKE.search(name):
            continue
        cands.append((int(bool(r["Emails"])), int(r["Score"]), r))
    cands.sort(key=lambda t: (-t[0], -t[1], t[2]["Name"]))
    return [r for _, _, r in cands[:N_TARGETS]]


def main() -> int:
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig", newline="")))
    targets = pick_targets(rows)
    print(f"{len(targets)} targets (of {sum(1 for r in rows if r['Class'] in BUYER_CLASSES and not r['Phones'])} phone-less buyers):")
    for r in targets:
        print(f"  {r['Score']:>3} {r['Name'][:28]:<28} {r['Emails'][:40]:<40} {r['Class'][:14]}")
    print(f"max Enformion cost ${len(targets) * COST_PER_MATCH:.2f} (ceiling ${MAX_SPEND:.2f}); Trestle ~$0.015/new number")
    if DRY:
        return 0
    if not (os.environ.get("ENFORMION_AP_NAME") and os.environ.get("ENFORMION_AP_PASSWORD")):
        print("ENFORMION creds missing in .env")
        return 2

    cache = load_enf_cache()
    audit = []
    found: dict[str, dict] = {}
    for r in targets:
        name = re.sub(r"\s*[-–].*$", "", r["Name"]).strip()
        toks = name.split()
        first, last = toks[0], toks[-1]
        emails = [e.strip().lower() for e in r["Emails"].split("|") if e.strip()]
        person, how = None, ""
        # 1. email-anchored
        for em in emails:
            persons = enf_search({"FirstName": first, "LastName": last, "Email": em, "Page": 1, "ResultsPerPage": 5},
                                 f"email|{em}", cache)
            for p in persons:
                if em in person_emails(p) or surname(p) == last.lower():
                    person, how = p, f"Enformion by email {em} ({'email on record' if em in person_emails(p) else 'surname match'})"
                    break
            if person:
                break
        # 2. name + Pensacola anchor
        if person is None:
            persons = enf_search({"FirstName": first, "LastName": last,
                                  "Addresses": [{"AddressLine2": "Pensacola, FL"}], "Page": 1, "ResultsPerPage": 5},
                                 f"name|{first.lower()}|{last.lower()}|pensacola", cache)
            cands = [p for p in persons if surname(p) == last.lower() and any(c in addr_blob(p) for c in AREA)]
            if cands:
                person, how = cands[0], "Enformion by name, Pensacola-area address history"
        if person is None:
            print(f"  MISS  {name}")
            audit.append({"name": name, "result": "miss"})
            continue
        if is_deceased(person):
            print(f"  SKIP  {name}: flagged deceased")
            audit.append({"name": name, "result": "deceased"})
            continue
        ph = phones_of(person)
        addr = best_address(person)
        nm = person.get("name") or {}
        found[r["Name"]] = {"how": how, "phones": ph, "address": addr,
                            "matched_name": " ".join(p for p in (nm.get("firstName"), nm.get("lastName")) if p),
                            "emails": sorted(person_emails(person))[:5], "age": person.get("age")}
        print(f"  HIT   {name:<26} {len(ph)} phones  {addr.get('fullAddress', '')[:50]:<50} [{how[:40]}]")
        audit.append({"name": name, "result": "hit", **found[r["Name"]]})
    print(f"Enformion spend this run: ${_spend:.2f}")

    # Trestle scoring, cache first
    tcache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    need = list(dict.fromkeys(d for f in found.values() for d, _, _ in f["phones"] if d not in tcache))
    print(f"Trestle: {sum(len(f['phones']) for f in found.values())} numbers, {len(need)} new (~${len(need) * 0.015:.2f})")
    if need:
        api_key = os.environ.get("TRESTLE_API_KEY", "")
        if not api_key:
            print("No TRESTLE_API_KEY - numbers kept unscored")
        else:
            results, errors = process_phones([(n, clean_phone(n)) for n in need], api_key, add_litigator=True)
            for res in results:
                d = clean_phone(str(res.get("phone_number", "")))
                if d:
                    tcache[d] = {"phone_number": d, "activity_score": str(res.get("activity_score", "")),
                                 "line_type": res.get("line_type", ""), "carrier": res.get("carrier", ""),
                                 "is_valid": str(res.get("is_valid", "")), "is_prepaid": str(res.get("is_prepaid", "")),
                                 "assigned_tag": res.get("assigned_tag", res.get("tier", "")),
                                 "is_litigator_risk": res.get("is_litigator_risk")}
            if errors:
                print(f"  {len(errors)} Trestle errors (kept unscored)")
            CACHE_PATH.write_text(json.dumps(tcache, indent=1))

    tier_rank = {"Dial First": 0, "Dial Second": 1, "Dial Third": 2, "Dial Fourth": 3, "": 4, "Drop": 5, "Litigator - DNC": 6}
    for r in rows:
        f = found.get(r["Name"])
        if not f:
            continue
        scored = []
        for d, ptype, conn in f["phones"]:
            c = tcache.get(d, {})
            tag = c.get("assigned_tag", "") or ""
            if c.get("is_litigator_risk") in (True, "True"):
                tag = "Litigator - DNC"
            scored.append((tier_rank.get(tag, 4), d, tag, c.get("line_type", "") or ptype, c.get("activity_score", "")))
        scored.sort()
        keep = [s for s in scored if s[2] not in ("Drop", "Litigator - DNC")]
        r["Phones"] = " | ".join(f"{d[:3]}-{d[3:6]}-{d[6:]}" for _, d, _, _, _ in keep)
        r["Phone Tiers"] = " | ".join(f"{d[:3]}-{d[3:6]}-{d[6:]} {tag or 'unscored'} ({lt} {sc})".strip() for _, d, tag, lt, sc in scored)
        a = f["address"]
        r["Traced Address"] = a.get("fullAddress", "") if a else ""
        r["Trace Note"] = f"{f['how']}; matched {f['matched_name']}; 2026-09-04"
        if f["emails"]:
            cur = [e.strip().lower() for e in r["Emails"].split("|") if e.strip()]
            for e in f["emails"]:
                if e not in cur and len(cur) < 3:
                    cur.append(e)
            r["Emails"] = " | ".join(cur)
    for r in rows:
        r.setdefault("Phone Tiers", "")
        r.setdefault("Traced Address", "")
        r.setdefault("Trace Note", "")
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    AUDIT_PATH.write_text(json.dumps(audit, indent=1, default=str), encoding="utf-8")
    hits = sum(1 for a in audit if a["result"] == "hit")
    print(f"\n{hits}/{len(targets)} hit; {sum(1 for f in found.values() if f['address'])} with an address; "
          f"CSV updated {CSV_PATH.name}; audit {AUDIT_PATH.name}")
    print(f"TOTAL COST: Enformion ${_spend:.2f} + Trestle ~${len(need) * 0.015:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
