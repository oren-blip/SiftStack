"""Make occupied-hold records CALLABLE but never MAILABLE.

Oren 2026-09-04, approving the gap between two of his own earlier calls:

  * 2026-08-18 [[project_occupied_hold]] -- occupied single-asset estates are
    held from ALL marketing; Step 4.97 tags "Hold - Occupied" and the records
    were de-listed in DataSift. That is why they belong to no list.
  * 2026-08-25 [[feedback_heir_occupied_call_no_mail]] -- "an at-property heir
    is NOT a blanket suppression. Phone outreach is fine; the mail piece is
    what gets held."

The second is narrower and newer, and the CRM only implements the first. Result:
53 records carrying 143 Dial First/Second numbers (two of them Hot Leads) that
nobody can call.

THE ORDER MATTERS. Simply re-listing those records would make them visible to
the MAIL presets too, because none of them exclude "Hold - Occupied":

    06. Needs First Mail  excludes: Do Not Market, Do Not Mail, Sold, Dead Area, Not Buy Box
    07. Mail Monthly      excludes: Do Not Mail, Return Mail, Do Not Market, Sold, Dead Area, Not Buy Box
    08. Vacant Mailing    excludes: Do Not Market, Do Not Mail, Sold, Dead Area, Not Buy Box

So this script runs FIRST: it adds the "Hold - Occupied" tag to the must_not of
those three mail presets. Only once mail is provably blind to them should the
records be put back in a list (separate script).

Every original preset body is written to output/preset_backup_occupied_20260904.json
before any PATCH, and each change is verified by re-GET.

    python add_occupied_hold_mail_exclusion_20260904.py           # dry run
    python add_occupied_hold_mail_exclusion_20260904.py --apply
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

from audit_rename_gap_20260822 import API, token  # noqa: E402

APPLY = "--apply" in sys.argv
BACKUP = REPO / "output" / "preset_backup_occupied_20260904.json"
HOLD_TAG_NAME = "Hold - Occupied"
# Presets that actually SEND mail. "09. Return Mail --> DP" is a routing preset
# for mail that came back, not a send, so it is deliberately left alone.
MAIL_PRESETS = ("06. Needs First Mail", "07. Mail Monthly", "08. Vacant Mailing")


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    tags = requests.get(f"{API}/api/internal/tag/?limit=500", headers=h, timeout=60).json()
    tag_id = {}
    for i in (tags.get("results") or tags.get("data") or []):
        tag_id[i.get("title") or i.get("name")] = str(i.get("uuid"))
    hold = tag_id.get(HOLD_TAG_NAME)
    if not hold:
        print(f"ABORT: no tag named {HOLD_TAG_NAME!r} in the account")
        return 1
    print(f"{HOLD_TAG_NAME} = {hold}")

    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h, timeout=60).json()
    presets = r.get("results") or r.get("data") or r

    backups, changed, already, failed = {}, 0, 0, 0
    for p in presets:
        title = (p.get("title") or p.get("name") or "").strip()
        if not any(title.startswith(m) for m in MAIL_PRESETS):
            continue
        uid = p["uuid"]
        det = requests.get(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                           timeout=60).json()
        det = det.get("data", det)
        filters = det.get("filters") or {}
        backups[uid] = {"title": title, "filters": copy.deepcopy(filters)}

        new = copy.deepcopy(filters)
        must = new.setdefault("must", {})
        mn = must.setdefault("must_not", {})
        ex = list(mn.get("any_tags") or [])
        print(f"\n=== {title}")
        if hold in ex:
            print("  already excludes Hold - Occupied")
            already += 1
            continue
        ex.append(hold)
        mn["any_tags"] = ex
        print(f"  excluded tags {len(ex) - 1} -> {len(ex)} (adding Hold - Occupied)")
        if not APPLY:
            print("  DRY: would PATCH")
            changed += 1
            continue

        BACKUP.parent.mkdir(exist_ok=True)
        BACKUP.write_text(json.dumps(backups, indent=1), encoding="utf-8")
        pr = requests.patch(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                            data=json.dumps({"filters": new}), timeout=60)
        print(f"  PATCH -> HTTP {pr.status_code}")
        vd = requests.get(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                          timeout=60).json()
        vd = vd.get("data", vd)
        got = (((vd.get("filters") or {}).get("must") or {}).get("must_not") or {}).get("any_tags") or []
        if hold in got:
            print("  verified: mail preset now blind to Hold - Occupied")
            changed += 1
        else:
            print("  *** VERIFY FAILED: exclusion not saved")
            failed += 1

    print(f"\n{'would change' if not APPLY else 'changed'}: {changed}   "
          f"already correct: {already}   failed: {failed}")
    if APPLY and backups:
        print(f"Backup of original preset bodies: {BACKUP}")
    if not APPLY:
        print("DRY RUN -- re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
