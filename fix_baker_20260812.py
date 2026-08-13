"""One-shot Baker 26E002844-590 fix (Oren approved 2026-08-12: "fix Baker").

The DataSift record at 2417 Normancrest Ct is a WRONG-parcel stranger record:
deed owner is a different, living Joseph C Baker (see manual_parcel_rejects.txt,
Claude deed-verified 2026-08-06). It shipped as "Heirs Baker" with zero phones,
zero outreach (0 mail / 0 calls / 0 sms, no notes, no tasks) and already wears
"Wrong Parcel - Do Not Mail". Keeping it risks mailing/texting a stranger.

Steps:
  1. Verify the record live (street must be 2417 Normancrest Ct, owner Baker,
     zero activity) — ABORT on any mismatch.
  2. Delete that ONE record by uuid.
  3. The corrected property (6034 Shining Oak Ln — deed SHIRLEY H. BAKER +
     JOSEPH BAKER, parcel 02756532) is uploaded separately via the normal
     upload wizard (upload_netnew_datasift.py) so it lands with tags + trace.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import requests
from dotenv import load_dotenv

load_dotenv()

UUID = "77aaa1a1-9ee0-4c27-aa77-616669c35710"
API = "https://apiv2.reisift.io"


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
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}"}
    r = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"pre-check GET -> {r.status_code}; record may already be gone. ABORT (no delete).")
        return 1
    d = r.json()
    street = (d.get("address") or {}).get("street")
    owner = d.get("owner") or {}
    activity = (d.get("directmail_attempts") or 0, d.get("predictivecall_attempts") or 0,
                d.get("sms_attempts") or 0)
    print(f"live: {street} | {owner.get('first_name')} {owner.get('last_name')} | activity={activity}")
    if street != "2417 Normancrest Ct" or owner.get("last_name") != "Baker" or any(activity):
        print("VERIFICATION FAILED — record is not the known-safe stranger row. ABORT.")
        return 1
    dr = requests.delete(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    print(f"DELETE -> {dr.status_code} {dr.text[:200]}")
    chk = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h, timeout=30)
    print(f"verify GET -> {chk.status_code} (404 = gone)")
    return 0 if chk.status_code == 404 else 1


if __name__ == "__main__":
    raise SystemExit(main())
