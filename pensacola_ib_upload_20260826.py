"""One-off: import the 13 Pensacola dispo buyers (3823 N 11th Ave campaign).

Clone of ib_upload_20260826.py (Rowan Mill model):
1. Wizard-upload into the existing "Cash Buyers" list.
   Uniform wizard tags: cash buyers, InvestorBase + batch tag.
   NO skip trace (phones already sourced: InvestorBase / Enformion+Trestle).
2. API per record (idempotent, verify by re-GET): status -> buyer;
   add-tags "Pensacola - 3823 N 11th" + type tag + "Buyer Priority 1" on the
   A-wave; description with purchase/flip evidence.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login, upload_csv

import fix_buyer_records_20260815 as fx

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pcola_upload")

API = "https://apiv2.reisift.io"
LIST_NAME = "Cash Buyers"
BATCH_TAG = "IB Pensacola 2026-08-26"
DEAL_TAG = "Pensacola - 3823 N 11th"
UPLOAD = REPO / "output" / "pensacola_buyers_upload_2026-08-26.csv"

# street-key -> (type_tag, priority_1, description)
BUYERS = {
    "2701 Silhouette Dr": ("Investor - Flipper", True,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — FLIPPER. Derrick Antonio Smith. "
        "Bought 1115 Barcia Dr (4 blocks from 3823 N 11th) $198K Sep 2025, renovated, "
        "resold $599,900 May 2026. Knows the pocket cold, just cashed out. "
        "Phone Enformion-verified (matches his IB listing number)."),
    "6235 Blue Angle Pkwy": ("Investor - Flipper", True,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — FLIPPER/DEVELOPER. Entity: Rivera "
        "Developer LLC. Bought 3830 N 11th Ave $250K Sep 2025 — DIRECTLY ACROSS THE STREET "
        "from the 3823 N 11th deal; still owns it. Natural buyer for the block."),
    "3510 Dunwody Dr": ("Investor - Hold", True,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — BUY & HOLD. InvestorBase #1 "
        "SmartMatch for 3823 N 11th. Bought 1883 Copley Dr 3/1.75 2,122sf $250K Sep 2025, "
        "holds it absentee. Buys same-era brick at ~$118/sqft."),
    "14 Domitilla St": ("Investor - Flipper", True,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — FLIPPER. Andrew Wayne Williams "
        "(IB alias 'Rr Williams', 143 linked deals). Bought 196 E Highland Dr $90K May 2025, "
        "resold $200K Oct 2025. Phones Enformion-traced + Trestle 100-score. "
        "Verify identity on first call (common name)."),
    "5753 Hwy 85 N Ste 7461": ("Investor - Hold", True,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — VOLUME BUYER, MAIL ONLY. Entity: "
        "KBG Pensacola Holdings LLC (WY LLC, FL-reg 12/2025; principal Sidney Franklin "
        "Byrne Jr; RA Stephanie Baine). 232 linked deals in IB. Bought 3003 Torres Ave "
        "$123K Mar 2026. No phone found (Tracerfy + Enformion both missed — mailbox-only "
        "footprint). Address is a mailbox suite: mail the deal flyer."),
    "1519 Sabal Palm Dr": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — ACTIVE. Bought 3304 N Roosevelt St "
        "$45K Jun 2026, still owns. Freshest individual buyer on the list."),
    "5437 Berryhill Rd": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — ACTIVE. IB names Ashton Baker; "
        "county deed on the evidence buy (2617 N 7th Ave $30K Jun 2026) shows Guyer "
        "Capital LLC (Milton) — same buy, verify entity on the call."),
    "358 St Louis St": ("Investor - Flipper", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — COMPANY, CAUTION. Heartland Buys "
        "LLC (heartlandbuys.com), Mobile AL 'we buy houses' operation covering Pensacola. "
        "Office line. ALSO WHOLESALES — send the flyer, not the file. Evidence: "
        "3151 Torres Ave $25.5K Dec 2025."),
    "13990 SW 72 Ave": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — South FL absentee. Bought 704 E "
        "Fairfield Dr $160K May 2026 with Jill Wolfe, still owns. No phone yet."),
    "4127 Mustang Ave": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — TX-based investor. Bought 3346 "
        "Marcus Dr $30K Feb 2026, still owns."),
    "3311 Gulf Breeze Pkwy # 169": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — BUY & HOLD. Charlotte 'Lottie' "
        "Richardson / Hold This Inc (Gulf Breeze; entity not on Sunbiz — verify). Bought "
        "3026 N Roosevelt St $22.5K Jul 2025. Phones Enformion-traced, Trestle 100-score. "
        "Address is a mailbox suite."),
    "62 Star Lake Dr": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — legacy. Family bought 1118 E Fisher "
        "St $450K Jun 2022 (Zach Schweigert on title). Higher price band, stale evidence."),
    "811 Woodbine Dr": ("Investor - Hold", False,
        "CASH BUYER (InvestorBase 8/2026, Pensacola) — likely owner-occupant, LOW "
        "priority. Bought 811 Woodbine Dr 4/3 4,114sf $550K Aug 2025 (with Stephanie "
        "Monie) and lives there. Wrong product for distress deals."),
}


def add_tags(h2, uuid, tags):
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                      headers=h2, json={"tags": tags}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def req(method, url, h, retries=4, **kw):
    for i in range(retries):
        try:
            return requests.request(method, url, headers=h, timeout=30, **kw)
        except requests.exceptions.ConnectionError:
            wait = 3 * (i + 1)
            logger.warning("connection reset — retry in %ds (%d/%d)", wait, i + 1, retries)
            time.sleep(wait)
    raise ConnectionError(f"gave up on {url}")


def fetch_by_tag(h, title):
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"search": title, "limit": 500}, timeout=30)
    tid = None
    for t in (r.json().get("results") or []):
        if (t.get("title") or "") == title:
            tid = t["uuid"]
            break
    if not tid:
        raise RuntimeError(f"tag {title!r} not found")
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": {"must": {"any_tags": [tid]}}}, timeout=30)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return out


async def main() -> int:
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        page = await (await b.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                               os.environ.get("DATASIFT_PASSWORD", "")):
                logger.error("Login failed")
                return 1
            res = await upload_csv(page, UPLOAD, mode="add",
                                   list_name=LIST_NAME, existing_list=True,
                                   finish=True, pull_date="08/26/2026",
                                   extra_tags=[BATCH_TAG],
                                   tags_override=["cash buyers", "InvestorBase"])
            if not res.get("success"):
                logger.error("Upload failed: %s", res.get("message"))
                return 1
            logger.info("Upload committed — waiting 120s for import to settle.")
            await page.wait_for_timeout(120000)
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await b.close()

    h = fx.api_headers(tok)
    h2 = {**h, "accept": "application/json", "origin": "https://app.reisift.io",
          "referer": "https://app.reisift.io/",
          "x-reisift-ui-version": "2022.02.01.7"}

    recs = fetch_by_tag(h, BATCH_TAG)
    logger.info("Batch-tagged records: %d (uploaded 13 rows — investigate any gap)",
                len(recs))
    done = fail = 0
    for rec in recs:
        uuid = rec["uuid"]
        street = (rec.get("address") or {}).get("street", "") or ""
        info = None
        sk = fx.street_key(street)
        for k, v in BUYERS.items():
            if fx.street_key(k) == sk:
                info = v
                break
        if info is None:
            logger.warning("record %s (%s): no buyer row matched", uuid, street)
            fail += 1
            continue
        type_tag, priority, desc = info
        ok = True
        g = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        cur = g.get("status")
        title = (cur.get("title") if isinstance(cur, dict) else cur) or ""
        if str(title).lower() != "buyer":
            req("PATCH", f"{API}/api/internal/property/{uuid}/", h,
                json={"status": "buyer"})
        tags = [DEAL_TAG, type_tag] + (["Buyer Priority 1"] if priority else [])
        ok &= add_tags(h2, uuid, tags)
        if not (g.get("description") or "").strip():
            r2 = req("PATCH", f"{API}/api/internal/property/{uuid}/", h,
                     json={"description": desc})
            ok &= r2.status_code in (200, 202)
        chk = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        s2 = chk.get("status")
        s2 = (s2.get("title") if isinstance(s2, dict) else s2) or ""
        ok &= str(s2).lower() == "buyer"
        got_tags = {t if isinstance(t, str) else (t.get("title") or "")
                    for t in (chk.get("tags") or [])}
        ok &= DEAL_TAG in got_tags
        done += ok
        fail += (not ok)
        logger.info("%s -> %s (%s)", street, "OK" if ok else "FAIL",
                    ", ".join(tags))
    logger.info("Processed: %d ok, %d fail.", done, fail)
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
