"""Enformion accuracy test — 3 hard cases + 2 known-answer cases.

Oren approved 2026-08-13. Free plan: only MATCHES count vs the 100/mo quota,
misses are free. Expected cost: <= 5 matches. Prints the full useful payload
(phones, addresses, relativesSummary heir graph) — read-only, no cache writes,
nothing written back to DataSift or the workbook.

MUST RUN FROM A US IP (the home desktop): Enformion geo-blocks foreign
client IPs with HTTP 444 "Blocked request ... based on location" — hit
2026-08-13 from the traveling laptop. Blocked calls use no quota.
"""
from __future__ import annotations

import json
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_REPO, "src"))
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(_REPO, ".env"))

URL = "https://devapi.enformion.com/PersonSearch"

TESTS = [
    # (label, first, last, city, state, zip, what we already know)
    ("HARD Mahaffey 26E000808-790", "Phillip", "Mahaffey", "Salisbury", "NC", "28146",
     "PR unlocatable by our waterfall; known DM2 Dale Mahaffey, Union Grove"),
    ("HARD Brown/Stanley 26E000492-540", "Ashlynn", "Stanley", "Lincolnton", "NC", "28092",
     "PR unlocatable; known DM2 Gary Ray Grahl, Iron Station"),
    ("HARD Shands 26E000811-790 (decedent)", "Sadie", "Shands", "Salisbury", "NC", "28146",
     "No PR on file, no obituary — want the relativesSummary heir graph"),
    ("TRUTH Baker 26E002844-590", "Shirley", "Baker", "Charlotte", "NC", "28269",
     "Known: wife Shirley H. Baker at 6034 Shining Oak Ln, Charlotte 28269"),
    ("TRUTH Preidt/Stone 26E001041-350", "Julia", "Stone", "Angola", "IN", "46703",
     "Known: sister Julia Stone at 180 Lane 201 Crooked Lake, Angola IN 46703"),
]

HEADERS = {
    "galaxy-ap-name": os.environ.get("ENFORMION_AP_NAME", ""),
    "galaxy-ap-password": os.environ.get("ENFORMION_AP_PASSWORD", ""),
    "galaxy-search-type": "Person",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def show_person(p: dict, verbose: bool) -> None:
    nm = p.get("name") or {}
    full = " ".join(x for x in (nm.get("firstName"), nm.get("middleName"),
                                nm.get("lastName")) if x)
    dec = p.get("isDeceased")
    print(f"  MATCH: {full} | age {p.get('age')} | deceased={dec}")
    if not verbose:
        return
    dob = p.get("dob") or p.get("dateOfBirth")
    dod = p.get("dod") or p.get("dateOfDeath")
    if dob or dod:
        print(f"    dob={dob} dod={dod}")
    for a in (p.get("addresses") or [])[:4]:
        if isinstance(a, dict):
            print(f"    addr: {a.get('fullAddress')} "
                  f"(first {a.get('firstReportedDate')}, last {a.get('lastReportedDate')})")
    for ph in (p.get("phoneNumbers") or [])[:6]:
        if isinstance(ph, dict):
            print(f"    phone: {ph.get('phoneNumber')} {ph.get('phoneType')} "
                  f"connected={ph.get('isConnected')} last={ph.get('lastReportedDate')}")
    for e in (p.get("emailAddresses") or [])[:3]:
        if isinstance(e, dict):
            print(f"    email: {e.get('emailAddress')}")
    rels = [r for r in (p.get("relativesSummary") or []) if isinstance(r, dict)]
    rels.sort(key=lambda r: ((r.get("relativeLevel") or "zz"), -(r.get("score") or 0)))
    if rels:
        print(f"    relatives ({len(rels)} total, closest first):")
    for r in rels[:12]:
        rn = " ".join(x for x in (r.get("firstName"), r.get("middleName"),
                                  r.get("lastName")) if x)
        print(f"      [{r.get('relativeLevel')}] {rn} | type={r.get('relativeType') or '?'} "
              f"| score={r.get('score')} | deceased={r.get('isDeceased')}")


def main() -> int:
    if not HEADERS["galaxy-ap-name"]:
        print("ENFORMION_AP_NAME missing from .env")
        return 1
    for label, first, last, city, state, zc, known in TESTS:
        print(f"\n{'=' * 70}\n{label}\n  search: {first} {last} @ {city}, {state} {zc}"
              f"\n  known:  {known}")
        body = {"FirstName": first, "LastName": last,
                "Addresses": [{"AddressLine2": f"{city}, {state} {zc}"}],
                "Page": 1, "ResultsPerPage": 5}
        try:
            r = requests.post(URL, headers=HEADERS, json=body, timeout=45)
        except Exception as e:  # noqa: BLE001
            print(f"  request failed: {e}")
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {r.text[:200]}")
            continue
        resp = r.json()
        persons = (resp.get("persons") or resp.get("people")
                   or resp.get("results") or [])
        counts = resp.get("counts") or {}
        print(f"  persons returned: {len(persons)}"
              + (f" | counts: {json.dumps(counts)[:120]}" if counts else ""))
        if not persons:
            print("  MISS (free — no quota used)")
            continue
        want = last.lower()
        ranked = sorted(
            persons,
            key=lambda p: (((p.get("name") or {}).get("lastName") or "")
                           .strip().split()[-1].lower() == want,
                           zc in json.dumps(p.get("addresses") or [])),
            reverse=True)
        show_person(ranked[0], verbose=True)
        for p in ranked[1:]:
            show_person(p, verbose=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
