"""DP push 2026-08-19 — Oren runs this himself (the Claude auto-mode
classifier blocks DataSift-writing scripts; same as 8/17).

    cd d:\\SiftStack
    python dp_push_20260819.py            # everything
    python dp_push_20260819.py --dry-run  # show what it WOULD do, no writes

What it does (all findings in output/reports/DP_*.md, ledger dp_log.csv):

A. Tag hygiene on the 4 records DP'd back on 8/14 whose tags were never
   updated: Jenkins + Peche lose the stale "Needs DP"; Jenkins, Peche,
   Punch, Cuthbertson gain "DP Complete".

B. Six heirs-of records get their DP results pushed (owner -> real DM,
   mailing fixed where the DM lives elsewhere, new Trestle-tiered phones
   appended, "Needs DP" -> "DP Complete"):
   - Gregory 26E002891-590: son Michael Kyle Gregory (AT property) + 3 phones
   - Adams 26E002995-590: widow Marianne Wagnon (AT property) + 4 phones
       ** occupied-hold candidate — spouse lives at the property **
   - Dunlap 26E003003-590: daughter Aretha Dunlap (mailing -> Coliseum Dr)
       + 4 phones (Stephen's fresh VA-area numbers incl.)
   - Zion 26E002962-590: son Christopher George Zion (mailing -> Asheville);
       his existing caller-CORRECT phone gets Dial First
       ** occupied-hold candidate — surviving spouse Jocelyne on site **
   - Overcash (DataFlik, 1250 Chow Dr): Kathryn Dixon (tax C/O) + 4 phones
   - Archie (DataFlik, 100 Cedar St): Eboni Archie (tax C/O) + 1 phone

Recipe: same guarded pattern as dp_fix_mailings_20260817.py — owner object
round-tripped in full, never blank over existing, add-tags/remove-tags/
endpoints (property PATCH tag removal is a silent no-op), verify by re-GET.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as _dt
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"
DRY = "--dry-run" in sys.argv

_LOG = open(REPO / "logs" / "dp_push_20260819.log", "a", encoding="utf-8")
_stdout_write = sys.stdout.write


def _tee(text):
    _stdout_write(text)
    _LOG.write(text)
    _LOG.flush()


sys.stdout.write = _tee
_stderr_write = sys.stderr.write


def _tee_err(text):
    _stderr_write(text)
    _LOG.write(text)
    _LOG.flush()


sys.stderr.write = _tee_err
print(f"\n===== run at {_dt.datetime.now()} dry_run={DRY} =====")

# ── A. tag-only hygiene (8/14 DP'd records) ────────────────────────────────
TAG_ONLY = [
    ("Jenkins 26E003002-590", "e8a8b451-94da-40fa-98bd-529a359bbf49",
     ["Needs DP"], ["DP Complete"]),
    ("Peche 26E001070-350", "2c19027b-d496-4d62-9c73-101ab549f99e",
     ["Needs DP"], ["DP Complete"]),
    ("Punch 26E000919-170", "dbe5c215-c295-4cfd-b50b-4d693a236aa7",
     [], ["DP Complete"]),
    ("Cuthbertson 26E002941-590", "ee516f1d-6675-4311-a204-1c4b2f9541bf",
     [], ["DP Complete"]),
]

# ── B. full DP pushes ──────────────────────────────────────────────────────
# phone dicts: number digits only; tags are plain strings (server maps them —
# proven 8/14, "tier tags + 'DM2 <name>' labels stick and verify")
PUSHES = [
    {"label": "Gregory 26E002891-590 @ 8518 Mcclure Cr",
     "uuid": "bda78623-c056-469f-bae7-4135daa84c98",
     "owner_frag": "gregory",
     "rename": ("Michael Kyle", "Gregory"),
     "mail": None,  # he lives at the property; leave mailing as-is
     "phones": [("7045601527", ["Dial First", "Son Michael Kyle Gregory"]),
                ("7046970610", ["Dial Fourth", "Michael landline"]),
                ("7043929157", ["Dial Fourth", "household landline"])],
     "rm": [], "add": ["DP Complete"]},
    {"label": "Adams 26E002995-590 @ 1825 Rice Planters Rd",
     "uuid": "f695a966-4e83-4017-8080-9247a71552de",
     "owner_frag": "adams",
     "rename": ("Marianne", "Wagnon"),
     "mail": None,  # widow lives at the property
     "phones": [("7043407961", ["Dial First", "Widow Marianne Wagnon"]),
                ("7043407962", ["Dial Second", "Marianne alt"]),
                ("9158759999", ["Dial First", "Son John Taylor Adams (Guthrie OK)"]),
                ("9152199517", ["Dial Second", "John voip"])],
     "rm": ["Needs DP"], "add": ["DP Complete", "Hold Review - Spouse Occupies"]},
    {"label": "Dunlap 26E003003-590 @ 1912 Wilmore Dr",
     "uuid": "dc6a8be3-deb0-46ff-96c9-c10f8d7a32ab",
     "owner_frag": "dunlap",
     "rename": ("Aretha", "Dunlap"),
     "mail": {"street": "1112 Coliseum Dr Apt C", "city": "Charlotte",
              "state": "NC", "postal_code": "28205"},
     "phones": [("7049091302", ["Dial First", "Daughter Aretha Dunlap"]),
                ("9802261496", ["Dial First", "Aretha alt"]),
                ("7047060890", ["Dial Second", "Son Stephen Dunlap (VA)"]),
                ("7044491342", ["Dial Fourth", "Judy Ann Dunlap (kin)"])],
     "rm": ["Needs DP"], "add": ["DP Complete"]},
    {"label": "Zion 26E002962-590 @ 832 Stratfordshire Dr",
     "uuid": "eae607c7-0038-4a63-ac07-d5e6b8476760",
     "owner_frag": "zion",
     "rename": ("Christopher George", "Zion"),
     "mail": {"street": "1905 Abbey Cir", "city": "Asheville",
              "state": "NC", "postal_code": "28805"},
     "phones": [],  # (704) 572-1093 already on the record — tag it below
     "tag_existing_phone": ("7045721093", ["Dial First"]),
     "rm": ["Needs DP"], "add": ["DP Complete", "Hold Review - Spouse Occupies"]},
    {"label": "Overcash (DataFlik) @ 1250 Chow Dr",
     "uuid": "d8d2cc44-a6f2-4941-a989-8f3fe035d541",
     "owner_frag": "overcash",
     "rename": ("Kathryn", "Dixon"),
     "mail": None,  # mailing already 122 Brewer Ln = her current address
     "phones": [("7046407591", ["Dial First", "Kathryn Dixon (tax contact, rel unverified)"]),
                ("7047874789", ["Dial First", "Son Timothy Overcash (obit)"]),
                ("7044256644", ["Dial First", "Timothy alt"]),
                ("7048570662", ["Dial Fourth", "Kathryn landline"])],
     "rm": [], "add": ["DP Complete"]},
    {"label": "Archie (DataFlik) @ 100 Cedar St",
     "uuid": "b612490b-2615-45b0-8934-08aa4422c7b6",
     "owner_frag": "archie",
     "rename": ("Eboni", "Archie"),
     "mail": None,  # mailing already 1300 Old Concord Rd Apt 5 = her address
     "phones": [("2024009396", ["Dial First", "Eboni Archie (tax contact)"])],
     "rm": [], "add": ["DP Complete"]},
]


def token() -> str | None:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        print("using DS_TOKEN from environment")
        return t
    try:
        from get_ds_token import get_token
        sys.path.insert(0, str(REPO))
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
    return asyncio.run(go())


def tag_titles(rec: dict) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (rec.get("tags") or [])]


def do_tags(h, uuid, rm, add):
    for tags, path in ((rm, "remove-tags"), (add, "add-tags")):
        if not tags:
            continue
        if DRY:
            print(f"  DRY: {path} {tags}")
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/{path}/",
                          headers=h, json={"tags": tags}, timeout=30)
        print(f"  {path} {tags} -> HTTP {r.status_code} {r.text[:150]}")


def push_one(h: dict, spec: dict) -> bool:
    print(f"\n=== {spec['label']}")
    uuid = spec["uuid"]
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET -> {r.status_code} — SKIP")
        return False
    d = r.json()
    owner = d.get("owner") or {}
    if spec["owner_frag"] not in (owner.get("last_name") or "").lower():
        print(f"  owner {owner.get('first_name')} {owner.get('last_name')!r} "
              f"lacks frag {spec['owner_frag']!r} — SKIP (already renamed?)")
        do_tags(h, uuid, spec["rm"], spec["add"])
        return False
    print(f"  live owner: {owner.get('first_name')} {owner.get('last_name')} "
          f"mail={(owner.get('address') or {}).get('street')!r} "
          f"phones={len(owner.get('phones') or [])}")

    new_owner = copy.deepcopy(owner)
    fn, ln = spec["rename"]
    new_owner["first_name"], new_owner["last_name"] = fn, ln
    if spec["mail"]:
        new_owner.setdefault("address", {})
        new_owner["address"].update(spec["mail"])
    existing_nums = {"".join(c for c in str(p.get("number") or "") if c.isdigit())
                     for p in (new_owner.get("phones") or [])}
    added = 0
    for num, tags in spec.get("phones", []):
        if num in existing_nums:
            print(f"  phone {num} already on record — skipping add")
            continue
        new_owner.setdefault("phones", []).append(
            {"number": num, "type": "MOBILE", "tags": tags})
        added += 1
    tep = spec.get("tag_existing_phone")
    if tep:
        num, tags = tep
        _TIERS = {"Dial First", "Dial Second", "Dial Third", "Dial Fourth", "Drop"}
        for p in new_owner.get("phones") or []:
            if "".join(c for c in str(p.get("number") or "") if c.isdigit()) == num:
                cur = [t if isinstance(t, str) else t.get("title") for t in (p.get("tags") or [])]
                # new tier tag REPLACES any existing tier tag (never both)
                if _TIERS & set(tags):
                    cur = [t for t in cur if t not in _TIERS]
                p["tags"] = list(dict.fromkeys([*(t for t in cur if t), *tags]))
                print(f"  tagging existing phone {num} -> {p['tags']}")

    if DRY:
        print(f"  DRY: would PATCH owner -> {fn} {ln}, mail={spec['mail']}, "
              f"+{added} phones")
        do_tags(h, uuid, spec["rm"], spec["add"])
        return True
    pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                        data=json.dumps({"owner": new_owner}), timeout=30)
    print(f"  PATCH owner -> {pr.status_code} {pr.text[:150]}")
    if pr.status_code not in (200, 202):
        return False
    do_tags(h, uuid, spec["rm"], spec["add"])

    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    co = cd.get("owner") or {}
    nums = {"".join(c for c in str(p.get("number") or "") if c.isdigit())
            for p in (co.get("phones") or [])}
    want = {n for n, _ in spec.get("phones", [])}
    name_ok = (co.get("first_name") == fn and co.get("last_name") == ln)
    phones_ok = want.issubset(nums)
    tags_now = tag_titles(cd)
    tags_ok = all(t in tags_now for t in spec["add"]) and not any(
        t in tags_now for t in spec["rm"])
    print(f"  verify: owner={co.get('first_name')} {co.get('last_name')} "
          f"phones_present={sorted(nums & want) if want else 'n/a'} "
          f"missing={sorted(want - nums)} tags_ok={tags_ok}")
    ok = name_ok and phones_ok and tags_ok
    print(f"  RESULT: {'OK' if ok else 'CHECK BY HAND'}")
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

    print("\n--- A. tag hygiene (8/14 DP'd records) ---")
    for label, uuid, rm, add in TAG_ONLY:
        print(f"=== {label}")
        do_tags(h, uuid, rm, add)
        if not DRY:
            chk = requests.get(f"{API}/api/internal/property/{uuid}/",
                               headers=h, timeout=30)
            tt = tag_titles(chk.json()) if chk.status_code == 200 else []
            ok = all(t in tt for t in add) and not any(t in tt for t in rm)
            print(f"  verify tags: {'OK' if ok else 'CHECK BY HAND'}")

    print("\n--- B. DP pushes ---")
    done = sum(1 for spec in PUSHES if push_one(h, spec))
    print(f"\n{done}/{len(PUSHES)} records pushed.")
    print("Reminder: after this run, Adams/Dunlap/Zion leave the Needs DP "
          "state; Overcash + Archie should flow from '01. Skipped No Numbers' "
          "into '02. Ready to Call' once the search index settles (~1-2 min).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
