"""One-off: DataSift skip trace of the KBG Pensacola Holding LLC buyer record.

Context: KBG is the A6 buyer on the 3823 N 11th dispo (232 linked deals) but
missed every paid trace on 8/26 because its only address was the Crestview PMB.
DataSift skip trace is unlimited on the plan (2026-08-23) and was deliberately
skipped for the 13-buyer upload. This runs it for the ONE KBG record:

1. API: find the record under batch tag "IB Pensacola 2026-08-26" by street
   "5753", snapshot current phones, add unique tag "KBG Trace 2026-08-27",
   verify by re-GET (search index is stale after writes — never verify by search).
2. Playwright: login -> skip_trace_records filtered on that tag. The flow
   ABORTS if the filter doesn't verify, so a lagging tag can't trace wide.

Read-back of returned phones is a separate later step (background job).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402
from push_smartskip_group1_20260825 import headers  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kbg_trace")

BATCH_TAG = "IB Pensacola 2026-08-26"
TRACE_TAG = "KBG Trace 2026-08-27"


def find_kbg(h) -> dict:
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"search": BATCH_TAG, "limit": 500}, timeout=30)
    tid = next((t["uuid"] for t in (r.json().get("results") or [])
                if (t.get("title") or "") == BATCH_TAG), None)
    if not tid:
        raise RuntimeError(f"batch tag {BATCH_TAG!r} not found")
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"limit": 200, "offset": 0,
                            "query": {"must": {"any_tags": [tid]}}}, timeout=30)
    r.raise_for_status()
    rows = r.json().get("results", [])
    logger.info("batch-tagged records: %d", len(rows))
    for rec in rows:
        street = ((rec.get("address") or {}).get("street") or "")
        if "5753" in street:
            return rec
    raise RuntimeError("no record with street containing 5753 in batch")


def main() -> int:
    tok = token()
    if not tok:
        logger.error("no DataSift token")
        return 1
    h = headers(tok)
    h2 = {**h, "accept": "application/json", "origin": "https://app.reisift.io",
          "referer": "https://app.reisift.io/",
          "x-reisift-ui-version": "2022.02.01.7"}

    rec = find_kbg(h)
    uuid = rec["uuid"]
    g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                     timeout=30).json()
    owner = (g.get("owners") or [{}])[0]
    phones = owner.get("phones") or []
    logger.info("KBG record %s — street %r, owner %r, phones BEFORE: %d",
                uuid, (g.get("address") or {}).get("street"),
                (owner.get("first_name"), owner.get("last_name")), len(phones))
    for p in phones:
        logger.info("  existing phone: %s (%s)", p.get("number"), p.get("type"))

    tags_now = [t.get("title") if isinstance(t, dict) else str(t)
                for t in (g.get("tags") or [])]
    if TRACE_TAG not in tags_now:
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h2, json={"tags": [TRACE_TAG]}, timeout=30)
        logger.info("add-tags -> HTTP %d", r.status_code)
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                           timeout=30).json()
        tags_chk = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (chk.get("tags") or [])]
        if TRACE_TAG not in tags_chk:
            logger.error("tag did not persist on re-GET — aborting")
            return 1
        logger.info("tag verified on record by re-GET")
    else:
        logger.info("trace tag already on record")

    # ---- Playwright UI skip trace, filtered to the one-record tag ----
    import os
    from playwright.async_api import async_playwright
    from datasift_uploader import login, skip_trace_records

    async def go() -> dict:
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True)
            page = await (await b.new_context(
                viewport={"width": 1280, "height": 800})).new_page()
            try:
                ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                                 os.environ.get("DATASIFT_PASSWORD", ""))
                if not ok:
                    return {"success": False, "message": "login failed"}
                return await skip_trace_records(page, "Cash Buyers",
                                                confirm=True,
                                                filter_tag=TRACE_TAG)
            finally:
                await b.close()

    res = asyncio.run(go())
    logger.info("skip trace result: %s", res)
    print(f"\nKBG_UUID={uuid}")
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
