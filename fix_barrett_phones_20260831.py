"""One-off: 3627 Cedar Springs Dr SW, Concord (Case 26E000195-120, Cabarrus).

Heir transfer 8/2026 -> Steven J Barrett now owns and occupies the house.
Enformion (8/31, $0.35) confirmed him at the property and returned two numbers
we did not have; Trestle scored 7042455901 = 100 (Dial First).

This script:
  * keeps Steven's three 704 numbers already on the record
  * adds 7042455901 (Mobile, Dial First) + 7812455901 (Landline, Dial Fourth)
  * drops the five Eileen Barrett (Townsend, MA) numbers from the 8/20 Tracerfy
    trace - all Dial Fourth, all marked DEAD, and not the signer
  * verifies by re-GET (a 200 that didn't stick is the known failure mode)

Dry-run by default; --apply writes. Backup of the pre-change record:
output/backup_1cfd5af2_20260831.json
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent / "src"))
from trestle_api_backfill import API, get_token, headers  # noqa: E402

UUID = "1cfd5af2-400a-484b-9053-c9b6bbaad2a7"
DROP = {"9785972004", "9788400061", "6037442024", "9784072152", "5088400061"}
ADD = [
    {"number": "7042455901", "type": "MOBILE", "tags": ["Dial First"],
     "status": None, "is_connected": None},
    {"number": "7812455901", "type": "LANDLINE", "tags": ["Dial Fourth"],
     "status": None, "is_connected": None},
]


def main() -> int:
    apply = "--apply" in sys.argv
    h = headers(get_token())
    url = f"{API}/api/internal/property/{UUID}/"
    d = requests.get(url, headers=h, timeout=60).json()
    owner = copy.deepcopy(d["owner"])
    have = {p["number"] for p in owner["phones"]}
    keep = [p for p in owner["phones"] if p["number"] not in DROP]
    keep += [p for p in ADD if p["number"] not in have]
    owner["phones"] = keep
    print(f"owner: {owner['first_name']} {owner['last_name']}")
    print(f"before: {sorted(have)}")
    print(f"after : {[(p['number'], p['type'], p['tags']) for p in keep]}")
    if not apply:
        print("dry-run - pass --apply to write")
        return 0

    r = requests.patch(url, headers=h, data=json.dumps({"owner": owner}),
                       timeout=60)
    print(f"PATCH -> {r.status_code}")
    if r.status_code not in (200, 202):
        print(r.text[:300])
        return 1
    live = requests.get(url, headers=h, timeout=60).json()["owner"]
    got = {p["number"]: (p["type"], p.get("tags")) for p in live["phones"]}
    print("LIVE phones:")
    for n, (t, tags) in got.items():
        print(f"   {n} {t} {tags}")
    want = {p["number"] for p in keep}
    missing = want - set(got)
    leftover = set(got) & DROP
    if missing or leftover:
        print(f"MISMATCH missing={sorted(missing)} leftover={sorted(leftover)}")
        return 2
    print("verified: phones match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
