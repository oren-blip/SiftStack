"""One-off: re-upload the 6 buyer rows DataSift's importer silently dropped
(2026-08-15 Rowan cash-buyer batch) with cleaned addresses, then skip trace
just them (tag 'Buyer Fix 2026-08-15') and set status -> buyer.

Address repairs (importer rejected the county GIS formats):
  116 S MAIN GQ ST STE C  -> 116 S Main St, Granite Quarry ("GQ" is the town)
  7335 HIGHWAY 52         -> 7335 US Highway 52
  5610 COMISKEY ALLEY     -> 5610 Comiskey Aly
  2440 STATESVILLE BLVD UNIT 130 -> unit dropped
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login, upload_csv
from upload_netnew_datasift import _skip_trace_week

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fix_missing6")

API = "https://apiv2.reisift.io"
LIST_NAME = "Cash Buyers"
BATCH_TAG = "Buyer Upload 2026-08-15"
FIX_TAG = "Buyer Fix 2026-08-15"
OUT = REPO / "output" / "rowan_buyers_fix6_2026-08-15.csv"

ROWS = [
    # street, city, state, zip, first, last, note-name
    ("116 S Main St", "Granite Quarry", "NC", "28146", "Samuel", "Young",
     "CASH BUYER (Rowan sweep 8/2026): individual, 8 purchases since 2/2025 "
     "(rows Young Samuel Adams + Young Samuel merged), 6+ in Salisbury. "
     "Orig GIS mailing: 116 S MAIN GQ ST STE C."),
    ("116 S Main St Ste C", "Granite Quarry", "NC", "28146", "Frank", "Elliott",
     "CASH BUYER (Rowan sweep 8/2026): High Rock Home Buyers LLC, 2 Salisbury "
     "buys, last 2026-08-12. Entity: High Rock Home Buyers Llc. Contact via "
     "Enformion address lookup."),
    ("7335 US Highway 52", "Salisbury", "NC", "28146", "Penny", "Bost",
     "CASH BUYER (Rowan sweep 8/2026): The MLN Living Trust. Contact via "
     "Enformion address lookup. Orig GIS mailing: 7335 HIGHWAY 52."),
    ("5610 Comiskey Aly", "Kannapolis", "NC", "28081", "Julie", "Stolte",
     "CASH BUYER (Rowan sweep 8/2026): Heavenly Homes J K LLC. Contact via "
     "Enformion address lookup. Orig GIS mailing: 5610 COMISKEY ALLEY."),
    ("2440 Statesville Blvd", "Salisbury", "NC", "28147", "James", "Murphy",
     "CASH BUYER (Rowan sweep 8/2026): Trishul Properties LLC (Unit 130). "
     "Contact via Enformion address lookup."),
]

COMPANIES = {"Elliott": "High Rock Home Buyers Llc",
             "Bost": "The Mln Living Trust",
             "Stolte": "Heavenly Homes J K Llc",
             "Murphy": "Trishul Properties Llc"}


def build_csv() -> None:
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Property Street Address", "Property City", "Property State",
                    "Property ZIP Code", "Owner First Name", "Owner Last Name",
                    "Tags", "Notes"])
        for street, city, st, zc, first, last, note in ROWS:
            w.writerow([street, city, st, zc, first, last, "cash buyers", note])
    logger.info("Built %s (%d rows)", OUT.name, len(ROWS))


def patch_after(tok: str) -> None:
    h = {"content-type": "application/json", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}"}
    for street, city, st, zc, first, last, _ in ROWS:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"query": {"must": {"search": street}}},
                          timeout=30)
        hits = [rec for rec in r.json().get("results", [])
                if (rec.get("address") or {}).get("street", "").strip().lower()
                == street.strip().lower()]
        if len(hits) != 1:
            logger.warning("%s: %d exact hits — status/company by hand",
                           street, len(hits))
            continue
        uuid = hits[0]["uuid"]
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30).json()
        # status
        cur = g.get("status")
        title = (cur.get("title") if isinstance(cur, dict) else cur) or ""
        if str(title).strip().lower() != "buyer":
            requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"status": "buyer"}, timeout=30)
        # company on the owner (only if empty — never overwrite)
        owner = g.get("owner") or {}
        comp = COMPANIES.get(last)
        if comp and not (owner.get("company") or "").strip():
            new_owner = dict(owner)
            new_owner["company"] = comp
            requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"owner": new_owner}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                           timeout=30).json()
        st2 = chk.get("status")
        st2 = (st2.get("title") if isinstance(st2, dict) else st2) or ""
        logger.info("%s: status=%r company=%r", street, st2,
                    (chk.get("owner") or {}).get("company"))


async def main() -> int:
    build_csv()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                               os.environ.get("DATASIFT_PASSWORD", "")):
                logger.error("Login failed")
                return 1
            res = await upload_csv(page, OUT, mode="add", list_name=LIST_NAME,
                                   existing_list=True, finish=True,
                                   pull_date="08/15/2026",
                                   extra_tags=[BATCH_TAG, FIX_TAG],
                                   tags_override=["cash buyers"])
            if not res.get("success"):
                logger.error("Upload failed: %s", res.get("message"))
                return 1
            logger.info("Fix upload committed.")
            traced = await _skip_trace_week(page, LIST_NAME, FIX_TAG, 90)
            logger.info("Skip trace started: %s", traced)
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await browser.close()
    patch_after(tok)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
