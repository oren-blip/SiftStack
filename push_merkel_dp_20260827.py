r"""2026-08-27 DP push: Merkel estate 26E000835-480 (Iredell) — Oren said go.

One record (uuid 24b45ac3-41a1-442e-9704-9545d7646e9a, 109 Whitewater Ln,
Mooresville). Court Parties names Robert T. Andaloro as Executor AND sole
Beneficiary; DP pack output/reports/DP_Week35_Merkel_26E000835-480.md.

Writes (all append/fill, nothing blanked):
  1. owner rename  Heirs Merkel -> Robert Andaloro (no suffix/comma in Last)
  2. owner.address -> court mailing 2032 Old Linwood Rd., Lexington NC 27292
     (owner.address is the key that saves; owner.mailing_address is a no-op)
  3. personal_representative -> "Robert T. Andaloro" (live value is the
     "Heirs of" placeholder, so this is the pr-upgrade fill, not a clobber)
  4. append 3 Enformion mobiles, all Trestle Dial First, labeled with
     provenance so a caller knows whose numbers they are
  5. tags: +Court Mailing Applied +DP Complete, -Needs DP

Guards: live owner must still be the Heirs placeholder at 109 Whitewater;
phone cap respected (records hold 30 but the API PATCH saves only the first
15 entries); verify by record GET (never search), else report VOID.

Run:  d:\SiftStack\.venv\Scripts\python.exe push_merkel_dp_20260827.py --apply
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from apn_gap_scout_20260826 import get_token, headers  # noqa: E402

API = "https://apiv2.reisift.io"
UUID = "24b45ac3-41a1-442e-9704-9545d7646e9a"
APPLY = "--apply" in sys.argv
PHONE_CAP = 15

NEW_FIRST, NEW_LAST = "Robert", "Andaloro"
PR_NAME = "Robert T. Andaloro"
MAILING = {"street": "2032 Old Linwood Rd.", "city": "Lexington",
           "state": "NC", "postal_code": "27292"}
PHONES = [
    {"number": "(516) 713-4886", "type": "MOBILE",
     "tags": ["Dial First", "Court Executor Robert Andaloro", "enformion-phone"]},
    {"number": "(631) 742-7126", "type": "MOBILE",
     "tags": ["Dial First", "Court Executor Robert Andaloro", "enformion-phone"]},
    {"number": "(714) 804-3809", "type": "MOBILE",
     "tags": ["Dial First", "Court Executor Robert Andaloro", "enformion-phone"]},
]
ADD_TAGS = ["Court Mailing Applied", "DP Complete"]
REMOVE_TAGS = ["Needs DP"]


def digits(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())[-10:]


def titles(tags) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (tags or [])]


def main() -> int:
    h = headers(get_token())
    r = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"GET failed HTTP {r.status_code}")
        return 1
    d = r.json()
    owner = d.get("owner") or {}
    addr = d.get("address") or {}
    live = (f"{(owner.get('first_name') or '').strip()} "
            f"{(owner.get('last_name') or '').strip()}").strip()
    live_pr = (d.get("personal_representative") or "").strip()
    print(f"live owner : {live!r}")
    print(f"live addr  : {addr.get('street')}, {addr.get('city')}")
    print(f"live PR    : {live_pr!r}")
    print(f"live phones: {len(owner.get('phones') or [])}  "
          f"emails: {len(owner.get('emails') or [])}")

    # identity guards
    if not (owner.get("first_name") or "").strip().lower().startswith(("heir", "estate")):
        print("owner is NOT a Heirs/Estate placeholder - SKIP (maybe already pushed)")
        return 1
    if "merkel" not in live.lower():
        print("surname Merkel not on live owner - SKIP, wrong record")
        return 1
    if not (addr.get("street") or "").strip().lower().startswith("109 "):
        print("street is not 109 ... - SKIP, wrong record")
        return 1

    new_owner = copy.deepcopy(owner)
    new_owner["first_name"], new_owner["last_name"] = NEW_FIRST, NEW_LAST

    na = new_owner.get("address") or {}
    na.update(MAILING)
    new_owner["address"] = na

    existing = {digits(p.get("number")) for p in (owner.get("phones") or [])}
    added = []
    for ph in PHONES:
        if digits(ph["number"]) in existing:
            print(f"  {ph['number']} already on record - skip")
            continue
        if len(new_owner.get("phones") or []) >= PHONE_CAP:
            print(f"  phone cap {PHONE_CAP} reached - {ph['number']} NOT added")
            break
        new_owner.setdefault("phones", []).append(ph)
        added.append(ph["number"])

    body = {"owner": new_owner}
    if not live_pr or live_pr.lower().startswith(("heirs of", "estate of")):
        body["personal_representative"] = PR_NAME
        print(f"PR placeholder/blank -> will set {PR_NAME!r}")
    else:
        print(f"PR already a real name {live_pr!r} - left as-is")

    print(f"plan: rename {live!r} -> {NEW_FIRST} {NEW_LAST!r}; "
          f"mailing -> {MAILING['street']}, {MAILING['city']}; "
          f"add phones {added}; tags +{ADD_TAGS} -{REMOVE_TAGS}")
    if not APPLY:
        print("DRY RUN - nothing written. Re-run with --apply.")
        return 0

    r = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                       data=json.dumps(body), timeout=30)
    print(f"PATCH owner(+PR) -> HTTP {r.status_code}")
    if r.status_code not in (200, 202):
        print(r.text[:300])
        return 1
    r = requests.post(f"{API}/api/internal/property/{UUID}/add-tags/",
                      headers=h, json={"tags": ADD_TAGS}, timeout=30)
    print(f"add-tags {ADD_TAGS} -> HTTP {r.status_code}")
    r = requests.post(f"{API}/api/internal/property/{UUID}/remove-tags/",
                      headers=h, json={"tags": REMOVE_TAGS}, timeout=30)
    print(f"remove-tags {REMOVE_TAGS} -> HTTP {r.status_code}")

    # verify against the RECORD (search index goes stale)
    time.sleep(0.5)
    v = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h,
                     timeout=30).json()
    vo = v.get("owner") or {}
    va = vo.get("address") or {}
    v_name = (f"{(vo.get('first_name') or '').strip()} "
              f"{(vo.get('last_name') or '').strip()}").strip()
    v_nums = {digits(p.get("number")) for p in (vo.get("phones") or [])}
    v_tags = titles(v.get("tags"))
    missing = [n for n in added if digits(n) not in v_nums]
    checks = {
        "owner renamed": v_name == f"{NEW_FIRST} {NEW_LAST}",
        "mailing street": (va.get("street") or "").lower().startswith("2032 old linwood"),
        "mailing zip": (va.get("postal_code") or "").startswith("27292"),
        "PR": (v.get("personal_representative") or "") == PR_NAME
              or "personal_representative" not in body,
        "phones landed": not missing,
        "tags added": all(t in v_tags for t in ADD_TAGS),
        "Needs DP gone": "Needs DP" not in v_tags,
    }
    for k, okv in checks.items():
        print(f"  verify {k}: {'OK' if okv else 'FAIL'}")
    if missing:
        print(f"  phones missing after write: {missing}")
    if all(checks.values()):
        print(f"\nALL VERIFIED. owner={v_name!r}  "
              f"mailing={va.get('street')}, {va.get('city')} {va.get('postal_code')}  "
              f"phones now {len(vo.get('phones') or [])}")
        return 0
    print("\nVOID/PARTIAL SAVE - inspect by hand before retrying.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
