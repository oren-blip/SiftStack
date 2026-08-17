"""One-off: stamp Rowan-Mill deal-fit priority tags on the Cash Buyers records
and produce call sheet v3 sorted by priority.

Tiers (for 1216 Rowan Mill Rd — Salisbury 28147, $150K buy, ~$260K ARV):
  Buyer Priority 1 — bought in Salisbury ZIPs (28144/46/47) at $50K-$350K
  Buyer Priority 2 — 3+ in-band purchases, last buy within 12 months
  Buyer Priority 3 — everyone else

Tag PATCH pattern per tag_dp_complete_20260813.py: round-trip existing tags
plus the new one, verify by re-GET, canary-first. Never writes empty.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login

# reuse the batch-record fetch + street matching from the 8/15 fix script
import fix_buyer_records_20260815 as fx

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("buyer_priority")

API = "https://apiv2.reisift.io"
A_LIST = REPO / "output" / "rowan_mill_dispo_buyers_A_list_2026-08-15.csv"
SHEET_V3 = REPO / "output" / "rowan_mill_dispo_buyers_CALL_SHEET_v3_2026-08-16.csv"
P_TAGS = {1: "Buyer Priority 1", 2: "Buyer Priority 2", 3: "Buyer Priority 3"}


def tier_and_reason(a: dict) -> tuple[int, str]:
    salis = int(a["Salisbury Buys"])
    n = int(a["Purchases (18mo)"])
    avg = int(a["Avg Price"])
    in_band = 50_000 <= avg <= 350_000
    try:
        months_since = (datetime(2026, 8, 16)
                        - datetime.strptime(a["Last Buy"], "%Y-%m-%d")).days / 30.4
    except ValueError:
        months_since = 99
    if salis >= 1 and in_band:
        return 1, (f"Buys in Salisbury ({salis}x) at in-band prices "
                   f"(avg ${avg:,}) — already buys this product here")
    if n >= 3 and in_band and months_since <= 12:
        return 2, (f"Active volume buyer: {n} in-band purchases "
                   f"(avg ${avg:,}), last {a['Last Buy']}")
    why = []
    if not in_band:
        why.append(f"avg ${avg:,} outside $50K-$350K band")
    if salis == 0:
        why.append("no Salisbury purchases")
    if months_since > 12:
        why.append("stale (12+ months)")
    return 3, "; ".join(why) or "low volume"


def patch_tag(h: dict, uuid: str, tag: str) -> bool:
    g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if g.status_code != 200:
        return False
    tags = g.json().get("tags", [])
    names = [t.get("name") if isinstance(t, dict) else t for t in tags]
    if tag in names:
        return True
    stale = [t for t in P_TAGS.values() if t != tag and t in names]
    if tags and not isinstance(tags[0], str):
        new_tags = [t for t in tags if (t.get("name") or "") not in stale]
        new_tags.append({"name": tag})
    else:
        new_tags = [t for t in tags if t not in stale] + [tag]
    if not new_tags:
        return False
    p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                       json={"tags": new_tags}, timeout=30)
    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    chk_names = [t.get("name") if isinstance(t, dict) else t
                 for t in chk.json().get("tags", [])]
    return p.status_code in (200, 202) and tag in chk_names


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
    with fx.CALL_SHEET_V2.open(newline="", encoding="utf-8-sig") as f:
        sheet = {r["Buyer Name"]: r for r in csv.DictReader(f)}

    fixed_streets = {
        "Young Samuel Adams": "116 S Main St",
        "Young Samuel": "116 S Main St",
        "High Rock Home Buyers Llc": "116 S Main St Ste C",
        "The Mln Living Trust": "7335 US Highway 52",
        "Heavenly Homes J K Llc": "5610 Comiskey Aly",
        "Trishul Properties Llc": "2440 Statesville Blvd",
    }

    cache: dict = {}
    ok = fail = 0
    canary_done = False
    v3_rows = []
    for a in alist:
        buyer = a["Buyer Name"]
        tier, reason = tier_and_reason(a)
        street = fixed_streets.get(buyer) or a["Mailing Address"].split(",")[0].strip()
        rec = fx.find_batch_record(h, street, cache)
        tagged = False
        if rec is None:
            logger.warning("%s: record not found — tag skipped", buyer)
            fail += 1
        else:
            tagged = patch_tag(h, rec["uuid"], P_TAGS[tier])
            if tagged:
                ok += 1
            else:
                fail += 1
                logger.error("%s: tag PATCH failed", buyer)
                if not canary_done:
                    logger.error("Canary failed — aborting remaining tag PATCHes.")
                    return 1
        canary_done = True
        s = sheet.get(buyer, {})
        v3_rows.append({
            "Priority": tier,
            "Fit For Rowan Mill": reason,
            "Buyer Name": buyer,
            "Contact": s.get("Contact", ""),
            "Company": s.get("Company", ""),
            "Phones": s.get("Phones", ""),
            "Emails": s.get("Emails", ""),
            "Past Purchases": a["Property Addresses"],
            "Purchases (18mo)": a["Purchases (18mo)"],
            "Salisbury Buys": a["Salisbury Buys"],
            "Avg Price": a["Avg Price"],
            "Last Buy": a["Last Buy"],
            "Mailing Address": a["Mailing Address"],
            "Score": a["Score"],
        })
        if (ok + fail) % 25 == 0:
            logger.info("progress: %d tagged / %d failed", ok, fail)

    v3_rows.sort(key=lambda r: (r["Priority"], -float(r["Score"])))
    with SHEET_V3.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(v3_rows[0].keys()))
        w.writeheader()
        w.writerows(v3_rows)

    from collections import Counter
    counts = Counter(r["Priority"] for r in v3_rows)
    logger.info("Tags: %d ok, %d failed. Tiers: P1=%d P2=%d P3=%d -> %s",
                ok, fail, counts[1], counts[2], counts[3], SHEET_V3.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
