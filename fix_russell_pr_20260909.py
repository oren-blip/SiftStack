"""Push the court's PR onto case 26E001831-590 by UUID.

2026-09-09. `pr_upgrade_step.py --queued` reported
"26E001831-590: record not found by address '4205 Olde Roxbury Dr'" and applied
0/1. The record exists -- there are TWO of them at that address:

  A b5f0c104-309a-44e4-942a-e7d52e85bf12  owner William Russell, 3 phones,
                                          tags Courthouse Data / DP Complete /
                                          NC Upload 2026-08-20
  B 0762c5f3-e856-44e0-8119-781074f963b9  EMPTY shell -- no owner, no phones --
                                          but it carries "NC Estates Week 21 2026"

pr_upgrade_step filters the export by the week tag, which only B has, and B has
no owner to match -- hence "not found". So this targets A by UUID directly,
which is the documented workaround when record search misses
([[project_attach_dp_reports_uuid_fallback]],
[[project_datasift_owner_is_shared_entity]]: resolve uuids over the API, never
the UI search).

Court record (workbook Week 21, verified against the consolidated workbook):
  Deceased      RUSSELL, HELON
  PR            PAMELA RUSSELL   (also a listed beneficiary: RUSSELL, PAMELA JEAN)
  PR mailing    4100 SAWHILL TRACE DRIVE, Charlotte NC 28213
DataSift currently has William Russell @ 9800 Newell Hickory Grove Rd, which is
the 2026-08-20 deep-prospecting guess (Notes: "DM William Beaver Russell
(Spouse/Sibling)"). Court beats the guess ([[feedback_case_file_wins]],
[[project_court_pr_beats_dp_guess]]). Oren approved the swap 2026-09-09, aware
that William's 3 phones stay on the record.

Writes through `owner.address` -- the key proven to persist;
`owner.mailing_address` saves NOTHING at HTTP 200
([[project_dm_mailing_key_silent_noop]]) -- and round-trips the WHOLE owner
object, because a trimmed phones array DELETES phones
([[project_phone_remove_via_owner_patch]]).

Usage:
    python fix_russell_pr_20260909.py            # dry run
    python fix_russell_pr_20260909.py --apply
"""
from __future__ import annotations

import copy
import json
import sys

import requests

from audit_rename_gap_20260822 import API, token  # noqa: E402

UUID = "b5f0c104-309a-44e4-942a-e7d52e85bf12"
CASE = "26E001831-590"

NEW_FIRST = "PAMELA"
NEW_LAST = "RUSSELL"
NEW_STREET = "4100 SAWHILL TRACE DRIVE"
NEW_CITY = "Charlotte"
NEW_STATE = "NC"
NEW_ZIP = "28213"


def _canon(s: str) -> str:
    return " ".join((s or "").upper().replace(",", " ").split())


def main() -> int:
    apply = "--apply" in sys.argv

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    d = requests.get(f"{API}/api/internal/property/{UUID}/",
                     headers=h, timeout=30).json()
    d = d.get("data", d)
    owner = d.get("owner") or {}
    cur = owner.get("address") or {}
    prop = (d.get("address") or {}).get("street")

    phones_before = len(owner.get("phones") or [])
    name_before = " ".join(filter(None, [owner.get("first_name") or "",
                                         owner.get("last_name") or ""])).strip()
    print(f"=== {CASE}  uuid {UUID}")
    print(f"  property : {prop}")
    print(f"  owner    : {name_before}")
    print(f"  mailing  : {cur.get('street')}, {cur.get('city')} "
          f"{cur.get('state')} {cur.get('postal_code')}")
    print(f"  phones   : {phones_before}")
    print(f"  -> court : {NEW_FIRST} {NEW_LAST}, {NEW_STREET}, "
          f"{NEW_CITY} {NEW_STATE} {NEW_ZIP}")

    if not owner:
        print("  ABORT: no owner object on this record")
        return 1

    new_owner = copy.deepcopy(owner)          # keeps phones/emails intact
    new_owner["first_name"] = NEW_FIRST
    new_owner["last_name"] = NEW_LAST
    addr = dict(cur)
    addr.update({"street": NEW_STREET, "city": NEW_CITY,
                 "state": NEW_STATE, "postal_code": NEW_ZIP})
    # Coordinates belong to the OLD address; drop them so DataSift re-geocodes.
    for k in ("latitude", "longitude", "county"):
        addr.pop(k, None)
    new_owner["address"] = addr

    if not apply:
        print("\n  DRY RUN - would PATCH owner name + owner.address. "
              "Re-run with --apply")
        return 0

    resp = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                          data=json.dumps({"owner": new_owner}), timeout=30)
    print(f"\n  PATCH -> HTTP {resp.status_code}")

    # Verify by re-GET, never by search: the search index is stale right after a
    # write ([[project_datasift_search_index_stale]]).
    v = requests.get(f"{API}/api/internal/property/{UUID}/",
                     headers=h, timeout=30).json()
    v = v.get("data", v)
    vo = v.get("owner") or {}
    va = vo.get("address") or {}
    name_after = " ".join(filter(None, [vo.get("first_name") or "",
                                        vo.get("last_name") or ""])).strip()
    phones_after = len(vo.get("phones") or [])
    print(f"  read-back name   : {name_after}")
    print(f"  read-back mailing: {va.get('street')}, {va.get('city')} "
          f"{va.get('state')} {va.get('postal_code')}")
    print(f"  read-back phones : {phones_after} (was {phones_before})")

    ok = True
    if _canon(name_after) != _canon(f"{NEW_FIRST} {NEW_LAST}"):
        print("  FAIL: name did not persist")
        ok = False
    # Compare loosely - DataSift normalizes ("Drive"->"Dr", spelling fixes).
    if _canon(va.get("street") or "").split()[:2] != _canon(NEW_STREET).split()[:2]:
        print("  FAIL: mailing street did not persist (the known silent no-op)")
        ok = False
    if _canon(va.get("city") or "") != _canon(NEW_CITY):
        print("  FAIL: mailing city did not persist")
        ok = False
    if phones_after != phones_before:
        print(f"  FAIL: phone count changed {phones_before} -> {phones_after}")
        ok = False

    print("\n  VERIFIED OK" if ok else "\n  VERIFY FAILED - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
