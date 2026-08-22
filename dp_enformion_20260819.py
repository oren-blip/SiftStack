"""DP 2026-08-19: Enformion Person Search (Step A) on the approved heirs-of
records. READ-ONLY research — no DataSift writes. Responses cached to
output/dp_enformion_20260819/ so re-runs don't re-bill (billed per match).

Targets (Oren approved 8/19):
  Gregory  26E002891-590  William A Gregory    8518 McClure Cr Charlotte 28208
  Adams    26E002995-590  Boyd Clifford Adams  1825 Rice Planters Rd Charlotte 28273
  Dunlap   26E003003-590  Query Russell Dunlap 1912 Wilmore Dr Charlotte 28203
  Zion     26E002962-590  Kenneth Gene Zion    832 Stratfordshire Dr Matthews 28105
  Overcash (DataFlik)     Jessie Overcash      1250 Chow Dr China Grove 28023
  Archie   (DataFlik)     James Archie         Salisbury (heir Eboni Archie)
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, r"d:\SiftStack")
try:
    from dotenv import load_dotenv
    load_dotenv(r"d:\SiftStack\.env")
except Exception:
    pass

CACHE = Path(r"d:\SiftStack\output\dp_enformion_20260819")
CACHE.mkdir(exist_ok=True)

HDRS = {
    "galaxy-ap-name": os.environ["ENFORMION_AP_NAME"],
    "galaxy-ap-password": os.environ["ENFORMION_AP_PASSWORD"],
    "galaxy-search-type": "Person",
    "content-type": "application/json",
}


def person_search(tag: str, body: dict) -> dict:
    """POST PersonSearch, disk-cached by tag. Failure = HTTP status, never
    the always-present `error` object."""
    f = CACHE / f"{tag}.json"
    if f.exists():
        print(f"  [{tag}] cache hit")
        return json.loads(f.read_text(encoding="utf-8"))
    r = requests.post("https://devapi.enformion.com/PersonSearch",
                      headers=HDRS, json=body, timeout=60)
    print(f"  [{tag}] HTTP {r.status_code}")
    if r.status_code != 200:
        print("   ", r.text[:300])
        return {}
    data = r.json()
    f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def year_of(v) -> str:
    """Recover a year from masked/partial/dict-shaped date fields."""
    if isinstance(v, dict):
        v = " ".join(str(x) for x in v.values())
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return m.group(0) if m else "?"


def show(tag: str, data: dict) -> None:
    people = data.get("persons") or data.get("people") or []
    print(f"===== {tag}: {len(people)} match(es)")
    for i, p in enumerate(people[:3]):
        name = p.get("name") or {}
        full = f"{name.get('firstName','')} {name.get('middleName','')} {name.get('lastName','')}"
        dob = year_of(p.get("dob") or p.get("dateOfBirth"))
        dods = p.get("datesOfDeath") or ([] if not p.get("dod") else [p.get("dod")])
        dod = year_of(dods[0] if dods else p.get("dod"))
        dead = p.get("isDeceased")
        print(f" [{i}] {full.strip()}  b.{dob}  deceased={dead} dod~{dod}")
        for a in (p.get("addresses") or [])[:4]:
            print(f"     addr: {a.get('fullAddress')}")
        for ph in (p.get("phoneNumbers") or [])[:8]:
            print(f"     phone: {ph.get('phoneNumber')} {ph.get('phoneType')} connected={ph.get('isConnected')} latest={ph.get('latestDate','')}")
        rels = p.get("relativesSummary") or []
        print(f"     relatives ({len(rels)}):")
        for rl in rels:
            ln = f"{rl.get('firstName','')} {rl.get('middleName','')} {rl.get('lastName','')}"
            print(f"       {rl.get('relativeLevel','?'):>2} {rl.get('relativeType') or 'Family':<10} {ln.strip():<32} b.{year_of(rl.get('dob'))} dead={rl.get('isDeceased')} score={rl.get('score')}")


SEARCHES = {
    "gregory_william": {"FirstName": "William", "LastName": "Gregory",
                        "Addresses": [{"AddressLine2": "Charlotte, NC 28208"}]},
    "adams_boyd": {"FirstName": "Boyd", "LastName": "Adams",
                   "Addresses": [{"AddressLine2": "Charlotte, NC 28273"}]},
    "dunlap_query": {"FirstName": "Query", "LastName": "Dunlap",
                     "Addresses": [{"AddressLine2": "Charlotte, NC 28203"}]},
    "zion_kenneth": {"FirstName": "Kenneth", "LastName": "Zion",
                     "Addresses": [{"AddressLine2": "Matthews, NC 28105"}]},
    "overcash_jessie": {"FirstName": "Jessie", "LastName": "Overcash",
                        "Addresses": [{"AddressLine2": "China Grove, NC 28023"}]},
    "archie_james": {"FirstName": "James", "LastName": "Archie",
                     "Addresses": [{"AddressLine2": "Salisbury, NC 28146"}]},
    # ── wave 2: street-anchored Gregory retry + signers + tax-contact heirs ──
    "gregory_bonaire": {"FirstName": "William", "LastName": "Gregory",
                        "Addresses": [{"AddressLine1": "3306 Bonaire Dr",
                                       "AddressLine2": "Charlotte, NC 28208"}]},
    "gregory_mcclure": {"FirstName": "William", "LastName": "Gregory",
                        "Addresses": [{"AddressLine1": "8518 Mcclure Cr",
                                       "AddressLine2": "Charlotte, NC 28208"}]},
    "adams_spouse_marianne": {"FirstName": "Marianne", "LastName": "Wagnon", "Dob": "1958"},
    "adams_son_john": {"FirstName": "John", "MiddleName": "Taylor", "LastName": "Adams", "Dob": "1986"},
    "dunlap_stephen": {"FirstName": "Stephen", "LastName": "Dunlap", "Dob": "1969"},
    "dunlap_judy": {"FirstName": "Judy", "LastName": "Dunlap", "Dob": "1950"},
    "zion_christopher": {"FirstName": "Christopher", "LastName": "Zion", "Dob": "1973"},
    "overcash_kathryn_dixon": {"FirstName": "Kathryn", "LastName": "Dixon",
                               "Addresses": [{"AddressLine1": "122 Brewer Ln",
                                              "AddressLine2": "China Grove, NC 28023"}]},
    "overcash_judy_jordan": {"FirstName": "Judy", "LastName": "Jordan",
                             "Addresses": [{"AddressLine1": "122 Brewer Ln",
                                            "AddressLine2": "China Grove, NC 28023"}]},
    "archie_eboni": {"FirstName": "Eboni", "LastName": "Archie",
                     "Addresses": [{"AddressLine1": "1300 Old Concord Rd",
                                    "AddressLine2": "Salisbury, NC 28146"}]},
    # ── wave 3 ──
    "gregory_son_michael": {"FirstName": "Michael", "MiddleName": "Kyle",
                            "LastName": "Gregory", "Dob": "1988"},
    "overcash_judy_jordan2": {"FirstName": "Judy", "LastName": "Jordan",
                              "Addresses": [{"AddressLine2": "China Grove, NC"}]},
    # ── wave 4: obit-confirmed signers ──
    "dunlap_aretha": {"FirstName": "Aretha", "LastName": "Dunlap", "Dob": "1978"},
    "overcash_timothy": {"FirstName": "Timothy", "MiddleName": "Dale",
                         "LastName": "Overcash", "Dob": "1956"},
    # ── wave 5 (8/19 PM): the 3 Verify-No-PR-Address records Oren approved ──
    "scearce_danny": {"FirstName": "Danny", "LastName": "Scearce",
                      "Addresses": [{"AddressLine1": "220 Neel Rd",
                                     "AddressLine2": "Salisbury, NC 28147"}]},
    "scearce_cheryl": {"FirstName": "Cheryl", "LastName": "Scearce",
                       "Addresses": [{"AddressLine2": "Salisbury, NC 28147"}]},
    "keener_barbara": {"FirstName": "Barbara", "LastName": "Keener",
                       "Addresses": [{"AddressLine1": "7050 Martin Mill Rd",
                                      "AddressLine2": "Hickory, NC 28602"}]},
    "courteau_robert": {"FirstName": "Robert", "LastName": "Courteau",
                        "Addresses": [{"AddressLine1": "536 Kiser Rd",
                                       "AddressLine2": "Bessemer City, NC 28016"}]},
    "keener_son_jeffrey": {"FirstName": "Jeffrey", "LastName": "Lawson", "Dob": "1974"},
    "courteau_son_everette": {"FirstName": "Everette", "LastName": "Courteau", "Dob": "1966"},
    "courteau_son_robertc": {"FirstName": "Robert", "MiddleName": "Clinton",
                             "LastName": "Courteau", "Dob": "1968"},
}

if __name__ == "__main__":
    only = sys.argv[1:] or list(SEARCHES)
    for tag in only:
        data = person_search(tag, SEARCHES[tag])
        show(tag, data)
