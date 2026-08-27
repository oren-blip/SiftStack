"""2026-08-26 verification (read-only): for each of the 9 land records missing
an APN, re-open the source CSV row that supplied the parcel and compare its
owner/decedent names against the DataSift record's owner. Guard against
stamping a same-street stranger parcel.

Run:  d:\SiftStack\.venv\Scripts\python.exe d:\SiftStack\apn_gap_verify_20260826.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
OUT = REPO / "output" / "apn_gap_20260826"


def norm_street(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^0\s+", "", s)
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def main() -> int:
    with open(OUT / "land_missing_apn_resolved.csv", newline="",
              encoding="utf-8-sig") as fh:
        targets = list(csv.DictReader(fh))

    for t in targets:
        src_files = sorted(REPO.glob(f"output/**/{t['source']}"))
        if not src_files:
            print(f"?? {t['street']}: source {t['source']} not found")
            continue
        matches = []
        with open(src_files[0], newline="", encoding="utf-8-sig",
                  errors="replace") as fh:
            rd = csv.DictReader(fh)
            cols = rd.fieldnames or []
            acol = next((c for c in cols if c.strip().lower() in
                         ("property address", "property street", "address",
                          "street")), None)
            zcol = next((c for c in cols if c.strip().lower() in
                         ("property zip", "zip", "zip code")), None)
            pcol = next((c for c in cols if c.strip().lower() in
                         ("parcel id", "parcel_id", "apn")), None)
            for row in rd:
                if norm_street(row.get(acol) or "") == norm_street(t["street"]) \
                        and (not zcol or (row.get(zcol) or "").strip()[:5]
                             == t["zip"]):
                    matches.append(row)
        print(f"\n== {t['street']}, {t['city']} {t['zip']}  "
              f"[DataSift owner: {t['owner']}]  -> parcel {t['found_parcel']}")
        for m in matches:
            names = {k: m.get(k) for k in
                     ("full_name", "first_name", "last_name", "decedent_name",
                      "tax_owner_name", "Owner First Name", "Owner Last Name",
                      "Decedent Name", "Personal Representative")
                     if m.get(k)}
            print(f"   src[{t['source']}] parcel={m.get(pcol)!r} names={names}")
        if not matches:
            print("   !! no row re-matched — index picked it from another key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
