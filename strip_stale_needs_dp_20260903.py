"""Remove the stale "Needs DP" tag from records that already have a REAL owner
and dialable phones.

Context (2026-09-03): the workflow audit found 20 records tagged "Needs DP" that
carry phones -- several with 6-7 Dial First/Second numbers -- sitting in a
research bucket instead of a call queue.

BUT only 3 of the 20 are safe. **17 still have owner = "Heirs <Surname>" in
DataSift**, so their "Needs DP" tag is CORRECT: phones landed (DataSift skip
trace / SmartSkip pushes) but no human was ever identified. Stripping the tag
there would push a placeholder person into calling -- exactly the failure mode
in [[dp-complete-tag-without-rename]]. Several are deliberate holds under the
court-PR-beats-DP-guess rule (26E001146-350 McClure, 26E000844-480 Privott).

So this touches ONLY records whose CRM owner is a real name.

Guards, per [[project_pr_upgrade_silent_save_failure]] and
[[project_datasift_search_index_stale]]:
  * re-GET each record first; skip if the owner reads "Heirs ..." after all
  * skip if the tag isn't actually present
  * verify by re-GET after the write -- never trust HTTP 200
  * never verify via search (the index is stale after writes)

    python strip_stale_needs_dp_20260903.py           # dry run
    python strip_stale_needs_dp_20260903.py --apply
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, token  # noqa: E402

TAG = "Needs DP"
AUDIT = REPO / "output" / "heirs_workflow_position_20260903.csv"
APPLY = "--apply" in sys.argv


def main() -> int:
    rows = [r for r in csv.DictReader(AUDIT.open(encoding="utf-8-sig"))
            if "Needs DP" in r["Lane"]]
    safe = [r for r in rows if r["Still Heirs in CRM"] == "no"]
    held = [r for r in rows if r["Still Heirs in CRM"] == "yes"]

    print(f"Tagged 'Needs DP' with phones on record : {len(rows)}")
    print(f"  SAFE  (real owner name in CRM)        : {len(safe)}")
    print(f"  HELD  (owner still 'Heirs X')         : {len(held)}  <- tag is correct, left alone")
    print(f"Mode: {'APPLY' if APPLY else 'DRY RUN (writes nothing)'}\n")
    for r in held:
        print(f"  HELD  {r['Case No.']:18} {r['CRM Owner'][:24]:24} "
              f"{r['Phones']} phone(s) but no identified person")
    print()
    if not safe:
        return 0

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    done = skipped = failed = 0
    for r in safe:
        uuid, case = r["CRM"], r["Case No."]
        print(f"=== {case}  {r['CRM Owner']}  ({r['Property']})")
        d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        d = d.get("data", d)
        owner = d.get("owner") or {}
        name = " ".join(filter(None, [owner.get("first_name") or "",
                                      owner.get("last_name") or ""])).strip()
        tags = [t.get("title") if isinstance(t, dict) else str(t)
                for t in (d.get("tags") or [])]
        if name.lower().startswith("heirs"):
            print(f"  SKIP: owner reads {name!r} on re-GET -- tag is correct")
            skipped += 1
            continue
        if TAG not in tags:
            print(f"  SKIP: {TAG!r} not on the record any more")
            skipped += 1
            continue
        if not APPLY:
            print(f"  DRY: would remove {TAG!r} from owner {name!r}")
            continue
        resp = requests.post(f"{API}/api/internal/property/{uuid}/remove-tags/",
                             headers=h, json={"tags": [TAG]}, timeout=30)
        print(f"  remove-tags -> HTTP {resp.status_code}")
        # Never trust the 200 -- read it back.
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        chk = chk.get("data", chk)
        now = [t.get("title") if isinstance(t, dict) else str(t)
               for t in (chk.get("tags") or [])]
        if TAG in now:
            print("  *** VERIFY FAILED: tag still present after write")
            failed += 1
        else:
            print(f"  verified removed. Owner {name!r}, "
                  f"{r['Dialable']} dialable phone(s) -- now free to flow into the call lanes.")
            done += 1

    print(f"\nremoved: {done}   skipped: {skipped}   failed: {failed}")
    if not APPLY:
        print("DRY RUN -- re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
