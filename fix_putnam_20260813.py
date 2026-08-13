"""One-shot Putnam 26E001064-350 record fix (Oren approved 2026-08-13: "fix the record").

The Week 33 upload (2026-08-11) carried the WRONG main parcel for this Gaston
estate: the $32K numberless aux lot "Belton Ave" (PID 181710, Gaston DESC1_DESC
'Auxiliary Improvement' — mistyped SFR, see nc_gis_lookup v19 bump) instead of
the decedent's $233K house at 423 Belton Ave (PID 181709). Worse, DataSift's
own enrich then matched the numberless street to a THIRD unrelated parcel
(parcel_id 184073, $110K, 0.08 ac) — so the record carried a stranger's data.

Steps (API-only — no UI free-text anywhere, see
feedback_never_automate_datasift_free_text):
  1. GET the record by uuid; ABORT unless street='Belton Ave' + owner Doris
     Wallace (the known-wrong state).
  2. PATCH property address street -> '423 Belton Ave', owner mailing street
     likewise (owner object round-tripped in full — never write blanks over
     existing, see project_pr_upgrade_silent_save_failure), parcel_id/apn ->
     181709, estimate_value -> 233110, lot_size -> 0.65 (all Gaston-GIS
     verified 2026-08-13).
  3. Re-GET and verify every field landed.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://apiv2.reisift.io"
UUID = "b69fcb9b-9d64-4a5e-aac0-0f405f008c66"
NEW_STREET = "423 Belton Ave"
NEW_PARCEL = "181709"
NEW_VALUE = "233110.00"
NEW_LOT_ACRES = 0.65


def token() -> str | None:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = await page.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close()
            return t
    return asyncio.run(go())


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    r = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"pre-check GET -> {r.status_code}. ABORT.")
        return 1
    d = r.json()
    addr = d.get("address") or {}
    owner = d.get("owner") or {}
    print(f"live: {addr.get('street')!r}, {addr.get('city')} | "
          f"{owner.get('first_name')} {owner.get('last_name')} | "
          f"parcel={d.get('parcel_id')} value={d.get('estimate_value')}")
    if (addr.get("street") != "Belton Ave" or addr.get("city") != "Mount Holly"
            or owner.get("last_name") != "Wallace"):
        print("VERIFICATION FAILED — record is not the known-wrong Putnam row. ABORT.")
        return 1

    new_addr = copy.deepcopy(addr)
    new_addr["street"] = NEW_STREET
    new_owner = copy.deepcopy(owner)
    if (new_owner.get("address") or {}).get("street") == "Belton Ave":
        new_owner["address"]["street"] = NEW_STREET
    # Guard: never send an owner object with blank names (would void the save
    # or wipe the contact).
    if not (new_owner.get("first_name") and new_owner.get("last_name")):
        print("owner object missing names — ABORT rather than risk blanking.")
        return 1

    body = {
        "address": new_addr,
        "owner": new_owner,
        "parcel_id": NEW_PARCEL,
        "apn": NEW_PARCEL,
        "estimate_value": NEW_VALUE,
        "lot_size": NEW_LOT_ACRES,
    }
    pr = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                        data=json.dumps(body), timeout=30)
    print(f"PATCH -> {pr.status_code} {pr.text[:300]}")
    if pr.status_code not in (200, 202):
        print("PATCH not accepted — STOPPING (no retry, no fallback).")
        return 1

    chk = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    ca = cd.get("address") or {}
    co = cd.get("owner") or {}
    ok = (ca.get("street") == NEW_STREET
          and (co.get("address") or {}).get("street") == NEW_STREET
          and str(cd.get("parcel_id")) == NEW_PARCEL
          and co.get("first_name") == "Doris" and co.get("last_name") == "Wallace")
    mail_street = (co.get("address") or {}).get("street")
    print(f"verify: street={ca.get('street')!r} mail={mail_street!r} "
          f"parcel={cd.get('parcel_id')} value={cd.get('estimate_value')} "
          f"lot={cd.get('lot_size')} owner={co.get('first_name')} {co.get('last_name')}")
    print("RESULT:", "OK" if ok else "MISMATCH — check the record by hand")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
