"""Finish the DP pushes that only ever sent phones — 3 records still owned by
"Heirs ..." in DataSift while tagged DP Complete. Plus the occupied hold Oren
approved for Punch on 8/22. (Oren runs this himself; the auto-mode classifier
blocks DataSift-writing scripts.)

    cd d:\\SiftStack
    python dp_push_punch_20260822.py            # dry run, shows every write
    python dp_push_punch_20260822.py --apply    # do it

Why this exists
---------------
Oren spotted Punch 26E000919-170 reading "DP Complete" while the owner was
still "Heirs Punch". Root cause: the 8/14 ready-to-call sweep pushed that
estate's PHONES (Punch is in dp_phones_20260814.csv) but left it out of the
DM CSV (dp_dm_20260814.csv), so the owner rename and DM fields never reached
DataSift — they only landed in manual_corrections.csv, which feeds the
WORKBOOK, not the CRM. The 8/19 push then filed Punch under TAG_ONLY and
added "DP Complete", making a half-pushed record look finished.

audit_rename_gap_20260822.py checked all 36 queued renames against the live
account: 26 pushed fine, 3 carry this exact gap. All 3 are here.

  Punch    26E000919-170  Heirs Punch       -> Charles Punch      + OCCUPIED HOLD
  Williams 26E000794-120  Heirs Of Williams -> Elaine Williams
  Wash     26E002820-590  Heirs Wash        -> Richard Wash

Only Punch gets the hold — Oren approved that one (surviving husband/PR
Charles lives at the property). Williams is a surviving-spouse case too and
may deserve the same treatment, but that is his call, so this script only
renames it. See project_surviving_spouse_flag_needs_obit (~40% mislabel).

Recipes reused verbatim: owner PATCH + add-tags/remove-tags from
dp_push_20260819.py (property PATCH of tags is a silent no-op); custom-field
update-values from fix_estate_of_dm_20260814.py; list stripping + PATCH
fallback from hold_occupied_20260819.py. Every write is verified by re-GET
per project_pr_upgrade_silent_save_failure — never trust a status code.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as _dt
import json
import logging
import os
import sys
from pathlib import Path

# datasift_core.login reports WHY a login failed through the logging module
# ("Login form dropped input (attempt N: password len 2/16)", "Sign In still
# disabled", NET POST statuses). Without a handler those are invisible and a
# failure looks like a bare "login failed". Turn them on.
logging.basicConfig(level=logging.INFO, format="  [%(name)s] %(message)s",
                    stream=sys.stdout)

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv

TIERS = {"Dial First", "Dial Second", "Dial Third", "Dial Fourth", "Drop"}
KEEP_LISTS = {"Inherited"}

# The 8/14 CSV had Phone 1-9 columns; the Punch pack scored 14. These 4 never
# landed. type is what DataSift stores; the Trestle truth rides in the tags.
PUNCH_NEW_PHONES = [
    ("8287816937", "MOBILE", ["Dial First", "Son David Jeffrey Punch"]),
    ("8284037407", "MOBILE", ["Dial Third", "Charles Punch / David Punch"]),
    ("8283229389", "LANDLINE", ["Dial Fourth", "Charles / Todd Punch - FixedVOIP per Trestle"]),
    ("8282565891", "LANDLINE", ["Dial Fourth", "Charles Punch - FixedVOIP per Trestle"]),
]
PUNCH_TAG_EXISTING = {
    "8285149008": ["Dial First", "Husband/PR Charles Dwight Punch"],
    "7043229389": ["Dial First", "Son David Jeffrey Punch"],
    "8284037399": ["Dial First", "Son David Jeffrey Punch"],
    "8286129425": ["Dial First", "Son Todd Allan Punch"],
    "8284212137": ["Dial First", "Son Todd Allan Punch"],
    "8287753878": ["Dial First", "Son Todd Allan Punch"],
    "8283285551": ["Dial First", "Son Todd Allan Punch - landline"],
    "8284033740": ["Dial Third", "Husband/PR Charles Dwight Punch"],
    "8282561038": ["Dial Fourth", "Son David Jeffrey Punch"],
    "8286958835": ["Dial Fourth", "Son Todd Allan Punch"],
}

TARGETS = [
    {
        "label": "Punch 26E000919-170 @ 994 22nd St Pl NE, Hickory",
        "uuid": "dbe5c215-c295-4cfd-b50b-4d693a236aa7",
        "guard_last": "punch", "guard_street": "994",
        "rename": ("Charles", "Punch"),
        "pr": "Charles D. Punch",
        "custom": {"decision maker": "Charles D. Punch",
                   "dm relationship": "husband",
                   "dm 2 name": "David Punch", "dm 2 relationship": "son",
                   "dm 3 name": "Todd Punch", "dm 3 relationship": "son"},
        "custom_if_blank": {"decedent": "Sarah Propst Punch",
                            "case number": "26E000919-170"},
        "new_phones": PUNCH_NEW_PHONES,
        "tag_existing": PUNCH_TAG_EXISTING,
        "add_tags": ["Surviving Spouse", "Hold - Occupied"],
        "remove_tags": ["Hold Review - Spouse Occupies"],
        "hold": True,          # strip lists — Oren approved 8/22
    },
    {
        "label": "Williams 26E000794-120 @ 420 Southcircle Dr NW",
        "uuid": "52bf0f83-1926-4e4b-9bf4-fe8d7a252df6",
        "guard_last": "williams", "guard_street": "420",
        "rename": ("Elaine", "Williams"),
        "pr": "Elaine Queen Williams",
        "custom": {"decision maker": "Elaine Queen Williams",
                   "dm relationship": "wife",
                   "dm 2 name": "Dennis Ray Williams", "dm 2 relationship": "son"},
        "custom_if_blank": {"case number": "26E000794-120"},
        "new_phones": [], "tag_existing": {},
        "add_tags": ["Surviving Spouse"],
        "remove_tags": [],
        "hold": False,         # occupancy unconfirmed — Oren's call
    },
    {
        "label": "Wash 26E002820-590",
        "uuid": "2eac5857-63c1-42d3-b11b-8c111d1ba5af",
        "guard_last": "wash", "guard_street": "",
        "rename": ("Richard", "Wash"),
        "pr": "Richard Keifer Wash",
        "custom": {"decision maker": "Richard Keifer Wash",
                   "dm relationship": "son",
                   "dm 2 name": "Aaron Joseph Wash",
                   "dm 2 relationship": "grandchild (per stirpes via late son Joseph)",
                   "dm 3 name": "Bryana Mari Wash",
                   "dm 3 relationship": "grandchild (per stirpes via late son Joseph)"},
        "custom_if_blank": {"case number": "26E002820-590"},
        "new_phones": [], "tag_existing": {},
        "add_tags": ["Multi-Signer (3)"],
        "remove_tags": [],
        "hold": False,
    },
]

_LOG = open(REPO / "logs" / "dp_push_punch_20260822.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]
print(f"\n===== run at {_dt.datetime.now()} apply={APPLY} =====")


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

    async def go(headless: bool):
        email = os.environ.get("DATASIFT_EMAIL", "")
        pw = os.environ.get("DATASIFT_PASSWORD", "")
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=headless)
            page = await (await b.new_context(
                viewport={"width": 1440, "height": 900})).new_page()
            try:
                ok = await login(page, email, pw)
                if not ok:
                    # Same remedy datasift_uploader.py uses (2026-07-31): these
                    # failures are transient and the SAME credentials work
                    # seconds later. One in-page retry before escalating.
                    print(f"  login(headless={headless}) failed — retrying once in 20s")
                    await page.wait_for_timeout(20000)
                    ok = await login(page, email, pw)
                print(f"  login(headless={headless}) -> {ok}; url={page.url}")
                t = (await page.evaluate("() => localStorage.getItem('rs_token')")
                     if ok else None)
                if ok and not t:
                    print("  logged in but no rs_token in localStorage")
                return t
            except Exception as e:  # noqa: BLE001
                print(f"  login(headless={headless}) raised: {e}")
                return None
            finally:
                await b.close()

    # Headless first. If it fails — DataSift's SPA sometimes refuses headless
    # sessions, especially after several logins in a row — retry with a VISIBLE
    # window so a captcha or "verify it's you" prompt can be cleared by hand.
    t = asyncio.run(go(True))
    if t:
        return t
    print("headless login failed — retrying with a VISIBLE browser window.")
    print("If a captcha or verification prompt appears, solve it; the script waits.")
    return asyncio.run(go(False))


def digits(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def titles(items) -> list[str]:
    return [x.get("title") if isinstance(x, dict) else str(x) for x in (items or [])]


def get_prop(h, uuid) -> dict:
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET property -> HTTP {r.status_code} {r.text[:150]}")
        return {}
    return r.json()


def cf_definitions(h) -> dict[str, str]:
    """label(lower) -> definition uuid, account-wide. Fetched once."""
    out: dict[str, str] = {}
    r = requests.get(f"{API}/api/internal/custom-fields/?entity_type=property"
                     "&offset=0&limit=1000", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  custom-fields list -> HTTP {r.status_code} — using record rows only")
        return out
    for f in (r.json().get("results") or []):
        lab = (f.get("label") or "").strip().lower()
        if lab and f.get("uuid"):
            out.setdefault(lab, f["uuid"])
    return out


def cf_values(h, uuid) -> dict[str, dict]:
    """label(lower) -> value row {uuid, custom_field, value} for one record."""
    r = requests.get(f"{API}/api/internal/property/{uuid}/custom-field/"
                     "?offset=0&limit=1000", headers=h, timeout=30)
    if r.status_code != 200:
        return {}
    out = {}
    for e in (r.json().get("results") or []):
        lab = ((e.get("custom_field") or {}).get("label") or "").strip().lower()
        if lab:
            out[lab] = e
    return out


def push_one(h: dict, defs: dict[str, str], spec: dict) -> bool:
    uuid = spec["uuid"]
    print(f"\n=== {spec['label']}")
    d = get_prop(h, uuid)
    if not d:
        return False
    owner = d.get("owner") or {}
    addr = d.get("address") or {}
    live_last = (owner.get("last_name") or "").strip().lower()
    live_street = (addr.get("street") or "").strip()
    print(f"  live owner : {owner.get('first_name')!r} {owner.get('last_name')!r}")
    print(f"  live addr  : {live_street}, {addr.get('city')}")
    print(f"  live PR    : {d.get('personal_representative')!r}")
    print(f"  live tags  : {titles(d.get('tags'))}")
    print(f"  live lists : {titles(d.get('lists'))}")
    print(f"  live phones: {len(owner.get('phones') or [])}")

    # ---- identity guard -----------------------------------------------------
    if spec["guard_last"] not in live_last:
        print(f"  IDENTITY MISMATCH (last={live_last!r}) — SKIP")
        return False
    if spec["guard_street"] and not live_street.startswith(spec["guard_street"]):
        print(f"  IDENTITY MISMATCH (street={live_street!r}) — SKIP")
        return False
    fn, ln = spec["rename"]
    if (owner.get("first_name") or "").strip().lower() == fn.lower():
        print("  owner already renamed — will still sync fields/tags/lists")

    # ---- 1. owner: rename + phones -----------------------------------------
    new_owner = copy.deepcopy(owner)
    new_owner["first_name"], new_owner["last_name"] = fn, ln
    existing = {digits(p.get("number")): p for p in (new_owner.get("phones") or [])}

    added = []
    for num, ptype, tags in spec["new_phones"]:
        if num in existing:
            print(f"  phone {num} already on record — not re-adding")
            continue
        new_owner.setdefault("phones", []).append(
            {"number": num, "type": ptype, "tags": tags})
        added.append(num)

    retagged = []
    for num, tags in spec["tag_existing"].items():
        p = existing.get(num)
        if not p:
            print(f"  phone {num} expected on record but absent — skipping tag")
            continue
        cur = [t if isinstance(t, str) else t.get("title") for t in (p.get("tags") or [])]
        if TIERS & set(tags):                       # a tier tag REPLACES any old tier
            cur = [t for t in cur if t not in TIERS]
        merged = list(dict.fromkeys([*(t for t in cur if t), *tags]))
        if merged != [t for t in (p.get("tags") or [])]:
            p["tags"] = merged
            retagged.append(num)

    print(f"  owner rename -> {fn} {ln}; +{len(added)} phones {added}; "
          f"retag {len(retagged)} existing")
    print("  mailing left untouched")

    if not APPLY:
        print(f"  DRY: would PATCH owner + personal_representative={spec['pr']!r}")
    else:
        body = {"owner": new_owner, "personal_representative": spec["pr"]}
        pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                            data=json.dumps(body), timeout=30)
        print(f"  PATCH owner+PR -> {pr.status_code} {pr.text[:150]}")
        if pr.status_code not in (200, 202):
            print("  owner PATCH failed — SKIP the rest of this record")
            return False

    # ---- 2. custom fields (Estate Files, group 94) --------------------------
    # FILL-IF-BLANK ONLY. A non-blank field is either already correct or a
    # hand-correction, and the live value is often the better one (Punch's
    # Decision Maker reads "Charles Dwight Punch"; the queued correction says
    # "Charles D. Punch"). Differences are printed, never written — clobbering
    # good data is exactly the failure project_pr_upgrade_silent_save_failure
    # is about.
    rows = cf_values(h, uuid)
    wanted, differs = {}, []
    for lab, val in {**spec["custom"], **spec["custom_if_blank"]}.items():
        cur = (rows.get(lab, {}).get("value") or "").strip()
        if not cur:
            wanted[lab] = val
        elif cur != val:
            differs.append((lab, cur, val))
        else:
            print(f"  custom {lab!r} already {cur!r} — no-op")
    for lab, cur, val in differs:
        print(f"  custom {lab!r} DIFFERS: live {cur!r} vs queued {val!r} "
              f"— LEAVING live value (change by hand if the queued one is better)")

    items, unresolved = [], []
    for lab, val in wanted.items():
        fuuid = defs.get(lab) or ((rows.get(lab) or {}).get("custom_field") or {}).get("uuid")
        if not fuuid:
            unresolved.append(lab)
            continue
        items.append({"field_uuid": fuuid, "value": val})
    if unresolved:
        print(f"  !! no field definition for {unresolved} — those go unwritten")
    for lab, val in wanted.items():
        print(f"  custom {lab!r}: {(rows.get(lab, {}).get('value') or '')!r} -> {val!r}")
    if not APPLY:
        print(f"  DRY: would PATCH {len(items)} custom-field values")
    elif items:
        url = f"{API}/api/internal/property/{uuid}/custom-field/update-values/"
        r = requests.patch(url, headers=h, data=json.dumps(items), timeout=30)
        print(f"  PATCH custom-field/update-values ({len(items)}) -> "
              f"{r.status_code} {r.text[:150]}")

    # ---- 3. tags (+ occupied hold: strip lists) -----------------------------
    live_lists = titles(d.get("lists"))
    drop = [l for l in live_lists if l not in KEEP_LISTS] if spec["hold"] else []
    print(f"  tags  += {spec['add_tags']}"
          + (f"; -= {spec['remove_tags']}" if spec["remove_tags"] else ""))
    if spec["hold"]:
        print(f"  HOLD: lists -= {drop}  (keeping {sorted(KEEP_LISTS & set(live_lists))})")
    else:
        print(f"  no hold — lists left as-is {live_lists}")
    if not APPLY:
        print("  DRY: no tag/list writes made")
    else:
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": spec["add_tags"]}, timeout=30)
        print(f"  add-tags -> {r.status_code} {r.text[:120]}")
        if spec["remove_tags"]:
            r = requests.post(f"{API}/api/internal/property/{uuid}/remove-tags/",
                              headers=h, json={"tags": spec["remove_tags"]}, timeout=30)
            print(f"  remove-tags -> {r.status_code} {r.text[:120]}")
        if drop:
            r = requests.post(f"{API}/api/internal/property/{uuid}/remove-lists/",
                              headers=h, json={"lists": drop}, timeout=30)
            print(f"  remove-lists {drop} -> {r.status_code} {r.text[:120]}")

    if not APPLY:
        return True

    # ---- 4. verify everything by re-GET ------------------------------------
    chk = get_prop(h, uuid)
    co = chk.get("owner") or {}
    nums = {digits(p.get("number")) for p in (co.get("phones") or [])}
    tags_now = titles(chk.get("tags"))
    lists_now = titles(chk.get("lists"))
    rows_now = cf_values(h, uuid)

    name_ok = (co.get("first_name") == fn and co.get("last_name") == ln)
    pr_ok = (chk.get("personal_representative") or "").strip() == spec["pr"]
    phones_ok = all(n in nums for n, *_ in spec["new_phones"])
    tags_ok = all(t in tags_now for t in spec["add_tags"]) and not any(
        t in tags_now for t in spec["remove_tags"])
    lists_ok = (not (set(lists_now) - KEEP_LISTS)) if spec["hold"] else True
    cf_bad = [lab for lab, val in wanted.items()
              if (rows_now.get(lab, {}).get("value") or "").strip() != val]

    # fallback: PATCH lists down if remove-lists silently no-opped
    if spec["hold"] and not lists_ok:
        keep = [l for l in lists_now if l in KEEP_LISTS]
        p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"lists": keep}, timeout=30)
        print(f"  fallback PATCH lists={keep} -> {p.status_code}")
        lists_now = titles(get_prop(h, uuid).get("lists"))
        lists_ok = not (set(lists_now) - KEEP_LISTS)

    print(f"  verify owner  : {co.get('first_name')} {co.get('last_name')}  ok={name_ok}")
    print(f"  verify PR     : {chk.get('personal_representative')!r}  ok={pr_ok}")
    if spec["new_phones"]:
        print(f"  verify phones : {len(nums)} on record; new present="
              f"{sorted(n for n, *_ in spec['new_phones'] if n in nums)} ok={phones_ok}")
    print(f"  verify tags   : {tags_now}  ok={tags_ok}")
    print(f"  verify lists  : {lists_now}  ok={lists_ok}")
    print(f"  verify custom : {'all set' if not cf_bad else 'NOT SET -> ' + str(cf_bad)}")

    ok = name_ok and pr_ok and phones_ok and tags_ok and lists_ok and not cf_bad
    print(f"  RESULT: {'OK' if ok else 'CHECK BY HAND'}")
    return ok


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}

    defs = cf_definitions(h)
    print(f"custom-field definitions loaded: {len(defs)}")

    results = [(t["label"], push_one(h, defs, t)) for t in TARGETS]

    print("\n==== SUMMARY ====")
    for label, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label}")
    if not APPLY:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0
    good = sum(1 for _, ok in results if ok)
    print(f"\n{good}/{len(results)} pushed.")
    print("Next: append dp_log.csv lines for the 8/22 completions, and re-run "
          "audit_rename_gap_20260822.py to confirm 0 gaps remain.")
    return 0 if good == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
