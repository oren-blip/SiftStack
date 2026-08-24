"""Append court-document phone numbers to their DataSift records.

The per-phone "Court Verified" tag queue (output/court_verified_phones.csv) was
uploaded 2026-08-22 — but that route only TAGS numbers DataSift already holds.
A court phone that the CRM never had still has to be appended to the record, and
that is a separate write this covers.

First case: Gilbert Winfred Russell Jr's 704-685-0631, off the Estates Action
Cover Sheet filed 7/28/26 on 26E001013-350. It sat in manual_corrections.csv
(which feeds the workbook, not the CRM) and never reached DataSift.

Court numbers are the highest-signal contacts in the pipeline — the clerk took
them from the filer. They are appended, never substituted: existing skip-trace
numbers keep their dial tiers.

No dial tier is set here. These numbers have not been Trestle-scored, and the
post-upload sweep tiers untiered numbers within its $1 cap.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_court_phones_20260823.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_court_phones_20260823.py --apply    # live
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
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
TAG = "Court Verified"
OUT = REPO / "output" / ("court_phone_push_20260823"
                         + ("" if APPLY else "_dryrun") + ".csv")

# (case, uuid, guard surname, phone, whose number it is, source document)
SPECS = [
    ("26E001013-350", "3d861922-e90f-4b49-b311-3dfb22fff1a6", "russell",
     "7046850631", "co-executor Gilbert Winfred Russell Jr",
     "Estates Action Cover Sheet filed 7/28/26"),
]


def digits(s) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(API + "/api/internal/property/" + uuid + "/", headers=h, timeout=30)
    if r.status_code != 200:
        print("  GET -> HTTP " + str(r.status_code))
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def main() -> int:
    print("===== court-phone push " + ("LIVE" if APPLY else "DRY RUN")
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
    for case, uuid, guard, phone, whose, doc in SPECS:
        print("\n=== " + case + "   " + whose)
        print("  source: " + doc)
        d = get_prop(h, uuid)
        if not d:
            failed += 1
            rows.append({"Case No.": case, "Phone": phone, "Result": "GET FAILED",
                         "UUID": uuid})
            continue
        owner = d.get("owner") or {}
        last = (owner.get("last_name") or "").strip()
        if guard and guard not in last.lower():
            print("  IDENTITY MISMATCH (owner surname " + repr(last) + ") - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Phone": phone, "Result": "SKIP identity",
                         "UUID": uuid})
            continue

        have = {digits(p.get("number"))[-10:] for p in (owner.get("phones") or [])}
        print("  live phones: " + str(sorted(have)))
        if phone in have:
            print("  already on the record - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Phone": phone, "Result": "SKIP already there",
                         "UUID": uuid})
            continue

        new_owner = copy.deepcopy(owner)
        tags = [TAG, whose]
        new_owner.setdefault("phones", []).append(
            {"number": phone, "type": "UNKNOWN", "tags": tags})
        print("  + " + phone + " tags " + str(tags) + " (no dial tier - unscored)")

        if not APPLY:
            rows.append({"Case No.": case, "Phone": phone, "Result": "DRY", "UUID": uuid})
            ok += 1
            continue

        r = requests.patch(API + "/api/internal/property/" + uuid + "/", headers=h,
                           data=json.dumps({"owner": new_owner}), timeout=30)
        print("  PATCH -> " + str(r.status_code) + " " + r.text[:90])
        if r.status_code not in (200, 202):
            failed += 1
            rows.append({"Case No.": case, "Phone": phone,
                         "Result": "PATCH " + str(r.status_code), "UUID": uuid})
            continue

        v = get_prop(h, uuid)
        vph = {digits(p.get("number"))[-10:] for p in ((v.get("owner") or {}).get("phones") or [])}
        good = phone in vph
        print("  VERIFY refetch: phone present=" + str(good))
        ok += good
        failed += (not good)
        rows.append({"Case No.": case, "Phone": phone,
                     "Result": "ADDED" if good else "DID NOT STICK", "UUID": uuid})

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Case No.", "Phone", "Result", "UUID"])
        w.writeheader()
        w.writerows(rows)
    print("\n==== " + ("LIVE" if APPLY else "DRY") + " SUMMARY ====")
    print("  ok/would-do " + str(ok) + "   skipped " + str(skipped)
          + "   failed " + str(failed))
    print("wrote " + str(OUT))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
