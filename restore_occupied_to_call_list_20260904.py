"""Put occupied-hold records back in a list so the CALL presets can see them.

Step 2 of the change Oren approved 2026-09-04. Step 1
(add_occupied_hold_mail_exclusion_20260904.py) already taught the three mail
presets to exclude "Hold - Occupied", and that is verified -- so restoring list
membership now makes these records callable WITHOUT making them mailable.

RUN STEP 1 FIRST. This script re-checks that the mail presets exclude the tag
and refuses to run if they do not; otherwise re-listing would resume mailing
people whose homes we deliberately agreed not to mail
([[feedback_heir_occupied_call_no_mail]]).

Target: the occupied-hold records that carry a Dial First/Second number -- 53 of
them, 143 good numbers, two marked Hot Lead. Records also carrying a hard
suppression (Sold / Do Not Market / Do Not Mail / Dead Area / Not Buy Box) are
SKIPPED: the call presets exclude those tags anyway, so listing them would
change nothing and would quietly touch records Oren suppressed on purpose.

List used: "PROBATE" (25d1e297...), the conventional one -- 2,599 of the
account's Courthouse Data records live there, versus 120 in the near-identical
"Probate". Picking the wrong twin would have left them just as invisible.

    python restore_occupied_to_call_list_20260904.py           # dry run
    python restore_occupied_to_call_list_20260904.py --apply
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, token  # noqa: E402

APPLY = "--apply" in sys.argv
SRC = REPO / "output" / "nsm_orphans_20260904.csv"
LIST_NAME = "PROBATE"
HOLD_TAG = "Hold - Occupied"
HARD_SUPPRESSIONS = ("Sold", "Do Not Market", "Do Not Mail", "Dead Area", "Not Buy Box")
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
    tag_id = {(i.get("title") or i.get("name")): str(i.get("uuid"))
              for i in (tags.get("results") or tags.get("data") or [])}
    hold = tag_id.get(HOLD_TAG)

    # -- SAFETY GATE: mail must already be blind to the tag ---------------
    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h, timeout=60).json()
    presets = r.get("results") or r.get("data") or r
    unguarded = []
    for p in presets:
        title = (p.get("title") or p.get("name") or "").strip()
        if not any(title.startswith(m) for m in MAIL_PRESETS):
            continue
        det = requests.get(f"{API}/api/internal/filter-preset/{p['uuid']}/",
                           headers=h, timeout=60).json()
        det = det.get("data", det)
        ex = (((det.get("filters") or {}).get("must") or {}).get("must_not") or {}).get("any_tags") or []
        if hold not in ex:
            unguarded.append(title)
    if unguarded:
        print("REFUSING TO RUN — these mail presets do NOT exclude "
              f"{HOLD_TAG!r} yet: {', '.join(unguarded)}")
        print("Run add_occupied_hold_mail_exclusion_20260904.py --apply first.")
        return 1
    print(f"safety gate OK — all {len(MAIL_PRESETS)} mail presets exclude {HOLD_TAG!r}")

    # -- KILLED CASES must never be re-listed -----------------------------
    # The orphan CSV is keyed by CRM uuid and carries no case number, so a
    # killed case is invisible here unless we map it back through the workbook
    # by property address. Vandall 26E000533-540 (killed 2026-08-31, "stay
    # dead" reconfirmed 9/2) showed up in the first dry run with 6 good phones
    # -- re-listing it would have walked a deliberately-killed lead straight
    # back into the call queue. Its "Hold - Occupied" tag is what put it in
    # this set in the first place.
    # Looking the address up from the workbook does NOT work: killing a case
    # REMOVES it from the polished CSVs, so there is nothing left to join on
    # (the same trap that stranded Vandall in the PR push queue). What survives
    # is the human reason text in manual_drops.txt, which names the property --
    # "60% parcel match at 4197 Kent St, heir-occupied". So match the record's
    # street against that text. A false skip costs one lead; a false include
    # resurrects a case Oren deliberately killed.
    try:
        drops_text = (REPO / "manual_drops.txt").read_bytes().decode("utf-8", "replace").lower()
    except OSError as e:
        print(f"WARNING: cannot read manual_drops.txt ({e}) — refusing to run")
        return 1

    def _is_killed(street: str) -> bool:
        parts = (street or "").strip().lower().split()
        if len(parts) < 2 or not parts[0][:1].isdigit():
            return False
        # house number + first street word, e.g. "4197 kent"
        return f"{parts[0]} {parts[1]}" in drops_text

    print(f"kill-list guard: matching candidate streets against "
          f"manual_drops.txt reason text ({len(drops_text)} chars)")

    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig"))
            if HOLD_TAG in r["Tags"] and int(r["Dial First/Second"] or 0) > 0]
    targets, skipped = [], []
    for r in rows:
        hits = [t for t in HARD_SUPPRESSIONS if t in r["Tags"]]
        if _is_killed(r.get("Property") or ""):
            hits = hits + ["KILLED CASE (manual_drops.txt)"]
        (skipped if hits else targets).append((r, hits))

    print(f"occupied-hold records with good phones: {len(rows)}")
    print(f"  to re-list : {len(targets)}   "
          f"({sum(int(r['Dial First/Second']) for r, _ in targets)} good numbers)")
    print(f"  skipped    : {len(skipped)} (already suppressed on purpose)")
    for r, hits in skipped:
        print(f"      SKIP {r['Owner'][:22]:22} {r['Property'][:24]:24} {', '.join(hits)}")
    print(f"Mode: {'APPLY' if APPLY else 'DRY RUN (writes nothing)'}\n")

    done = already = failed = 0
    for r, _ in targets:
        u = r["uuid"]
        d = requests.get(f"{API}/api/internal/property/{u}/", headers=h, timeout=30).json()
        d = d.get("data", d)
        cur = [str(x) for x in (d.get("lists") or [])]
        if LIST_NAME in cur:
            already += 1
            continue
        if not APPLY:
            print(f"  DRY: would add {r['Owner'][:24]:24} {r['Property'][:26]:26} "
                  f"-> {LIST_NAME}  ({r['Dial First/Second']} good)")
            done += 1
            continue
        resp = requests.post(f"{API}/api/internal/property/{u}/add-lists/",
                             headers=h, data=json.dumps({"lists": [LIST_NAME]}), timeout=30)
        v = requests.get(f"{API}/api/internal/property/{u}/", headers=h, timeout=30).json()
        v = v.get("data", v)
        now = [str(x) for x in (v.get("lists") or [])]
        tags_now = [str(t) for t in (v.get("tags") or [])]
        ok = LIST_NAME in now and HOLD_TAG in tags_now
        print(f"  {'OK ' if ok else 'BAD'} {r['Owner'][:22]:22} HTTP {resp.status_code}  "
              f"lists={', '.join(now)[:40]}")
        if ok:
            done += 1
        else:
            failed += 1

    print(f"\n{'would list' if not APPLY else 'listed'}: {done}   "
          f"already there: {already}   failed: {failed}")
    if not APPLY:
        print("DRY RUN -- re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
