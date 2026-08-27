"""Stamp case context onto the court-PR sweep records (Oren approved 8/26).

He found the Headen record (26E002921-590) with no notes and no custom fields —
nothing on the page said what case it was. This fills the "Estate Files"
custom-field group (94) for every record the 8/26 sweep located:

    Case Number   <- sweep CSV
    Decedent      <- sweep CSV
    Beneficiaries <- heirs_pr_probe.csv (court Parties list), if we have it

FILL-BLANKS-ONLY: an existing non-empty value is never overwritten — if a
record already carries a DIFFERENT case number, it is flagged for review
instead. Writes go to PATCH /property/{uuid}/custom-field/update-values/
(the dp_push_punch recipe) and are verified by refetching the values.

    python cf_backfill_20260826.py            # DRY RUN
    python cf_backfill_20260826.py --apply    # live
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
SWEEP_CSV = REPO / "output" / "court_mailing_sweep_20260826.csv"
PROBE_CSV = REPO / "output" / "heirs_pr_probe.csv"
OUT = REPO / "output" / f"cf_backfill_20260826{'' if APPLY else '_dryrun'}.csv"

FIELDS = {  # label -> definition uuid (Estate Files group 94, fetched 8/26)
    "Case Number": "1d7dd246-1fa0-4130-b4fe-08c270958da3",
    "Decedent": "d9cf7ae6-cb4b-4c1a-92a7-e460eae18ed8",
    "Beneficiaries": "9c3fc422-1c39-4326-8561-e9ea67bde08e",
}


def cf_values(h: dict, uuid: str) -> dict[str, str]:
    """label -> current value for one record."""
    r = requests.get(f"{API}/api/internal/property/{uuid}/custom-field/"
                     "?offset=0&limit=1000", headers=h, timeout=30)
    if r.status_code != 200:
        return {}
    out = {}
    for e in (r.json().get("results") or []):
        lab = ((e.get("custom_field") or {}).get("label") or "").strip()
        if lab:
            out[lab] = (e.get("value") or "").strip()
    return out


def main() -> int:
    rows_in = [r for r in csv.DictReader(open(SWEEP_CSV, encoding="utf-8-sig"))
               if (r.get("UUID") or "").strip()]
    benes = {r["Case No."]: (r.get("Beneficiaries") or "").strip()
             for r in csv.DictReader(open(PROBE_CSV, encoding="utf-8-sig"))}
    print(f"{'LIVE' if APPLY else 'DRY RUN'} — records with a UUID: {len(rows_in)}")

    tok = token()
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    out_rows, n_write, n_noop, n_flag, n_fail = [], 0, 0, 0, 0
    for i, r in enumerate(rows_in, 1):
        case, uuid = r["Case No."], r["UUID"].strip()
        wanted = {"Case Number": case, "Decedent": (r.get("Decedent") or "").strip()}
        if benes.get(case):
            wanted["Beneficiaries"] = benes[case]
        cur = cf_values(h, uuid)
        items, skipped, conflict = [], [], ""
        for lab, val in wanted.items():
            if not val:
                continue
            have = cur.get(lab, "")
            if have:
                if lab == "Case Number" and have != case:
                    conflict = f"record carries case {have!r}, sweep says {case!r}"
                skipped.append(lab)
                continue
            items.append({"field_uuid": FIELDS[lab], "value": val})
        rec = {"Case No.": case, "UUID": uuid,
               "Writes": "|".join(x["value"][:30] for x in items),
               "Kept existing": "|".join(skipped), "Result": "", "Note": conflict}
        print(f"[{i}/{len(rows_in)}] {case}  writes={len(items)} "
              f"keep={skipped or '-'}{'  CONFLICT: ' + conflict if conflict else ''}")
        if conflict:
            rec["Result"] = "FLAG case-number conflict"
            out_rows.append(rec); n_flag += 1
            continue
        if not items:
            rec["Result"] = "OK nothing to fill"
            out_rows.append(rec); n_noop += 1
            continue
        if not APPLY:
            rec["Result"] = "DRY would write " + ", ".join(
                x["field_uuid"][:8] for x in items)
            out_rows.append(rec); n_write += 1
            continue
        resp = requests.patch(
            f"{API}/api/internal/property/{uuid}/custom-field/update-values/",
            headers=h, data=json.dumps(items), timeout=30)
        after = cf_values(h, uuid)
        good = (resp.status_code in (200, 202)
                and all(after.get(lab, "") for lab in wanted if wanted[lab]))
        rec["Result"] = "WRITTEN" if good else f"FAILED HTTP {resp.status_code}"
        if not good:
            rec["Note"] = (resp.text or "")[:150]
        out_rows.append(rec)
        n_write, n_fail = (n_write + 1, n_fail) if good else (n_write, n_fail + 1)
        print(f"    PATCH -> {resp.status_code}  verify "
              f"{'OK' if good else 'FAILED'}")

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n===== {'written' if APPLY else 'would write'}: {n_write}   "
          f"already filled: {n_noop}   flagged: {n_flag}   failed: {n_fail}")
    print(f"results -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
