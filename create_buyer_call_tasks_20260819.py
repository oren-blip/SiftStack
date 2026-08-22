"""One-off: create a DataSift task on each Buyer Priority 1 record so the
Rowan Mill dispo calls sit in Oren's Tasks queue.

Records found by the 'Buyer Priority 1' tag (any_tags query grammar — no
street matching needed). Task recipe mirrors _create_needs_dp_tasks in
upload_netnew_datasift.py: POST /api/internal/task/ with
assigned_to_property + assigned_to_user. Due end-of-day Eastern, 3 days out.
Skips records that already carry an open task with the same title (rerun-safe).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login
from upload_netnew_datasift import _OREN_USER_UUID

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("buyer_tasks")

API = "https://apiv2.reisift.io"
P1_TAG = "Buyer Priority 1"
TITLE = "Call buyer — 1216 Rowan Mill dispo"


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def p1_records(h: dict) -> list[dict]:
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"search": P1_TAG, "limit": 10}, timeout=30)
    tag_id = next((t["uuid"] for t in (r.json().get("results") or [])
                   if (t.get("title") or "") == P1_TAG), None)
    if not tag_id:
        raise RuntimeError(f"tag {P1_TAG!r} not found")
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": {"must": {"any_tags": [tag_id]}}},
                          timeout=30)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return out


def has_existing_task(h: dict, uuid: str) -> bool:
    r = requests.get(f"{API}/api/internal/task/", headers=h,
                     params={"property": uuid, "limit": 20}, timeout=30)
    if r.status_code != 200:
        return False
    rows = r.json().get("results") or r.json().get("data") or []
    return any((t.get("title") or "") == TITLE for t in rows)


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

    h = headers(tok)
    recs = p1_records(h)
    logger.info("Priority 1 records found: %d", len(recs))
    due = (datetime.now(timezone.utc) + timedelta(days=4)).strftime(
        "%Y-%m-%dT03:59:59.999000Z")
    made = skipped = failed = 0
    for i, rec in enumerate(recs):
        uuid = rec["uuid"]
        street = (rec.get("address") or {}).get("street", "?")
        if has_existing_task(h, uuid):
            skipped += 1
            continue
        r = requests.post(f"{API}/api/internal/task/", headers=h, timeout=30,
                          json={"title": TITLE, "all_day": True,
                                "due_date": due, "event_type": "task",
                                "assigned_to_user": _OREN_USER_UUID,
                                "assigned_to_property": uuid})
        if r.status_code in (200, 201):
            made += 1
        else:
            failed += 1
            logger.warning("%s: task POST -> HTTP %d %s", street,
                           r.status_code, r.text[:120])
            if made == 0 and failed == 1:
                logger.error("First task failed — aborting before spamming errors.")
                return 1
        if (i + 1) % 20 == 0:
            logger.info("progress: %d created / %d skipped / %d failed",
                        made, skipped, failed)
    logger.info("DONE: %d tasks created, %d already existed, %d failed. Due %s.",
                made, skipped, failed, due[:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
