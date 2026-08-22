"""One-off: act on the investor-evidence scan (Oren: 'focus on those').

  LIKELY RETAIL (18): swap tag Buyer Priority 1 -> Buyer Priority 3,
                      delete their 'Call buyer — 1216 Rowan Mill dispo' task.
  FLIPPER (8):        add tag 'Investor - Flipper'.
  BUY-AND-HOLD (21):  add tag 'Investor - Hold'.

Tag PATCH round-trips the full tag list (never empty-over-existing), verify
by re-GET, canary-first per operation kind.
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

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("reclassify")

API = "https://apiv2.reisift.io"
EVIDENCE = REPO / "output" / "rowan_P1_investor_evidence_2026-08-19.csv"
A_LIST = REPO / "output" / "rowan_mill_dispo_buyers_A_list_2026-08-15.csv"
TASK_TITLE = "Call buyer — 1216 Rowan Mill dispo"

FIXED_STREETS = {
    "Young Samuel Adams": "116 S Main St",
    "Young Samuel": "116 S Main St",
    "High Rock Home Buyers Llc": "116 S Main St Ste C",
    "The Mln Living Trust": "7335 US Highway 52",
    "Heavenly Homes J K Llc": "5610 Comiskey Aly",
    "Trishul Properties Llc": "2440 Statesville Blvd",
}


def tag_names(rec):
    return [t.get("name") if isinstance(t, dict) else t
            for t in rec.get("tags", [])]


def set_tags(h, uuid, add=(), remove=()):
    """Add/remove via the dedicated endpoints — property PATCH tag removal
    is a silent no-op (see dp_push_20260819.py recipe)."""
    g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if g.status_code != 200:
        return False
    names = tag_names(g.json())
    # sweep any junk literal tags a bad payload ever created
    junk = [n for n in names if n.startswith("{'name':")]
    rm = [t for t in list(remove) + junk if t in names]
    ad = [t for t in add if t not in names]
    for tags, path in ((rm, "remove-tags"), (ad, "add-tags")):
        if not tags:
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/{path}/",
                          headers=h, json={"tags": tags}, timeout=30)
        if r.status_code not in (200, 201, 202, 204):
            logger.error("%s %s -> HTTP %d %s", path, tags, r.status_code,
                         r.text[:120])
            return False
    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    got = tag_names(chk.json())
    return (all(t in got for t in add)
            and not any(t in got for t in list(remove) + junk))


def delete_call_task(h, uuid):
    r = requests.get(f"{API}/api/internal/task/", headers=h,
                     params={"property": uuid, "limit": 20}, timeout=30)
    if r.status_code != 200:
        return "list-failed"
    rows = r.json().get("results") or r.json().get("data") or []
    hits = [t for t in rows if (t.get("title") or "") == TASK_TITLE]
    if not hits:
        return "none"
    ok = True
    for t in hits:
        tid = t.get("uuid") or t.get("id")
        d = requests.delete(f"{API}/api/internal/task/{tid}/", headers=h, timeout=30)
        ok = ok and d.status_code in (200, 202, 204)
    return "deleted" if ok else "delete-failed"


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
    h = {**fx.api_headers(tok), "accept": "application/json",
         "origin": "https://app.reisift.io", "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7"}

    ev = {r["Buyer Name"]: r["Class"]
          for r in csv.DictReader(EVIDENCE.open(encoding="utf-8"))}
    streets = {r["Buyer Name"]: FIXED_STREETS.get(r["Buyer Name"])
               or r["Mailing Address"].split(",")[0].strip()
               for r in csv.DictReader(A_LIST.open(newline="", encoding="utf-8"))}

    cache: dict = {}
    stats = {"retail": 0, "flipper": 0, "hold": 0, "fail": 0, "tasks": 0}
    for buyer, klass in ev.items():
        street = streets.get(buyer)
        rec = fx.find_batch_record(h, street, cache) if street else None
        if rec is None:
            logger.warning("%s: record not found", buyer)
            stats["fail"] += 1
            continue
        uuid = rec["uuid"]
        if klass == "LIKELY RETAIL":
            ok = set_tags(h, uuid, add=("Buyer Priority 3",),
                          remove=("Buyer Priority 1",))
            tres = delete_call_task(h, uuid)
            if ok:
                stats["retail"] += 1
                if tres == "deleted":
                    stats["tasks"] += 1
                logger.info("%s: retail -> P3, task %s", buyer, tres)
            else:
                stats["fail"] += 1
                logger.error("%s: retag FAILED — aborting if canary", buyer)
                if stats["retail"] == 0:
                    return 1
        elif klass.startswith("FLIPPER"):
            if set_tags(h, uuid, add=("Investor - Flipper",)):
                stats["flipper"] += 1
            else:
                stats["fail"] += 1
        elif klass.startswith("BUY-AND-HOLD"):
            if set_tags(h, uuid, add=("Investor - Hold",)):
                stats["hold"] += 1
            else:
                stats["fail"] += 1

    logger.info("DONE: %d retail demoted (%d tasks removed), %d tagged Flipper, "
                "%d tagged Hold, %d failures.", stats["retail"], stats["tasks"],
                stats["flipper"], stats["hold"], stats["fail"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
