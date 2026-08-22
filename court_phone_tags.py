"""Court-verified phone tags: seed the queue from history, then upload to DataSift.

Oren, 2026-08-22 (Courteau 26E001077-350): "I want some kind of label or marker
to let me know that this is the confirmed court found phone no so I can
recognize and prioritize these numbers in the future."

DataSift has two independent tag namespaces and this uses both:
  * record-level `court-verified-phone` (src/nc_datasift_export.py) flags the LEAD
  * phone-level `Court Verified` (this script) flags the NUMBER, so it shows in
    the record's phone list next to that phone's Trestle dial tier

Phone tagging goes through the same route as the Trestle tier tags -- Upload File
-> Update Data -> "Tagging phones by phone numbers" -- which ADDS a tag rather
than replacing, so an existing "Dial First" survives.

    python court_phone_tags.py --seed     # rebuild queue from every FTM CSV
    python court_phone_tags.py            # show what is queued
    python court_phone_tags.py --upload   # push the queue to DataSift

nc_phone_backfill.py appends to the queue automatically whenever a court doc
FILLs, PROMOTEs, or CONFIRMs a number, so --seed is only for backfilling history.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import logging
import os
import sys

sys.path.insert(0, "src")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("court_phone_tags")

QUEUE_CSV = "output/court_verified_phones.csv"
UPLOAD_CSV = "output/court_phone_tags_upload.csv"
PHONE_TAG = "Court Verified"
FIELDS = ["Phone Number", "Phone Tag", "Case No.", "Decedent", "Uploaded"]


def _digits(v: str) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())[-10:]


def load_queue() -> list[dict]:
    if not os.path.exists(QUEUE_CSV):
        return []
    with open(QUEUE_CSV, encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if _digits(r.get("Phone Number", ""))]


def save_queue(rows: list[dict]) -> None:
    os.makedirs("output", exist_ok=True)
    with open(QUEUE_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def seed_from_history() -> list[dict]:
    """Scan every *_dm_enriched.csv for rows the backfill marked `pdf-phone`.

    Those are the numbers a court document produced before the phone-level tag
    existed -- 9 of them as of 2026-08-22, going back to Week 28.
    """
    rows = {r["Phone Number"]: r for r in load_queue()}
    added = 0
    for path in sorted(glob.glob("output/*_dm_enriched.csv")):
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    if "pdf-phone" not in (r.get("Match Reason") or ""):
                        continue
                    d = _digits(r.get("Phone 1", ""))
                    if len(d) != 10 or d in rows:
                        continue
                    rows[d] = {"Phone Number": d, "Phone Tag": PHONE_TAG,
                               "Case No.": (r.get("Case No.") or "").strip(),
                               "Decedent": (r.get("Deceased Owner") or "").strip()}
                    added += 1
        except OSError as e:
            logger.warning("skip %s: %s", path, e)
    out = list(rows.values())
    save_queue(out)
    logger.info("Seeded %d new court-verified phone(s); queue now %d -> %s",
                added, len(out), QUEUE_CSV)
    return out


def write_upload_csv(rows: list[dict]) -> str:
    """Two-column file the DataSift phone-tag wizard auto-maps."""
    with open(UPLOAD_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Phone Number", "Phone Tag"])
        for r in rows:
            w.writerow([_digits(r["Phone Number"]), r.get("Phone Tag") or PHONE_TAG])
    return UPLOAD_CSV


def _stamp_uploaded(sent: list[dict]) -> None:
    """Date-stamp the rows just pushed so the next run only sends new ones."""
    from datetime import date
    today = date.today().isoformat()
    sent_keys = {_digits(r["Phone Number"]) for r in sent}
    queue = load_queue()
    for r in queue:
        if _digits(r["Phone Number"]) in sent_keys and not (r.get("Uploaded") or "").strip():
            r["Uploaded"] = today
    save_queue(queue)
    logger.info("Stamped %d phone(s) as uploaded %s", len(sent_keys), today)


async def _upload(rows: list[dict]) -> None:
    from playwright.async_api import async_playwright

    from datasift_core import login
    from datasift_uploader import upload_phone_tags

    path = write_upload_csv(rows)
    logger.info("Uploading %d phone tag(s) from %s", len(rows), path)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page):
                raise SystemExit("DataSift login failed")
            res = await upload_phone_tags(page, path)
            logger.info("Result: %s", res.get("message"))
            if not res.get("success"):
                raise SystemExit("phone tag upload failed")
            _stamp_uploaded(rows)
        finally:
            await browser.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true",
                    help="rebuild the queue from historical *_dm_enriched.csv files")
    ap.add_argument("--upload", action="store_true",
                    help="push the not-yet-uploaded phones to DataSift")
    ap.add_argument("--all", action="store_true",
                    help="with --upload: re-send every phone, including ones "
                         "already uploaded")
    args = ap.parse_args()

    everything = seed_from_history() if args.seed else load_queue()
    if not everything:
        logger.info("Queue empty (%s).", QUEUE_CSV)
        return

    pending = [r for r in everything if not (r.get("Uploaded") or "").strip()]
    rows = everything if args.all else pending
    logger.info("%d court-verified phone(s) total, %d not yet tagged in DataSift:",
                len(everything), len(pending))
    for r in everything:
        logger.info("   %-12s %-18s %-32s %s", r["Phone Number"],
                    r.get("Case No.", ""), r.get("Decedent", ""),
                    f"uploaded {r['Uploaded']}" if (r.get("Uploaded") or "").strip()
                    else "NOT YET UPLOADED")
    if not args.upload:
        logger.info("Listing only. Add --upload to tag the %d new one(s) in DataSift.",
                    len(pending))
        return
    if not rows:
        logger.info("Nothing new to upload. Use --upload --all to re-send everything.")
        return
    asyncio.run(_upload(rows))


if __name__ == "__main__":
    main()
