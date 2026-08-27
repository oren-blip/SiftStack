"""Finish the 5 Pensacola buyer records the upload's address match missed.

DataSift REWRITES the street on save, so matching an uploaded row back to
its record by street key fails on anything it normalized:
    6235 Blue Angle Pkwy      -> 6235 N Blue Angel Pkwy   (spelling + directional)
    5753 Hwy 85 N Ste 7461    -> 5753 Highway 85 N Pmb 7461 (Hwy/Ste expanded)
    358 St Louis St           -> 358 Saint Louis St
    13990 SW 72 Ave           -> 13990 Sw 72Nd Ave         (ordinal added)
    3311 Gulf Breeze Pkwy #169-> 3311 Gulf Breeze Pkwy Pmb 169
Same class as the mailing-sweep normalization already documented.

So this pass keys on the record UUID (logged by the upload run) instead of
the address. Idempotent: every write is checked before it is made and
verified by re-GET, so a rerun is a no-op.
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
from datasift_uploader import login

import fix_buyer_records_20260815 as fx
from pensacola_ib_upload_20260826 import API, BUYERS, DEAL_TAG, add_tags, req

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pcola_postfix")

# uuid -> the upload CSV street it came from (key into BUYERS)
MISSED = {
    "308dd0e4-22d2-4497-b04d-a01ac34e7374": "6235 Blue Angle Pkwy",
    "9bd642d3-7001-4bd8-9e06-49e61ded02df": "5753 Hwy 85 N Ste 7461",
    "d2dfb2ba-fc92-4ee6-824a-d1a23381d3ec": "358 St Louis St",
    "1e1d024a-21b1-4d83-8c7c-8f39b8dfceb0": "13990 SW 72 Ave",
    "f0d4a20a-9dc2-4498-9f91-42683c432149": "3311 Gulf Breeze Pkwy # 169",
}


async def main() -> int:
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
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

    ok_n = fail_n = 0
    for uuid, csv_street in MISSED.items():
        type_tag, priority, desc = BUYERS[csv_street]
        g = req("GET", f"{API}/api/internal/property/{uuid}/", h).json()
        street = (g.get("address") or {}).get("street", "")
        ok = True

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
        ok &= DEAL_TAG in got_tags and type_tag in got_tags
        ok &= bool((chk.get("description") or "").strip())

        ok_n += ok
        fail_n += (not ok)
        logger.info("%s (%s) -> %s (%s)", street, csv_street,
                    "OK" if ok else "FAIL", ", ".join(tags))
        time.sleep(0.4)

    logger.info("Postfix: %d ok, %d fail.", ok_n, fail_n)
    return 0 if fail_n == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
