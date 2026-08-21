"""Trestle tier backfill that reads phones from the DataSift API, not an export.

WHY THIS EXISTS
---------------
`trestle_backfill_step.py` audits a "Phone Enrichment" CSV export. That export
was proven (2026-08-20) to contain only a SUBSET of each record's phones:

    0 Hickory Hwy       export: 0 phones   API: 3 phones (1 untiered)
    4635 Crabapple St   export: 1 phone    API: 5 phones (2 untiered)
    286 Troutman Farm   export: 1 phone    API: 2 phones (1 untiered)

So the export-based sweep reported "every phone carries a tier tag" while 17
phones sat untiered in '02. Ready to Call'. Reading the record via
`GET property/{uuid}/` returns the true phone list, so this version audits the
API and is not blind to phones the export drops.

It also closes the second half of the gap: our upload pushes ~1 phone/record,
then DataSift's OWN skip trace adds more phones minutes-to-hours later. The
nightly tier step + sweep both run inside that window, so the late arrivals
were never scored.

Default run is a FREE AUDIT (no Trestle spend, no writes).

    python trestle_api_backfill.py                    # audit RTC + last 7 days
    python trestle_api_backfill.py --apply            # score + tag
    python trestle_api_backfill.py --preset "02. Ready to Call" --apply
    python trestle_api_backfill.py --tag "NC Upload 2026-08-20" --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from phone_validator import clean_phone, process_phones, COST_PER_PHONE  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api_backfill")

API = "https://apiv2.reisift.io"
TIER_TAGS = ("dial first", "dial second", "dial third", "dial fourth",
             "drop", "litigator")
CACHE_PATH = REPO / "output" / ".trestle_score_cache.json"
TAGS_CSV = REPO / "output" / "phone_tags_api_backfill.csv"


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def get_token() -> str:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        return t
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tok = (await page.evaluate("() => localStorage.getItem('rs_token')")
                   if ok else None)
            await b.close()
            return tok
    tok = asyncio.run(go())
    if not tok:
        raise RuntimeError("DataSift login failed")
    return tok


def tag_texts(obj) -> list[str]:
    """Phone tags arrive as dicts from some endpoints, plain strings from others."""
    out = []
    for t in (obj or []):
        if isinstance(t, dict):
            out.append(str(t.get("title") or t.get("name") or ""))
        else:
            out.append(str(t))
    return [t for t in out if t]


def has_tier(tags: list[str]) -> bool:
    low = " | ".join(tags).lower()
    return any(t in low for t in TIER_TAGS)


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _search(h: dict, query: dict) -> list:
    """POST property/ with x-http-method-override: GET (the search idiom)."""
    rows_all, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": query}, timeout=60)
        if r.status_code != 200:
            logger.warning("search %s: %s", r.status_code, r.text[:200])
            return rows_all
        rows = r.json().get("results", [])
        rows_all.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return rows_all


def tag_uuid_map(h: dict) -> dict:
    out, offset = {}, 0
    while True:
        r = requests.get(f"{API}/api/internal/tag/", headers=h,
                         params={"limit": 200, "offset": offset}, timeout=30)
        if r.status_code != 200:
            break
        rows = r.json().get("results") or []
        for t in rows:
            out[(t.get("title") or "").strip()] = t.get("uuid")
        if len(rows) < 200:
            break
        offset += 200
    return out


def collect_scope(h: dict, preset_name: str | None, tags: list[str],
                  recent_days: int) -> dict:
    """Return {uuid: record} for every record in the audit scope."""
    pool: dict[str, dict] = {}

    if preset_name:
        r = requests.get(f"{API}/api/internal/filter-preset/", headers=h,
                         params={"limit": 200}, timeout=30)
        presets = r.json().get("results") or [] if r.status_code == 200 else []
        target = next((p for p in presets
                       if preset_name.lower() in
                       (p.get("title") or p.get("name") or "").lower()), None)
        if target:
            uuid = target.get("uuid") or target.get("id")
            d = requests.get(f"{API}/api/internal/filter-preset/{uuid}/",
                             headers=h, timeout=30)
            body = d.json() if d.status_code == 200 else {}
            q = body.get("query") or body.get("filters") or body.get("filter")
            if q:
                rows = _search(h, q)
                # The preset's nested must_not (any status) is not honoured by
                # the search API -> replicate it client-side: statusless only.
                for rec in rows:
                    st = rec.get("status")
                    st_txt = (st.get("title") if isinstance(st, dict) else st) or ""
                    if not str(st_txt).strip():
                        pool[rec["uuid"]] = rec
                logger.info("Preset %r: %d hit(s) -> %d statusless",
                            target.get("title"), len(rows), len(pool))
        else:
            logger.warning("preset %r not found", preset_name)

    want_tags = list(tags)
    if recent_days > 0:
        today = datetime.now().date()
        want_tags += [f"NC Upload {today - timedelta(days=i):%Y-%m-%d}"
                      for i in range(recent_days + 1)]
    if want_tags:
        tmap = tag_uuid_map(h)
        for tg in dict.fromkeys(want_tags):
            tu = tmap.get(tg)
            if not tu:
                continue
            rows = _search(h, {"must": {"all_tags": [tu]}})
            if rows:
                logger.info("Tag %r: %d record(s)", tg, len(rows))
            for rec in rows:
                pool.setdefault(rec["uuid"], rec)
    return pool


def find_untiered(h: dict, pool: dict) -> list[dict]:
    """Read each record's FULL phone list and return the untiered ones."""
    findings = []
    for i, (ru, _) in enumerate(pool.items(), 1):
        if i % 25 == 0:
            logger.info("  ...read %d/%d records", i, len(pool))
        fr = requests.get(f"{API}/api/internal/property/{ru}/", headers=h,
                          timeout=30)
        if fr.status_code != 200:
            logger.warning("  record %s -> HTTP %s", ru[:8], fr.status_code)
            continue
        prop = fr.json().get("data") or fr.json()
        addr = prop.get("address") or {}
        street = addr.get("street") if isinstance(addr, dict) else str(addr)
        owners = []
        if prop.get("owner"):
            owners.append(prop["owner"])
        owners.extend(prop.get("secondary_owners") or [])
        for ow in owners:
            oname = f"{ow.get('first_name','')} {ow.get('last_name','')}".strip()
            for ph in (ow.get("phones") or []):
                raw = ph.get("number") or ph.get("phone") or ""
                tags = tag_texts(ph.get("tags"))
                if has_tier(tags):
                    continue
                cleaned = clean_phone(raw)
                if not cleaned:
                    continue
                findings.append({"uuid": ru, "address": street,
                                 "owner": oname, "phone": cleaned,
                                 "raw": raw, "tags": tags})
    return findings


