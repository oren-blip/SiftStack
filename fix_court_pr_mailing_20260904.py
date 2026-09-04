"""Finish the job pr_upgrade_step started: push the COURT's mailing address.

2026-09-04. `pr_upgrade_step.py --queued` renamed 14 records to the court's PR
and reported success on every one -- names verified correct. But the mailing
address did NOT move on 11 of them, silently: no warning, no failed save, the
UI form was filled and the record saved.

That leaves the WORST possible state. Before the push a record said
"Amy Snipes, 324 Groff St" -- wrong person, wrong address, obviously stale.
After it says "Donna Little, 324 Groff St" -- right person, WRONG address, and
it now looks correct. Mail goes out confidently to the previous person's house.
Nine of them are in a different CITY (Karen Diggs mailed to Charlotte when the
court has her in Kershaw SC; Asha Henman to Seaford when the court says
Chicago).

Why the UI path failed is still unknown -- the zips are all present, so this is
NOT the blank-ZIP validation void from
[[project_pr_upgrade_silent_save_failure]]. Rather than debug the form, this
writes through the API using `owner.address`, the key proven to be the one that
actually persists ([[project_dm_mailing_key_silent_noop]]:
`owner.mailing_address` saves NOTHING at HTTP 200 -- and indeed reads back null
on these records).

Guards:
  * only writes when the workbook has a COURT address (street+city+state+zip);
    a Mailing Address equal to the Property Address is the pipeline's
    "mail it to the house" fallback, not a court address -- skipped
  * owner object round-tripped whole; phones array untouched
    ([[phone-remove-via-owner-patch]]: a trimmed phones array DELETES phones)
  * never blanks a populated field
  * verified by re-GET, including phone count -- never trusts the 200

    python fix_court_pr_mailing_20260904.py            # dry run
    python fix_court_pr_mailing_20260904.py --apply
    python fix_court_pr_mailing_20260904.py --apply --only 26E000150-120
"""
from __future__ import annotations

import copy
import csv
import json
import re
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, search, token  # noqa: E402
from consolidate_weeks import auto_pick_weekly_files  # noqa: E402

APPLY = "--apply" in sys.argv
ONLY = ""
if "--only" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--only") + 1]

CASES = ["26E000150-120", "26E000667-350", "26E000329-540", "26E001915-590",
         "26E001824-590", "26E001820-590", "26E000496-480", "26E000542-790",
         "26E000328-540", "26E001102-350", "26E001141-350", "26E000899-120",
         "26E000868-480", "26E000508-540"]


def _canon(s: str) -> str:
    """Loose address compare so 'Dr'/'Drive' and 'US HWY'/'Us Highway' agree."""
    s = (s or "").lower().replace(",", " ")
    for a, b in ((r"\b(drive|dr)\b", "dr"), (r"\b(avenue|ave)\b", "ave"),
                 (r"\b(street|st)\b", "st"), (r"\b(road|rd)\b", "rd"),
                 (r"\b(trail|trl)\b", "trl"), (r"\b(highway|hwy)\b", "hwy"),
                 (r"\b(north|n)\b", "n"), (r"\b(south|s)\b", "s"),
                 (r"\b(east|e)\b", "e"), (r"\b(west|w)\b", "w"),
                 (r"\b(apartment|apt)\b", "apt")):
        s = re.sub(a, b, s)
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def main() -> int:
    wb: dict[str, dict] = {}
    for (_y, _w), p in sorted(auto_pick_weekly_files(include_archived=True).items()):
        with p.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("Case No.") or "").strip()
                if c in CASES:
                    wb[c] = r

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    fixed = already = skipped = failed = 0
    for case in CASES:
        if ONLY and case != ONLY:
            continue
        r = wb.get(case)
        if not r:
            print(f"{case}: not in workbook — skip")
            skipped += 1
            continue
        street = (r.get("Mailing Address") or "").strip()
        city = (r.get("Mailing City") or "").strip()
        state = (r.get("Mailing State") or "").strip()
        zipc = (r.get("Mailing Zip") or "").strip()
        prop = (r.get("Property Address") or "").strip()

        print(f"\n=== {case}")
        if not (street and city and state and zipc):
            print(f"  SKIP: incomplete court address ({street!r} {city!r} {state!r} {zipc!r})")
            skipped += 1
            continue
        if _canon(street) == _canon(prop):
            print(f"  SKIP: mailing == property ({street}) — that is the pipeline's "
                  f"'mail it to the house' fallback, not a court address")
            skipped += 1
            continue

        num = (prop.split() or [""])[0].lower()
        hits = [x for x in search(h, prop)
                if ((x.get("address") or {}).get("street") or "").lower().startswith(num + " ")]
        if not hits:
            print(f"  SKIP: record not found by property address {prop!r}")
            skipped += 1
            continue
        uuid = hits[0]["uuid"]
        d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        d = d.get("data", d)
        owner = d.get("owner") or {}
        cur = owner.get("address") or {}
        name = " ".join(filter(None, [owner.get("first_name") or "",
                                      owner.get("last_name") or ""])).strip()
        phones_before = len(owner.get("phones") or [])
        cur_str = f"{cur.get('street') or ''}, {cur.get('city') or ''}"
        print(f"  owner  : {name}")
        print(f"  current: {cur_str}")
        print(f"  court  : {street}, {city} {state} {zipc}")

        if _canon(cur_str) == _canon(f"{street}, {city}"):
            print("  already correct")
            already += 1
            continue

        new_owner = copy.deepcopy(owner)
        addr = dict(cur)              # keep county/lat/long/etc, replace the parts we know
        addr.update({"street": street, "city": city, "state": state,
                     "postal_code": zipc})
        # Coordinates belong to the OLD address — stale lat/long on a new street
        # is worse than none, and DataSift re-geocodes.
        for k in ("latitude", "longitude", "county"):
            addr.pop(k, None)
        new_owner["address"] = addr

        if not APPLY:
            print("  DRY: would PATCH owner.address")
            fixed += 1
            continue

        resp = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                              data=json.dumps({"owner": new_owner}), timeout=30)
        print(f"  PATCH -> HTTP {resp.status_code}")
        v = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        v = v.get("data", v)
        vo = v.get("owner") or {}
        va = vo.get("address") or {}
        got = f"{va.get('street') or ''}, {va.get('city') or ''}"
        phones_after = len(vo.get("phones") or [])
        print(f"  verify : {got}   phones {phones_before} -> {phones_after}")
        if _canon(got) != _canon(f"{street}, {city}"):
            print("  *** VERIFY FAILED: mailing did not change")
            failed += 1
        elif phones_after != phones_before:
            print("  *** WARNING: phone count changed")
            failed += 1
        else:
            fixed += 1

    print(f"\n{'would fix' if not APPLY else 'fixed'}: {fixed}   already correct: {already}"
          f"   skipped: {skipped}   failed: {failed}")
    if not APPLY:
        print("DRY RUN — re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
