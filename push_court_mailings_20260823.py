"""Point 4 records at the address the COURT gives, not the one research found.

Oren approved all four on 2026-08-23 under his standing rule
([[feedback_case_file_wins]]): when the case file and our enrichment disagree
about where a person lives, the case file wins.

Found by audit_wrong_person_20260822.py:

  26E000780-120 Kachmarik  CRM Portland OR   -> court: 1715 Castlerock Rd,
                           Houston TX. Our DP had said Harrisburg NC. Three
                           sources, three answers; the court's is the one the
                           clerk mailed the notice to.
  26E001077-350 Courteau   CRM 2207 Circlestone Ct -> court: 2609 Maple St,
                           Hopewell VA. Odyssey names him Applicant AND
                           Administrator at that address.
  26E001114-350 Verna      CRM 108 Chronicle St (that is the DECEDENT's address
                           and the property) -> court: 8214 Wamac Ct, Charlotte.
  26E001013-350 Russell    CRM 325 Gaither Rd -> court: 2713 Rawhide Dr,
                           Belmont. 325 Gaither Rd is beneficiary Wanda
                           McCormick's address, not Gilbert's - the record was
                           mailing one heir's letter to a different heir.

Recipe from dp_fix_mailings_20260817.py: full owner round-trip, mailing on
owner["address"] (owner["mailing_address"] is silently discarded - see
project_dm_mailing_key_silent_noop), verified by re-GET.

SCOPE: owner["address"] only. Names, phones, tags, lists untouched.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_court_mailings_20260823.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_court_mailings_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_dm_mailing_gap_20260822 import norm  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / ("court_mailing_push_20260823"
                         + ("" if APPLY else "_dryrun") + ".csv")

# (case, uuid, guard owner first, guard owner last, mailing, court role)
SPECS = [
    ("26E000780-120", "bfd23e3a-1b5f-4df9-adce-977a60c72c16", "haley", "kachmarik",
     {"street": "1715 Castlerock Rd", "city": "Houston", "state": "TX",
      "postal_code": "77090"}, "Beneficiary (Haley Ann Kachmarik)"),
    ("26E001077-350", "a46fda3a-2884-4b61-a909-351d4d7b2db2", "robert", "courteau",
     {"street": "2609 Maple St", "city": "Hopewell", "state": "VA",
      "postal_code": "23860"}, "Applicant + Administrator"),
    ("26E001114-350", "d8345438-1843-4ff5-b3bd-1b9805e9f83b", "victor", "verna",
     {"street": "8214 Wamac Ct", "city": "Charlotte", "state": "NC",
      "postal_code": "28214"}, "Applicant"),
    ("26E001013-350", "3d861922-e90f-4b49-b311-3dfb22fff1a6", "gilbert", "",
     {"street": "2713 Rawhide Dr", "city": "Belmont", "state": "NC",
      "postal_code": "28012"}, "co-executor / beneficiary (Estates cover sheet)"),
    # --- added 2026-08-23, second wave -------------------------------------
    # Both records were PR-corrected BY HAND after dp_push_mailings_20260822
    # wrote them ("PR Corrected" + "Phones - Other Heir" tags), so each ended up
    # holding the previous heir's address under the new heir's name. Neither
    # Richard Sigmon nor Arceal Dudley is a party on their case at all.
    ("26E000978-170", "0f300394-ecb5-4b42-97b9-7134fbac8e12", "rebecca", "albrecht",
     {"street": "3423 Iva Ada Rd", "city": "Hillsborough", "state": "NC",
      "postal_code": "27278"}, "Administrator CTA (was Richard Sigmon's address)"),
    ("26E002979-590", "36a6f7b1-8779-4ce6-be3a-02c16900502a", "korey", "dudley",
     {"street": "422 Timberlane Dr", "city": "Mount Holly", "state": "NC",
      "postal_code": "28120"}, "Executor (was Arceal Dudley's address)"),
]


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(API + "/api/internal/property/" + uuid + "/", headers=h, timeout=30)
    if r.status_code != 200:
        print("  GET -> HTTP " + str(r.status_code))
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def main() -> int:
    print("===== court-mailing push " + ("LIVE" if APPLY else "DRY RUN")
          + " at " + str(_dt.datetime.now()) + " =====")
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    rows = []
    ok = skipped = failed = 0
    for case, uuid, g_first, g_last, mail, role in SPECS:
        print("\n=== " + case + "   court role: " + role)
        d = get_prop(h, uuid)
        if not d:
            failed += 1
            rows.append({"Case No.": case, "Result": "GET FAILED", "Before": "",
                         "After": "", "UUID": uuid})
            continue
        owner = d.get("owner") or {}
        oa = owner.get("address") or {}
        pa = d.get("address") or {}
        first = (owner.get("first_name") or "").strip()
        last = (owner.get("last_name") or "").strip()
        before = ", ".join(x for x in [oa.get("street"), oa.get("city"),
                                       oa.get("state")] if x)
        print("  live owner   : " + first + " " + last)
        print("  live mailing : " + (before or "(blank)"))
        print("  property     : " + str(pa.get("street")) + ", " + str(pa.get("city")))

        # identity guard - the record must still be the person we audited
        # DataSift keeps middle names in first_name ("Robert Clinton"), so guard
        # on the first token, not the whole field
        if g_first and (first.lower().split() or [""])[0] != g_first:
            print("  IDENTITY MISMATCH (first name " + repr(first) + ") - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP identity", "Before": before,
                         "After": "", "UUID": uuid})
            continue
        if g_last and last.lower() != g_last:
            print("  IDENTITY MISMATCH (surname " + repr(last) + ") - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP identity", "Before": before,
                         "After": "", "UUID": uuid})
            continue
        # loose compare so a rerun is a true no-op after DataSift's own
        # street correction (Castlerock Rd -> Castlerock Dr)
        def house(s: str) -> str:
            return (norm(s or "").split() or [""])[0]

        if (house(oa.get("street")) == house(mail["street"])
                and norm(oa.get("city") or "") == norm(mail["city"])):
            print("  mailing already matches the court - nothing to do")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP already correct",
                         "Before": before, "After": "", "UUID": uuid})
            continue

        new_owner = copy.deepcopy(owner)
        na = new_owner.get("address") or {}
        na.update(mail)
        new_owner["address"] = na
        after = (mail["street"] + ", " + mail["city"] + " " + mail["state"]
                 + " " + mail["postal_code"])
        print("  mailing " + repr(before or "(blank)") + " -> " + repr(after))

        if not APPLY:
            rows.append({"Case No.": case, "Result": "DRY", "Before": before,
                         "After": after, "UUID": uuid})
            ok += 1
            continue

        r = requests.patch(API + "/api/internal/property/" + uuid + "/", headers=h,
                           data=json.dumps({"owner": new_owner}), timeout=30)
        print("  PATCH -> " + str(r.status_code) + " " + r.text[:100])
        if r.status_code not in (200, 202):
            failed += 1
            rows.append({"Case No.": case, "Result": "PATCH " + str(r.status_code),
                         "Before": before, "After": "", "UUID": uuid})
            continue

        v = get_prop(h, uuid)
        va = (v.get("owner") or {}).get("address") or {}
        # DataSift VALIDATES the address on save and stores the postal-service
        # version: "1715 Castlerock Rd" (as the court typed it) came back as
        # "1715 Castlerock Dr, Houston TX 77090-1825" with a Harris County
        # geocode. That is a correction, not a failed write - so verify on the
        # house number + city + ZIP5, not the exact street string.
        def key(street: str, city: str, zipc: str) -> tuple:
            return ((norm(street).split() or [""])[0], norm(city),
                    (zipc or "")[:5])
        good = key(va.get("street"), va.get("city"), va.get("postal_code")) == \
            key(mail["street"], mail["city"], mail["postal_code"])
        if good and norm(va.get("street") or "") != norm(mail["street"]):
            print("  (DataSift corrected the street to " + repr(va.get("street"))
                  + " on save)")
        print("  VERIFY refetch: mailing=" + repr(va.get("street"))
              + " -> " + ("OK" if good else "DID NOT STICK"))
        ok += good
        failed += (not good)
        rows.append({"Case No.": case, "Result": "MAILING SET" if good else "VOID SAVE",
                     "Before": before,
                     "After": ", ".join(x for x in [va.get("street"), va.get("city")] if x),
                     "UUID": uuid})

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Case No.", "Result", "Before", "After", "UUID"])
        w.writeheader()
        w.writerows(rows)
    print("\n==== " + ("LIVE" if APPLY else "DRY") + " SUMMARY ====")
    print("  ok/would-do " + str(ok) + "   skipped " + str(skipped)
          + "   failed " + str(failed))
    print("wrote " + str(OUT))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
