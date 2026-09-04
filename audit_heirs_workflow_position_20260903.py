"""READ-ONLY: where in the DataSift workflow do the "Heirs of" rows actually sit?

Oren, 2026-09-03: "They are callable today: of these, where are they in my
workflow?"

The workbook shows ~149 rows whose CONTACT is still the literal "Heirs"
placeholder, but ~98 of them already carry a DM Name (deep prospecting found a
real decision-maker) and ~76 carry a DM phone. The court-PR-beats-DP-guess rule
deliberately leaves the Personal Representative column reading "Heirs of X"
until the court names someone -- so the sheet LOOKS unworked while the record
may be fully marketable.

This answers: for each such case, what does the live CRM record show --
property status, lists, tags, phone count -- i.e. which marketing lane is it
actually in, if any.

Writes NOTHING. GETs and searches only.

    python audit_heirs_workflow_position_20260903.py
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, search, token  # noqa: E402
from consolidate_weeks import auto_pick_weekly_files  # noqa: E402

OUT = REPO / "output" / "heirs_workflow_position_20260903.csv"


def heirs_rows() -> list[dict]:
    """Every row the workbook shows whose CONTACT is still 'Heirs'."""
    out = []
    for (year, week), path in sorted(auto_pick_weekly_files(include_archived=True).items()):
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                fn = (r.get("First Name") or "").strip().lower()
                pr = (r.get("Personal Representative") or "").strip().lower()
                if fn == "heirs" or pr.startswith("heirs of"):
                    r["_week"] = f"{week} {year}"
                    out.append(r)
    return out


def main() -> int:
    rows = heirs_rows()
    print(f"'Heirs' contact rows in the workbook: {len(rows)}")
    with_dm = [r for r in rows if (r.get("DM Name") or "").strip()]
    print(f"  ...of which already have a DM Name: {len(with_dm)}")
    print(f"  ...of which have a DM Phone       : "
          f"{sum(1 for r in rows if (r.get('DM Phone') or '').strip())}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    results = []
    status_c, lane_c = collections.Counter(), collections.Counter()
    for i, r in enumerate(rows, 1):
        case = (r.get("Case No.") or "").strip()
        street = (r.get("Property Address") or "").strip()
        num = (street.split() or [""])[0].lower()
        rec = None
        for q in [street] if street else []:
            hits = search(h, q)
            if num:
                hits = [x for x in hits
                        if ((x.get("address") or {}).get("street") or "").lower().startswith(num + " ")]
            if len(hits) == 1:
                rec = hits[0]
            elif len(hits) > 1:
                rec = hits[0]
            break
        if not rec:
            status_c["NOT IN CRM"] += 1
            results.append({"Case No.": case, "Week": r["_week"],
                            "Property": street, "DM Name": r.get("DM Name", ""),
                            "DM Phone": r.get("DM Phone", ""),
                            "CRM": "NOT FOUND", "CRM Owner": "",
                            "Still Heirs in CRM": "", "Status": "", "Lists": "",
                            "Tags": "", "Phones": 0, "Dialable": 0,
                            "Lane": "NOT IN CRM"})
            continue

        uuid = rec.get("uuid") or rec.get("id") or ""
        try:
            d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                             timeout=30).json()
        except Exception:  # noqa: BLE001
            d = rec
        d = d.get("data", d) if isinstance(d, dict) else rec

        # Record shape (verified live 2026-09-03): `status` is the lead status
        # string, `property_status` is null; `lists` and `tags` are plain
        # strings; the contact is `owner` (a DICT), not an `owners` list.
        status = (d.get("status") or d.get("property_status") or "") or "(none)"
        if isinstance(status, dict):
            status = status.get("name") or status.get("title") or "(none)"
        lists = sorted({(x.get("name") if isinstance(x, dict) else str(x))
                        for x in (d.get("lists") or [])})
        tags = sorted({(t.get("name") if isinstance(t, dict) else str(t))
                       for t in (d.get("tags") or [])})
        owner = d.get("owner") if isinstance(d.get("owner"), dict) else {}
        phone_objs = list(owner.get("phones") or [])
        for so in (d.get("secondary_owners") or []):
            if isinstance(so, dict):
                phone_objs += list(so.get("phones") or [])
        phones = len(phone_objs)
        dialable = sum(1 for p in phone_objs
                       if any(str(t).startswith("Dial First") or str(t).startswith("Dial Second")
                              for t in (p.get("tags") or [])))
        owner_name = " ".join(filter(None, [owner.get("first_name") or "",
                                            owner.get("last_name") or ""])).strip()
        still_heirs = owner_name.lower().startswith("heirs")

        suppressed = [t for t in tags
                      if t in ("Do Not Mail", "Do Not Market", "Sold", "Needs DP")]
        blocked = [t for t in suppressed if t != "Needs DP"]
        if blocked:
            lane = f"SUPPRESSED ({', '.join(blocked)})"
        elif phones == 0:
            lane = "no phones on record"
        elif "Needs DP" in tags and not any(t.lower().startswith("dp complete") for t in tags):
            lane = "has phones but still flagged Needs DP"
        elif dialable:
            lane = "CALLABLE (Dial First/Second on record)"
        else:
            lane = "phones on record, none Dial First/Second"
        status_c[str(status)] += 1
        lane_c[lane] += 1
        results.append({"Case No.": case, "Week": r["_week"], "Property": street,
                        "DM Name": r.get("DM Name", ""), "DM Phone": r.get("DM Phone", ""),
                        "CRM": uuid, "CRM Owner": owner_name,
                        "Still Heirs in CRM": "yes" if still_heirs else "no",
                        "Status": status, "Lists": ", ".join(lists),
                        "Tags": ", ".join(tags), "Phones": phones,
                        "Dialable": dialable, "Lane": lane})
        if i % 25 == 0:
            print(f"  ...{i}/{len(rows)}")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    print("\n=== CRM property status ===")
    for k, v in status_c.most_common():
        print(f"  {v:4}  {k}")
    print("\n=== marketing lane ===")
    for k, v in lane_c.most_common():
        print(f"  {v:4}  {k}")
    print(f"\nPer-case detail: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
