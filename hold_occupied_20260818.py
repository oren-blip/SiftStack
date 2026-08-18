"""One-off 2026-08-18: pull already-uploaded OCCUPIED single-asset estates
out of DataSift marketing (Oren approved both halves today).

Forward path is handled by fix_addresses_and_prep Step 4.97 (occupied-hold:
row stays in workbook, excluded from the upload CSV). This script is the
RETROACTIVE half: for held cases that a prior upload already committed to
DataSift, remove the record from ALL lists (lists drive the niche-sequential
presets, so no more mail/SMS/call spend) and add the Tag "Hold - Occupied"
as the durable marker. Records are NOT deleted, statuses untouched, tags
otherwise untouched — Oren can still work one by hand from the workbook.

Usage:
    python hold_occupied_20260818.py            # dry run: find + report only
    python hold_occupied_20260818.py --apply    # do it (verified per record)

List removal route is unverified before first run, so --apply probes it on
ONE record, re-GETs to verify the lists actually emptied, and aborts before
touching the rest if the route is a silent no-op (the property-PATCH-tags
lesson, see skipped-no-numbers memory).
"""
from __future__ import annotations

import asyncio
import csv
import glob
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

API = "https://apiv2.reisift.io"
HOLD_TAG = "Hold - Occupied"
# The Inherited list is sold-audit intel, not a marketing list — occupied
# records deliberately STAY on it (tag-excluded from marketing instead).
# See feedback_inherited_offsite_focus: Davenport is on both.
KEEP_LISTS = {"Inherited"}


# ── hold-set discovery (same logic as pipeline Step 4.97) ─────────────────

def latest_week_csvs(min_week: int = 29) -> dict[int, str]:
    byweek: dict[int, str] = {}
    for f in glob.glob("output/nc_estates_ftm_*_week*_datasift.csv"):
        wk = int(re.search(r"week(\d+)_datasift", f).group(1))
        if wk < min_week:
            continue
        if wk not in byweek or os.path.getmtime(f) > os.path.getmtime(byweek[wk]):
            byweek[wk] = f
    return byweek


def build_hold_set() -> list[dict]:
    from fix_addresses_and_prep import hold_occupied_single_asset
    held: dict[str, dict] = {}
    for wk, f in sorted(latest_week_csvs().items()):
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        hold_occupied_single_asset(rows)
        for r in rows:
            if "occupied-hold" not in (r.get("Match Reason") or ""):
                continue
            case = (r.get("Case No.") or "").strip()
            if case and case not in held:
                held[case] = {
                    "week": wk,
                    "case": case,
                    "county": r.get("County", ""),
                    "decedent": r.get("Deceased Owner", ""),
                    "street": (r.get("Property Address") or "").strip(),
                    "city": (r.get("Property City") or "").strip(),
                    "pr_last": (r.get("Last Name") or "").strip(),
                }
    return list(held.values())


# ── auth (DS_TOKEN env -> Chrome storage -> Playwright login) ─────────────

def token() -> str | None:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        print("using DS_TOKEN from environment")
        return t
    try:
        from get_ds_token import get_token
        t = get_token()
        if t:
            return t
        print("no working token in Chrome storage — Playwright login fallback")
    except Exception as e:  # noqa: BLE001
        print(f"Chrome token harvest failed ({e}) — Playwright login fallback")
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
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    return asyncio.run(go())


# ── record lookup ─────────────────────────────────────────────────────────

def find_record(h: dict, item: dict) -> dict | None:
    """Search by property street; require the decedent's or PR's surname in
    the record's owner block so a same-street stranger never matches."""
    street = item["street"]
    if not street:
        return None
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        print(f"  search {street!r} -> HTTP {r.status_code}")
        return None
    hits = (r.json() or {}).get("results", [])
    dec_last = (item["decedent"].split(",")[0] or "").strip().lower()
    frags = {f for f in (dec_last, item["pr_last"].lower()) if f}
    good = []
    for hit in hits:
        blob = str(hit).lower()
        if any(f in blob for f in frags):
            good.append(hit)
    if len(good) != 1:
        print(f"  {item['case']}: {len(hits)} hits / {len(good)} surname-matched "
              f"for {street!r} — SKIP (need exactly 1)")
        return None
    return good[0]


