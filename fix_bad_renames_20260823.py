"""Correct the 5 DataSift renames that named the wrong person (Oren approved 8/23).

The 8/22 push (dp_push_renames_20260822.py) wrote DP-guessed heirs as the owner.
The court probe (output/heirs_pr_probe.csv) then showed 5 of those 8 name someone
other than the court's PR - and Silverthorne's name was not a party to the case at
all. See [[project_court_pr_beats_dp_guess]].

Per record:
  - owner first/last  -> the court's PR
  - personal_representative -> the court's PR (overwrites ONLY the value we
    ourselves wrote on 8/22; a PR we did not write is left alone)
  - add tags "PR Corrected" + "Phones - Other Heir" (Oren 8/23: the phones on
    these records belong to the heir we wrongly named, keep them but warn the
    caller)
  - Silverthorne only: clear status "not_interested" -> None. That rejection was
    collected from Henry Silverthorne, who has no connection to the estate, so it
    says nothing about the property (Oren 8/23).

NOT touched: phones, emails, mailing, lists, custom fields, other tags.

Guards - every one must pass or the record is skipped:
  1. live owner == exactly what dp_rename_push_20260822.csv says we wrote
     (proves this is our record and our mistake, not someone's later edit)
  2. live property street starts with the house number from the probe
  3. court PR is non-blank and differs from the live owner
Never blanks a populated field except the one deliberate status clear.
Verifies by GET refetch - the SEARCH index is stale after writes
(project_datasift_search_index_stale).

    python fix_bad_renames_20260823.py            # DRY RUN, writes nothing
    python fix_bad_renames_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / f"fix_bad_renames_20260823{'' if APPLY else '_dryrun'}.csv"

ADD_TAGS = ["PR Corrected", "Phones - Other Heir"]
# The only record whose status we clear, and the exact value we expect to find.
CLEAR_STATUS = {"26E002977-590": "not_interested"}

BAD = ["26E002977-590", "26E003002-590", "26E000978-170",
       "26E002979-590", "26E001070-350"]


def titles(tags) -> list:
    return [t.get("title") if isinstance(t, dict) else t for t in (tags or [])]


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET -> HTTP {r.status_code}")
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def main() -> int:
    print(f"===== fix bad renames {'LIVE' if APPLY else 'DRY RUN'} "
          f"at {_dt.datetime.now()} =====")
    probe = {r["Case No."]: r for r in csv.DictReader(
        open(REPO / "output" / "heirs_pr_probe.csv", encoding="utf-8-sig"))}
    pushed = {r["Case No."]: r for r in csv.DictReader(
        open(REPO / "output" / "dp_rename_push_20260822.csv", encoding="utf-8-sig"))}

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
    for case in BAD:
        q, p = probe[case], pushed[case]
        uuid = p["UUID"]
        court = (q["Court PR"] or "").strip()
        wrote = (p["After"] or "").strip()
        house = (q["Property"] or "").strip().split(" ")[0]
        print(f"\n=== {case}  {q['County']}  {q['Decedent'][:40]}")
        print(f"  we wrote   : {wrote!r}   court says: {court!r} ({q['Court Role']})")

        rec = {"Case No.": case, "UUID": uuid, "Was": wrote, "Now": "",
               "Court Role": q["Court Role"], "Result": ""}

        if not court or len(court.split()) < 2:
            print("  court PR missing/unsplittable - SKIP")
            rec["Result"] = "SKIP no court PR"; rows.append(rec); skipped += 1
            continue
        first, last = court.split()[0], court.split()[-1]

        d = get_prop(h, uuid)
        if not d:
            rec["Result"] = "GET FAILED"; rows.append(rec); failed += 1
            continue
        owner = d.get("owner") or {}
        addr = d.get("address") or {}
        live = (f"{(owner.get('first_name') or '').strip()} "
                f"{(owner.get('last_name') or '').strip()}").strip()
        street = (addr.get("street") or "").strip()
        live_pr = (d.get("personal_representative") or "").strip()
        live_status = d.get("status")
        print(f"  live owner : {live!r}   PR {live_pr!r}   status {live_status!r}")

        # ---- guards -------------------------------------------------
        if live.lower() != wrote.lower():
            print(f"  GUARD: live owner {live!r} != what we wrote {wrote!r} - SKIP")
            rec["Result"] = "SKIP not our write"; rows.append(rec); skipped += 1
            continue
        if house and not street.lower().startswith(house.lower()):
            print(f"  GUARD: street {street!r} does not start {house!r} - SKIP")
            rec["Result"] = "SKIP address"; rows.append(rec); skipped += 1
            continue
        if live.lower() == court.lower():
            print("  already the court's PR - nothing to fix")
            rec["Result"] = "SKIP already correct"; rows.append(rec); skipped += 1
            continue

        # ---- build the write ----------------------------------------
        new_owner = copy.deepcopy(owner)
        new_owner["first_name"], new_owner["last_name"] = first, last
        body = {"owner": new_owner}
        # Overwrite the PR only if it is the value WE wrote on 8/22.
        if live_pr and live_pr.lower() == (p["PR"] or "").strip().lower():
            body["personal_representative"] = court
            print(f"  PR {live_pr!r} was ours -> {court!r}")
        elif live_pr:
            print(f"  PR {live_pr!r} is not ours - left as-is")
        else:
            body["personal_representative"] = court

        clearing = case in CLEAR_STATUS and live_status == CLEAR_STATUS[case]
        if case in CLEAR_STATUS and not clearing:
            print(f"  status is {live_status!r}, expected "
                  f"{CLEAR_STATUS[case]!r} - NOT clearing")

        print(f"  rename {live!r} -> {first} {last!r}; tags +{ADD_TAGS}"
              + ("; status -> None" if clearing else ""))
        print("  phones/emails/mailing/lists untouched "
              f"(phones on file: {len(owner.get('phones') or [])})")

        if not APPLY:
            rec["Now"] = f"{first} {last}"; rec["Result"] = "DRY"
            rows.append(rec); ok += 1
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json=body, timeout=30)
        print(f"  PATCH owner+PR -> {r.status_code} {r.text[:100]}")
        if r.status_code not in (200, 202):
            rec["Result"] = f"PATCH {r.status_code}"; rows.append(rec); failed += 1
            continue

        if clearing:
            # The property PATCH refuses a null status ("This field may not be
            # null"); the UI's "Default" choice is not a status record at all,
            # it is the null state. The dedicated sub-endpoint is the only door.
            rs = requests.post(f"{API}/api/internal/property/{uuid}/status/",
                               headers=h, json={"status": None}, timeout=30)
            print(f"  POST status/ ->None -> {rs.status_code}")

        rt = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                           headers=h, json={"tags": ADD_TAGS}, timeout=30)
        print(f"  add-tags {ADD_TAGS} -> {rt.status_code}")

        # ---- verify by refetch (search index is stale) ---------------
        v = get_prop(h, uuid)
        vo = v.get("owner") or {}
        after = (f"{(vo.get('first_name') or '').strip()} "
                 f"{(vo.get('last_name') or '').strip()}").strip()
        vtags = titles(v.get("tags"))
        good = after.lower() == f"{first} {last}".lower()
        tags_ok = all(t in vtags for t in ADD_TAGS)
        status_ok = (v.get("status") is None) if clearing else True
        print(f"  VERIFY: owner={after!r} PR={(v.get('personal_representative') or '')!r} "
              f"phones={len(vo.get('phones') or [])} tags_ok={tags_ok} "
              f"status={v.get('status')!r} -> {'OK' if good else 'DID NOT STICK'}")
        rec["Now"] = after
        rec["Result"] = ("CORRECTED" if good and tags_ok and status_ok
                         else "PARTIAL" if good else "VOID SAVE")
        rows.append(rec)
        ok += good
        failed += (not good)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n==== {'LIVE' if APPLY else 'DRY'} SUMMARY ====")
    print(f"  ok/would-do {ok}   skipped {skipped}   failed {failed}")
    print(f"wrote {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
