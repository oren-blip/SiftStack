"""One-off 2026-09-02: Oren chose "stay dead" for Vandall 26E000533-540
(Linda Sue Light Vandall, 4197 Kent St, Maiden — Lincoln case).

He killed the case 2026-08-31 (manual_drops.txt: heir-occupied — court PR
Paula Oxentine's mailing == the property), but the record had already been
uploaded to DataSift on 8/25 as "Heirs Vandall" and was still live on every
list, so it could get mailed. This holds it: add Tag "Hold - Occupied",
remove ALL lists (lists drive the niche-sequential presets; a killed case
keeps none, not even Inherited), verify by re-GET. Record NOT deleted,
owner name and status untouched.

Same recipe as hold_occupied_20260819.py, plus an owner guard: the record
is only touched while its owner still reads "Heirs Vandall" — if someone
renamed or replaced it, stop and say so instead.

    .venv\\Scripts\\python.exe hold_vandall_20260902.py            # dry run
    .venv\\Scripts\\python.exe hold_vandall_20260902.py --apply    # do it
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
HOLD_TAG = "Hold - Occupied"
APPLY = "--apply" in sys.argv

_LOG = open(REPO / "logs" / "hold_vandall_20260902.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]
print(f"\n===== run at {_dt.datetime.now()} apply={APPLY} =====")

LABEL = "Vandall 26E000533-540"
UUID = "63cbda38-105a-40da-a277-99c8159f5d85"


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
    d = get_full(h, UUID)
    owner = d.get("owner") or {}
    first = (owner.get("first_name") or "").strip()
    last = (owner.get("last_name") or "").strip()
    lists = titles(d.get("lists"))
    tags = titles(d.get("tags"))
    street = ((d.get("address") or {}).get("street") or "")
    print(f"\n=== {LABEL}: owner='{first} {last}' street='{street}'")
    print(f"    lists={lists} held={'YES' if HOLD_TAG in tags else 'no'}")
    if first != "Heirs" or last != "Vandall":
        print("  GUARD: owner is no longer 'Heirs Vandall' — record changed "
              "since 9/1, NOT touching it. Look by hand.")
        return 1
    if not APPLY:
        print(f"  DRY: would add {HOLD_TAG!r} and remove ALL lists {lists}")
        return 0
    r = requests.post(f"{API}/api/internal/property/{UUID}/add-tags/",
                      headers=h, json={"tags": [HOLD_TAG]}, timeout=30)
    print(f"  add-tags {HOLD_TAG!r} -> {r.status_code}")
    if lists:
        r = requests.post(f"{API}/api/internal/property/{UUID}/remove-lists/",
                          headers=h, json={"lists": lists}, timeout=30)
        print(f"  remove-lists {lists} -> {r.status_code}")
    chk = get_full(h, UUID)
    lt, tt = titles(chk.get("lists")), titles(chk.get("tags"))
    good = HOLD_TAG in tt and not lt
    # fallback: PATCH lists down if remove-lists no-opped
    if lt:
        p = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                           json={"lists": []}, timeout=30)
        print(f"  fallback PATCH lists=[] -> {p.status_code}")
        lt = titles(get_full(h, UUID).get("lists"))
        good = HOLD_TAG in tt and not lt
    print(f"  verify: lists={lt} tags has hold={HOLD_TAG in tt}")
    print(f"  RESULT: {'OK' if good else 'CHECK BY HAND'}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
