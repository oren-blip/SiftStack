"""Correct two records whose CRM owner is neither the court's PR nor the deed holder.

    python fix_deed_owner_names_20260823.py            # dry run
    python fix_deed_owner_names_20260823.py --apply

From the 8/23 heir-transfer deed review. Both were found by comparing the
register-of-deeds owner against the CRM, and both were verified against the
court record before being listed here — the 8/22 lesson
([[project_court_pr_beats_dp_guess]]) is that a rename pushed without that
check names the wrong person 5 times out of 8.

26E000508-480 Poplin (Iredell)
    CRM owner is `Rebecca Poplin` — the DECEDENT. The deed (transferred
    2026-04-28) reads BAGGARLEY MICHELLE W + C DILAN WHITE and the court
    appointed "Baggarley, Michelle White". Court and deed AGREE, which is the
    strongest evidence this pipeline produces.

    Note this record arrived via the SiftMap vacant pull, not the probate
    pipeline — it carries Priority 1 / Free & Clear / Absentee Owners and no
    Courthouse Data tag. The stale owner is third-party data, not our mistake,
    but it is being actively marketed, so it is worth the same correction.

26E000743-790 Kesler (Rowan)
    Three different Keslers: CRM says `Christopher`, the court appointed
    `Donald`, the deed reads `KESLER JOHN ROBERT ETAL`. Christopher matches
    neither and is not in dp_log.csv or manual_corrections.csv, so nothing
    deliberate set it.

    Renamed to the court's PR, not the deed holder, because the owner field is
    this pipeline's marketing contact and the PR is who the court authorised to
    sell. John Robert Kesler and the unnamed "ETAL" co-owners are who must sign,
    which is what the record's `Multi-Signer (ETAL)` tag is there to say.

The mailing address is deliberately NOT touched — that is a separate decision,
and on Poplin the address on file (121 Victoria Dr) belongs to whoever SiftMap
had, not necessarily to Michelle Baggarley.
"""
from __future__ import annotations
import argparse
import copy
import csv
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
OUT = REPO / "output" / "deed_owner_fixes_20260823.csv"

# case -> (uuid, expect_first, expect_last, new_first, new_last, source)
FIXES = [
    ("26E000508-480", "83879169-0da7-4574-a4e1-ef71661ac5f2",
     "Rebecca", "Poplin", "Michelle", "Baggarley",
     "court PR + deed agree"),
    ("26E000743-790", "502178f3-1218-4c78-8e3e-27d790b1a1fd",
     "Christopher", "Kesler", "Donald", "Kesler",
     "court PR (deed holder John Robert Kesler ETAL must also sign)"),
]


def headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


def _call(method: str, url: str, **kw):
    """Survive the transient TLS resets apiv2 threw on 2026-08-23."""
    for attempt in range(4):
        try:
            return requests.request(method, url, timeout=30, **kw)
        except requests.exceptions.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def get_record(h: dict, uuid: str) -> dict | None:
    r = _call("GET", f"{API}/api/internal/property/{uuid}/", headers=h)
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("data") or d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    h = headers(token())
    out = []
    for case, uuid, exp_f, exp_l, new_f, new_l, why in FIXES:
        rec = get_record(h, uuid)
        if rec is None:
            print(f"  READ FAILED  {case}")
            out.append({"case": case, "result": "READ FAILED"})
            continue
        o = rec.get("owner") or {}
        live_f = (o.get("first_name") or "").strip()
        live_l = (o.get("last_name") or "").strip()
        street = (rec.get("address") or {}).get("street") or ""

        row = {"case": case, "uuid": uuid, "property": street,
               "was": f"{live_f} {live_l}".strip(),
               "now": f"{new_f} {new_l}", "why": why}

        # Refuse to act on a record that has changed under us since the review.
        if (live_f, live_l) != (exp_f, exp_l):
            if (live_f, live_l) == (new_f, new_l):
                print(f"  SKIP already {new_f} {new_l}  {case}")
                row["result"] = "SKIP already correct"
            else:
                print(f"  SKIP owner moved to {live_f} {live_l!r} (expected "
                      f"{exp_f} {exp_l}) - not overwriting  {case}")
                row["result"] = f"SKIP unexpected owner {live_f} {live_l}"
            out.append(row)
            continue

        if not args.apply:
            print(f"  would rename  {case} | {street:26s} | "
                  f"{live_f} {live_l} -> {new_f} {new_l}   ({why})")
            row["result"] = "DRY RUN"
            out.append(row)
            continue

        # Round-trip the whole owner object; a partial PATCH silently voids the
        # save (project_pr_upgrade_silent_save_failure).
        new_owner = copy.deepcopy(o)
        new_owner["first_name"], new_owner["last_name"] = new_f, new_l
        r = _call("PATCH", f"{API}/api/internal/property/{uuid}/",
                  headers=h, json={"owner": new_owner})
        ok = r.status_code in (200, 201, 202, 204)

        landed = False
        for attempt in range(4):   # the write is durable before the read shows it
            back = get_record(h, uuid)
            bo = (back or {}).get("owner") or {}
            if ((bo.get("first_name") or "").strip() == new_f
                    and (bo.get("last_name") or "").strip() == new_l):
                landed = True
                break
            if attempt < 3:
                time.sleep(3)

        row["result"] = "RENAMED (verified)" if (ok and landed) else "FAILED"
        print(f"  {row['result']:20s} {case} | {live_f} {live_l} -> {new_f} {new_l}")
        out.append(row)

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["case", "uuid", "property", "was",
                                          "now", "why", "result"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print(f"\nwrote {OUT}")
    if not args.apply:
        print("DRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
