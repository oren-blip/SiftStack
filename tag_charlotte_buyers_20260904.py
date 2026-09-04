"""Tag the 2026-09-04 Charlotte buyer batch so the source is obvious on the record.

  "Charlotte Metro Buyer"   -> all 41 (they buy in the 8 Charlotte-metro counties)
  "Charlotte REI FB Group"  -> only the 8 also seen posting in the Facebook group

Tags are ADDED via POST /property/{uuid}/add-tags/ (a PATCH of the tags array is a
silent no-op) and every write is verified with a GET read-back.

    python tag_charlotte_buyers_20260904.py            # dry run
    python tag_charlotte_buyers_20260904.py --apply
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
import requests
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")


def token() -> str | None:
    """Chrome localStorage first; Playwright login when that token has expired."""
    import os, asyncio
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
    print("Chrome token expired - Playwright login fallback")
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tk = await page.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close()
            return tk
    return asyncio.run(go())

API = "https://apiv2.reisift.io"
BATCH_TAG = "Charlotte Metro Buyer"
FB_TAG = "Charlotte REI FB Group"
UPLOAD_TAG = "Buyer Prospector 2026-09-04"
WB = Path("output/Charlotte_Metro_NC_Buyer_Analysis_2026-09-03.xlsx")


def titles(items):
    """GET /property/{uuid}/ returns tags as PLAIN STRINGS; other endpoints return
    {"title": ...} dicts. Handle both, or verification silently reads back []."""
    return [i.get("title") if isinstance(i, dict) else str(i) for i in (items or [])]


def nm(s):
    return re.sub(r"[^a-z]", "", str(s).lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    tk = token()
    if not tk:
        print("no DataSift token"); return 2
    h = {"Authorization": f"Bearer {tk}", "Content-Type": "application/json"}

    # Match on ADDRESS, not name: DataSift stores a shortened owner name for some
    # records ("Dillon Mabe" vs the workbook's "Dillon Hamilton Mabe"), so a name
    # key silently misses them. The mailing address is exact on both sides.
    wb = pd.read_excel(WB, sheet_name="All Records").fillna("")

    def akey(street, zip_):
        st = re.sub(r"(ste|suite|unit|apt|#)\s*\S+$", "", str(street).lower())
        return re.sub(r"[^a-z0-9]", "", st), re.sub(r"\D", "", str(zip_))[:5]

    fb_addr = {akey(r["BuyerMailingAddress"], r["BuyerMailingZIP"])
               for _, r in wb.iterrows() if r["Active in Charlotte REI FB group"]}

    tags, off = [], 0
    while True:   # the tag endpoint pages; a single limit=500 call misses recent tags
        j = requests.get(f"{API}/api/internal/tag/?limit=200&offset={off}", headers=h, timeout=30).json()
        res = j.get("results") or j.get("data") or []
        tags += res
        if len(res) < 200: break
        off += 200
    up = next((t for t in tags if str(t.get("title", "")).strip() == UPLOAD_TAG), None)
    if not up:
        print(f"upload tag {UPLOAD_TAG!r} not found"); return 2
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"limit": 200, "query": {"must": {"any_tags": [up["uuid"]]}}}, timeout=60)
    r.raise_for_status()
    recs = r.json().get("results", [])
    print(f"batch records: {len(recs)}")

    ok = fail = skip = 0
    for p in recs:
        uuid = p["uuid"]
        d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        d = d.get("data") or d
        o = d.get("owner") or {}
        ad = d.get("address") or {}
        k = akey(ad.get("street"), ad.get("zip5") or ad.get("postal_code"))
        have = titles(d.get("tags"))
        want = [BATCH_TAG] + ([FB_TAG] if k in fb_addr else [])
        need = [t for t in want if t not in have]
        label = f"{o.get('first_name','')} {o.get('last_name','')}".strip()
        if not need:
            skip += 1; continue
        if not a.apply:
            print(f"  DRY {label:<24} would add {need}")
            continue
        rr = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                           headers=h, json={"tags": need}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
        chk = chk.get("data") or chk
        got = titles(chk.get("tags"))
        if all(t in got for t in want):
            ok += 1
            print(f"  ok  {label:<24} +{need}")
        else:
            fail += 1
            print(f"  FAIL {label:<24} HTTP {rr.status_code}; tags now {got}")
    print(f"\ntagged: {ok} | already had them: {skip} | failed: {fail}")
    if not a.apply:
        print("(dry run - re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
