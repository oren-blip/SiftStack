"""One-off: repair per-row tags for the 2026-08-14 W33 net-new upload (15 rows).

Root cause: datasift_uploader._tags_from_csv() returns the FIRST non-empty
row's Tags and the wizard applies them uniformly to every uploaded record.
Row 1 of today's NETNEW was a 'Heirs of' row, so all 15 records got that
row's tags ('Needs DP' included) and NO record got the per-row tags from
rows 2-15 — most critically the skip-trace scope tag
'Skip Trace 2026-08-14 093711 W33' (so the scoped skip trace could never
start), plus Lot Cluster / Surviving Spouse? / Verify: No PR Address /
Multi-Signer (2) / enformion-phone / Low-Confidence Parcel.

Repair (mirrors tag_needs_dp_20260813.py, which is this same class of fix):
  1. One mini 'Add Data' upsert per missing TAG, rows = only the rows that
     should carry it (wizard-level tags are uniform per upload, so per-tag
     uploads are exactly per-row correct). Skip-trace tag goes first.
  2. API PATCH to remove the wrongly-applied 'Needs DP' from the 12
     non-'Heirs of' records: tags round-tripped in full minus the one tag
     (never write empty over existing), verified by re-GET. First record is
     a canary — abort the rest if the verify fails.

After this, rerun resume_skiptrace_tier_20260814.py (skip trace -> tier ->
text touches).
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login, upload_csv

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fix_tags")

API = "https://apiv2.reisift.io"
NETNEW = REPO / "output" / "nc_estates_ftm_2026-08-14_093711_week33_datasift_upload_NETNEW.csv"
OUTDIR = REPO / "output"
ADDR_COLS = ["Property Street Address", "Property City",
             "Property State", "Property ZIP Code"]
# Tags the 11:31 wizard actually applied to every record (row 1's set + batch)
APPLIED = {"Courthouse Data", "NC Estates Week 33 2026", "Needs DP",
           "NC Upload 2026-08-14"}
SKIP_TRACE_TAG = "Skip Trace 2026-08-14 093711 W33"


def load_rows() -> list[dict]:
    with NETNEW.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def missing_by_tag(rows: list[dict]) -> dict[str, list[dict]]:
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        want = {t.strip() for t in (r.get("Tags") or "").split(",") if t.strip()}
        for t in sorted(want - APPLIED):
            by_tag[t].append(r)
    return by_tag


async def push_tag_uploads(page, by_tag: dict[str, list[dict]]) -> bool:
    # Skip-trace tag first — it unblocks the paid steps.
    order = sorted(by_tag, key=lambda t: (t != SKIP_TRACE_TAG, t))
    ok = True
    for tag in order:
        rows = by_tag[tag]
        safe = "".join(c if c.isalnum() else "_" for c in tag)[:40]
        out = OUTDIR / f"tagfix_20260814_{safe}.csv"
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(ADDR_COLS + ["Tags"])
            for r in rows:
                w.writerow([r.get(c, "") for c in ADDR_COLS] + [tag])
        logger.info("Uploading tag %r onto %d record(s)...", tag, len(rows))
        up = await upload_csv(page, out, mode="add", list_name="PROBATE",
                              existing_list=True, finish=True)
        if not up.get("success"):
            logger.error("Upload for tag %r FAILED: %s — push %s by hand.",
                         tag, up.get("message"), out)
            ok = False
        else:
            logger.info("Tag %r pushed.", tag)
    return ok


def find_uuid(h: dict, street: str, city: str) -> str | None:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        logger.warning("search %r -> HTTP %d", street, r.status_code)
        return None
    results = r.json().get("results", [])
    hits = [rec for rec in results
            if (rec.get("address") or {}).get("street", "").strip().lower()
            == street.strip().lower()]
    if len(hits) != 1:
        logger.warning("search %r: %d exact street matches — skipping",
                       street, len(hits))
        return None
    return hits[0].get("uuid")


def remove_needs_dp(h: dict, rows: list[dict]) -> tuple[int, int]:
    """Remove 'Needs DP' from records whose CSV row does not carry it.
    Returns (fixed, failed). First record is a canary."""
    targets = [r for r in rows
               if "Needs DP" not in (r.get("Tags") or "")]
    fixed = failed = 0
    for i, r in enumerate(targets):
        street, city = r["Property Street Address"], r["Property City"]
        uuid = find_uuid(h, street, city)
        if not uuid:
            failed += 1
            continue
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30)
        if g.status_code != 200:
            logger.warning("GET %s -> %d", uuid, g.status_code)
            failed += 1
            continue
        rec = g.json()
        tags = rec.get("tags", [])
        names = [t.get("name") if isinstance(t, dict) else t for t in tags]
        if "Needs DP" not in names:
            logger.info("%s: no 'Needs DP' present — nothing to do.", street)
            fixed += 1
            continue
        new_tags = [t for t in tags
                    if (t.get("name") if isinstance(t, dict) else t) != "Needs DP"]
        if not new_tags:
            logger.warning("%s: removal would empty the tag list — skipping "
                           "(never write empty over existing).", street)
            failed += 1
            continue
        p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"tags": new_tags}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                           timeout=30)
        chk_names = [t.get("name") if isinstance(t, dict) else t
                     for t in chk.json().get("tags", [])]
        if p.status_code in (200, 202) and "Needs DP" not in chk_names \
                and "NC Upload 2026-08-14" in chk_names:
            logger.info("%s: 'Needs DP' removed (verified; %d tags remain).",
                        street, len(chk_names))
            fixed += 1
        else:
            logger.error("%s: PATCH did not verify (HTTP %d, tags now %s)",
                         street, p.status_code, chk_names)
            failed += 1
            if i == 0:
                logger.error("Canary record failed — ABORTING the remaining "
                             "removals. Fix by hand or rerun after diagnosing.")
                return fixed, failed + len(targets) - 1
    return fixed, failed


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2
    rows = load_rows()
    by_tag = missing_by_tag(rows)
    for t, rs in by_tag.items():
        logger.info("Will add %r to %d record(s)", t, len(rs))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("Login failed")
                return 1
            uploads_ok = await push_tag_uploads(page, by_tag)
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await browser.close()

    h = {"content-type": "application/json", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}"}
    fixed, failed = remove_needs_dp(h, rows)
    logger.info("Needs DP removal: %d fixed, %d failed/skipped.", fixed, failed)
    return 0 if (uploads_ok and failed == 0) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
