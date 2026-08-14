"""One-off: clear the bare "Estate of" Decision Maker placeholder from
already-uploaded DataSift records (Oren reported 2026-08-14, Williams
26E000794-120 / 420 Southcircle Dr NW on screen).

Root cause (fixed same day in src/obituary_enricher.py): the obituary
enricher's Path 5 estate fallback built "Estate of {owner_name}", and for
probate rows owner_name is the PR/executor — blank on exactly the no-PR
cases that reach the fallback. Result: Decision Maker custom field =
literal "Estate of", DM Relationship = "estate", on 2-5 rows/week.
17 uploaded cases carry it (weeks 28-33) + 3 possible manual-era records.

Self-guarding: a record is only touched when its Decision Maker custom
field is EXACTLY "Estate of" (case-insensitive) — records whose DM was
since hand-corrected are skipped untouched.

Endpoints (READ discovered by sniffing the record Fields tab; WRITE found in
app.reisift.io/main.min.js `updateEntityCustomFields`, 2026-08-14):
  GET   /api/internal/property/{uuid}/custom-field/?limit=1000
  PATCH /api/internal/property/{uuid}/custom-field/update-values/
        (per-value-row and collection PATCH/DELETE/POST all 404/405 — this
        bulk route is the ONLY write path; exact body shape unverified, so
        clear_value tries the likely shapes and trusts only the re-GET)
Verified by re-GET per project_pr_upgrade_silent_save_failure rules.

Usage:
    python fix_estate_of_dm_20260814.py --dry-run
    python fix_estate_of_dm_20260814.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://apiv2.reisift.io"

# Case No. -> (decedent surname, [search strings tried in order]).
# Full CSV street first; DataSift may have re-normalized it (Williams: CSV
# "420 South Cir Nw" -> DS "420 Southcircle Dr NW"), so the surname is the
# last resort (hits filtered to owner First Name == "Heirs").
CASES = {
    "26E000498-540": ("Smith",       ["6039 Old South Dr"]),
    "26E000658-480": ("Dunn",        ["149 Woodlawn Dr"]),
    # Clark 26E000760-480 + James 26E002599-590 verified NOT in DataSift
    # (0 search hits; neither is in the upload ledger) — left in so a future
    # upload that carries them still gets checked.
    "26E000760-480": ("Clark",       ["262 Fremont Loop"]),
    "26E000789-790": ("Kimball",     ["607 Hidden Creek Cir"]),
    "26E000793-480": ("Brawley",     ["143 Bufflehead Dr"]),
    "26E000794-120": ("Williams",    ["420 Southcircle Dr NW", "420 South Cir Nw"]),
    "26E000885-170": ("Rhoney",      ["477 14th Avenue Dr NE", "477 14th Ave Dr NE"]),
    "26E000887-170": ("Eckard",      ["4115 Wandering Ln NE"]),
    "26E000888-170": ("Hartsoe",     ["3032 Phifer St"]),
    "26E000942-170": ("Keener",      ["7050 Martin Mill Rd"]),
    "26E002599-590": ("James",       ["5126 Glenbrier Dr"]),
    "26E002844-590": ("Baker",       ["6034 Shining Oak Ln", "2417 Normancrest Ct"]),
    "26E002847-590": ("James",       ["5522 Slaton Rd"]),
    "26E002891-590": ("Gregory",     ["8518 Mcclure Cr", "8518 Mcclure Circle"]),
    "26E002907-590": ("Sylvester",   ["5514 Samuel Neel Rd"]),
    "26E002910-590": ("Roberson",    ["3206 Connecticut Av", "3206 Connecticut Ave"]),
    "26E002916-590": ("Holbrook",    ["115 S Church St"]),
    "26E002941-590": ("Cuthbertson", ["1153 Pondella Dr"]),
    "26E002995-590": ("Adams",       ["1825 Rice Planters Rd"]),
    "26E003003-590": ("Dunlap",      ["1912 Wilmore Dr"]),
}


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


def get_cf_values(h: dict, uuid: str) -> list[dict]:
    r = requests.get(f"{API}/api/internal/property/{uuid}/custom-field/?offset=0&limit=1000",
                     headers=h, timeout=30)
    if r.status_code != 200:
        return []
    return r.json().get("results") or []


def cf_by_label(ents: list[dict]) -> dict[str, dict]:
    out = {}
    for e in ents:
        lab = ((e.get("custom_field") or {}).get("label") or "").strip().lower()
        if lab:
            out[lab] = e
    return out


def clear_values(h: dict, prop_uuid: str, entries: list[dict]) -> bool:
    """Bulk-clear custom-field values via the UI's update-values route.

    Body shape (from the route's own 400: "field_uuid is required"): a flat
    list of {"field_uuid": ..., "value": ...}. Tried with the custom-field
    DEFINITION uuid first, then the value-row uuid. The caller trusts ONLY
    the re-GET verification, never the status code.
    """
    url = f"{API}/api/internal/property/{prop_uuid}/custom-field/update-values/"
    for key in ("def", "row"):
        items = [{"field_uuid": (e["custom_field"]["uuid"] if key == "def" else e["uuid"]),
                  "value": ""} for e in entries]
        pr = requests.patch(url, headers=h, data=json.dumps(items), timeout=30)
        if pr.status_code in (200, 202):
            return True
        print(f"    PATCH ({key} uuid) -> {pr.status_code} {pr.text[:150]}")
    return False


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

    fixed, untouched, skipped = [], [], []
    for case_no, (surname, streets) in CASES.items():
        print(f"\n=== {case_no} ({surname}) ===")
        # Find the record: exact-ish street search first, then surname search
        # restricted to "Heirs <surname>" owner records.
        cand = None
        for text in streets:
            hits = search(h, text)
            if len(hits) == 1:
                cand = hits[0]
                break
            if len(hits) > 1:
                num = (text.split() or [""])[0]
                exact = [r for r in hits
                         if ((r.get("address") or {}).get("street") or "").lower().startswith(num.lower() + " ")]
                if len(exact) == 1:
                    cand = exact[0]
                    break
        if cand is None:
            hits = [r for r in search(h, surname)
                    if ((r.get("owner") or {}).get("first_name") or "").strip().lower() == "heirs"
                    and ((r.get("owner") or {}).get("last_name") or "").strip().lower() == surname.lower()]
            if len(hits) == 1:
                cand = hits[0]
        if cand is None:
            skipped.append((case_no, surname, "no unique record found"))
            print("  no unique record found — skipping")
            continue

        uuid = cand.get("uuid") or cand.get("id")
        addr = cand.get("address") or {}
        owner = cand.get("owner") or {}
        print(f"  found: {addr.get('street')}, {addr.get('city')} | "
              f"owner {owner.get('first_name')} {owner.get('last_name')} | {uuid}")

        ents = cf_by_label(get_cf_values(h, uuid))
        dec_val = (ents.get("decedent", {}).get("value") or "").strip().lower()
        dm_e = ents.get("decision maker")
        rel_e = ents.get("dm relationship")
        dm_val = (dm_e or {}).get("value") or ""
        rel_val = (rel_e or {}).get("value") or ""
        print(f"  Decedent={dec_val!r}  Decision Maker={dm_val!r}  DM Relationship={rel_val!r}")

        # Identity guard: the record's decedent (or owner surname) must match.
        own_last = (owner.get("last_name") or "").strip().lower()
        if surname.lower() not in dec_val and own_last != surname.lower():
            skipped.append((case_no, surname, f"identity mismatch (decedent={dec_val!r})"))
            print("  identity mismatch — skipping")
            continue
        if dm_val.strip().lower() != "estate of":
            untouched.append((case_no, surname, dm_val))
            print("  DM is not the bare placeholder — leaving untouched")
            continue
        if dry:
            print("  DRY RUN: would clear Decision Maker"
                  + (" + DM Relationship" if rel_val.strip().lower() == "estate" else ""))
            fixed.append((case_no, surname))
            continue

        targets = [dm_e]
        if rel_e and rel_val.strip().lower() == "estate":
            targets.append(rel_e)
        clear_values(h, uuid, targets)
        # Verify by re-GET — a DataSift save can fail silently.
        chk = cf_by_label(get_cf_values(h, uuid))
        chk_dm = (chk.get("decision maker", {}).get("value") or "").strip()
        if chk_dm.lower() != "estate of":
            print(f"  verified: Decision Maker now {chk_dm!r}")
            fixed.append((case_no, surname))
        else:
            skipped.append((case_no, surname, "verify failed — clear did not stick"))
            print("  VERIFY FAILED — 'Estate of' still on record")

    print(f"\n==== SUMMARY {'(DRY RUN)' if dry else ''} ====")
    print(f"cleared: {len(fixed)}  {[c for c, *_ in fixed]}")
    for c, s, v in untouched:
        print(f"untouched (DM={v!r}): {c} ({s})")
    for c, s, why in skipped:
        print(f"skipped: {c} ({s}) — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
