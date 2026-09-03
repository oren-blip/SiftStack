"""One-off 2026-09-02: Oren's go — add two INBOUND buyer prospects to the
Cash Buyers list, harvested from the SMS agent's handed-off threads (both
texted asking for the 3823 N 11th Pensacola deal and were sent the link).

These are EXISTING seller-lead records, so unlike the InvestorBase upload
(pensacola_ib_upload_20260826.py) status is deliberately NOT flipped to
"buyer" — Ashton is still a live "maybe" seller and a status change would
pull them out of seller marketing. Tags + list membership only:

  add-tags:  cash buyers, Pensacola - 3823 N 11th, SMS Inbound Buyer 2026-09-02
  add-lists: Cash Buyers   (fallback: PATCH lists=[existing + Cash Buyers])

Owner guard per record; every write verified by re-GET (search is stale
after writes — never verify via search).

    .venv\\Scripts\\python.exe add_pensacola_buyers_20260902.py            # dry run
    .venv\\Scripts\\python.exe add_pensacola_buyers_20260902.py --apply    # do it
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
from pathlib import Path

import requests

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
LIST_NAME = "Cash Buyers"
TAGS = ["cash buyers", "Pensacola - 3823 N 11th", "SMS Inbound Buyer 2026-09-02"]
APPLY = "--apply" in sys.argv

_LOG = open(REPO / "logs" / "add_pensacola_buyers_20260902.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]
print(f"\n===== run at {_dt.datetime.now()} apply={APPLY} =====")

# (label, uuid, expected owner last name)
RECORDS = [
    ("Ashton Baker / 5437 Berryhill Rd, Milton FL / 850-390-6830",
     "8ada61e2-5131-460c-b74c-4be84e1ea217", "Baker"),
    ("Robert Schweigert / 62 Star Lake Dr, Pensacola FL / 850-291-2334",
     "712ead02-6663-4019-96ed-483ed5aa8bb1", "Schweigert"),
]


def token() -> str | None:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        return t
    try:
        from get_ds_token import get_token
        t = get_token()
        if t:
            return t
    except Exception as e:  # noqa: BLE001
        print(f"Chrome token harvest failed ({e})")
    print("Playwright login fallback")
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


def get_full(h, uuid):
    return requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                        timeout=30).json()


def titles(items):
    return [x.get("title") if isinstance(x, dict) else str(x) for x in (items or [])]


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    all_ok = True
    for label, uuid, want_last in RECORDS:
        d = get_full(h, uuid)
        owner = d.get("owner") or {}
        first = (owner.get("first_name") or "").strip()
        last = (owner.get("last_name") or "").strip()
        lists, tags = titles(d.get("lists")), titles(d.get("tags"))
        status = d.get("status")
        print(f"\n=== {label}")
        print(f"    owner='{first} {last}' status={status!r}")
        print(f"    lists={lists}")
        need_tags = [t for t in TAGS if t not in tags]
        need_list = LIST_NAME not in lists
        if last != want_last:
            print(f"  GUARD: owner last name is {last!r}, expected {want_last!r}"
                  " — record changed, NOT touching it. Look by hand.")
            all_ok = False
            continue
        if not need_tags and not need_list:
            print("  nothing to do — already tagged and on the list")
            continue
        if not APPLY:
            print(f"  DRY: would add tags {need_tags} and"
                  f"{'' if need_list else ' NOT'} add list {LIST_NAME!r}")
            continue

        if need_tags:
            r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                              headers=h, json={"tags": need_tags}, timeout=30)
            print(f"  add-tags {need_tags} -> {r.status_code}")
        if need_list:
            r = requests.post(f"{API}/api/internal/property/{uuid}/add-lists/",
                              headers=h, json={"lists": [LIST_NAME]}, timeout=30)
            print(f"  add-lists [{LIST_NAME!r}] -> {r.status_code}")

        chk = get_full(h, uuid)
        lt, tt = titles(chk.get("lists")), titles(chk.get("tags"))
        if need_list and LIST_NAME not in lt:
            p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                               json={"lists": lists + [LIST_NAME]}, timeout=30)
            print(f"  fallback PATCH lists+= -> {p.status_code}")
            chk = get_full(h, uuid)
            lt, tt = titles(chk.get("lists")), titles(chk.get("tags"))
        good = all(t in tt for t in TAGS) and LIST_NAME in lt
        if chk.get("status") != status:
            print(f"  WARNING: status changed {status!r} -> {chk.get('status')!r}")
            good = False
        print(f"  verify: on-list={LIST_NAME in lt} tags-ok="
              f"{all(t in tt for t in TAGS)} status={chk.get('status')!r}")
        print(f"  RESULT: {'OK' if good else 'CHECK BY HAND'}")
        all_ok &= good

    print(f"\nOVERALL: {'OK' if all_ok else 'CHECK BY HAND'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
