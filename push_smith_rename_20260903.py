"""Push the ONE queued rename that never reached DataSift: 26E000888-790.

Found 2026-09-03: of the 28 records still owned by "Heirs X" in DataSift, exactly
one had a rename sitting in manual_corrections.csv that was never pushed --
26E000888-790 (Rowan, 285 Aviation Dr, Kannapolis). The workbook says Vernie
Smith; the CRM still says "Heirs Smith". Oren approved the push.

Provenance: dp_log 2026-09-02, Level L3, RESOLVED --
  "Obit 5/11/2026 (Cleveland NC): widow Vernie Heaggans Smith (704-278-2440 T30)
   + 5 children"
manual_corrections.csv rows 1081-1085 queue First Name / Last Name / DM fields.

Personal Representative is deliberately LEFT ALONE. The court has named nobody
(Beneficiaries blank, PR reads "Heirs of John Henry Smith, Jr"), and
court-PR-beats-DP-guess says our research never overwrites the court's record.
Only the CONTACT (owner first/last name) changes, which is what actually drives
who gets called.

Guards, all from prior burns:
  * owner object is DEEP-COPIED and re-sent whole -- a trimmed phones array
    silently DELETES phones ([[phone-remove-via-owner-patch]])
  * identity: surname must appear in the live owner, house number must match
  * only proceeds if the live owner is still a Heirs/Estate placeholder
  * PR filled only if blank -- never clobbered
    ([[project_pr_upgrade_silent_save_failure]])
  * verified by re-GET, incl. phone count -- never trust the HTTP 200
    ([[project_datasift_search_index_stale]]: never verify via search)

    python push_smith_rename_20260903.py            # dry run
    python push_smith_rename_20260903.py --apply
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, search, token  # noqa: E402

APPLY = "--apply" in sys.argv

CASE = "26E000888-790"
STREET_NUM = "285"
STREET = "285 Aviation Dr"
SURNAME = "smith"
NEW_FIRST, NEW_LAST = "Vernie", "Smith"


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    hits = [x for x in search(h, STREET)
            if ((x.get("address") or {}).get("street") or "").lower().startswith(STREET_NUM + " ")]
    if len(hits) != 1:
        print(f"ABORT: street search returned {len(hits)} candidate(s), need exactly 1")
        for x in hits[:5]:
            print("   ", (x.get("address") or {}).get("street"), x.get("uuid"))
        return 1
    uuid = hits[0].get("uuid")

    d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
    d = d.get("data", d)
    owner = d.get("owner") or {}
    addr = d.get("address") or {}
    before = f"{(owner.get('first_name') or '').strip()} {(owner.get('last_name') or '').strip()}".strip()
    street = (addr.get("street") or "").strip()
    live_pr = (d.get("personal_representative") or "").strip()
    phones_before = len(owner.get("phones") or [])

    print(f"=== {CASE}   uuid {uuid}")
    print(f"  live owner : {before!r}")
    print(f"  live addr  : {street}, {addr.get('city')}")
    print(f"  live PR    : {live_pr!r}")
    print(f"  live phones: {phones_before}")

    if SURNAME not in before.lower():
        print(f"  ABORT identity: surname {SURNAME!r} not in live owner {before!r}")
        return 1
    if not street.lower().startswith(STREET_NUM + " "):
        print(f"  ABORT identity: street {street!r} does not start {STREET_NUM!r}")
        return 1
    if not (owner.get("first_name") or "").strip().lower().startswith(("heir", "estate")):
        print("  NOTHING TO DO: owner is already a real name")
        return 0

    new_owner = copy.deepcopy(owner)
    new_owner["first_name"], new_owner["last_name"] = NEW_FIRST, NEW_LAST
    body = {"owner": new_owner}
    # Personal Representative is left ALONE by default, even when blank.
    # dp_push_renames_20260822.py fills-if-blank, but that was for cases with a
    # court-named PR available. Here the court has appointed NOBODY (Beneficiaries
    # blank, workbook PR = "Heirs of John Henry Smith, Jr"), and Vernie is OUR
    # obituary research. The PR field is where court truth lives -- writing a
    # research guess into it makes a guess look court-appointed to whoever reads
    # it next. The owner rename is what actually drives calling/mailing.
    # Pass --set-pr to override.
    if "--set-pr" in sys.argv and not live_pr:
        body["personal_representative"] = f"{NEW_FIRST} {NEW_LAST}"
        print(f"  --set-pr given, PR blank -> setting {NEW_FIRST} {NEW_LAST}")
    elif live_pr:
        print(f"  PR left as-is ({live_pr!r}) -- never overwritten")
    else:
        print("  PR left BLANK -- court has appointed nobody; Vernie is our "
              "research, not a court appointment (pass --set-pr to write it anyway)")

    print(f"  rename {before!r} -> {NEW_FIRST} {NEW_LAST!r}; "
          f"phones/mailing/tags/lists round-tripped untouched")
    if not APPLY:
        print("\nDRY RUN -- re-run with --apply.")
        return 0

    r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                       data=json.dumps(body), timeout=30)
    print(f"  PATCH -> HTTP {r.status_code} {r.text[:140]}")
    if r.status_code not in (200, 202):
        return 1

    v = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
    v = v.get("data", v)
    vo = v.get("owner") or {}
    after = f"{(vo.get('first_name') or '').strip()} {(vo.get('last_name') or '').strip()}".strip()
    phones_after = len(vo.get("phones") or [])
    print(f"  verify owner : {after!r}")
    print(f"  verify phones: {phones_after} (was {phones_before})")
    if after.lower() != f"{NEW_FIRST} {NEW_LAST}".lower():
        print("  *** VERIFY FAILED: owner did not change")
        return 1
    if phones_after != phones_before:
        print(f"  *** WARNING: phone count changed {phones_before} -> {phones_after}")
        return 1
    print("\nDONE -- rename landed, phones intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
