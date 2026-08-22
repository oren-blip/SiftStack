"""READ-ONLY audit #2: every DP-RESOLVED case still owned by "Heirs ..." in DataSift.

audit_rename_gap_20260822.py only walked the 36 cases that had a First/Last Name
correction queued in manual_corrections.csv. Oren then hit ANOTHER surviving-spouse
case whose DP report reads resolved while DataSift still shows "Heirs <Decedent>",
so the real population is dp_log.csv: 211 unique cases logged Outcome=resolved.

Writes NOTHING. Every call is a GET / search. Safe to run any time.

    cd d:\SiftStack
    python audit_dp_resolved_heirs_20260822.py

Output: output/dp_resolved_heirs_audit_20260822.csv + console summary.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))

from audit_rename_gap_20260822 import (  # noqa: E402
    API, case_addresses, queued_renames, search, token,
)

OUT = REPO / "output" / "dp_resolved_heirs_audit_20260822.csv"
_DM = re.compile(r"\bDM\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})")
_PR = re.compile(r"\b(?:PR|widow|widower)\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})")


def resolved_cases() -> dict[str, dict[str, str]]:
    """Case No. -> latest resolved dp_log row (dedup: last log entry wins)."""
    out: dict[str, dict[str, str]] = {}
    with (REPO / "dp_log.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("Outcome") or "").strip().lower() != "resolved":
                continue
            case = (row.get("Case No.") or "").strip()
            if case:
                out[case] = row
    return out


def hinted_name(notes: str) -> str:
    for pat in (_DM, _PR):
        m = pat.search(notes or "")
        if m:
            return m.group(1).strip()
    return ""


def main() -> int:
    cases = resolved_cases()
    addrs = case_addresses()
    queued = queued_renames()
    print(f"DP-resolved cases in dp_log.csv: {len(cases)}")
    print(f"of those, with a queued rename in manual_corrections.csv: "
          f"{sum(1 for c in cases if c in queued)}")

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    rows, gaps = [], []
    for i, case in enumerate(sorted(cases), 1):
        log = cases[case]
        decedent = (log.get("Decedent") or "").strip()
        notes = (log.get("Notes") or "").strip()
        q = queued.get(case, {})
        want = f"{q.get('first name','')} {q.get('last name','')}".strip() or hinted_name(notes)
        street, city = addrs.get(case, ("", ""))
        rec, note = None, ""

        num = (street.split() or [""])[0].lower() if street else ""
        surname = (q.get("last name") or "").strip() or decedent
        for term in ([street] if street else []) + ([surname] if surname else []):
            hits = search(h, term)
            if len(hits) == 1:
                rec = hits[0]
                break
            if len(hits) > 1:
                exact = hits
                if num:
                    exact = [x for x in exact
                             if ((x.get("address") or {}).get("street") or "")
                             .lower().startswith(num + " ")]
                if len(exact) == 1:
                    rec = exact[0]
                    break
                note = f"{len(hits)} hits on {term!r} ({len(exact)} after filter)"

        if rec is None:
            status, live, uuid, tags = "NOT FOUND", "", "", []
        else:
            o = rec.get("owner") or {}
            first = (o.get("first_name") or "").strip()
            last = (o.get("last_name") or "").strip()
            live = f"{first} {last}".strip()
            uuid = rec.get("uuid") or rec.get("id") or ""
            tags = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (rec.get("tags") or [])]
            status = "GAP" if first.lower().startswith(("heir", "estate")) else "RENAMED"

        dp_done = any("dp complete" in t.lower() for t in tags)
        print(f"[{i:3d}/{len(cases)}] {case:20s} {status:9s} live={live!r:26s} "
              f"want={want or '?'!r}{'  [DP Complete]' if dp_done else ''}"
              f"{'  ' + note if note else ''}")
        rows.append({"Case No.": case, "Status": status, "Live Owner": live,
                     "Wanted Owner": want, "Decedent": decedent,
                     "Queued in manual_corrections": "yes" if q else "no",
                     "DP Complete tag": "yes" if dp_done else "no",
                     "Property": f"{street}, {city}".strip(", "),
                     "DP Date": (log.get("Date") or "").strip(),
                     "Doc": (log.get("Doc") or "").strip(),
                     "UUID": uuid, "Note": note, "DP Notes": notes[:160]})
        if status == "GAP":
            gaps.append(rows[-1])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["Status"]] = counts.get(r["Status"], 0) + 1
    print("\n==== SUMMARY ====")
    for k in sorted(counts):
        print(f"  {k:10s} {counts[k]}")
    if gaps:
        print(f"\nSTILL 'Heirs' IN DATASIFT ({len(gaps)}):")
        for g in gaps:
            print(f"  {g['Case No.']:20s} {g['Live Owner']!r} -> {g['Wanted Owner'] or '?'!r}"
                  f"   {g['Property']}   queued={g['Queued in manual_corrections']}"
                  f" dp_tag={g['DP Complete tag']}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
