"""2026-08-26 phase 2 (still READ-ONLY): full-record fetch for the NSM union,
true land classification (structure_type + 0-prefix), true APN-blank check,
then parcel resolution against the local weekly pipeline CSVs.

The list endpoint's rows carry NO structure_type/parcel_id — phase 1's
"0 have an APN" was an artifact. This GETs every record individually.

Run:  d:\SiftStack\.venv\Scripts\python.exe d:\SiftStack\apn_gap_phase2_20260826.py
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from apn_gap_scout_20260826 import API, OUT, get_token, headers

FULL = OUT / "records_full.json"


def fetch_full(h: dict, uuids: list[str]) -> list[dict]:
    if FULL.exists():
        cached = json.loads(FULL.read_text(encoding="utf-8"))
        if len(cached) >= len(uuids):
            print(f"using cached {len(cached)} full records")
            return cached

    def one(u):
        r = requests.get(f"{API}/api/internal/property/{u}/", headers=h,
                         timeout=30)
        return r.json() if r.status_code == 200 else {"uuid": u, "_error": r.status_code}

    out = []
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, rec in enumerate(ex.map(one, uuids), 1):
            out.append(rec)
            if i % 100 == 0:
                print(f"  {i}/{len(uuids)} fetched")
    FULL.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def norm_street(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^0\s+", "", s)          # vacant-lot 0-prefix
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def build_local_index() -> dict[tuple[str, str], dict]:
    """street+zip -> {parcel, source_file}. Scans weekly pipeline CSVs that
    carry both an address and a Parcel ID column."""
    idx: dict[tuple[str, str], dict] = {}
    files = sorted(REPO.glob("output/**/*.csv"))
    for f in files:
        if "apn_gap" in str(f):
            continue
        try:
            with open(f, newline="", encoding="utf-8-sig", errors="replace") as fh:
                rd = csv.DictReader(fh)
                cols = rd.fieldnames or []
                pcol = next((c for c in cols if c and c.strip().lower()
                             in ("parcel id", "parcel_id", "apn")), None)
                acol = next((c for c in cols if c and c.strip().lower() in
                             ("property address", "property street", "address",
                              "street")), None)
                zcol = next((c for c in cols if c and c.strip().lower() in
                             ("property zip", "zip", "property zip code",
                              "postal_code", "zip code")), None)
                if not (pcol and acol):
                    continue
                for row in rd:
                    parcel = (row.get(pcol) or "").strip()
                    if not parcel:
                        continue
                    st = norm_street(row.get(acol) or "")
                    zp = ((row.get(zcol) or "").strip()[:5]) if zcol else ""
                    if not st:
                        continue
                    key = (st, zp)
                    # newer files win (sorted order: later mtime not guaranteed,
                    # but weekly names sort by date)
                    idx[key] = {"parcel": parcel, "src": f.name,
                                "case": (row.get("Case No.") or row.get("Case No") or "").strip()}
                    idx.setdefault((st, ""), {"parcel": parcel, "src": f.name,
                                              "case": idx[key]["case"]})
        except Exception as e:
            print(f"  (skip {f.name}: {e})")
    print(f"local index: {len(idx)} street+zip -> parcel entries")
    return idx


def main() -> int:
    union = json.loads((OUT / "records_union.json").read_text(encoding="utf-8"))
    membership: dict[str, list[str]] = {}
    for rec in union:
        membership[rec.get("uuid")] = []
    # membership per preset was only printed in phase 1; re-derive from the
    # phase-1 CSVs if needed. For the fix itself membership is cosmetic.
    miss_csv = OUT / "land_missing_apn.csv"
    presets_by_uuid = {}
    if miss_csv.exists():
        with open(miss_csv, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                presets_by_uuid[row["uuid"]] = row["presets"]

    h = headers(get_token())
    full = fetch_full(h, [r.get("uuid") for r in union])

    land = []
    for rec in full:
        if rec.get("_error"):
            continue
        st_type = (rec.get("structure_type") or "").lower()
        street = ((rec.get("address") or {}).get("street") or "").strip()
        is_land = (any(k in st_type for k in ("vacant", "land", "lot"))
                   or street.startswith("0 "))
        if not is_land:
            continue
        parcel = (rec.get("parcel_id") or rec.get("apn") or "")
        land.append({
            "uuid": rec.get("uuid"),
            "street": street,
            "city": ((rec.get("address") or {}).get("city") or ""),
            "zip": str((rec.get("address") or {}).get("postal_code") or "")[:5],
            "owner": " ".join(x for x in [
                (rec.get("owner") or {}).get("first_name"),
                (rec.get("owner") or {}).get("last_name")] if x),
            "structure_type": rec.get("structure_type") or "",
            "parcel_id": str(parcel or "").strip(),
            "presets": presets_by_uuid.get(rec.get("uuid"), ""),
        })

    missing = [r for r in land if not r["parcel_id"]]
    print(f"\nLAND records in NSM flow: {len(land)}; missing APN: {len(missing)}")

    idx = build_local_index()
    for r in missing:
        key = (norm_street(r["street"]), r["zip"])
        hit = idx.get(key) or idx.get((norm_street(r["street"]), ""))
        if hit:
            r["found_parcel"] = hit["parcel"]
            r["source"] = hit["src"]
            r["case_no"] = hit.get("case", "")
        else:
            r["found_parcel"] = ""
            r["source"] = ""
            r["case_no"] = ""

    with open(OUT / "land_missing_apn_resolved.csv", "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(missing[0].keys()) if missing
                           else ["uuid"])
        w.writeheader()
        w.writerows(missing)

    hits = [r for r in missing if r["found_parcel"]]
    print(f"resolved from local CSVs: {len(hits)}/{len(missing)}")
    for r in missing:
        mark = r["found_parcel"] or "-- NOT FOUND LOCALLY --"
        print(f"  {r['street']}, {r['city']} {r['zip']} | {r['owner']} | "
              f"{r['case_no']} | {mark} ({r['source']})")
    print(f"\nWrote {OUT}\\land_missing_apn_resolved.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
