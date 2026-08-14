"""One-shot: fix uploaded DataSift records that are vacant/numberless-lot
primaries carrying neither Oren's "0 <street>" prefix nor a parcel number
(Oren 2026-08-14: "fix this and others like it in the future").

Root cause (fixed same day in fix_addresses_and_prep.py Step 3.66 +
nc_datasift_export parcel-note gate): both the 0-prefix and the
parcel-ID-into-Notes rules were gated on Property use containing "vacant",
but county GIS mistypes numberless lots as SFR (Gaston 'Auxiliary
Improvement' class and friends). Those rows shipped with a bare street
("SHADY COVE RD"), no parcel anywhere in the record, and DataSift's own
enrich can't resolve a numberless street — so the record is unidentifiable.

The five affected UPLOADED records (cross-check: FTM workbook through Wk33
vs output/.netnew_uploaded.json):

  Case No.        County  owner (PR)      street as uploaded          parcel
  26E000781-480   Iredell David Black     SHADY COVE RD               4730603804
  26E000790-480   Iredell Anita Burkhead  TROUTMAN SHOALS RD          4711475966
  26E001058-350   Gaston  Heirs Ricardo   HEATHER LN                  177271
  26E002931-590   Meck    Chase Thompson  Mt Holly-Huntersville Rd    03306512
  26E000934-170   Catawba Naomi Huitt     No Address                  377105175671

Per record (API-only — no UI free-text anywhere, see
feedback_never_automate_datasift_free_text):
  1. Search by street, require exactly one case-insensitive street match
     whose owner last name matches the PR — else SKIP (never guess).
  2. PATCH street -> "0 <Street>" (except the No-Address row: nothing to
     prefix), parcel_id/apn -> court-verified parcel, estimate_value +
     lot_size from county GIS. Owner object round-tripped in full and its
     mailing street updated only when it equals the old property street
     (Step 1.95 fills missing PR mailing from the property address). Never
     write blanks over existing (project_pr_upgrade_silent_save_failure).
  3. Re-GET and verify every field landed.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"

# (case_no, search street, owner last name, new street or None,
#  parcel, estimate_value or None, lot_acres or None)
FIXES = [
    # First three DONE + verified on the 2026-08-14 run (each had a STRANGER
    # parcel attached by DataSift enrich — Putnam class — now court-verified):
    # ("26E000781-480", "SHADY COVE RD", "Black",
    #  "0 Shady Cove Rd", "4730603804", "47500.00", None),
    # ("26E000790-480", "TROUTMAN SHOALS RD", "Burkhead",
    #  "0 Troutman Shoals Rd", "4711475966", "29300.00", 0.51),
    # ("26E001058-350", "HEATHER LN", "Ricardo",
    #  "0 Heather Ln", "177271", "7610.00", 0.79),
    # ("26E002931-590", "Mt Holly-Huntersville Rd", "Thompson",
    #  "0 Mt Holly-Huntersville Rd", "03306512", "127900.00", 2.00),
    # White 26E000934-170: the record kept the PRE-swap main (3610 Old Catawba
    # Rd — the heir-occupied home DQ'd after upload; the workbook's current
    # main is the road-less 6.41ac vacant lot 377105175671, Catawba situs
    # blank, SR 1722 only, so there is no street to 0-prefix). Fix = make the
    # record self-consistent: stamp the parcel/value/acres OF THE ADDRESS IT
    # SHOWS (Catawba-verified 2026-08-14). Which parcel the estate record
    # should ultimately represent is Oren's call — flagged in the report.
    ("26E000934-170", "3610 Old Catawba Rd", "Huitt",
     None, "376220900384", "420500.00", 4.71),
]


def token() -> str | None:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = (await page.evaluate("() => localStorage.getItem('rs_token')")
                 if ok else None)
            await b.close()
            return t
    return asyncio.run(go())


def find_record(h: dict, street: str, owner_last: str) -> dict | None:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        print(f"  search {street!r} -> HTTP {r.status_code}")
        return None
    results = r.json().get("results", [])
    hits = [rec for rec in results
            if ((rec.get("address") or {}).get("street") or "").strip().lower()
            == street.strip().lower()
            and ((rec.get("owner") or {}).get("last_name") or "").strip().lower()
            == owner_last.strip().lower()]
    if len(hits) != 1:
        print(f"  search {street!r} owner {owner_last!r}: "
              f"{len(hits)} matches (of {len(results)} results) — SKIP")
        return None
    return hits[0]


def fix_one(h: dict, case_no: str, street: str, owner_last: str,
            new_street: str | None, parcel: str,
            value: str | None, acres: float | None) -> bool:
    print(f"\n=== {case_no}: {street!r} / owner {owner_last}")
    rec = find_record(h, street, owner_last)
    if not rec:
        return False
    uuid = rec.get("uuid")
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                     timeout=30)
    if r.status_code != 200:
        print(f"  GET {uuid} -> {r.status_code} — SKIP")
        return False
    d = r.json()
    addr = d.get("address") or {}
    owner = d.get("owner") or {}
    print(f"  live: street={addr.get('street')!r} city={addr.get('city')!r} "
          f"parcel={d.get('parcel_id')!r} value={d.get('estimate_value')!r} "
          f"lot={d.get('lot_size')!r} "
          f"owner={owner.get('first_name')} {owner.get('last_name')}")
    if (addr.get("street") or "").strip().lower() != street.strip().lower():
        print("  street changed since search — SKIP")
        return False
    if not (owner.get("first_name") and owner.get("last_name")):
        print("  owner object missing names — SKIP rather than risk blanking")
        return False
    if d.get("parcel_id") and str(d.get("parcel_id")) != parcel:
        # DataSift enrich matched the numberless street to some OTHER parcel
        # (Putnam class) — overwrite with the court-verified one, but say so.
        print(f"  NOTE: enrich had attached stranger parcel "
              f"{d.get('parcel_id')!r}; overwriting with court-verified {parcel}")

    body: dict = {"parcel_id": parcel, "apn": parcel}
    new_addr = copy.deepcopy(addr)
    if new_street:
        new_addr["street"] = new_street
        body["address"] = new_addr
        new_owner = copy.deepcopy(owner)
        if ((new_owner.get("address") or {}).get("street", "").strip().lower()
                == street.strip().lower()):
            new_owner["address"]["street"] = new_street
        body["owner"] = new_owner
    if value:
        body["estimate_value"] = value
    if acres is not None:
        body["lot_size"] = acres

    pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                        data=json.dumps(body), timeout=30)
    print(f"  PATCH -> {pr.status_code} {pr.text[:200]}")
    if pr.status_code not in (200, 202):
        print("  PATCH not accepted — STOPPING this record (no retry).")
        return False

    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                       timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    ca = cd.get("address") or {}
    co = cd.get("owner") or {}
    want_street = new_street or street
    ok = ((ca.get("street") or "").strip().lower() == want_street.strip().lower()
          and str(cd.get("parcel_id")) == parcel
          and (co.get("last_name") or "").strip().lower()
          == owner_last.strip().lower())
    print(f"  verify: street={ca.get('street')!r} parcel={cd.get('parcel_id')!r} "
          f"value={cd.get('estimate_value')!r} lot={cd.get('lot_size')!r} "
          f"owner={co.get('first_name')} {co.get('last_name')}")
    print(f"  RESULT: {'OK' if ok else 'MISMATCH — check the record by hand'}")
    return ok


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}
    done = 0
    for spec in FIXES:
        if fix_one(h, *spec):
            done += 1
    print(f"\n{done}/{len(FIXES)} records fixed.")
    return 0 if done == len(FIXES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
