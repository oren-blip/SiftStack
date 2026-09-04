"""READ-ONLY: where do tonight's 27 court-named-PR cases sit in the workflow?

Oren, 2026-09-04: "as we find new court PRs, I am not seeing them in my
workflow. Should we send them back to the beginning of NSM so I can call/text?
Some will already have been sent mail, but maybe to the wrong address?"

Three things this answers, per case:
  1. Does DataSift still show the OLD placeholder owner? (we fixed the workbook,
     not the CRM -- the push queue is the bridge, and it is manual)
  2. Has it been MAILED already, and was the mail sent to an address that
     differs from the court's PR address we just learned?
  3. What lists / tags / status is it carrying now -- i.e. is it in a lane at all

Writes NOTHING. GETs and searches only.

    python audit_court_pr_workflow_20260904.py
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, search, token  # noqa: E402
from consolidate_weeks import auto_pick_weekly_files  # noqa: E402

CASES = [c.strip() for c in
         (REPO / "output" / "court_pr_recovered_20260903.txt")
         .read_text(encoding="utf-8").splitlines() if c.strip()]
OUT = REPO / "output" / "court_pr_workflow_20260904.csv"


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace(".", "").replace(",", "").split())


def main() -> int:
    # Our side: what the court just told us, from the polished weekly CSVs.
    ours: dict[str, dict] = {}
    for (_y, _w), p in sorted(auto_pick_weekly_files(include_archived=True).items()):
        with p.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("Case No.") or "").strip()
                if c in CASES:
                    ours[c] = r
    print(f"court-named PR cases recovered: {len(CASES)}   found in workbook: {len(ours)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    rows, lane_c, mail_c = [], collections.Counter(), collections.Counter()
    for case in CASES:
        r = ours.get(case, {})
        street = (r.get("Property Address") or "").strip()
        num = (street.split() or [""])[0].lower()
        court_pr = (r.get("Personal Representative") or "").strip()
        court_mail = ", ".join(x for x in [(r.get("Mailing Address") or "").strip(),
                                           (r.get("Mailing City") or "").strip()] if x)

        rec = None
        if street:
            hits = [x for x in search(h, street)
                    if ((x.get("address") or {}).get("street") or "").lower().startswith(num + " ")]
            if hits:
                rec = hits[0]
        if not rec:
            lane_c["NOT IN CRM"] += 1
            rows.append({"Case No.": case, "Court PR": court_pr, "Property": street,
                         "In CRM": "no", "CRM Owner": "", "CRM Mailing": "",
                         "Court Mailing": court_mail, "Mail Address Wrong": "",
                         "Mailed": "", "Last Mailed": "", "Calls": "", "SMS": "",
                         "Phones": 0, "Status": "", "Lists": "", "Lane": "NOT IN CRM"})
            continue

        uuid = rec.get("uuid") or ""
        d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        d = d.get("data", d)
        owner = d.get("owner") or {}
        crm_owner = " ".join(filter(None, [owner.get("first_name") or "",
                                           owner.get("last_name") or ""])).strip()
        oaddr = owner.get("address") or {}
        crm_mail = ", ".join(x for x in [(oaddr.get("street") or "").strip(),
                                         (oaddr.get("city") or "").strip()] if x)
        mailed = int(d.get("directmail_attempts") or 0)
        last_mailed = d.get("last_direct_mailed") or ""
        calls = int(d.get("predictivecall_attempts") or 0)
        sms = int(d.get("sms_attempts") or 0)
        phones = len(owner.get("phones") or [])
        status = d.get("status") or "(none)"
        lists = ", ".join(sorted(str(x) for x in (d.get("lists") or [])))
        tags = sorted(str(t) for t in (d.get("tags") or []))

        still_placeholder = crm_owner.lower().startswith(("heirs", "estate"))
        # Did mail go somewhere other than where the court says the PR lives?
        mail_wrong = ""
        if mailed and court_mail and crm_mail:
            mail_wrong = "yes" if _norm(crm_mail) != _norm(court_mail) else "no"
        if mail_wrong == "yes":
            mail_c["mailed to an address the court disagrees with"] += 1
        elif mailed:
            mail_c["mailed, address matches the court"] += 1
        else:
            mail_c["never mailed"] += 1

        if still_placeholder:
            lane = "CRM still shows placeholder owner"
        elif any(t in tags for t in ("Do Not Market", "Do Not Mail", "Sold")):
            lane = "suppressed"
        elif not lists:
            lane = "in CRM, no list"
        else:
            lane = "real owner, in a list"
        lane_c[lane] += 1

        rows.append({"Case No.": case, "Court PR": court_pr, "Property": street,
                     "In CRM": "yes", "CRM Owner": crm_owner, "CRM Mailing": crm_mail,
                     "Court Mailing": court_mail, "Mail Address Wrong": mail_wrong,
                     "Mailed": mailed, "Last Mailed": str(last_mailed)[:10],
                     "Calls": calls, "SMS": sms, "Phones": phones,
                     "Status": status, "Lists": lists, "Lane": lane})

    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print("\n=== where they sit ===")
    for k, v in lane_c.most_common():
        print(f"  {v:3}  {k}")
    print("\n=== mail history ===")
    for k, v in mail_c.most_common():
        print(f"  {v:3}  {k}")
    touched = [r for r in rows if (r["Mailed"] or 0) or (r["Calls"] or 0) or (r["SMS"] or 0)]
    print(f"\nalready worked (mail/call/text attempted): {len(touched)} of {len(rows)}")
    print(f"\nPer-case detail: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
