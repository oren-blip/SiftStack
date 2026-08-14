"""Trestle tier backfill: find + fix phones with no dial-priority tag.

Why records sit in '02. Ready to Call' without Trestle scoring:
trestle_tier_step.py only runs right after each upload's skip trace, scoped
to that one upload's batch tag. Phones that reach a record ANY other way are
never scored, so the record shows phones with no Dial tier:
  1. Deep-prospecting pushes (manual_corrections / API PATCH / record edit)
     — e.g. the 2026-08-14 'Ready-to-call no-phone sweep' (6 records).
  2. pr_upgrade_step.py per-record 'Skip Trace Owner' re-traces.
  3. Skip-trace results that land after the tier step's 10-min settle export.
  4. Uploads that pre-date the tier step's introduction.

Default run is a FREE AUDIT: exports the whole list's Phone Enrichment CSV,
reports every record/phone missing a tier tag, and prices the fix (cached
scores are free; new ones are $0.015 each). Nothing is scored or uploaded.

    python trestle_backfill_step.py                    # audit only, no spend
    python trestle_backfill_step.py --csv output/phone_enrichment_export.csv
                                                       # audit an existing export
    python trestle_backfill_step.py --apply            # score + upload tags
    python trestle_backfill_step.py --apply --headless
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402  (loads .env)
from playwright.async_api import async_playwright  # noqa: E402
from datasift_core import login  # noqa: E402
from datasift_uploader import export_phone_enrichment, upload_phone_tags  # noqa: E402
from phone_validator import clean_phone, process_phones, COST_PER_PHONE  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tier_backfill")

# A phone counts as "scored" if any of these appears in its Phone Tags cell.
TIER_TAGS = ("Dial First", "Dial Second", "Dial Third", "Dial Fourth",
             "Drop", "Litigator - DNC")
CACHE_PATH = Path("output") / ".trestle_score_cache.json"
TAGS_CSV = Path("output") / "phone_tags_backfill.csv"


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def find_unscored(export_csv: Path,
                  created_since: str | None = None) -> tuple[list[dict], int, int]:
    """Scan the Phone Enrichment export for phones with no tier tag.

    created_since ('YYYY-MM-DD') limits the scan to records whose Created
    date is on/after that day — lets the fix target only the records still
    being actively called instead of the whole historical list.

    Returns (findings, records_with_phones, total_phones). Each finding:
    {address, city, owner, phone (cleaned), raw, tags}.
    """
    findings: list[dict] = []
    n_records = total_phones = 0
    with export_csv.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        phone_idx = [i for i in range(1, 100) if f"Phone {i}" in headers]
        for row in reader:
            if created_since:
                created = (row.get("Created") or "").split(" ")[0].split("T")[0]
                if created and created < created_since:
                    continue
            row_has_phone = False
            for i in phone_idx:
                raw = (row.get(f"Phone {i}") or "").strip()
                if not raw:
                    continue
                row_has_phone = True
                total_phones += 1
                tags = (row.get(f"Phone Tags {i}") or "").strip()
                if any(t.lower() in tags.lower() for t in TIER_TAGS):
                    continue
                cleaned = clean_phone(raw)
                if not cleaned:
                    continue
                findings.append({
                    "address": row.get("Property address", ""),
                    "city": row.get("Property city", ""),
                    "owner": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
                    "phone": cleaned,
                    "raw": raw,
                    "tags": tags,
                })
            if row_has_phone:
                n_records += 1
    return findings, n_records, total_phones


def write_audit_csv(findings: list[dict], cache: dict) -> Path:
    out = Path("output") / f"trestle_backfill_audit_{datetime.now():%Y%m%d_%H%M}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Property Address", "City", "Owner", "Phone",
                    "Current Phone Tags", "Cached Tier"])
        for fd in findings:
            cached = cache.get(fd["phone"], {})
            w.writerow([fd["address"], fd["city"], fd["owner"], fd["phone"],
                        fd["tags"], cached.get("assigned_tag", "")])
    return out


async def run(*, list_name: str, all_records: bool, csv_path: Path | None,
              apply: bool, headless: bool, max_cost: float,
              created_since: str | None = None) -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    api_key = os.environ.get("TRESTLE_API_KEY", "")
    if not csv_path and (not email or not password):
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2
    if apply and not api_key:
        logger.error("TRESTLE_API_KEY not set (needed for --apply)")
        return 2

    async with async_playwright() as p:
        browser = page = None
        try:
            if not csv_path or apply:
                browser = await p.chromium.launch(headless=headless)
                ctx = await browser.new_context(
                    viewport={"width": 1280, "height": 800})
                page = await ctx.new_page()
                if not await login(page, email, password):
                    logger.error("DataSift login failed")
                    return 1

            if not csv_path:
                scope = "ALL records" if all_records else f"list {list_name!r}"
                logger.info("Exporting Phone Enrichment CSV (%s)...", scope)
                res = await export_phone_enrichment(
                    page, list_name=None if all_records else list_name,
                    all_records=all_records)
                if not res.get("success") or not res.get("download_path"):
                    logger.error("Export failed: %s", res.get("message"))
                    return 1
                csv_path = Path(res["download_path"])
                logger.info("Exported: %s", csv_path)

            findings, n_records, total_phones = find_unscored(
                csv_path, created_since)
            if created_since:
                logger.info("Scope: records created on/after %s", created_since)
            cache = load_cache()
            unique = list(dict.fromkeys(fd["phone"] for fd in findings))
            cached = [ph for ph in unique if ph in cache]
            fresh = [ph for ph in unique if ph not in cache]
            cost = len(fresh) * COST_PER_PHONE

            audit_csv = write_audit_csv(findings, cache)
            by_rec: dict[str, int] = {}
            for fd in findings:
                by_rec[fd["address"]] = by_rec.get(fd["address"], 0) + 1
            logger.info("Scanned %d records with phones (%d phones total).",
                        n_records, total_phones)
            logger.info("UNSCORED: %d phones on %d records — %d already in the "
                        "score cache (free), %d need Trestle ($%.2f).",
                        len(findings), len(by_rec), len(cached), len(fresh), cost)
            for addr, n in sorted(by_rec.items()):
                logger.info("  %-40s %d unscored phone(s)", addr, n)
            logger.info("Audit CSV: %s", audit_csv)

            if not findings:
                logger.info("Nothing to fix — every phone carries a tier tag.")
                return 0
            if not apply:
                logger.info("Audit only (no spend). Re-run with --apply to "
                            "score the %d fresh phone(s) for $%.2f and upload "
                            "tags for all %d unscored phone(s).",
                            len(fresh), cost, len(unique))
                return 0

            if cost > max_cost:
                logger.error("Fresh-score cost $%.2f exceeds --max-cost $%.2f "
                             "— aborting before any spend.", cost, max_cost)
                return 3

            results = []
            if fresh:
                logger.info("Scoring %d phone(s) via Trestle ($%.2f)...",
                            len(fresh), cost)
                scored, errors = process_phones([(ph, ph) for ph in fresh],
                                                api_key)
                if errors:
                    logger.warning("%d phone(s) errored and won't be tagged.",
                                   len(errors))
                for r in scored:
                    cache[r["phone_number"]] = r
                CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
                results.extend(scored)
            results.extend(cache[ph] for ph in cached)

            with TAGS_CSV.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Phone Number", "Phone Tag"])
                n_tags = 0
                for r in results:
                    if r.get("is_valid") is not False and r.get("assigned_tag"):
                        w.writerow([r["phone_number"], r["assigned_tag"]])
                        n_tags += 1
            logger.info("Tags CSV: %s (%d phones)", TAGS_CSV, n_tags)
            if not n_tags:
                logger.warning("No taggable results — nothing to upload.")
                return 1

            by_tier: dict[str, int] = {}
            for r in results:
                if r.get("assigned_tag"):
                    by_tier[r["assigned_tag"]] = by_tier.get(r["assigned_tag"], 0) + 1
            for t in sorted(by_tier):
                logger.info("  %-14s %d", t, by_tier[t])

            logger.info("Uploading phone tags to DataSift...")
            up = await upload_phone_tags(page, TAGS_CSV)
            if not up.get("success"):
                logger.error("Tag upload failed: %s — upload %s by hand via "
                             "Upload File -> Update Data -> Tag phones by "
                             "phone number.", up.get("message"), TAGS_CSV)
                return 1
            logger.info("Done — dial-priority tags are live on the backfilled "
                        "records.")
            return 0
        finally:
            if browser:
                await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", dest="list_name", default="PROBATE",
                    help="DataSift list to scan (default PROBATE)")
    ap.add_argument("--all-records", action="store_true",
                    help="scan the whole account instead of one list")
    ap.add_argument("--csv", type=Path, default=None,
                    help="reuse an existing Phone Enrichment export "
                         "(skips the export step)")
    ap.add_argument("--apply", action="store_true",
                    help="score unscored phones + upload tags (default: "
                         "free audit only)")
    ap.add_argument("--max-cost", type=float, default=5.0,
                    help="abort --apply if fresh Trestle spend would exceed "
                         "this many dollars (default 5.00)")
    ap.add_argument("--created-since", default=None, metavar="YYYY-MM-DD",
                    help="only fix records created on/after this date "
                         "(e.g. 2026-06-01 = active NC weeks only)")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(list_name=args.list_name,
                           all_records=args.all_records,
                           csv_path=args.csv, apply=args.apply,
                           headless=args.headless, max_cost=args.max_cost,
                           created_since=args.created_since))


if __name__ == "__main__":
    raise SystemExit(main())
