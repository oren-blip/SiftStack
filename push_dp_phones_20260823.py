"""Append the 2 DP-found phones that never reached DataSift.

Found 2026-08-23 auditing all 107 cases that carry a queued `Phone 1`/`DM Phone`
in manual_corrections.csv against the live records: 101 were already on their
record, 6 were not. Only these 2 have a queued phone whose owner MATCHES the
person the record currently names:

  26E000978-170  Richard Sigmon   828-327-2725
  26E002979-590  Arceal Dudley    919-803-6211

Both were renamed by dp_push_renames_20260822.py, which by design pushed the
NAME only and left phones alone — so the number stayed in manual_corrections
(which feeds the workbook, not the CRM).

The other 4 are NOT here on purpose: the queued phone belongs to a different
human than the record now names (26E000780-120's record is Haley Kachmarik but
the phone is Robert's; 26E000782-480's record is Lisa Hall but the phone is
Edward Lunsford's; 26E002931-590's owner differs from the queued Chase
Thompson), or the contact is explicitly not an heir (26E002835-590 Amanda
Woodard, "former state-appointed guardian - info contact"). Those need Oren to
decide who the right contact is - see [[feedback_case_file_wins]].

No dial tier: neither number has been Trestle-scored. The post-upload sweep
tiers untiered numbers inside its $1 cap.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_dp_phones_20260823.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_dp_phones_20260823.py --apply    # live
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
OUT = REPO / "output" / ("dp_phone_push_20260823"
                         + ("" if APPLY else "_dryrun") + ".csv")

# (case, uuid, owner first, owner last, phone, relationship)
SPECS = [
    ("26E000978-170", "0f300394-ecb5-4b42-97b9-7134fbac8e12",
     "richard", "sigmon", "8283272725", "Spouse/Sibling"),
    ("26E002979-590", "36a6f7b1-8779-4ce6-be3a-02c16900502a",
     "arceal", "dudley", "9198036211", "Spouse/Sibling"),
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
    print("===== DP-phone push " + ("LIVE" if APPLY else "DRY RUN")
          + " at " + str(_dt.datetime.now()) + " =====")
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

    rows = []
    ok = skipped = failed = 0
    for case, uuid, g_first, g_last, phone, rel in SPECS:
        print("\n=== " + case)
        d = get_prop(h, uuid)
        if not d:
            failed += 1
            rows.append({"Case No.": case, "Phone": phone, "Result": "GET FAILED",
                         "UUID": uuid})
            continue
        owner = d.get("owner") or {}
        first = (owner.get("first_name") or "").strip()
        last = (owner.get("last_name") or "").strip()
        print("  live owner : " + first + " " + last)

        # both halves of the name must match - a shared surname is not enough
        if (first.lower().split() or [""])[0] != g_first or last.lower() != g_last:
            print("  IDENTITY MISMATCH (want " + g_first + " " + g_last + ") - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Phone": phone, "Result": "SKIP identity",
                         "UUID": uuid})
            continue

        have = {digits(p.get("number"))[-10:] for p in (owner.get("phones") or [])}
        if phone in have:
            print("  " + phone + " already on the record - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Phone": phone,
                         "Result": "SKIP already there", "UUID": uuid})
            continue

        tag = rel + " " + first + " " + last
        new_owner = copy.deepcopy(owner)
        new_owner.setdefault("phones", []).append(
            {"number": phone, "type": "UNKNOWN", "tags": [tag]})
        print("  live phones: " + str(sorted(have)))
        print("  + " + phone + " tags ['" + tag + "'] (no dial tier - unscored)")

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
        vph = {digits(p.get("number"))[-10:]
               for p in ((v.get("owner") or {}).get("phones") or [])}
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
