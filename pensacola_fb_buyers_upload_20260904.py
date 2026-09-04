"""Add the Facebook-harvested Pensacola buyers that have a VERIFIED home address to the
"Cash Buyers" list in DataSift (Oren's go, 9/4 ~02:45: "Add the 51 with an email").

Only rows whose 9/4 Enformion trace graded HIGH (email on the record, or name match with a
Pensacola-area address) qualify - a DataSift record IS a property, so a person without a
trustworthy address cannot be a record. The rest stay on the sheet.

Clone of pensacola_ib_upload_20260826.py:
1. Wizard-upload into the existing "Cash Buyers" list. Uniform wizard tags:
   cash buyers, FB Pensacola 2026-09 + batch tag. No skip trace (phones already traced).
2. API per record (idempotent, verified by re-GET): status -> buyer; add-tags
   "Pensacola - 3823 N 11th"; description with the buyer's own words + trace provenance.
Phone dial tiers arrive via the twice-daily "SiftStack Tier Sweep" from the Trestle cache.

    .venv\\Scripts\\python.exe pensacola_fb_buyers_upload_20260904.py --dry-run   # writes the CSV only
    .venv\\Scripts\\python.exe pensacola_fb_buyers_upload_20260904.py             # upload + postfix
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import re
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fb_upload")

API = "https://apiv2.reisift.io"
LIST_NAME = "Cash Buyers"
BATCH_TAG = "FB Pensacola 2026-09-04"
SOURCE_TAG = "FB Pensacola 2026-09"
DEAL_TAG = "Pensacola - 3823 N 11th"
SRC = REPO / "output" / "pensacola_fb_cash_buyers_2026-09-04.csv"
UPLOAD = REPO / "output" / "pensacola_fb_buyers_upload_2026-09-04.csv"
DRY = "--dry-run" in sys.argv
BUYER_CLASSES = ("CASH BUYER", "BUYER who also wholesales", "DEAL RESPONDER (asked about a deal)")


def parse_addr(full: str) -> tuple[str, str, str, str]:
    """'581 S 72nd Ave, Apt 4; Pensacola, FL 32506-7629' -> street, city, state, zip5."""
    street, _, rest = full.partition(";")
    m = re.match(r"\s*(.+?),\s*([A-Z]{2})\s+(\d{5})", rest)
    if not m:
        return "", "", "", ""
    return street.strip(), m.group(1).strip(), m.group(2), m.group(3)


def build_rows() -> list[dict]:
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig", newline="")))
    out = []
    for r in rows:
        if r["Class"] not in BUYER_CLASSES or not r["Emails"].strip():
            continue
        if not r.get("Trace Confidence", "").startswith("high"):
            continue
        street, city, state, zc = parse_addr(r["Traced Address"])
        if not street or street.lower().startswith("po box"):
            continue
        name = re.sub(r"\s*[-–].*$", "", r["Name"]).strip().split()
        first, last = name[0], name[-1]
        phones = [p.strip() for p in r["Phones"].split("|") if p.strip()][:3]
        emails = [e.strip() for e in r["Emails"].split("|") if e.strip()][:2]
        quote = re.sub(r"\s+", " ", r["Evidence"].split(" || ")[0]).strip()[:220]
        crit = r["Criteria"][:160]
        desc = (f"CASH BUYER (Facebook {r['Group']}, 9/2026) - {r['Class'].split(' (')[0]}. "
                f"Their words: \"{quote}\"" + (f" Criteria: {crit}." if crit else "") +
                f" Home address + phones: Enformion 9/4 ({r['Trace Confidence']}); phones Trestle-scored. "
                f"Not yet verified by a live conversation.")
        row = {"Property Street Address": street, "Property City": city, "Property State": state,
               "Property ZIP Code": zc, "Owner First Name": first, "Owner Last Name": last}
        for i in range(3):
            row[f"Phone {i + 1}"] = phones[i] if i < len(phones) else ""
        for i in range(2):
            row[f"Email {i + 1}"] = emails[i] if i < len(emails) else ""
        row["Tags"] = f"cash buyers, {SOURCE_TAG}, {BATCH_TAG}"
        row["_desc"] = desc
        out.append(row)
    return out


def add_tags(h2, uuid, tags):
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/", headers=h2, json={"tags": tags}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def req(method, url, h, retries=4, **kw):
    for i in range(retries):
        try:
            return requests.request(method, url, headers=h, timeout=30, **kw)
        except requests.exceptions.ConnectionError:
            time.sleep(3 * (i + 1))
    raise ConnectionError(f"gave up on {url}")


def fetch_by_tag(h, title):
    r = requests.get(f"{API}/api/internal/tag/", headers=h, params={"search": title, "limit": 500}, timeout=30)
    tid = next((t["uuid"] for t in (r.json().get("results") or []) if (t.get("title") or "") == title), None)
    if not tid:
        raise RuntimeError(f"tag {title!r} not found")
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/", headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset, "query": {"must": {"any_tags": [tid]}}}, timeout=30)
        r.raise_for_status()
        page = r.json().get("results", [])
        out.extend(page)
        if len(page) < 200:
            break
        offset += 200
    return out


async def main() -> int:
    rows = build_rows()
    fields = [k for k in rows[0].keys() if not k.startswith("_")]
    with open(UPLOAD, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    logger.info("%d buyer rows -> %s", len(rows), UPLOAD.name)
    for r in rows:
        logger.info("  %s %s | %s, %s %s %s | %s | %s", r["Owner First Name"], r["Owner Last Name"],
                    r["Property Street Address"], r["Property City"], r["Property State"], r["Property ZIP Code"],
                    r["Phone 1"], r["Email 1"])
    if DRY:
        return 0
    postfix_only = "--postfix-only" in sys.argv

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        page = await (await b.new_context(viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, os.environ.get("DATASIFT_EMAIL", ""), os.environ.get("DATASIFT_PASSWORD", "")):
                logger.error("Login failed")
                return 1
            if not postfix_only:
                res = await upload_csv(page, UPLOAD, mode="add", list_name=LIST_NAME, existing_list=True,
                                       finish=True, pull_date="09/04/2026", extra_tags=[BATCH_TAG],
                                       tags_override=["cash buyers", SOURCE_TAG])
                if not res.get("success"):
                    logger.error("Upload failed: %s", res.get("message"))
                    return 1
                logger.info("Upload committed - waiting 120s for import to settle.")
                await page.wait_for_timeout(120000)
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await b.close()

    h = fx.api_headers(tok)
    h2 = {**h, "accept": "application/json", "origin": "https://app.reisift.io",
          "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7"}
    # The tag index lags a fresh upload by minutes (Week-33 lesson: ~30 min worst case).
    # Poll the batch tag until records appear or the wait budget runs out.
    recs = []
    deadline = time.time() + float(os.environ.get("FB_UPLOAD_WAIT_MIN", "20")) * 60
    while True:
        try:
            recs = fetch_by_tag(h, BATCH_TAG)
        except RuntimeError as e:
            logger.info("tag not indexed yet: %s", e)
        if recs or time.time() > deadline:
            break
        logger.info("batch tag shows 0 records - retry in 60s")
        time.sleep(60)
    logger.info("Batch-tagged records: %d (uploaded %d rows - investigate any gap)", len(recs), len(rows))
    by_key = {fx.street_key(r["Property Street Address"]): r for r in rows}
    done = fail = 0
    for rec in recs:
        uuid = rec["uuid"]
        street = (rec.get("address") or {}).get("street", "") or ""
        info = by_key.get(fx.street_key(street))
        if info is None:
            # DataSift rewrites streets on save - fall back to a token-set match
            toks = set(re.findall(r"[a-z0-9]+", street.lower()))
            info = next((v for k, v in by_key.items() if len(toks & set(k.split())) >= 2), None)
        if info is None:
            logger.warning("record %s (%s): no upload row matched", uuid, street)
            fail += 1
            continue
        ok = True
        g = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        cur = g.get("status")
        title = (cur.get("title") if isinstance(cur, dict) else cur) or ""
        if str(title).lower() != "buyer":
            req("PATCH", f"{API}/api/internal/property/{uuid}/", h, json={"status": "buyer"})
        ok &= add_tags(h2, uuid, [DEAL_TAG])
        if not (g.get("description") or "").strip():
            r2 = req("PATCH", f"{API}/api/internal/property/{uuid}/", h, json={"description": info["_desc"]})
            ok &= r2.status_code in (200, 202)
        chk = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        s2 = chk.get("status")
        s2 = (s2.get("title") if isinstance(s2, dict) else s2) or ""
        ok &= str(s2).lower() == "buyer"
        got = {t if isinstance(t, str) else (t.get("title") or "") for t in (chk.get("tags") or [])}
        ok &= DEAL_TAG in got
        done += ok
        fail += (not ok)
        logger.info("%s %s -> %s  uuid=%s", info["Owner First Name"], info["Owner Last Name"], "OK" if ok else "FAIL", uuid)
    logger.info("Processed: %d ok, %d fail.", done, fail)
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
