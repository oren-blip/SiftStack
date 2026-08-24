"""Parker 26E001117-350 — strip the WRONG Robin Parker off the record.

Gaston case file (portal, read by Oren 2026-08-22): decedent Parker, Seth Allyn
and petitioner Parker, Robin Lynn BOTH at 116 Walking Horse Run, Stanley NC
28164 — the property itself. Robin is heir-occupied, not an off-site heir.

What is on the record instead: 17279 Phillips Hill Rd, Laurel, DE (Sussex
County), five DE emails and four 302-area-code phones. Two independent sources
matched the same wrong person on a common name — Tracerfy skip trace wrote the
DE address/emails/phones, and the 8/20 Enformion sweep resolved the same DE
Robin Parker, so the DP push tagged its phones "Spouse/Sibling Robin Parker" +
dial tiers. Callers have since marked two of them WRONG and DEAD. (A third
wrong Parker is in the workbook: PR mailing 173 Garden Gate Ct, Middle Island
NY, from the free people-search PR lookup.)

Oren's standing rule, given 2026-08-22: **the case file wins.**

This does three things and nothing else:
  1. mailing  -> 116 Walking Horse Run, Stanley NC 28164 (the property)
  2. every 302 phone: dial-tier tags removed, "Wrong Person - Do Not Dial"
     added, status WRONG - so they leave the dial queue instead of vanishing
     (a deleted number gets re-added by the next skip trace)
  3. leaves the owner NAME as Robin Parker - that IS the court's petitioner

Owner name, tags, lists, custom fields are otherwise untouched. Verified by
re-GET (never trust the 200 - project_pr_upgrade_silent_save_failure).

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\fix_parker_wrong_person_20260822.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\fix_parker_wrong_person_20260822.py --apply    # live
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
UUID = "82388e71-4028-4523-a433-ace84ef460d7"
CASE = "26E001117-350"

COURT_MAILING = {"street": "116 Walking Horse Run", "city": "Stanley",
                 "state": "NC", "postal_code": "28164"}
WRONG_AREA = "302"          # Delaware — the wrong Parker's numbers
WRONG_TAG = "Wrong Person - Do Not Dial"
TIER_TAGS = {"Dial First", "Dial Second", "Dial Third", "Dial Fourth"}


def digits(s) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def main() -> int:
    print("===== Parker wrong-person cleanup "
          + ("LIVE" if APPLY else "DRY RUN") + " =====")
    tok = token()
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
    pa = d.get("address") or {}
    oa = owner.get("address") or {}

    # identity guard - right case, right property, right person
    if not (pa.get("street") or "").lower().startswith("116 walking horse"):
        print("property is " + repr(pa.get("street")) + ", not 116 Walking Horse Run - ABORT")
        return 1
    if (owner.get("last_name") or "").strip().lower() != "parker":
        print("owner is " + repr(owner.get("last_name")) + ", not Parker - ABORT")
        return 1
    print("  property : " + str(pa.get("street")) + ", " + str(pa.get("city")))
    print("  owner    : " + str(owner.get("first_name")) + " " + str(owner.get("last_name")))
    print("  mailing  : " + str(oa.get("street")) + ", " + str(oa.get("city"))
          + " " + str(oa.get("state")))

    new_owner = copy.deepcopy(owner)
    na = new_owner.get("address") or {}
    na.update(COURT_MAILING)
    new_owner["address"] = na
    print("  mailing -> " + COURT_MAILING["street"] + ", " + COURT_MAILING["city"]
          + " " + COURT_MAILING["state"] + " " + COURT_MAILING["postal_code"])

    touched = 0
    for p in (new_owner.get("phones") or []):
        num = digits(p.get("number"))[-10:]
        if not num.startswith(WRONG_AREA):
            continue
        tags = [t for t in (p.get("tags") or []) if t not in TIER_TAGS]
        if WRONG_TAG not in tags:
            tags.append(WRONG_TAG)
        print("  phone " + num + ": tags " + str(p.get("tags")) + " -> " + str(tags)
              + ", status " + str(p.get("status")) + " -> WRONG")
        p["tags"] = tags
        p["status"] = "WRONG"
        touched += 1
    print("  " + str(touched) + " Delaware phone(s) retired; owner name left as Robin Parker")

    if not APPLY:
        print("\nDRY RUN - nothing written.")
        return 0

    r = requests.patch(API + "/api/internal/property/" + UUID + "/", headers=h,
                       data=json.dumps({"owner": new_owner}), timeout=30)
    print("  PATCH -> " + str(r.status_code) + " " + r.text[:120])
    if r.status_code not in (200, 202):
        return 1

    v = requests.get(API + "/api/internal/property/" + UUID + "/", headers=h, timeout=30)
    vd = v.json()
    vd = vd.get("data") or vd.get("result") or vd
    vo = vd.get("owner") or {}
    va = vo.get("address") or {}
    mail_ok = (va.get("street") or "").lower() == COURT_MAILING["street"].lower()
    bad = [digits(p.get("number"))[-10:] for p in (vo.get("phones") or [])
           if digits(p.get("number"))[-10:].startswith(WRONG_AREA)
           and (set(p.get("tags") or []) & TIER_TAGS or WRONG_TAG not in (p.get("tags") or []))]
    print("  VERIFY refetch: mailing=" + repr(va.get("street"))
          + " -> " + ("OK" if mail_ok else "DID NOT STICK"))
    print("  VERIFY refetch: DE phones still in a dial tier: " + (str(bad) if bad else "none"))
    return 0 if (mail_ok and not bad) else 1


if __name__ == "__main__":
    raise SystemExit(main())
