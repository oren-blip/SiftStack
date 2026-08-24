"""Overwrite DataSift owner names that disagree with the court record (Oren approved 8/23).

Third and last pass of the 8/23 court-PR cleanup:
  1. fix_bad_renames_20260823.py       - 5 records mis-named by the 8/22 push
  2. push_court_pr_renames_20260823.py - 10 records still blank ("Heirs X")
  3. THIS                              - records an EARLIER DP sweep named, whose
                                         name is not the court's PR

Targets are derived, not hand-typed: rows in output/court_pr_renames_20260823.csv
that the previous pass skipped as "already named", where the live CRM name differs
from the court's PR by first OR last name. Middle-name variants of the same human
(e.g. "Robert Clinton Courteau" vs court "Robert Courteau") are NOT touched.

Per record: owner -> court PR, personal_representative -> court PR, tags
"PR Corrected" + "Phones - Other Heir" (when phones exist). Phones, emails,
mailing, lists, status untouched.

Guards - all must pass:
  1. UUID known from the previous pass (no re-search, no chance of a wrong match)
  2. live owner still equals what that pass observed (nothing changed underneath)
  3. house number still matches the probe's property address
  4. court PR differs from live by first or last name
Every write verified by GET refetch (the SEARCH index is stale after writes).

    python fix_stale_dp_names_20260823.py            # DRY RUN
    python fix_stale_dp_names_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
OUT = REPO / "output" / f"stale_dp_names_20260823{'' if APPLY else '_dryrun'}.csv"


def titles(tags) -> list:
    return [t.get("title") if isinstance(t, dict) else str(t) for t in (tags or [])]


def same_person(live: str, court: str) -> bool:
    """True when the two strings are the same human written differently."""
    lw, cw = live.split(), court.split()
    if not lw or not cw:
        return False
    return lw[0].lower() == cw[0].lower() and lw[-1].lower() == cw[-1].lower()


def targets() -> list:
    src = REPO / "output" / "court_pr_renames_20260823.csv"
    out = []
    for r in csv.DictReader(open(src, encoding="utf-8-sig")):
        if r["Result"] != "SKIP already named":
            continue
        live, court = (r["Was"] or "").strip(), (r["Court PR"] or "").strip()
        if not live or not court or len(court.split()) < 2:
            continue
        if live.lower() == court.lower() or same_person(live, court):
            continue
        if not (r.get("UUID") or "").strip():
            continue
        out.append(r)
    return out


def main() -> int:
    print(f"===== stale DP names {'LIVE' if APPLY else 'DRY RUN'} "
          f"at {_dt.datetime.now()} =====")
    probe = {r["Case No."]: r for r in csv.DictReader(
        open(REPO / "output" / "heirs_pr_probe.csv", encoding="utf-8-sig"))}
    tgts = targets()
    print(f"records whose CRM name disagrees with the court: {len(tgts)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    rows, ok, skipped, failed = [], 0, 0, 0
    for i, t in enumerate(tgts, 1):
        case, uuid = t["Case No."], t["UUID"]
        court, seen = t["Court PR"].strip(), t["Was"].strip()
        first, last = court.split()[0], court.split()[-1]
        house = (probe.get(case, {}).get("Property") or "").strip().split(" ")[0]
        rec = {"Case No.": case, "County": t["County"], "Decedent": t["Decedent"],
               "Was": seen, "Now": "", "Court PR": court,
               "Court Role": t["Court Role"], "UUID": uuid, "Result": ""}
        print(f"\n[{i}/{len(tgts)}] {case}  {t['County']}  {t['Decedent'][:32]}")
        print(f"  CRM {seen!r} -> court {court!r} ({t['Court Role']})")

        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            print(f"  GET -> {r.status_code} - SKIP")
            rec["Result"] = f"GET {r.status_code}"; rows.append(rec); failed += 1
            continue
        d = r.json(); d = d.get("data") or d.get("result") or d
        owner = d.get("owner") or {}
        live = (f"{(owner.get('first_name') or '').strip()} "
                f"{(owner.get('last_name') or '').strip()}").strip()
        street = ((d.get("address") or {}).get("street") or "").strip()
        live_pr = (d.get("personal_representative") or "").strip()
        nph = len(owner.get("phones") or [])

        if live.lower() != seen.lower():
            print(f"  GUARD: live owner {live!r} != {seen!r} seen earlier - SKIP")
            rec["Result"] = "SKIP changed"; rows.append(rec); skipped += 1
            continue
        if house and not street.lower().startswith(house.lower()):
            print(f"  GUARD: {street!r} does not start {house!r} - SKIP")
            rec["Result"] = "SKIP address"; rows.append(rec); skipped += 1
            continue

        new_owner = copy.deepcopy(owner)
        new_owner["first_name"], new_owner["last_name"] = first, last
        body = {"owner": new_owner, "personal_representative": court}
        tags = ["PR Corrected"] + (["Phones - Other Heir"] if nph else [])
        print(f"  PR {live_pr!r} -> {court!r}; phones {nph}; tags +{tags}")

        if not APPLY:
            rec["Now"] = f"{first} {last}"; rec["Result"] = "DRY"
            rows.append(rec); ok += 1
            continue

        pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                            json=body, timeout=30)
        if pr.status_code not in (200, 202):
            print(f"  PATCH -> {pr.status_code} {pr.text[:110]}")
            rec["Result"] = f"PATCH {pr.status_code}"; rows.append(rec); failed += 1
            continue
        rt = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                           headers=h, json={"tags": tags}, timeout=30)

        v = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        vd = v.json(); vd = vd.get("data") or vd.get("result") or vd
        vo = vd.get("owner") or {}
        after = (f"{(vo.get('first_name') or '').strip()} "
                 f"{(vo.get('last_name') or '').strip()}").strip()
        good = after.lower() == f"{first} {last}".lower()
        tags_ok = all(x in titles(vd.get("tags")) for x in tags)
        print(f"  PATCH {pr.status_code} / tags {rt.status_code} / VERIFY {after!r} "
              f"phones={len(vo.get('phones') or [])} tags_ok={tags_ok} "
              f"-> {'OK' if good else 'DID NOT STICK'}")
        rec["Now"] = after
        rec["Result"] = "CORRECTED" if good and tags_ok else "PARTIAL" if good else "VOID"
        rows.append(rec); ok += good; failed += (not good)
        time.sleep(0.4)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n==== {'LIVE' if APPLY else 'DRY'} SUMMARY ====")
    print(f"  corrected {ok}   skipped {skipped}   failed {failed}")
    print(f"wrote {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
