"""One-off 2026-08-19: Oren approved the REAL occupied hold for the two
spouse-occupied estates found in today's call-flow heirs DP sweep:

    Adams 26E002995-590  (widow Marianne Wagnon lives at 1825 Rice Planters Rd)
    Zion  26E002962-590  (widow Jocelyne Zion lives at 832 Stratfordshire Dr)

Same recipe as hold_occupied_20260818.py: add Tag "Hold - Occupied", remove
ALL lists except "Inherited" (lists drive the niche-sequential presets),
verify by re-GET. Also swaps out today's interim "Hold Review - Spouse
Occupies" tag. Records NOT deleted, statuses untouched.

    python hold_occupied_20260819.py            # dry run
    python hold_occupied_20260819.py --apply    # do it
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
REVIEW_TAG = "Hold Review - Spouse Occupies"
KEEP_LISTS = {"Inherited"}
APPLY = "--apply" in sys.argv

_LOG = open(REPO / "logs" / "hold_occupied_20260819.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]
print(f"\n===== run at {_dt.datetime.now()} apply={APPLY} =====")

TARGETS = [
    ("Adams 26E002995-590", "f695a966-4e83-4017-8080-9247a71552de"),
    ("Zion 26E002962-590", "eae607c7-0038-4a63-ac07-d5e6b8476760"),
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
    ok_count = 0
    for label, uuid in TARGETS:
        d = get_full(h, uuid)
        lists = titles(d.get("lists"))
        tags = titles(d.get("tags"))
        drop = [l for l in lists if l not in KEEP_LISTS]
        print(f"\n=== {label}: lists={lists} held={'YES' if HOLD_TAG in tags else 'no'}")
        if not APPLY:
            print(f"  DRY: would add {HOLD_TAG!r}, remove {REVIEW_TAG!r}, "
                  f"remove lists {drop}")
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": [HOLD_TAG]}, timeout=30)
        print(f"  add-tags {HOLD_TAG!r} -> {r.status_code}")
        r = requests.post(f"{API}/api/internal/property/{uuid}/remove-tags/",
                          headers=h, json={"tags": [REVIEW_TAG]}, timeout=30)
        print(f"  remove-tags {REVIEW_TAG!r} -> {r.status_code}")
        if drop:
            r = requests.post(f"{API}/api/internal/property/{uuid}/remove-lists/",
                              headers=h, json={"lists": drop}, timeout=30)
            print(f"  remove-lists {drop} -> {r.status_code}")
        chk = get_full(h, uuid)
        lt, tt = titles(chk.get("lists")), titles(chk.get("tags"))
        good = (HOLD_TAG in tt and REVIEW_TAG not in tt
                and not (set(lt) - KEEP_LISTS))
        # fallback: PATCH lists down if remove-lists no-opped
        if set(lt) - KEEP_LISTS:
            keep = [l for l in lt if l in KEEP_LISTS]
            p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                               json={"lists": keep}, timeout=30)
            print(f"  fallback PATCH lists={keep} -> {p.status_code}")
            lt = titles(get_full(h, uuid).get("lists"))
            good = (HOLD_TAG in tt and not (set(lt) - KEEP_LISTS))
        print(f"  verify: lists={lt} tags has hold={HOLD_TAG in tt} "
              f"review gone={REVIEW_TAG not in tt}")
        print(f"  RESULT: {'OK' if good else 'CHECK BY HAND'}")
        ok_count += bool(good)
    if APPLY:
        print(f"\n{ok_count}/{len(TARGETS)} held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
