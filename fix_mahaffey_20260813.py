"""One-shot Mahaffey 26E000808-790 record fix (Oren approved 2026-08-13).

Enformion PersonSearch (accuracy test, enformion_test_20260813.py) located the
court-named PR our waterfall couldn't: Phillip Lee Mahaffey, 61, at
850 Luther Barger Rd # Q, Salisbury NC 28146 — the estate's own street,
address current to 7/1/2026. Identity is certain: his relatives list contains
decedent Clive L Mahaffey AND known DM2 Dale Travis Mahaffey.

Record owner "Phil Mahaffey" carries the synthesized mailing "0 Luther Barger
Rd" (vacant land — mail dies there) and one Tracerfy phone. This PATCH:
  1. mailing street -> 850 Luther Barger Rd # Q (city/state/zip unchanged)
  2. APPENDS phone (704) 279-0798 (Enformion, connected landline) — existing
     phone kept
  3. appends record tag "enformion-phone" (honest-source pattern)
  4. tries to add his 3 emails; dropped harmlessly if the API rejects them

API-only, round-tripped owner object, verified by re-GET
(project_pr_upgrade_silent_save_failure rules honored).
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
UUID = "0d4f6263-6d35-438d-856b-67506daa31b1"
NEW_STREET = "850 Luther Barger Rd # Q"
NEW_PHONE = "7042790798"
NEW_EMAILS = ["phillip.mahaffey@aol.com", "phillipmahaffey@netzero.net",
              "pmahaffey@bellsouth.net"]
TAG = "enformion-phone"


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
    owner = d.get("owner") or {}
    oaddr = owner.get("address") or {}
    print(f"live: owner {owner.get('first_name')} {owner.get('last_name')} | "
          f"mailing {oaddr.get('street')!r} | phones "
          f"{[p.get('number') for p in owner.get('phones') or []]}")
    if (owner.get("last_name") != "Mahaffey"
            or oaddr.get("street") != "0 Luther Barger Rd"):
        print("VERIFICATION FAILED — not the known-wrong Mahaffey state. ABORT.")
        return 1
    if not (owner.get("first_name") and owner.get("last_name")):
        print("owner missing names — ABORT rather than risk blanking.")
        return 1

    new_owner = copy.deepcopy(owner)
    new_owner["address"]["street"] = NEW_STREET
    phones = new_owner.get("phones") or []
    if not any("".join(c for c in (p.get("number") or "") if c.isdigit())
               == NEW_PHONE for p in phones):
        phones.append({"number": NEW_PHONE, "type": "UNKNOWN", "tags": [],
                       "status": "UNKNOWN", "is_connected": None})
    new_owner["phones"] = phones
    new_owner["emails"] = list(new_owner.get("emails") or []) + NEW_EMAILS

    tags = list(d.get("tags") or [])
    if TAG not in tags:
        tags.append(TAG)

    body = {"owner": new_owner, "tags": tags}
    pr = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                        data=json.dumps(body), timeout=30)
    print(f"PATCH -> {pr.status_code} {pr.text[:300]}")
    if pr.status_code not in (200, 202):
        # Retry once without emails — unknown schema, don't let it sink the rest.
        new_owner.pop("emails", None)
        pr = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                            data=json.dumps({"owner": new_owner, "tags": tags}),
                            timeout=30)
        print(f"PATCH retry (no emails) -> {pr.status_code} {pr.text[:300]}")
        if pr.status_code not in (200, 202):
            print("PATCH not accepted — STOPPING (no retry, no fallback).")
            return 1

    chk = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    co = cd.get("owner") or {}
    nums = ["".join(c for c in (p.get("number") or "") if c.isdigit())
            for p in co.get("phones") or []]
    ok = ((co.get("address") or {}).get("street") == NEW_STREET
          and NEW_PHONE in nums
          and co.get("first_name") == "Phil" and co.get("last_name") == "Mahaffey"
          and TAG in (cd.get("tags") or []))
    print(f"verify: mailing={(co.get('address') or {}).get('street')!r} "
          f"phones={nums} emails={co.get('emails')} "
          f"tag={'yes' if TAG in (cd.get('tags') or []) else 'NO'}")
    print("RESULT:", "OK" if ok else "MISMATCH — check the record by hand")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
