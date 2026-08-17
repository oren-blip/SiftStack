"""One-shot: stamp parcel info on the Ray Kluttz vacant lot (Brookshire Dr,
Salisbury NC — Oren 2026-08-17: numberless lot, no APN, "can't see the
property info").

One of the 12 DataFlik bulk repairs (8/14) that surfaced in "02. Ready to
Call". Rowan GIS single exact match, identity confirmed by the tax mailing
("% RAY B KLUTTZ JR") matching the record's mailing exactly:

  PARCEL_ID 356 241 — 0 BROOKSHIRE DR, 2.2 calc acres, TOT_VAL $28,050
  OWNNAME KLUTTZ RAY BANKS SR & WF / OWN2 KLUTTZ JOYCE DARE (deed 2013)

Patches (API-only, fix_vacant_prefix_20260814 pattern):
  street -> "0 Brookshire Dr" (vacant-lot 0-prefix convention),
  parcel_id/apn -> 356 241, estimate_value 28050, lot_size 2.2,
  owner mailing state SC -> NC (county tax-roll typo: ZIP 28146 is NC).
Never writes blanks over existing; re-GETs and verifies every field.
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
UUID = "17eae944-eee2-433f-851b-63a96a19ae37"  # from Oren's browser URL
OWNER_LAST = "kluttz"
OLD_STREET = "brookshire dr"
NEW_STREET = "0 Brookshire Dr"
PARCEL = "356 241"
VALUE = "28050.00"
ACRES = 2.2


def token() -> str | None:
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
            t = (await page.evaluate("() => localStorage.getItem('rs_token')")
                 if ok else None)
            await b.close()
            return t
    return asyncio.run(go())


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

    r = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h,
                     timeout=30)
    if r.status_code != 200:
        print(f"GET -> {r.status_code} — abort")
        return 1
    d = r.json()
    addr = d.get("address") or {}
    owner = d.get("owner") or {}
    oaddr = owner.get("address") or {}
    print(f"live: street={addr.get('street')!r} city={addr.get('city')!r} "
          f"parcel={d.get('parcel_id')!r} value={d.get('estimate_value')!r} "
          f"lot={d.get('lot_size')!r}\n"
          f"owner={owner.get('first_name')} {owner.get('last_name')} "
          f"mail={oaddr.get('street')!r} {oaddr.get('city')!r} "
          f"{oaddr.get('state')!r} {oaddr.get('postal_code')!r}")

    if OWNER_LAST not in (owner.get("last_name") or "").lower():
        print("owner mismatch — abort")
        return 1
    if (addr.get("street") or "").strip().lower() not in (OLD_STREET,
                                                          NEW_STREET.lower()):
        print("street mismatch — abort")
        return 1
    if not (owner.get("first_name") and owner.get("last_name")):
        print("owner names missing — abort rather than risk blanking")
        return 1
    if d.get("parcel_id") and str(d.get("parcel_id")) != PARCEL:
        print(f"NOTE: stranger parcel {d.get('parcel_id')!r} attached; "
              f"overwriting with GIS-verified {PARCEL}")

    body: dict = {"parcel_id": PARCEL, "apn": PARCEL,
                  "estimate_value": VALUE, "lot_size": ACRES}
    new_addr = copy.deepcopy(addr)
    new_addr["street"] = NEW_STREET
    body["address"] = new_addr
    new_owner = copy.deepcopy(owner)
    # county tax-roll typo: "SALISBURY, SC 28146" — 28146 is NC
    if ((new_owner.get("address") or {}).get("state") or "").upper() == "SC" \
            and str((new_owner.get("address") or {}).get(
                "postal_code") or "").startswith("28"):
        new_owner["address"]["state"] = "NC"
        body["owner"] = new_owner
        print("fixing mailing state SC -> NC (ZIP 28146 is NC)")

    pr = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                        data=json.dumps(body), timeout=30)
    print(f"PATCH -> {pr.status_code} {pr.text[:200]}")
    if pr.status_code not in (200, 202):
        return 1

    chk = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h,
                       timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    ca = cd.get("address") or {}
    co = cd.get("owner") or {}
    coa = co.get("address") or {}
    ok = ((ca.get("street") or "").strip().lower() == NEW_STREET.lower()
          and str(cd.get("parcel_id")) == PARCEL
          and (co.get("last_name") or "").strip().lower() == OWNER_LAST)
    print(f"verify: street={ca.get('street')!r} parcel={cd.get('parcel_id')!r} "
          f"value={cd.get('estimate_value')!r} lot={cd.get('lot_size')!r} "
          f"mail state={coa.get('state')!r}")
    print(f"RESULT: {'OK' if ok else 'MISMATCH — check the record by hand'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
