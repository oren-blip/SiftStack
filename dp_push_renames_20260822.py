"""Rename the 8 DP-resolved estates still owned by "Heirs ..." in DataSift.

Found by audit_dp_resolved_heirs_20260822.py + verify_gaps_by_uuid_20260822.py:
9 of 211 DP-resolved cases never got the owner rename pushed. Oren approved 8 on
2026-08-22 (Yow 26E000776-790 excluded - its DP report flags the matched parcel
may be a different Robert Yow, and the record is tagged Do Not Market).

Owner PATCH recipe + identity guard reused from dp_push_punch_20260822.py.

SCOPE: owner first/last name ONLY, plus personal_representative if it is blank.
Phones, mailing, tags, lists, custom fields are NOT touched - the "Needs DP" /
missing "DP Complete" tag gap is a separate decision.

Verification refetches GET /property/{uuid}/ after each write, because the SEARCH
index is stale for ~15 min after a write (see project_datasift_search_index_stale).

    python dp_push_renames_20260822.py            # DRY RUN, writes nothing
    python dp_push_renames_20260822.py --apply    # live
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
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / f"dp_rename_push_20260822{'' if APPLY else '_dryrun'}.csv"

# (case, uuid, first, last, guard_surname, guard_house_no, PR full name, label)
SPECS = [
    ("26E003002-590", "e8a8b451-94da-40fa-98bd-529a359bbf49", "Jerry", "Jenkins",
     "jenkins", "7513", "Jerry Charles Jenkins",
     "Jenkins - 7513 Surprise Ct, Charlotte (surviving spouse, deed co-owner)"),
    # Guard is 2149, not the workbook's 2137: this estate is a two-parcel lot
    # cluster (PID 3661868120 @ 2137 main + PID 3661951739 @ 2149) and the
    # DataSift record landed on 2149. Confirmed sole Vance record on that road,
    # tagged NC Estates Week 29 2026 + Lot Cluster. NOTE for Oren: 2149 is where
    # DM Michael Vance lives, so this record mails the heir-occupied parcel, not
    # the 2137 main parcel.
    ("26E000432-540", "4572ef30-f0d1-4d5d-b9d9-d8d9a0dfebe9", "Michael", "Vance",
     "vance", "2149", "Michael E Vance",
     "Vance - 2149 Brevard Place Rd, Iron Station (lot cluster w/ 2137 main)"),
    ("26E000905-350", "f8cfc3ae-90f2-4944-9ed9-e383b2700164", "Douglas", "Smith",
     "smith", "106", "Douglas Alan Smith",
     "Smith - 106 Sloan St, Belmont"),
    ("26E000978-170", "0f300394-ecb5-4b42-97b9-7134fbac8e12", "Richard", "Sigmon",
     "sigmon", "1026", "Richard Lee Sigmon",
     "Sigmon - 1026 10th St Ct NW, Hickory"),
    ("26E002979-590", "36a6f7b1-8779-4ce6-be3a-02c16900502a", "Arceal", "Dudley",
     "dudley", "9112", "Arceal Dudley",
     "Dudley - 9112 Tree Haven Dr, Charlotte"),
    ("26E000740-480", "2e9138ba-a7b9-487b-85ab-985cee10e784", "Raymond", "Hill",
     "hill", "306", "Raymond Stephen Hill",
     "Hill - 306 S Greenbriar Rd, Harmony (4 co-equal children; first-call son)"),
    ("26E001070-350", "2c19027b-d496-4d62-9c73-101ab549f99e", "Richard", "Peche",
     "peche", "821", "Richard S Peche",
     "Peche - 821 S Main St, Belmont (3 sons; first-call son)"),
    ("26E002977-590", "b701b80d-2452-42ad-9605-9da4e62294f0", "Henry", "Silverthorne",
     "silverthorne", "8228", "Henry Doug Silverthorne",
     "Silverthorne - 8228 Cedarbrook Dr, Charlotte (relationship VERIFY per DP)"),
]


def titles(items) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t) for t in (items or [])]


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET {uuid} -> HTTP {r.status_code}")
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def main() -> int:
    print(f"===== rename push {'LIVE' if APPLY else 'DRY RUN'} at {_dt.datetime.now()} =====")
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    rows = []
    ok = skipped = failed = 0
    for case, uuid, fn, ln, g_last, g_num, pr_name, label in SPECS:
        print(f"\n=== {case}  {label}")
        d = get_prop(h, uuid)
        if not d:
            failed += 1
            rows.append({"Case No.": case, "Result": "GET FAILED", "Before": "",
                         "After": "", "PR": "", "UUID": uuid})
            continue
        owner = d.get("owner") or {}
        addr = d.get("address") or {}
        before = (f"{(owner.get('first_name') or '').strip()} "
                  f"{(owner.get('last_name') or '').strip()}").strip()
        street = (addr.get("street") or "").strip()
        live_pr = (d.get("personal_representative") or "").strip()
        print(f"  live owner : {before!r}")
        print(f"  live addr  : {street}, {addr.get('city')}")
        print(f"  live PR    : {live_pr!r}")
        print(f"  live phones: {len(owner.get('phones') or [])}   "
              f"tags: {len(titles(d.get('tags')))}")

        # identity guard - surname must be in the live owner text, house no must match
        if g_last not in before.lower():
            print(f"  IDENTITY MISMATCH (surname {g_last!r} not in {before!r}) - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP identity", "Before": before,
                         "After": "", "PR": live_pr, "UUID": uuid})
            continue
        if not street.lower().startswith(g_num + " "):
            print(f"  IDENTITY MISMATCH (street {street!r} != {g_num}...) - SKIP")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP identity", "Before": before,
                         "After": "", "PR": live_pr, "UUID": uuid})
            continue
        if not (owner.get("first_name") or "").strip().lower().startswith(("heir", "estate")):
            print("  owner is NOT a Heirs/Estate placeholder - SKIP (nothing to fix)")
            skipped += 1
            rows.append({"Case No.": case, "Result": "SKIP already named", "Before": before,
                         "After": "", "PR": live_pr, "UUID": uuid})
            continue

        new_owner = copy.deepcopy(owner)
        new_owner["first_name"], new_owner["last_name"] = fn, ln
        body = {"owner": new_owner}
        # fill-if-blank only; never clobber a live PR (project_pr_upgrade_silent_save_failure)
        if not live_pr:
            body["personal_representative"] = pr_name
            print(f"  PR blank -> will set {pr_name!r}")
        elif live_pr.lower() != pr_name.lower():
            print(f"  PR already {live_pr!r} (DP says {pr_name!r}) - left as-is")

        print(f"  rename {before!r} -> {fn} {ln!r}; phones/mailing/tags/lists untouched")
        if not APPLY:
            print("  DRY: would PATCH owner"
                  + (" + PR" if "personal_representative" in body else ""))
            rows.append({"Case No.": case, "Result": "DRY", "Before": before,
                         "After": f"{fn} {ln}",
                         "PR": body.get("personal_representative", live_pr), "UUID": uuid})
            ok += 1
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           data=json.dumps(body), timeout=30)
        print(f"  PATCH -> {r.status_code} {r.text[:120]}")
        if r.status_code not in (200, 202):
            failed += 1
            rows.append({"Case No.": case, "Result": f"PATCH {r.status_code}",
                         "Before": before, "After": "", "PR": live_pr, "UUID": uuid})
            continue

        # verify by refetch - search index is stale, detail endpoint is not
        v = get_prop(h, uuid)
        vo = v.get("owner") or {}
        after = (f"{(vo.get('first_name') or '').strip()} "
                 f"{(vo.get('last_name') or '').strip()}").strip()
        vpr = (v.get("personal_representative") or "").strip()
        vph = len(vo.get("phones") or [])
        good = after.lower() == f"{fn} {ln}".lower()
        print(f"  VERIFY refetch: owner={after!r} PR={vpr!r} phones={vph} "
              f"-> {'OK' if good else 'DID NOT STICK'}")
        ok += good
        failed += (not good)
        rows.append({"Case No.": case, "Result": "RENAMED" if good else "VOID SAVE",
                     "Before": before, "After": after, "PR": vpr, "UUID": uuid})

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n==== {'LIVE' if APPLY else 'DRY'} SUMMARY ====")
    print(f"  ok/would-do {ok}   skipped {skipped}   failed {failed}")
    print(f"wrote {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
