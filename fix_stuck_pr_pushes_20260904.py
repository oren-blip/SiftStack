"""Land the two PR corrections that pr_upgrade_step could not push.

2026-09-04. Both cases have a COURT-filed PR and a COURT-filed mailing address
sitting in the Week 36 workbook; neither reached DataSift.

  26E000865-480  1609 Museum Rd, Statesville   Linda Mull -> Delores Wong
      The UI push could not find the record at all ("record not found by
      address"), and its mailing was garbage: the whole address crammed into
      the street line -- "1420 19Th St Sw Hickory Nc 28602" -- under city
      "Statesville", which is not even the right town. That is Linda Mull's
      old data. The court says Delores Wong, 719 Farthing Hayes Rd, Boone.
      Needs BOTH the name and the address.

  26E000862-480  161 Blueview Rd, Mooresville  (already named Diane Bryan)
      Renamed fine, but the mailing stayed on the property -- the pipeline's
      "mail it to the house" fallback, tagged "Verify: No PR Address". The
      court file HAS her address: the Beneficiaries list carries
      "Bryan, Diane E - 183 Castles Gate Dr, Mooresville, NC 28117".
      Needs the address only.

Written as a script, not an inline command, per [[phone-remove-via-owner-patch]].

Safety, same as fix_court_pr_mailing_20260904:
  * addressed by UUID, so a stale search index cannot misroute the write
    ([[project_datasift_search_index_stale]])
  * owner object round-tripped whole -- a trimmed phones array DELETES phones
  * stale lat/long/county dropped so DataSift re-geocodes the new street
  * never writes an empty value over a populated one
    ([[project_pr_upgrade_silent_save_failure]])
  * verified by re-GET, including the phone count -- never trusts the 200

    python fix_stuck_pr_pushes_20260904.py            # dry run
    python fix_stuck_pr_pushes_20260904.py --apply
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, token  # noqa: E402

APPLY = "--apply" in sys.argv

# uuid confirmed by direct GET on 2026-09-04, not by search.
JOBS = [
    {"case": "26E000865-480",
     "uuid": "d80365ee-ac30-45dc-a814-8e2a82713bc0",
     "property": "1609 Museum Rd",
     "first": "Delores", "last": "Wong",
     "street": "719 Farthing Hayes Rd", "city": "Boone",
     "state": "NC", "zip": "28607"},
    {"case": "26E000862-480",
     "uuid": "b32efea4-b189-4042-a776-ae9713b246d1",
     "property": "161 Blueview Rd",
     "first": "Diane", "last": "Bryan",
     "street": "183 Castles Gate Dr", "city": "Mooresville",
     "state": "NC", "zip": "28117"},
]


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
         "x-reisift-ui-version": "2022.02.01.7",
         "authorization": "Bearer " + tok, "content-type": "application/json"}

    fixed = failed = 0
    for j in JOBS:
        print(f"\n=== {j['case']}  ({j['property']})")
        r = requests.get(f"{API}/api/internal/property/{j['uuid']}/", headers=h, timeout=30)
        if r.status_code != 200:
            print(f"  GET HTTP {r.status_code} — skipped")
            failed += 1
            continue
        d = r.json()
        d = d.get("data", d)
        owner = d.get("owner") or {}
        cur = owner.get("address") or {}
        name_before = " ".join(filter(None, [owner.get("first_name") or "",
                                             owner.get("last_name") or ""])).strip()
        phones_before = len(owner.get("phones") or [])
        print(f"  name    : {name_before!r} -> {j['first']} {j['last']}")
        print(f"  mailing : {cur.get('street')!r}, {cur.get('city')!r}"
              f"  ->  {j['street']}, {j['city']} {j['state']} {j['zip']}")
        print(f"  phones  : {phones_before}")

        new_owner = copy.deepcopy(owner)
        new_owner["first_name"] = j["first"]
        new_owner["last_name"] = j["last"]
        addr = dict(cur)
        addr.update({"street": j["street"], "city": j["city"],
                     "state": j["state"], "postal_code": j["zip"]})
        for k in ("latitude", "longitude", "county"):
            addr.pop(k, None)
        new_owner["address"] = addr

        if not APPLY:
            print("  DRY: would PATCH owner name + address")
            fixed += 1
            continue

        resp = requests.patch(f"{API}/api/internal/property/{j['uuid']}/", headers=h,
                              data=json.dumps({"owner": new_owner}), timeout=30)
        print(f"  PATCH -> HTTP {resp.status_code}")

        v = requests.get(f"{API}/api/internal/property/{j['uuid']}/", headers=h, timeout=30).json()
        v = v.get("data", v)
        vo = v.get("owner") or {}
        va = vo.get("address") or {}
        got_name = " ".join(filter(None, [vo.get("first_name") or "",
                                          vo.get("last_name") or ""])).strip()
        phones_after = len(vo.get("phones") or [])
        print(f"  verify  : {got_name!r} @ {va.get('street')!r}, {va.get('city')!r}"
              f"   phones {phones_before} -> {phones_after}")

        ok_name = got_name.lower() == f"{j['first']} {j['last']}".lower()
        ok_addr = (va.get("street") or "").lower() == j["street"].lower()
        if not ok_name:
            print("  *** VERIFY FAILED: name did not change")
            failed += 1
        elif not ok_addr:
            print("  *** VERIFY FAILED: mailing did not change")
            failed += 1
        elif phones_after != phones_before:
            print("  *** WARNING: phone count changed")
            failed += 1
        else:
            fixed += 1

    print(f"\n{'would fix' if not APPLY else 'fixed'}: {fixed}   failed: {failed}")
    if not APPLY:
        print("DRY RUN — re-run with --apply.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
