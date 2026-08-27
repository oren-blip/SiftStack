"""Resume/finish the InvestorBase import post-processing (upload itself OK).

Idempotent: checks each record's status/tags/description before writing, so
reruns are safe. Retries every API call on ConnectionReset (DataSift drops
long PATCH loops). Address matching falls back to token-SET comparison —
DataSift reorders directionals ('Fuller Mill N Rd' -> 'Fuller Mill Rd N').
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
from datasift_uploader import login

import fix_buyer_records_20260815 as fx
from ib_upload_20260826 import (BATCH_TAG, TYPE_TAG, build_desc, fetch_by_tag)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ib_postfix")

API = "https://apiv2.reisift.io"
PROCESSED = REPO / "output" / "ib_processed_2026-08-26.csv"


def req(method, url, h, retries=4, **kw):
    for i in range(retries):
        try:
            r = requests.request(method, url, headers=h, timeout=30, **kw)
            return r
        except requests.exceptions.ConnectionError:
            wait = 3 * (i + 1)
            logger.warning("connection reset — retrying in %ds (%d/%d)",
                           wait, i + 1, retries)
            time.sleep(wait)
    raise ConnectionError(f"gave up on {url}")


def tok_set(s):
    s = re.sub(r"[.,#]", " ", (s or "").upper())
    toks = [fx._SUFFIX_ABBR.get(t, t) for t in s.split()]
    return frozenset(t for t in toks if t not in ("PMB",))


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
    h2 = {**h, "accept": "application/json", "origin": "https://app.reisift.io",
          "referer": "https://app.reisift.io/",
          "x-reisift-ui-version": "2022.02.01.7"}

    proc = list(csv.DictReader(PROCESSED.open(encoding="utf-8-sig")))
    new_rows = [p for p in proc if p["Flag"] == "NEW"]
    overlaps = [p for p in proc if p["Flag"].startswith("OVERLAP")]
    by_key = {fx.street_key(p["Mailing"]): p for p in new_rows}
    by_set = {tok_set(p["Mailing"]): p for p in new_rows}

    recs = fetch_by_tag(h, BATCH_TAG)
    logger.info("Batch records: %d", len(recs))
    done = skipped = fail = 0
    for rec in recs:
        uuid = rec["uuid"]
        street = (rec.get("address") or {}).get("street", "")
        p = by_key.get(fx.street_key(street)) or by_set.get(tok_set(street))
        if p is None:
            # last resort: subset match (DS added tokens like PMB 213)
            cands = [v for k, v in by_set.items()
                     if k <= tok_set(street) or tok_set(street) <= k]
            p = cands[0] if len(cands) == 1 else None
        if p is None:
            logger.error("%s: STILL unmatched — handle by hand", street)
            fail += 1
            continue

        g = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        names = [t.get("name") if isinstance(t, dict) else t
                 for t in g.get("tags", [])]
        cur = g.get("status")
        cur_t = ((cur.get("title") if isinstance(cur, dict) else cur) or "").lower()
        want_tags = [t for t in
                     (["Buyer Priority 1", "Salisbury Cash Buyers", TYPE_TAG.get(p["Type"], "")])
                     if t and t not in names]
        need_desc = not (g.get("description") or "").strip()
        if cur_t == "buyer" and not want_tags and not need_desc:
            skipped += 1
            continue
        ok = True
        if cur_t != "buyer":
            req("PATCH", f"{API}/api/internal/property/{uuid}/", h,
                json={"status": "buyer"})
        if want_tags:
            r = req("POST", f"{API}/api/internal/property/{uuid}/add-tags/",
                    h2, json={"tags": want_tags})
            ok &= r.status_code in (200, 201, 202, 204)
        if need_desc:
            r = req("PATCH", f"{API}/api/internal/property/{uuid}/", h,
                    json={"description": build_desc(p)})
            ok &= r.status_code in (200, 202)
        chk = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        s2 = chk.get("status")
        s2 = ((s2.get("title") if isinstance(s2, dict) else s2) or "").lower()
        chk_names = [t.get("name") if isinstance(t, dict) else t
                     for t in chk.get("tags", [])]
        ok &= s2 == "buyer" and all(t in chk_names for t in want_tags)
        done += ok
        fail += (not ok)
        if not ok:
            logger.error("%s: verify failed", street)
        if (done + skipped + fail) % 25 == 0:
            logger.info("progress: %d done / %d already-done / %d fail",
                        done, skipped, fail)
    logger.info("New records: %d fixed, %d already complete, %d failed.",
                done, skipped, fail)

    # ── overlaps: phones/emails + tags ────────────────────────────────────
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
        new_owner = dict(owner)
        changed = False
        phones = list(owner.get("phones") or [])
        if p["Phone"] and p["Phone"] not in {ph.get("number") for ph in phones}:
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
            req("PATCH", f"{API}/api/internal/property/{uuid}/", h,
                json={"owner": new_owner})
            chk = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
            got = chk.get("owner") or {}
            if p["Phone"] and p["Phone"] not in {ph.get("number")
                                                for ph in (got.get("phones") or [])}:
                ok = False
            if p["Email"] and p["Email"] not in [e.lower()
                                                 for e in (got.get("emails") or [])]:
                ok = False
        names = [t.get("name") if isinstance(t, dict) else t
                 for t in rec.get("tags", [])]
        want = [t for t in (["InvestorBase", "Salisbury Cash Buyers", TYPE_TAG.get(p["Type"], "")])
                if t and t not in names]
        if want:
            r = req("POST", f"{API}/api/internal/property/{uuid}/add-tags/",
                    h2, json={"tags": want})
            ok &= r.status_code in (200, 201, 202, 204)
        ov_ok += ok
        ov_fail += (not ok)
        logger.info("overlap %s -> %s", p["Entity"][:36], "OK" if ok else "FAIL")
    logger.info("Overlaps: %d ok, %d fail.", ov_ok, ov_fail)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
