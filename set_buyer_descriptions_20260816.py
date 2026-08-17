"""One-off: write the buyer-intel summary into each Cash Buyers record's
`description` field (renders on the record page under the gallery).

Content per record: CASH BUYER header, Rowan Mill priority tier + why,
entity + human contact, purchase history, past purchase addresses.
Canary proven on 141 Warrior Ct (desc_canary). Only writes when the field
is empty — never overwrites. Verifies every write by re-GET.
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
from datasift_uploader import login

import fix_buyer_records_20260815 as fx
from tag_buyer_priority_20260816 import tier_and_reason

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("buyer_desc")

API = "https://apiv2.reisift.io"
A_LIST = REPO / "output" / "rowan_mill_dispo_buyers_A_list_2026-08-15.csv"
ENFORMION = REPO / "output" / "rowan_buyers_enformion_2026-08-15.json"

FIXED_STREETS = {
    "Young Samuel Adams": "116 S Main St",
    "Young Samuel": "116 S Main St",
    "High Rock Home Buyers Llc": "116 S Main St Ste C",
    "The Mln Living Trust": "7335 US Highway 52",
    "Heavenly Homes J K Llc": "5610 Comiskey Aly",
    "Trishul Properties Llc": "2440 Statesville Blvd",
}


def build_text(a: dict) -> str:
    tier, reason = tier_and_reason(a)
    parts = [f"CASH BUYER (Rowan sweep 8/2026) — Priority {tier}. {reason}."]
    if a["Entity"] == "Y":
        parts.append(f"Entity: {a['Buyer Name']}.")
    parts.append(f"{a['Purchases (18mo)']} purchase(s) since 2/2025, "
                 f"avg ${int(a['Avg Price']):,}, last buy {a['Last Buy']}.")
    addrs = a["Property Addresses"]
    if addrs:
        parts.append(f"Bought: {addrs[:280]}.")
    if a["Sister LLCs (same mailing)"]:
        parts.append(f"Sister entities: {a['Sister LLCs (same mailing)'][:120]}.")
    return " ".join(parts)[:900]


async def main() -> int:
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await (await b.new_context()).new_page()
        try:
            if not await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                               os.environ.get("DATASIFT_PASSWORD", "")):
                logger.error("Login failed")
                return 1
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await b.close()

    h = fx.api_headers(tok)
    with A_LIST.open(newline="", encoding="utf-8") as f:
        alist = list(csv.DictReader(f))

    cache: dict = {}
    ok = skipped = fail = 0
    for i, a in enumerate(alist):
        buyer = a["Buyer Name"]
        street = FIXED_STREETS.get(buyer) or a["Mailing Address"].split(",")[0].strip()
        rec = fx.find_batch_record(h, street, cache)
        if rec is None:
            logger.warning("%s: record not found", buyer)
            fail += 1
            continue
        if (rec.get("description") or "").strip():
            skipped += 1  # already has one (canary, or shared-address record)
            continue
        text = build_text(a)
        r = requests.patch(f"{API}/api/internal/property/{rec['uuid']}/",
                           headers=h, json={"description": text}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{rec['uuid']}/",
                           headers=h, timeout=30).json()
        if r.status_code in (200, 202) and chk.get("description") == text:
            ok += 1
        else:
            fail += 1
            logger.error("%s: description PATCH did not verify (HTTP %d)",
                         buyer, r.status_code)
            if ok == 0 and fail == 1:
                logger.error("First write failed — aborting.")
                return 1
        if (i + 1) % 25 == 0:
            logger.info("progress: %d written / %d skipped / %d failed",
                        ok, skipped, fail)

    logger.info("DONE: %d written, %d already had one, %d failed.",
                ok, skipped, fail)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