def get_full(h: dict, uuid: str) -> dict:
    return requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                        timeout=30).json()


def list_titles(rec: dict) -> list[str]:
    out = []
    for l in rec.get("lists") or []:
        out.append(l.get("title") if isinstance(l, dict) else str(l))
    return [x for x in out if x]


def tag_titles(rec: dict) -> list[str]:
    out = []
    for t in rec.get("tags") or []:
        out.append(t.get("title") if isinstance(t, dict) else str(t))
    return [x for x in out if x]


# ── mutations ─────────────────────────────────────────────────────────────

def add_hold_tag(h: dict, uuid: str) -> bool:
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                      headers=h, json={"tags": [HOLD_TAG]}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def remove_lists(h: dict, uuid: str, titles: list[str]) -> tuple[bool, str]:
    """Try the remove-tags-style twin first; verify by re-GET."""
    goal_ok = lambda: not (set(list_titles(get_full(h, uuid))) - KEEP_LISTS)  # noqa: E731
    r = requests.post(f"{API}/api/internal/property/{uuid}/remove-lists/",
                      headers=h, json={"lists": titles}, timeout=30)
    route = f"remove-lists/ HTTP {r.status_code}"
    if r.status_code in (200, 201, 202, 204):
        if goal_ok():
            return True, route
        route += " (no-op)"
    # Fallback: PATCH lists down to the keepers — verify, never trust the
    # status code (property PATCH of tags is a proven silent no-op).
    keep = [l for l in list_titles(get_full(h, uuid)) if l in KEEP_LISTS]
    p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                       json={"lists": keep}, timeout=30)
    route += f"; PATCH lists={keep} HTTP {p.status_code}"
    if goal_ok():
        return True, route
    return False, route


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    apply = "--apply" in sys.argv
    held = build_hold_set()
    print(f"\nHold candidates from workbook weeks 29-34: {len(held)}\n")

    t = token()
    if not t:
        print("NO TOKEN — log into app.reisift.io in Chrome or set DS_TOKEN")
        return 1
    h = {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

    found, route_proven = [], False
    for item in sorted(held, key=lambda x: (x["week"], x["case"])):
        hit = find_record(h, item)
        if not hit:
            continue
        rec = get_full(h, hit["uuid"])
        lists, tags = list_titles(rec), tag_titles(rec)
        already = HOLD_TAG in tags and not (set(lists) - KEEP_LISTS)
        print(f"Wk{item['week']} {item['case']} {item['decedent'][:28]:28s} "
              f"uuid={hit['uuid'][:8]} lists={lists} "
              f"{'[already held]' if already else ''}")
        if already:
            continue
        found.append((item, hit["uuid"], lists))

    print(f"\nIn DataSift and needing the hold: {len(found)}")
    if not apply:
        print("Dry run — re-run with --apply to tag + de-list them.")
        return 0

    done = 0
    for item, uuid, lists in found:
        ok_tag = add_hold_tag(h, uuid)
        removable = [l for l in lists if l not in KEEP_LISTS]
        ok_lists, route = (remove_lists(h, uuid, removable) if removable
                           else (True, "no marketing lists"))
        rec = get_full(h, uuid)
        verified = (HOLD_TAG in tag_titles(rec)
                    and not (set(list_titles(rec)) - KEEP_LISTS))
        print(f"{item['case']}: tag={'OK' if ok_tag else 'FAIL'} "
              f"lists removed={'OK' if ok_lists else 'FAIL'} ({route}) "
              f"verified={'YES' if verified else 'NO'}")
        if not verified and not route_proven:
            print("First record failed verification — ABORTING before the rest.")
            return 1
        route_proven = True
        if verified:
            done += 1
    print(f"\nDone: {done}/{len(found)} records held out of marketing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
