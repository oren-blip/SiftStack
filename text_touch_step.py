"""Text-touch step: 4 personalized SMS drafts on every record of a week's upload.

Implements the text-touch-builder skill as a weekly pipeline step:

  1. Ensure the four custom fields exist (Text Touch 1-4, group Misc.) via the
     DataSift internal API (Bearer token lifted from the logged-in session).
  2. Export the week's records from DataSift (Phone Enrichment export filtered
     to the week tag) — the export carries DataSift's OWN address text, so the
     re-import upserts onto the right records (including Oren's hand-entered
     rows whose addresses differ from the pipeline's GIS text).
  3. Run the skill's generator (variant pools, seeded per record) -> import CSV.
  4. Upload via Add Data -> existing list: address columns + Text Touch 1-4
     auto-map by header name; DataSift upserts by address, filling the fields.

Usage:
    python text_touch_step.py --week 31                       # export + generate + upload
    python text_touch_step.py --week 31 --sender Oren
    python text_touch_step.py --week 31 --export output/phone_enrichment_export.csv
    python text_touch_step.py --week 31 --dry-run             # no upload, print samples
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402  (loads .env)
import requests  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
from datasift_core import login  # noqa: E402
from datasift_uploader import export_phone_enrichment, upload_csv  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("text_touch")

API = "https://apiv2.reisift.io/api/internal/custom-fields/"
TOUCH_FIELDS = ["Text Touch 1", "Text Touch 2", "Text Touch 3", "Text Touch 4"]
GENERATOR = Path(__file__).parent / ".claude/skills/text-touch-builder/scripts/build_text_touches.py"


def _api_headers(token: str) -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {token}",
        "X-REISIFT-UI-VERSION": "2022.02.01.7",
        "Content-Type": "application/json",
    }


def _items(js) -> list:
    if isinstance(js, list):
        return js
    if isinstance(js, dict):
        for k in ("results", "data", "items"):
            if isinstance(js.get(k), list):
                return js[k]
    return []


def ensure_touch_fields(token: str) -> bool:
    """Create any missing Text Touch 1-4 custom fields. Returns True when all
    four exist (already or after creation)."""
    h = _api_headers(token)
    r = requests.get(API, headers=h, params={"entity_type": "property"}, timeout=30)
    if r.status_code != 200:
        logger.error("Custom-fields list failed: HTTP %d %s", r.status_code, r.text[:200])
        return False
    existing = {(f.get("label") or "").strip() for f in _items(r.json())}
    missing = [n for n in TOUCH_FIELDS if n not in existing]
    if not missing:
        logger.info("Custom fields already exist: %s", ", ".join(TOUCH_FIELDS))
        return True

    rg = requests.get(API + "groups/", headers=h, timeout=30)
    if rg.status_code != 200:
        logger.error("Custom-field groups fetch failed: HTTP %d", rg.status_code)
        return False
    groups = _items(rg.json())
    group_id = None
    for g in groups:
        if (g.get("name") or "").strip().lower().startswith("misc"):
            group_id = g.get("id")
            break
    if group_id is None and groups:
        group_id = groups[0].get("id")
    if group_id is None:
        rgc = requests.post(API + "groups/", headers=h,
                            json={"entity_type": "property", "name": "Misc."}, timeout=30)
        if rgc.status_code not in (200, 201):
            logger.error("Could not create a custom-field group: HTTP %d %s",
                         rgc.status_code, rgc.text[:200])
            return False
        group_id = rgc.json().get("id")

    for name in missing:
        payload = {"entity_type": "property", "group_id": group_id, "label": name,
                   "field_type": "text", "required": False, "is_active": True,
                   "placeholder": ""}
        rc = requests.post(API, headers=h, json=payload, timeout=30)
        if rc.status_code in (200, 201):
            logger.info("Created custom field: %s", name)
        else:
            logger.error("Create %r failed: HTTP %d %s", name, rc.status_code, rc.text[:200])
            return False
    return True


async def run(tag: str, *, sender: str, export_csv: str | None,
              list_name: str, dry_run: bool, headless: bool) -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("DataSift login failed")
                return 1

            token = await page.evaluate("() => localStorage.getItem('rs_token')")
            if not token:
                logger.error("No rs_token in localStorage — cannot manage custom fields")
                return 1
            if not ensure_touch_fields(token):
                return 1

            if export_csv:
                export_path = Path(export_csv)
                logger.info("Using existing export: %s", export_path)
            else:
                logger.info("Exporting records (tag=%r)...", tag)
                res = await export_phone_enrichment(page, filter_tag=tag)
                if not res.get("success") or not res.get("download_path"):
                    logger.error("Export failed: %s", res.get("message"))
                    return 1
                export_path = Path(res["download_path"])

            out_csv = Path("output") / f"text_touches_{tag.replace(' ', '_')}.csv"
            cmd = [sys.executable, str(GENERATOR), str(export_path),
                   "--sender", sender, "--out", str(out_csv)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            print(proc.stdout[-2000:])
            if proc.returncode != 0:
                logger.error("Generator failed: %s", proc.stderr[-500:])
                return 1

            if dry_run:
                logger.info("--dry-run: not uploading. Touches CSV: %s", out_csv)
                return 0

            logger.info("Uploading text touches into list %r (upsert by address)...",
                        list_name)
            up = await upload_csv(page, out_csv, mode="add",
                                  list_name=list_name, existing_list=True, finish=True)
            if not up.get("success"):
                logger.error("Touches upload failed: %s — upload %s by hand "
                             "(Add Data -> existing list -> map Text Touch 1-4).",
                             up.get("message"), out_csv)
                return 1
            logger.info("Text touches uploaded — callers can copy the next touch "
                        "straight off the record.")
            return 0
        finally:
            await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--year", type=int, default=datetime.now().year)
    ap.add_argument("--tag", default=None, help="explicit tag (overrides --week)")
    ap.add_argument("--sender", default="Oren", help="first name signing the texts")
    ap.add_argument("--export", default=None,
                    help="reuse an existing DataSift export CSV instead of re-exporting")
    ap.add_argument("--list", dest="list_name", default="PROBATE")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    tag = args.tag or (f"NC Estates Week {args.week} {args.year}" if args.week else None)
    if not tag:
        ap.error("--week or --tag required")
    return asyncio.run(run(tag, sender=args.sender, export_csv=args.export,
                           list_name=args.list_name, dry_run=args.dry_run,
                           headless=args.headless))


if __name__ == "__main__":
    raise SystemExit(main())
