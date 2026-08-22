"""Point the 20 DP'd records that still mail to the PROPERTY at their DM.

Found by audit_dm_mailing_gap_20260822.py (2026-08-22, prompted by Casto):
the 8/20 heirs push wrote the DM mailing to owner["mailing_address"], a key the
API does not read. Every PATCH returned HTTP 200 and the rename + phones in the
same body landed, so 0 of 16 mailings actually saved and nothing flagged it.
The 8/22 rename push then scoped mailing out by design. Net effect: 20 records
carry the right heir's NAME and PHONES but still mail to the dead owner's house.

Recipe is dp_fix_mailings_20260817.py's, which is the one that verifiably works:
owner object round-tripped in full, mailing written to owner["address"], never
blank over an existing value, verified by re-GET (the SEARCH index is stale for
~15 min after a write - project_datasift_search_index_stale).

SCOPE: owner["address"] ONLY. Names, phones, tags, lists, custom fields are not
touched - those are already correct on every row here.

Guards, per record, all must pass or it is skipped:
  * live owner surname == the DM surname the DP run resolved
  * live mailing street == the live PROPERTY street (that IS the defect; if the
    mailing has since changed, a human looks at it instead)
  * parsed DM address has street + city + state + zip

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_mailings_20260822.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_mailings_20260822.py --apply    # live

Input:  output/dm_mailing_gap_20260822.csv (rerun the audit first if it is stale)
Output: output/dm_mailing_push_20260822[_dryrun].csv
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
from audit_dm_mailing_gap_20260822 import norm, parse_expected  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
AUDIT = REPO / "output" / "dm_mailing_gap_20260822.csv"
OUT = REPO / "output" / ("dm_mailing_push_20260822"
                         + ("" if APPLY else "_dryrun") + ".csv")


_ABBR = {"cr": "cir", "crcl": "cir", "trl": "tr", "trail": "tr", "hwy": "hw",
         "highway": "hw", "expy": "exp", "pkwy": "pk", "parkway": "pk"}


def _same_street(a: str, b: str) -> bool:
    """norm() with the leftover suffix spellings folded - '4427 Hamilton Cir'
    and '4427 Hamilton Cr' are the same house, and that record is a DM-at-
    property case, not a mailing defect."""
    def key(s: str) -> str:
        return " ".join(_ABBR.get(t, t) for t in norm(s).split())
    return bool(a) and bool(b) and key(a) == key(b)


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(API + "/api/internal/property/" + uuid + "/", headers=h, timeout=30)
    if r.status_code != 200:
        print("  GET " + uuid + " -> HTTP " + str(r.status_code))
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def main() -> int:
    print("===== mailing push " + ("LIVE" if APPLY else "DRY RUN")
          + " at " + str(_dt.datetime.now()) + " =====")
    targets = [r for r in csv.DictReader(AUDIT.open(encoding="utf-8-sig"))
               if r["Status"].startswith("GAP") and r["UUID"].strip()]
    print("gap rows in " + AUDIT.name + ": " + str(len(targets)))

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
    for t in targets:
        case, uuid = t["Case No."], t["UUID"]
        want = parse_expected(t["DP Says Mailing"])
        print("\n=== " + (case or t["Property"]) + "  " + t["DM"])
        if not want or not all(want.get(k) for k in ("street", "city", "state", "zip")):
            print("  DP address does not parse to street/city/state/zip - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP unparseable",
                         "Before": t["Live Mailing"], "After": "", "UUID": uuid})
            continue

        d = get_prop(h, uuid)
        if not d:
            failed += 1
            rows.append({"Case No.": case, "Result": "GET FAILED",
                         "Before": "", "After": "", "UUID": uuid})
            continue
        owner = d.get("owner") or {}
        oa = owner.get("address") or {}
        pa = d.get("address") or {}
        before = ", ".join(x for x in [oa.get("street"), oa.get("city")] if x)
        live_last = (owner.get("last_name") or "").strip()
        dm_last = (t["DM"].split() or [""])[-1]
        print("  live owner   : " + (owner.get("first_name") or "") + " " + live_last)
        print("  live mailing : " + (before or "(blank)"))
        print("  live property: " + str(pa.get("street")) + ", " + str(pa.get("city")))

        live_first = (owner.get("first_name") or "").strip()
        dm_first = (t["DM"].split() or [""])[0]
        if dm_last and live_last.lower() != dm_last.lower():
            print("  IDENTITY MISMATCH (owner " + live_last + " != DM " + dm_last + ") - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP identity",
                         "Before": before, "After": "", "UUID": uuid})
            continue
        if dm_first and live_first.lower() != dm_first.lower():
            # same surname, different person - e.g. the record reads Randall
            # Simmons while the DP run resolved Torrence Simmons. Mailing a
            # sibling's address to the named owner is worse than leaving it.
            print("  SAME SURNAME, DIFFERENT PERSON (record " + live_first
                  + ", DP " + dm_first + ") - SKIP, human call")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP first-name mismatch",
                         "Before": before, "After": "", "UUID": uuid})
            continue
        lm, lp = norm(oa.get("street") or ""), norm(pa.get("street") or "")
        if norm(want["street"]) == lp or _same_street(want["street"], pa.get("street")):
            print("  DP address IS the property - DM lives there, nothing to mail elsewhere")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP DM at property",
                         "Before": before, "After": "", "UUID": uuid})
            continue
        if lm and lm != lp:
            print("  mailing is no longer the property (" + before + ") - SKIP, human call")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP mailing moved",
                         "Before": before, "After": "", "UUID": uuid})
            continue

        new_owner = copy.deepcopy(owner)
        na = new_owner.get("address") or {}
        na.update({"street": want["street"], "city": want["city"],
                   "state": want["state"], "postal_code": want["zip"]})
        new_owner["address"] = na
        after = want["street"] + ", " + want["city"] + " " + want["state"] + " " + want["zip"]
        print("  mailing " + repr(before or "(property)") + " -> " + repr(after)
              + "; name/phones/tags untouched")

        if not APPLY:
            rows.append({"Case No.": case, "Result": "DRY", "Before": before,
                         "After": after, "UUID": uuid})
            ok += 1
            continue

        r = requests.patch(API + "/api/internal/property/" + uuid + "/", headers=h,
                           data=json.dumps({"owner": new_owner}), timeout=30)
        print("  PATCH -> " + str(r.status_code) + " " + r.text[:120])
        if r.status_code not in (200, 202):
            failed += 1
            rows.append({"Case No.": case, "Result": "PATCH " + str(r.status_code),
                         "Before": before, "After": "", "UUID": uuid})
            continue

        v = get_prop(h, uuid)
        va = (v.get("owner") or {}).get("address") or {}
        good = norm(va.get("street") or "") == norm(want["street"])
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
