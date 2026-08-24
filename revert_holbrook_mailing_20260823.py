"""Undo the 8/22 mailing change on Holbrook 26E002916-590 — Oren's call 8/23.

dp_push_mailings_20260822.py moved this record's mailing from its own property
(115 S Church St, Huntersville) to 9934 Hyde Glen Ct, Charlotte, on the strength
of a queued `Mailing Address` in manual_corrections.csv. The court file says
that queued address is the DECEDENT's (Donald Holbrook), not an heir's — so the
push made the record mail to a dead man's house. That is the change this undoes.

The record is unresolved beyond the address, which is why Oren chose the reset
rather than the executor's address:
  * its property is 115 S Church St, Huntersville, but the estate's property in
    the court file is 9934 Hyde Glen Ct, Charlotte — a different house
  * the court's executor is Adam Christopher Holbrook, 143 S Church Street,
    Huntersville — one block from the record's own property
  * the record's owner reads Jennifer Pratt, who is not a party on the case
So the record may be attached to the wrong estate entirely. Reverting restores
the pre-8/22 state and nothing else; the identity question stays open.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\revert_holbrook_mailing_20260823.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\revert_holbrook_mailing_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
UUID = "4c6ff27f-47a0-43cd-bf42-3f656afece21"
CASE = "26E002916-590"

# exactly what the push overwrote (dm_mailing_push_20260822.csv "Before"),
# with city/state/ZIP taken from the record's own property block
RESTORE = {"street": "115 S Church St", "city": "Huntersville",
           "state": "NC", "postal_code": "28078-6296"}
UNDO_STREET = "9934 hyde glen ct"     # what must be there now for a safe revert


def main() -> int:
    print("===== Holbrook " + CASE + " revert "
          + ("LIVE" if APPLY else "DRY RUN") + " =====")
    tok = None
    for attempt in range(4):
        tok = token()
        if tok:
            break
        print("  login attempt " + str(attempt + 1) + " failed - retrying")
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    r = requests.get(API + "/api/internal/property/" + UUID + "/", headers=h, timeout=30)
    if r.status_code != 200:
        print("GET -> HTTP " + str(r.status_code))
        return 1
    d = r.json()
    d = d.get("data") or d.get("result") or d
    owner = d.get("owner") or {}
    oa = owner.get("address") or {}
    pa = d.get("address") or {}
    print("  property: " + str(pa.get("street")) + ", " + str(pa.get("city")))
    print("  owner   : " + str(owner.get("first_name")) + " " + str(owner.get("last_name")))
    print("  mailing : " + str(oa.get("street")) + ", " + str(oa.get("city")))

    if not (pa.get("street") or "").lower().startswith("115 s church"):
        print("  property is not 115 S Church St — ABORT")
        return 1
    if (oa.get("street") or "").lower() != UNDO_STREET:
        print("  mailing is no longer the value the 8/22 push wrote "
              + repr(oa.get("street")) + " — someone else has edited it; ABORT")
        return 1

    new_owner = copy.deepcopy(owner)
    na = new_owner.get("address") or {}
    na.update(RESTORE)
    new_owner["address"] = na
    print("  revert -> " + RESTORE["street"] + ", " + RESTORE["city"] + " "
          + RESTORE["state"] + " " + RESTORE["postal_code"])

    if not APPLY:
        print("\nDRY RUN — nothing written.")
        return 0

    r = requests.patch(API + "/api/internal/property/" + UUID + "/", headers=h,
                       data=json.dumps({"owner": new_owner}), timeout=30)
    print("  PATCH -> " + str(r.status_code) + " " + r.text[:90])
    if r.status_code not in (200, 202):
        return 1
    v = requests.get(API + "/api/internal/property/" + UUID + "/", headers=h, timeout=30)
    vd = v.json()
    vd = vd.get("data") or vd.get("result") or vd
    va = (vd.get("owner") or {}).get("address") or {}
    good = (va.get("street") or "").lower().startswith("115 s church")
    print("  VERIFY refetch: mailing=" + repr(va.get("street"))
          + " -> " + ("OK" if good else "DID NOT STICK"))
    print("\nSTILL OPEN: owner reads Jennifer Pratt (not a court party), and this "
          "record's property may not belong to the Holbrook estate at all.")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
