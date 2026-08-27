"""One-off: import the InvestorBase buyer list (1216 Rowan Mill dispo).

1. Wizard-upload 75 net-new buyers into the existing "Cash Buyers" list.
   Tags at wizard (uniform): cash buyers, InvestorBase + batch tag.
   NO skip trace — InvestorBase supplies wireless numbers already.
2. API per record: status -> buyer; add-tags "Buyer Priority 1" +
   "Investor - Flipper"/"Investor - Hold" (IB's own classification);
   description with purchase/flip evidence.
3. The 10 overlap records: append IB phone (type MOBILE) + email via owner
   round-trip PATCH (never overwrite, verify by re-GET), add "InvestorBase"
   + type tag.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import re
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

import fix_buyer_records_20260815 as fx

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ib_upload")

API = "https://apiv2.reisift.io"
LIST_NAME = "Cash Buyers"
BATCH_TAG = "IB Upload 2026-08-26"
UPLOAD = REPO / "output" / "ib_new_upload_2026-08-26.csv"
PROCESSED = REPO / "output" / "ib_processed_2026-08-26.csv"

TYPE_TAG = {"flipper": "Investor - Flipper", "landlord": "Investor - Hold"}


def street_key(s):
    return fx.street_key(s)


def tag_uuid(h, title):
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"search": title, "limit": 500}, timeout=30)
    for t in (r.json().get("results") or []):
        if (t.get("title") or "") == title:
            return t["uuid"]
    return None


def fetch_by_tag(h, title):
    tid = tag_uuid(h, title)
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


def add_tags(h, uuid, tags):
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                      headers=h, json={"tags": tags}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def build_desc(p):
    t = "FLIPPER" if p["Type"] == "flipper" else "BUY & HOLD"
    parts = [f"CASH BUYER (InvestorBase 8/2026) — {t}."]
    if p["Entity"] and (p["First"] or p["Last"]):
        parts.append(f"Entity: {p['Entity']}.")
    if p["Bought"].strip(", "):
        parts.append(f"Salisbury purchase: {p['Bought']}.")
    if p["Evidence"]:
        parts.append(p["Evidence"][0].upper() + p["Evidence"][1:] + ".")
    parts.append("Wireless + email from InvestorBase (no trace needed).")
    return " ".join(parts)[:900]


async def main() -> int:
    proc = list(csv.DictReader(PROCESSED.open(encoding="utf-8-sig")))
    new_by_street = {street_key(p["Mailing"]): p for p in proc
                     if p["Flag"] == "NEW"}
    overlaps = [p for p in proc if p["Flag"].startswith("OVERLAP")]

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

    # ── new records: status/tags/description ──────────────────────────────
    recs = fetch_by_tag(h, BATCH_TAG)
    logger.info("Batch-tagged records: %d (uploaded %d rows — investigate any gap)",
                len(recs), len(new_by_street))
    done = fail = 0
    for rec in recs:
        uuid = rec["uuid"]
        st = street_key((rec.get("address") or {}).get("street", ""))
        p = new_by_street.get(st)
        if p is None:
            logger.warning("record %s (%s): no IB row matched", uuid,
                           (rec.get("address") or {}).get("street"))
            fail += 1
            continue
        ok = True
        # status
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30).json()
        cur = g.get("status")
        title = (cur.get("title") if isinstance(cur, dict) else cur) or ""
        if str(title).lower() != "buyer":
            requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"status": "buyer"}, timeout=30)
        # tags
        tags = ["Buyer Priority 1"]
        if TYPE_TAG.get(p["Type"]):
            tags.append(TYPE_TAG[p["Type"]])
        ok &= add_tags(h2, uuid, tags)
        # description
        if not (g.get("description") or "").strip():
            text = build_desc(p)
            r2 = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                                json={"description": text}, timeout=30)
            ok &= r2.status_code in (200, 202)
        # verify status stuck
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                           timeout=30).json()
        s2 = chk.get("status")
        s2 = (s2.get("title") if isinstance(s2, dict) else s2) or ""
        ok &= str(s2).lower() == "buyer"
        done += ok
        fail += (not ok)
        if ok and done == 1:
            logger.info("canary OK: %s", (rec.get("address") or {}).get("street"))
        if (done + fail) % 25 == 0:
            logger.info("new-record progress: %d ok / %d fail", done, fail)
    logger.info("New records processed: %d ok, %d fail.", done, fail)

    # ── overlaps: append phone/email + tags on existing records ──────────
    cache: dict = {}
    ov_ok = ov_fail = 0
    for p in overlaps:
        rec = fx.find_batch_record(h, p["Mailing"].split(",")[0], cache)
        if rec is None:
            logger.warning("overlap %s: record not found", p["Entity"])
            ov_fail += 1
            continue
        uuid = rec["uuid"]
        owner = rec.get("owner") or {}
        changed = False
        new_owner = dict(owner)
        phones = list(owner.get("phones") or [])
        nums = {ph.get("number") for ph in phones}
        if p["Phone"] and p["Phone"] not in nums:
            phones.append({"number": p["Phone"], "type": "MOBILE",
                           "tags": [], "status": "UNKNOWN"})
            new_owner["phones"] = phones
            changed = True
        emails = list(owner.get("emails") or [])
        if p["Email"] and p["Email"] not in [e.lower() for e in emails]:
            emails.append(p["Email"])
            new_owner["emails"] = emails
            changed = True
        ok = True
        if changed:
            r2 = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                                json={"owner": new_owner}, timeout=30)
            chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                               timeout=30).json()
            got = chk.get("owner") or {}
            got_nums = {ph.get("number") for ph in (got.get("phones") or [])}
            got_ems = [e.lower() for e in (got.get("emails") or [])]
            if p["Phone"] and p["Phone"] not in got_nums:
                ok = False
            if p["Email"] and p["Email"] not in got_ems:
                ok = False
            if not ok:
                logger.error("overlap %s: phone/email PATCH did not verify "
                             "(HTTP %d)", p["Entity"], r2.status_code)
        tags = ["InvestorBase"]
        if TYPE_TAG.get(p["Type"]):
            tags.append(TYPE_TAG[p["Type"]])
        ok &= add_tags(h2, uuid, tags)
        ov_ok += ok
        ov_fail += (not ok)
        logger.info("overlap %s -> %s (%s)", p["Entity"][:34],
                    "OK" if ok else "FAIL", ", ".join(tags))
    logger.info("Overlaps: %d ok, %d fail.", ov_ok, ov_fail)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
