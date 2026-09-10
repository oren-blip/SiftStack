"""Delete the empty duplicate record at 4205 Olde Roxbury Dr.

2026-09-09. Two DataSift records exist for 4205 Olde Roxbury Dr, Charlotte NC:

  A b5f0c104-309a-44e4-942a-e7d52e85bf12  the real one -- owner (now PAMELA
                                          Russell, fixed by
                                          fix_russell_pr_20260909.py), 3 phones,
                                          tags Courthouse Data / DP Complete /
                                          NC Upload 2026-08-20
  B 0762c5f3-e856-44e0-8119-781074f963b9  an empty shell -- no owner, no phones,
                                          no notes, no status, no assignee, no
                                          parcel, no value -- whose ONLY unique
                                          asset is the tag "NC Estates Week 21
                                          2026"

Because pr_upgrade_step filters the weekly export by that week tag, it only ever
saw B, found no owner on it, and reported
"26E001831-590: record not found by address" -- applying 0/1 every run.

Oren approved deleting B on 2026-09-09. Deleting BEFORE re-tagging A is
deliberate: the only way to ADD a tag is a mini upsert-by-address upload (tag
PATCH over the API is a silent no-op, [[project_netnew_upload_tags_first_row_bug]]),
and an upsert keyed on the address is ambiguous while two records share it -- it
could land on B or mint a third.

Snapshots B to output/ before deleting so the tag set is recoverable.

Usage:
    python delete_dup_roxbury_20260909.py            # dry run
    python delete_dup_roxbury_20260909.py --apply
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

from audit_rename_gap_20260822 import API, token  # noqa: E402

DUP = "0762c5f3-e856-44e0-8119-781074f963b9"   # delete this one
KEEP = "b5f0c104-309a-44e4-942a-e7d52e85bf12"  # never touch this one
SNAPSHOT = Path("output") / "deleted_record_0762c5f3_20260909.json"


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

    dup = requests.get(f"{API}/api/internal/property/{DUP}/",
                       headers=h, timeout=30).json()
    dup = dup.get("data", dup)
    keep = requests.get(f"{API}/api/internal/property/{KEEP}/",
                        headers=h, timeout=30).json()
    keep = keep.get("data", keep)

    dup_owner = dup.get("owner") or {}
    keep_owner = keep.get("owner") or {}

    print(f"DELETE candidate {DUP}")
    print(f"  address: {(dup.get('address') or {}).get('street')}")
    print(f"  owner  : {dup_owner.get('first_name')} {dup_owner.get('last_name')}")
    print(f"  phones : {len(dup_owner.get('phones') or [])}")
    print(f"  tags   : {dup.get('tags')}")
    print(f"KEEP            {KEEP}")
    print(f"  address: {(keep.get('address') or {}).get('street')}")
    print(f"  owner  : {keep_owner.get('first_name')} {keep_owner.get('last_name')}")
    print(f"  phones : {len(keep_owner.get('phones') or [])}")
    print(f"  tags   : {keep.get('tags')}")

    # Refuse to delete anything that is not the inert shell we audited. If the
    # record has grown an owner, a phone, a note or a status since, stop and let
    # a human look.
    guards = []
    if dup_owner.get("first_name") or dup_owner.get("last_name"):
        guards.append("it now has an owner name")
    if dup_owner.get("phones"):
        guards.append("it now has phones")
    if dup_owner.get("emails"):
        guards.append("it now has emails")
    if dup.get("notes"):
        guards.append("it now has notes")
    if dup.get("property_status"):
        guards.append("it now has a status")
    if dup.get("assignee"):
        guards.append("it now has an assignee")
    if (dup.get("address") or {}).get("street") != (keep.get("address") or {}).get("street"):
        guards.append("the two records are no longer the same address")
    if not keep_owner.get("first_name"):
        guards.append("the KEEP record has no owner - do not delete the spare")
    if guards:
        print("\nABORT - not the inert duplicate that was approved:")
        for g in guards:
            print("  -", g)
        return 1

    if not apply:
        print("\nDRY RUN - would snapshot then DELETE. Re-run with --apply")
        return 0

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(
        {"deleted_at": datetime.now().isoformat(timespec="seconds"),
         "uuid": DUP, "record": dup}, indent=2, default=str), encoding="utf-8")
    print(f"\n  snapshot -> {SNAPSHOT}")

    r = requests.delete(f"{API}/api/internal/property/{DUP}/",
                        headers=h, timeout=30)
    print(f"  DELETE -> HTTP {r.status_code}")

    # Verify by re-GET, not by search (the index lags writes).
    v = requests.get(f"{API}/api/internal/property/{DUP}/", headers=h, timeout=30)
    print(f"  re-GET deleted record -> HTTP {v.status_code} "
          f"(404/403 = gone)")
    k = requests.get(f"{API}/api/internal/property/{KEEP}/", headers=h, timeout=30)
    kd = k.json()
    kd = kd.get("data", kd)
    ko = kd.get("owner") or {}
    print(f"  re-GET kept record    -> HTTP {k.status_code}, owner "
          f"{ko.get('first_name')} {ko.get('last_name')}, "
          f"{len(ko.get('phones') or [])} phones")

    if v.status_code == 200:
        print("\n  FAIL: the duplicate still reads back - delete did not take")
        return 1
    if k.status_code != 200 or not ko.get("first_name"):
        print("\n  ALARM: the KEPT record is not healthy - check immediately")
        return 1
    print("\n  DONE - duplicate gone, real record intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