async def _upload_tags(headless: bool) -> bool:
    from playwright.async_api import async_playwright
    from datasift_core import login
    from datasift_uploader import upload_phone_tags
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=headless)
        page = await (await b.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, email, password):
                logger.error("DataSift login failed")
                return False
            res = await upload_phone_tags(page, TAGS_CSV)
            if not res.get("success"):
                logger.error("Tag upload failed: %s", res.get("message"))
                return False
            return True
        finally:
            await b.close()


def run_sweep(*, preset: str | None = "02. Ready to Call",
              tags: list[str] | None = None, recent_days: int = 7,
              apply: bool = False, max_cost: float = 5.0,
              headless: bool = False) -> int:
    """Audit (and optionally fix) untiered phones. Returns a process exit code.

    Importable so the nightly upload can call it directly.
    """
    h = headers(get_token())
    pool = collect_scope(h, preset or None, list(tags or []), recent_days)
    logger.info("Scope: %d unique record(s)", len(pool))
    if not pool:
        logger.info("Nothing in scope.")
        return 0

    findings = find_untiered(h, pool)
    cache = load_cache()
    unique = list(dict.fromkeys(f["phone"] for f in findings))
    cached = [p for p in unique if p in cache]
    fresh = [p for p in unique if p not in cache]
    cost = len(fresh) * COST_PER_PHONE

    out = REPO / "output" / f"trestle_api_backfill_{datetime.now():%Y%m%d_%H%M}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Property Address", "Owner", "Phone", "Existing Phone Tags",
                    "Cached Tier", "Record UUID"])
        for fd in findings:
            w.writerow([fd["address"], fd["owner"], fd["phone"],
                        "; ".join(fd["tags"]),
                        cache.get(fd["phone"], {}).get("assigned_tag", ""),
                        fd["uuid"]])

    by_rec: dict[str, int] = {}
    for fd in findings:
        by_rec[fd["address"]] = by_rec.get(fd["address"], 0) + 1
    logger.info("UNTIERED: %d phone(s) on %d record(s) — %d cached (free), "
                "%d need Trestle ($%.2f)",
                len(findings), len(by_rec), len(cached), len(fresh), cost)
    for a, n in sorted(by_rec.items()):
        logger.info("   %-32s %d untiered", a, n)
    logger.info("Audit CSV: %s", out)

    if not findings:
        logger.info("Nothing to fix — every phone in scope carries a tier tag.")
        return 0
    if not apply:
        logger.info("Audit only (no spend). Re-run with --apply to score "
                    "%d fresh phone(s) for $%.2f and tag all %d.",
                    len(fresh), cost, len(unique))
        return 0
    if cost > max_cost:
        logger.error("Cost $%.2f exceeds --max-cost $%.2f — aborting before "
                     "any spend.", cost, max_cost)
        return 3

    results = []
    if fresh:
        logger.info("Scoring %d phone(s) via Trestle ($%.2f)...", len(fresh), cost)
        api_key = os.environ.get("TRESTLE_API_KEY", "")
        if not api_key:
            logger.error("TRESTLE_API_KEY not set")
            return 2
        scored, errors = process_phones([(p, p) for p in fresh], api_key)
        if errors:
            logger.warning("%d phone(s) errored and won't be tagged.", len(errors))
        for r in scored:
            cache[r["phone_number"]] = r
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        results.extend(scored)
    results.extend(cache[p] for p in cached)

    n_tags = 0
    with TAGS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Phone Number", "Phone Tag"])
        for r in results:
            if r.get("is_valid") is not False and r.get("assigned_tag"):
                w.writerow([r["phone_number"], r["assigned_tag"]])
                n_tags += 1
    by_tier: dict[str, int] = {}
    for r in results:
        if r.get("assigned_tag"):
            by_tier[r["assigned_tag"]] = by_tier.get(r["assigned_tag"], 0) + 1
    for t in sorted(by_tier):
        logger.info("   %-16s %d", t, by_tier[t])
    logger.info("Tags CSV: %s (%d phone(s))", TAGS_CSV, n_tags)
    if not n_tags:
        logger.warning("No taggable results — nothing to upload.")
        return 1

    logger.info("Uploading phone tags to DataSift...")
    if not asyncio.run(_upload_tags(headless)):
        logger.error("Upload failed — %s is ready to upload by hand via "
                     "Upload File -> Update Data -> Tag phones by phone number.",
                     TAGS_CSV)
        return 1
    logger.info("Done — dial-priority tags are live.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preset", default="02. Ready to Call",
                    help="filter preset to audit (default '02. Ready to Call'; "
                         "pass '' to skip)")
    ap.add_argument("--tag", action="append", default=[],
                    help="extra batch tag to audit (repeatable)")
    ap.add_argument("--recent-days", type=int, default=7,
                    help="also audit 'NC Upload YYYY-MM-DD' tags for the last "
                         "N days (default 7; 0 disables)")
    ap.add_argument("--apply", action="store_true",
                    help="score untiered phones + upload tags (default: free audit)")
    ap.add_argument("--max-cost", type=float, default=5.0,
                    help="abort --apply if fresh Trestle spend exceeds this (default 5.00)")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    return run_sweep(preset=args.preset, tags=args.tag,
                     recent_days=args.recent_days, apply=args.apply,
                     max_cost=args.max_cost, headless=args.headless)


if __name__ == "__main__":
    raise SystemExit(main())
