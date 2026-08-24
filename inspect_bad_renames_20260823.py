"""READ-ONLY: show live DataSift state for the 5 renames that named the wrong person.

The 8/22 rename push (dp_push_renames_20260822.py) wrote DP-guessed heirs as the
owner. The 8/22-23 court probe (output/heirs_pr_probe.csv) then showed 5 of those
8 name someone other than the court's PR. Before correcting anything, look at what
is actually on each record - owner, PR, mailing, phones, tags - so the fix does not
create a second wrong state (e.g. new owner name mailing to the old person's address).

Writes nothing. python inspect_bad_renames_20260823.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"

# cases where the court PR != what we pushed on 8/22
BAD = ["26E002977-590", "26E003002-590", "26E000978-170",
       "26E002979-590", "26E001070-350"]


def main() -> int:
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
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}"}

    for case in BAD:
        p, q = pushed[case], probe[case]
        r = requests.get(f"{API}/api/internal/property/{q['hex'] and p['UUID']}/",
                         headers=h, timeout=30)
        if r.status_code != 200:
            print(f"{case}: GET -> HTTP {r.status_code}")
            continue
        d = r.json()
        d = d.get("data") or d.get("result") or d
        o = d.get("owner") or {}
        a = d.get("address") or {}
        m = o.get("mailing_address") or d.get("mailing_address") or {}
        print(f"\n=== {case}  {q['County']}  {q['Decedent']}")
        print(f"  property   : {a.get('street')}, {a.get('city')} {a.get('zip')}")
        print(f"  live owner : {(o.get('first_name') or '').strip()} "
              f"{(o.get('last_name') or '').strip()}   (we pushed: {p['After']})")
        print(f"  live PR    : {(d.get('personal_representative') or '').strip()!r}"
              f"   (we pushed: {p['PR']})")
        print(f"  COURT SAYS : {q['Court PR']}  ({q['Court Role']})")
        print(f"  court mail : {q['PR Mailing'] or '(none on file)'}")
        print(f"  live mail  : {m.get('street') or '(blank)'}, {m.get('city') or ''} "
              f"{m.get('zip') or ''}")
        print(f"  phones {len(o.get('phones') or [])}  emails {len(o.get('emails') or [])}"
              f"  status {d.get('property_status') or d.get('status')}")
        print(f"  beneficiaries on file: {q['Beneficiaries'] or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
