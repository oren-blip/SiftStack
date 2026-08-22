"""READ-ONLY pass 2: close the NOT FOUNDs left by audit_dp_resolved_heirs_20260822.py.

Two populations were unresolved in pass 1:
  * 24 real Case Nos. with no address in the FTM case->address map, so only a
    surname search ran and it returned many hits.
  * 96 "NSM10 <street>" pseudo-cases (step-10 no-response DM re-traces) whose
    key IS the address, so the FTM map never matched.

Here: NSM10 rows search their embedded street; real cases scan every surname hit
for an owner reading "Heirs <surname>" / "Estate of <surname>" in the logged
county, which is enough to flag a gap for manual confirmation.

Writes NOTHING. Output: output/dp_gap_pass2_20260822.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))

from audit_rename_gap_20260822 import search, token  # noqa: E402

OUT = REPO / "output" / "dp_gap_pass2_20260822.csv"


def main() -> int:
    prev = list(csv.DictReader(
        (REPO / "output" / "dp_resolved_heirs_audit_20260822.csv")
        .open(encoding="utf-8-sig", newline="")))
    todo = [r for r in prev if r["Status"] == "NOT FOUND"]
    print(f"pass-1 NOT FOUNDs to re-check: {len(todo)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    rows, gaps = [], []
    for i, r in enumerate(sorted(todo, key=lambda x: x["Case No."]), 1):
        case = r["Case No."]
        dec = (r["Decedent"] or "").strip()
        # dp_log Decedent is "Surname", "Surname, First Middle", or
        # "First Last (DM, no-response)" for the NSM10 rows.
        surname = dec.split(",")[0].split("(")[0].strip().split()[-1] if dec else ""
        status, live, uuid, prop, note = "STILL NOT FOUND", "", "", "", ""

        if case.startswith("NSM10 "):
            street = case[len("NSM10 "):].strip()
            num = (street.split() or [""])[0].lower()
            hits = search(h, street)
            cand = [x for x in hits
                    if ((x.get("address") or {}).get("street") or "")
                    .lower().startswith(num + " ")] if num else hits
            if len(cand) == 1:
                rec = cand[0]
                o = rec.get("owner") or {}
                live = f"{(o.get('first_name') or '').strip()} {(o.get('last_name') or '').strip()}".strip()
                uuid = rec.get("uuid") or rec.get("id") or ""
                prop = (rec.get("address") or {}).get("street") or street
                status = ("GAP" if (o.get("first_name") or "").strip().lower()
                          .startswith(("heir", "estate")) else "RENAMED")
            else:
                note = f"{len(hits)} hits on street ({len(cand)} after house-no filter)"
        else:
            hits = search(h, surname) if surname else []
            heirsy = []
            for x in hits:
                o = x.get("owner") or {}
                fn = (o.get("first_name") or "").strip()
                ln = (o.get("last_name") or "").strip()
                if not fn.lower().startswith(("heir", "estate")):
                    continue
                blob = f"{fn} {ln}".lower()
                if surname.lower() in blob:
                    heirsy.append(x)
            if heirsy:
                status = "GAP CANDIDATE"
                parts = []
                for x in heirsy[:4]:
                    o = x.get("owner") or {}
                    a = x.get("address") or {}
                    parts.append(f"{(o.get('first_name') or '').strip()} "
                                 f"{(o.get('last_name') or '').strip()}".strip()
                                 + f" @ {(a.get('street') or '').strip()}, "
                                   f"{(a.get('city') or '').strip()}")
                live = " | ".join(parts)
                uuid = heirsy[0].get("uuid") or heirsy[0].get("id") or ""
                prop = (heirsy[0].get("address") or {}).get("street") or ""
                note = f"{len(heirsy)} heirs-named record(s) among {len(hits)} '{surname}' hits"
            else:
                status = "NO HEIRS RECORD"
                note = f"{len(hits)} '{surname}' hits, none owned by Heirs/Estate"

        print(f"[{i:3d}/{len(todo)}] {case:34s} {status:16s} {live[:70]}  {note}")
        rows.append({"Case No.": case, "Status": status, "Live Owner(s)": live,
                     "Decedent": dec, "County": "", "Property": prop,
                     "UUID": uuid, "Note": note,
                     "Doc": r.get("Doc", ""), "DP Date": r.get("DP Date", "")})
        if status in ("GAP", "GAP CANDIDATE"):
            gaps.append(rows[-1])

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["Status"]] = counts.get(r["Status"], 0) + 1
    print("\n==== PASS 2 SUMMARY ====")
    for k in sorted(counts):
        print(f"  {k:18s} {counts[k]}")
    if gaps:
        print(f"\nADDITIONAL 'Heirs' HITS ({len(gaps)}):")
        for g in gaps:
            print(f"  {g['Case No.']:34s} {g['Status']:14s} {g['Live Owner(s)'][:90]}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
