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


def _contact_at_property_unflagged(r: dict) -> bool:
    """Sweep-only class D (Szabo/Drennan 26E002951-590): pre-2026-08-13
    builds exempted ALL promoted DMs from the lives-at-the-property DQ, so a
    contact with a REAL address == the property could ship with no occupancy
    flag at all. Today's pipeline drops these at Step 4.05; already-uploaded
    ones still need the hold. Jam-aware compare, synthetic mailings and
    'Heirs of' backstops excluded."""
    from fix_addresses_and_prep import (_hold_norm_addr, _heir_addr_match,
                                        _has_sibling_parcels)
    mr = r.get("Match Reason") or ""
    # Promoted rows ONLY. Non-promoted rows always faced the Step 1.9 DQ, so
    # a surviving one with mailing==property means the mailing was BLANK at
    # 1.9 time and Step 1.95 filled it synthetically (pre-8/12 builds lack
    # the marker) — occupancy unknown, must NOT hold. Only promoted DMs were
    # exempt from the DQ pre-8/13, so only they can carry an unflagged REAL
    # at-property address.
    if not ("dm-promoted-pr" in mr or "beneficiary-promoted-pr" in mr):
        return False
    # Synthetic-fill markers (8/12+ builds) and their companion tag.
    if "mailing-from-property" in mr or _has_sibling_parcels(r):
        return False
    if "Verify: No PR Address" in (r.get("Tags") or ""):
        return False
    if (r.get("First Name") or "").strip().lower() == "heirs":
        return False
    prop = _hold_norm_addr(r.get("Property Address"))
    mail = _hold_norm_addr(r.get("Mailing Address"))
    if not prop or not mail:
        return False
    mail_head = mail
    for c in (r.get("Mailing City"), r.get("Property City")):
        cn = _hold_norm_addr(c)
        i = mail.rfind(cn) if cn else -1
        if i > 0:
            mail_head = mail[:i]
            break
    if not (_heir_addr_match(prop, mail) or _heir_addr_match(prop, mail_head)):
        return False
    # Pre-8/12 builds: promotion-synthetic fills carry NO marker, so
    # mailing==property alone is ambiguous. Require PROOF the address came
    # from a real source: (a) a real-lookup reason code, or (b) the obit
    # survivor JSON in the raw scrape file lists the DM's street == property
    # (that's what made Szabo real). Ambiguous rows are skipped and reported.
    if any(t in mr for t in ("pr-people-search", "pr-tracerfy",
                             "coowner-address")):
        return True
    return _obit_json_confirms_at_property(r)


_OBIT_JSON_CACHE: dict[str, dict] = {}


def _obit_json_confirms_at_property(r: dict) -> bool:
    """Scan raw tn_notices_*.csv files for this case; True when the heir
    JSON's entry for the promoted DM carries a street matching the property
    (a real obituary/people-search address, not our fill)."""
    import json as _json
    from fix_addresses_and_prep import _hold_norm_addr, _heir_addr_match
    case = (r.get("Case No.") or "").strip()
    if not case:
        return False
    if not _OBIT_JSON_CACHE:
        for f in sorted(glob.glob("output/tn_notices_*.csv")):
            try:
                for row in csv.reader(open(f, encoding="utf-8-sig")):
                    line = ",".join(row)
                    m = re.search(r"#case=(\S+?)[\s\"]", line + ' ')
                    if not m:
                        continue
                    for cell in row:
                        if cell.startswith("[{"):
                            _OBIT_JSON_CACHE[m.group(1)] = cell
                            break
            except Exception:  # noqa: BLE001
                continue
    blob = _OBIT_JSON_CACHE.get(case)
    if not blob:
        return False
    try:
        heirs = _json.loads(blob)
    except Exception:  # noqa: BLE001
        return False
    prop = _hold_norm_addr(r.get("Property Address"))
    pr_last = (r.get("Last Name") or "").strip().lower()
    pr_first = (r.get("First Name") or "").strip().lower()
    for h_ in heirs:
        name = (h_.get("name") or "").lower()
        if pr_last and pr_last in name and pr_first and pr_first in name:
            st = _hold_norm_addr(h_.get("street"))
            return bool(st and prop and _heir_addr_match(prop, st))
    return False


def build_hold_set() -> list[dict]:
    from fix_addresses_and_prep import hold_occupied_single_asset
    held: dict[str, dict] = {}
    for wk, f in sorted(latest_week_csvs().items()):
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        hold_occupied_single_asset(rows)
        for r in rows:
            mr = r.get("Match Reason") or ""
            if "occupied-hold" not in mr:
                if not _contact_at_property_unflagged(r):
                    continue
                print(f"  CLASS-D (at-property, unflagged) {r.get('County')}/"
                      f"{r.get('Case No.')}: {r.get('Personal Representative')!r}")
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
