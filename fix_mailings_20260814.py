"""One-shot: repair PR mailing addresses that shipped as the VACANT LOT
itself (Oren 2026-08-14: "DM/PR mailing address is not a vacant lot, so we
can skip and contact").

Root cause fixed same day in fix_addresses_and_prep.py: Step 1.95 / the DM
promotion fallback stamped the property address into a blank mailing even
when the property is a mailbox-less vacant lot, and the sibling swaps threw
away the DQ'd family home's address. Pipeline now preserves the prior main
as the mailing (mailing-from-prior-main) and never stamps an unmailable
property.

Records to repair (both swap-on-dq: the family home was DQ'd heir-occupied
and the DQ evidence puts family AT that home — Gaston GIS verified today):

  26E001081-350 Hoffman: mailing '0 Redbud Dr'  -> 4209 Old Forge Dr,
      Gastonia NC 28056 (DQ'd parcel 116808; deed 'HOFFMAN C DOUGLAS +
      HOFFMAN NANCY R' — PR Douglas co-owns with the decedent, tax mail
      goes there; likely the surviving husband).
  26E001076-350 Canipe:  mailing '0 Sunny Ln'   -> 115 Sunny Ln,
      Cherryville NC 28021 (DQ'd parcel 159749, 'CANIPE GAIL C ENHANCED
      LIFE ESTATE'). Also stamps main parcel 159758 if blank/stranger.

API-only (no UI free-text); owner object round-tripped in full; never
write blanks over existing; verified by re-GET.
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

# (case, uuid or None, search street, owner last, new mailing dict,
#  parcel or None)
FIXES = [
    ("26E001081-350", "d5d09880-3897-419a-a8a9-a8ab727b8d03", None, "Hoffman",
     {"street": "4209 Old Forge Dr", "city": "Gastonia", "state": "NC",
      "postal_code": "28056"}, None),
    ("26E001076-350", None, "0 Sunny Ln", "Canipe",
     {"street": "115 Sunny Ln", "city": "Cherryville", "state": "NC",
      "postal_code": "28021"}, "159758"),
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


def find_uuid(h: dict, street: str, owner_last: str) -> str | None:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        print(f"  search {street!r} -> HTTP {r.status_code}")
        return None
    hits = [rec for rec in r.json().get("results", [])
            if ((rec.get("address") or {}).get("street") or "").strip().lower()
            == street.strip().lower()
            and ((rec.get("owner") or {}).get("last_name") or "").strip().lower()
            == owner_last.strip().lower()]
    if len(hits) != 1:
        print(f"  search {street!r} owner {owner_last!r}: {len(hits)} matches — SKIP")
        return None
    return hits[0].get("uuid")


def fix_one(h: dict, case: str, uuid: str | None, street: str | None,
            owner_last: str, mail: dict, parcel: str | None) -> bool:
    print(f"\n=== {case} (owner {owner_last}) -> mail {mail['street']}")
    if not uuid:
        uuid = find_uuid(h, street, owner_last)
        if not uuid:
            return False
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET -> {r.status_code} — SKIP")
        return False
    d = r.json()
    owner = d.get("owner") or {}
    oaddr = owner.get("address") or {}
    print(f"  live: prop={((d.get('address') or {}).get('street'))!r} "
          f"parcel={d.get('parcel_id')!r} owner={owner.get('first_name')} "
          f"{owner.get('last_name')} mail={oaddr.get('street')!r} "
          f"{oaddr.get('city')!r}")
    if (owner.get("last_name") or "").strip().lower() != owner_last.lower():
        print("  owner mismatch — SKIP")
        return False
    if not (owner.get("first_name") and owner.get("last_name")):
        print("  owner missing names — SKIP rather than risk blanking")
        return False
    cur_mail = (oaddr.get("street") or "").strip()
    if cur_mail and not (cur_mail.startswith("0 ") or cur_mail == "0"
                         or not cur_mail[0].isdigit()):
        print(f"  owner mailing {cur_mail!r} already a real numbered address — SKIP")
        return False

    new_owner = copy.deepcopy(owner)
    new_owner.setdefault("address", {})
    new_owner["address"].update(mail)
    body: dict = {"owner": new_owner}
    if parcel and not d.get("parcel_id"):
        body["parcel_id"] = parcel
        body["apn"] = parcel
    pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                        data=json.dumps(body), timeout=30)
    print(f"  PATCH -> {pr.status_code} {pr.text[:150]}")
    if pr.status_code not in (200, 202):
        return False
    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    co = cd.get("owner") or {}
    ca = co.get("address") or {}
    ok = ((ca.get("street") or "").strip().lower() == mail["street"].lower()
          and (co.get("last_name") or "").strip().lower() == owner_last.lower())
    print(f"  verify: mail={ca.get('street')!r} {ca.get('city')!r} "
          f"{ca.get('postal_code')!r} parcel={cd.get('parcel_id')!r}")
    print(f"  RESULT: {'OK' if ok else 'MISMATCH — check by hand'}")
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
    done = sum(1 for spec in FIXES if fix_one(h, *spec))
    print(f"\n{done}/{len(FIXES)} records fixed.")
    return 0 if done == len(FIXES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
