"""2026-08-26 READ-ONLY scout: land records missing APNs across the NSM flow.

Oren: "many of the land records in my Ready to Call step are missing APNs" +
"check the rest of the NSM flow as well". This sweeps EVERY preset in the NSM
folder (the one holding "02. Ready to Call"), replicates each stored query
(with property_type=clean — the API ignores nested must_not and counts
Incomplete records otherwise), unions the records, and reports land records
whose parcel_id/apn is blank. No writes.

Run:  d:\SiftStack\.venv\Scripts\python.exe d:\SiftStack\apn_gap_scout_20260826.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
OUT = REPO / "output" / "apn_gap_20260826"
OUT.mkdir(parents=True, exist_ok=True)


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def get_token() -> str:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        return t
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tok = (await page.evaluate("() => localStorage.getItem('rs_token')")
                   if ok else None)
            await b.close()
            return tok
    tok = asyncio.run(go())
    if not tok:
        raise RuntimeError("DataSift login failed")
    return tok


def fetch_preset_records(h: dict, query: dict) -> list[dict]:
    q = dict(query)
    q["property_type"] = "clean"
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset, "query": q},
                          timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return out


def is_land(rec: dict) -> tuple[bool, str]:
    """Land = vacant lot. Signals: structure_type says land/lot/vacant,
    or our '0 <street>' vacant-lot prefix convention, or zero living sqft
    with a lot_size present."""
    st = (rec.get("structure_type") or "").lower()
    street = ((rec.get("address") or {}).get("street") or "").strip()
    if any(k in st for k in ("vacant", "land", "lot")):
        return True, f"structure_type={rec.get('structure_type')!r}"
    if street.startswith("0 "):
        return True, "0-prefix street"
    sqft = rec.get("living_area_sqft") or rec.get("living_sqft") or rec.get("sqft")
    if (not st) and (not sqft) and rec.get("lot_size"):
        return True, f"no structure/sqft, lot_size={rec.get('lot_size')}"
    return False, ""


def main() -> int:
    h = headers(get_token())

    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h,
                     params={"limit": 200}, timeout=30)
    r.raise_for_status()
    presets = r.json().get("results") or r.json().get("data") or []
    (OUT / "presets_all.json").write_text(json.dumps(presets, indent=1),
                                          encoding="utf-8")

    # NSM folder = whichever folder holds "02. Ready to Call"
    nsm_folder = None
    for p in presets:
        name = p.get("title") or p.get("name") or ""
        if "ready to call" in name.lower():
            f = p.get("folder")
            nsm_folder = (f.get("uuid") or f.get("id")) if isinstance(f, dict) else f
            print(f"NSM folder anchor: {name!r} -> folder {nsm_folder} "
                  f"({f.get('title') if isinstance(f, dict) else ''})")
            break
    if nsm_folder is None:
        print("No 'Ready to Call' preset found — inspect presets_all.json")
        return 1

    nsm = []
    for p in presets:
        f = p.get("folder")
        fid = (f.get("uuid") or f.get("id")) if isinstance(f, dict) else f
        if fid == nsm_folder:
            nsm.append(p)
    nsm.sort(key=lambda p: (p.get("title") or p.get("name") or ""))
    print(f"{len(nsm)} presets in the NSM folder:")
    for p in nsm:
        print(f"  {p.get('title') or p.get('name')}")

    # Union records across presets, remembering which presets each hits.
    by_uuid: dict[str, dict] = {}
    membership: dict[str, list[str]] = {}
    for p in nsm:
        title = p.get("title") or p.get("name") or "?"
        uuid = p.get("uuid") or p.get("id")
        det = requests.get(f"{API}/api/internal/filter-preset/{uuid}/",
                           headers=h, timeout=30)
        detail = det.json() if det.status_code == 200 else p
        query = detail.get("query") or detail.get("filters") or detail.get("filter")
        if not query:
            print(f"  !! {title}: no stored query — skipped")
            continue
        try:
            recs = fetch_preset_records(h, query)
        except requests.HTTPError as e:
            print(f"  !! {title}: query failed ({e}) — skipped")
            continue
        print(f"  {title}: {len(recs)} records")
        for rec in recs:
            ru = rec.get("uuid") or rec.get("id")
            by_uuid.setdefault(ru, rec)
            membership.setdefault(ru, []).append(title)

    print(f"\nUnion: {len(by_uuid)} unique records across the NSM flow")

    land_missing, land_ok = [], []
    for ru, rec in by_uuid.items():
        land, why = is_land(rec)
        if not land:
            continue
        parcel = (rec.get("parcel_id") or rec.get("apn") or "")
        row = {
            "uuid": ru,
            "street": ((rec.get("address") or {}).get("street") or ""),
            "city": ((rec.get("address") or {}).get("city") or ""),
            "state": ((rec.get("address") or {}).get("state") or ""),
            "zip": ((rec.get("address") or {}).get("postal_code") or ""),
            "county": rec.get("county") or "",
            "owner": " ".join(x for x in [
                (rec.get("owner") or {}).get("first_name"),
                (rec.get("owner") or {}).get("last_name")] if x),
            "structure_type": rec.get("structure_type") or "",
            "parcel_id": str(parcel),
            "land_signal": why,
            "presets": "; ".join(membership.get(ru, [])),
        }
        (land_missing if not str(parcel).strip() else land_ok).append(row)

    (OUT / "records_union.json").write_text(
        json.dumps(list(by_uuid.values()), indent=1), encoding="utf-8")
    for name, rows in (("land_missing_apn.csv", land_missing),
                       ("land_with_apn.csv", land_ok)):
        with open(OUT / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(
                (rows or land_missing or [{"uuid": ""}])[0].keys()))
            w.writeheader()
            w.writerows(rows)

    print(f"\nLand records: {len(land_missing) + len(land_ok)} "
          f"({len(land_missing)} MISSING APN, {len(land_ok)} have one)")
    for row in land_missing:
        print(f"  MISSING  {row['street']}, {row['city']} {row['zip']} "
              f"| {row['owner']} | {row['land_signal']} | {row['presets']}")
    print(f"\nWrote {OUT}\\land_missing_apn.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
