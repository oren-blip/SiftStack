"""One-off: add the 'DP Complete' tag to the 15 already-worked DP cases.

Oren approved 2026-08-13 ("yes" to tagging generated DP cases). Counterpart to
tag_needs_dp_20260813.py: "Needs DP" = still open, "DP Complete" = worked.

API-only (record search + PATCH, same recipe as fix_putnam_20260813.py) —
NOT the upload-wizard upsert, which would CREATE a stranger record for any
case whose address isn't already in DataSift.

Per case: search by property street, accept only a unique record whose
street matches a known candidate address, round-trip the record's full tag
list with 'DP Complete' appended. Never writes blanks (see
project_pr_upgrade_silent_save_failure). Run with --dry-run first.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://apiv2.reisift.io"
TAG = "DP Complete"

# Case No. -> candidate property streets, tried in order (first = current
# belief of what's on the DS record; later = pre-correction upload address).
CASES = {
    "26E002835-590": ("Dixon", ["7645 Wallace Ln"]),
    "26E000740-480": ("Hill", ["306 S Greenbriar Rd"]),
    # DS stores this estate's record at parcel 430 (of the 3 life-estate parcels)
    "26E001011-350": ("Lineberger", ["430 Ike Lynch Rd"]),
    "26E001008-350": ("Pendleton", ["115 Southpoint Dr"]),  # DS: one word
    "26E000776-790": ("Yow", ["1300 Sides Ave"]),
    "26E002844-590": ("Baker", ["6034 Shining Oak Ln"]),  # stranger @ Normancrest deleted 8/12
    "26E002916-590": ("Holbrook", ["115 S Church St"]),
    "26E001041-350": ("Preidt", ["221 Fielding St"]),
    "26E000801-790": ("Williams", ["1002 W Stokes St"]),
    "26E002976-590": ("Robertson", ["4336 Silo Ln", "16018 River Tree Ln"]),
    "26E002853-590": ("Hatcher", ["10015 Franklin Dr"]),
    "26E000780-480": ("Flammer", ["106 Friendly Cir"]),
    "26E000795-790": ("Foster", ["2683 Oddie Rd"]),
    "26E000808-790": ("Mahaffey", ["0 Luther Barger Rd", "Luther Barger Rd"]),
    "26E000492-540": ("Brown", ["1192 Alf Hoover Rd"]),
}


def norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"^0\s+", "", s)          # vacant-lot "0 " prefix convention
    s = re.sub(r"\s+", " ", s)
    return s


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


def search(h: dict, text: str) -> list[dict]:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      data=json.dumps({"query": {"must": {"search": text}}}),
                      timeout=30)
    if r.status_code != 200:
        print(f"  search {text!r} -> HTTP {r.status_code}")
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def main() -> int:
    dry = "--dry-run" in sys.argv
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    tagged, skipped, already = [], [], []
    for case_no, (name, streets) in CASES.items():
        print(f"\n=== {case_no} ({name}) ===")
        match = None
        for street in streets:
            hits = search(h, street)
            cands = [r for r in hits
                     if norm((r.get("address") or {}).get("street")) == norm(street)]
            if len(cands) == 1:
                match = cands[0]
                break
            if len(cands) > 1:
                print(f"  {street!r}: {len(cands)} records match — ambiguous, skipping case")
                break
            print(f"  {street!r}: no exact match ({len(hits)} raw hits)")
        if match is None:
            skipped.append((case_no, name, "no unique record"))
            continue

        uuid = match.get("uuid") or match.get("id")
        addr = match.get("address") or {}
        owner = match.get("owner") or {}
        # Round-trip via GET so we PATCH from the full live object, not a
        # possibly-trimmed search result.
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if g.status_code != 200:
            print(f"  GET {uuid} -> {g.status_code}, skipping")
            skipped.append((case_no, name, f"GET {g.status_code}"))
            continue
        live = g.json()
        tags = live.get("tags")
        print(f"  found: {addr.get('street')}, {addr.get('city')} | "
              f"owner {owner.get('first_name')} {owner.get('last_name')} | uuid {uuid}")
        print(f"  tags ({type(tags).__name__}): {json.dumps(tags)[:300]}")

        if tags is None:
            skipped.append((case_no, name, "no tags field on record — inspect by hand"))
            continue
        tag_names = [t if isinstance(t, str) else (t.get("name") or "") for t in tags]
        if any(n.strip().lower() == TAG.lower() for n in tag_names):
            print("  already tagged — nothing to do")
            already.append((case_no, name))
            continue
        if dry:
            print(f"  DRY RUN: would add {TAG!r}")
            tagged.append((case_no, name))
            continue

        if tags and not isinstance(tags[0], str):
            new_tags = copy.deepcopy(tags) + [{"name": TAG}]
        else:
            new_tags = list(tags) + [TAG]
        pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                            data=json.dumps({"tags": new_tags}), timeout=30)
        if pr.status_code not in (200, 202):
            print(f"  PATCH -> {pr.status_code} {pr.text[:200]} — skipping, no retry")
            skipped.append((case_no, name, f"PATCH {pr.status_code}"))
            continue
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        cn = [t if isinstance(t, str) else (t.get("name") or "")
              for t in (chk.json().get("tags") or [])] if chk.status_code == 200 else []
        if any(n.strip().lower() == TAG.lower() for n in cn):
            print("  verified: tag landed")
            tagged.append((case_no, name))
        else:
            print("  VERIFY FAILED — tag not on record after PATCH")
            skipped.append((case_no, name, "verify failed"))

    print(f"\n==== SUMMARY {'(DRY RUN)' if dry else ''} ====")
    print(f"tagged:  {len(tagged)}  {[c for c, _ in tagged]}")
    print(f"already: {len(already)} {[c for c, _ in already]}")
    for c, n, why in skipped:
        print(f"skipped: {c} ({n}) — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
