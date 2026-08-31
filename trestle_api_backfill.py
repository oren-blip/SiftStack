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

LINE TYPES (2026-08-22)
-----------------------
The same sweep also fills in each phone's Mobile / Landline / VOIP. DataSift's
CSV upload has only plain "Phone N" columns — no line-type column — so every
phone we upload lands as UNKNOWN, while phones DataSift skip-traces itself and
phones our DP scripts POST through the API (which send "type") get a real one.
Measured that day: 164 of the 300 phones in '02. Ready to Call' were UNKNOWN,
and every single one had arrived by CSV upload.

Trestle returns `line_type` on the very call we already pay for the activity
score, so this pass is FREE — it reads the score cache and never calls Trestle
on its own. Phones with no cached line type are left alone, not guessed.

WHEN IT RUNS (2026-08-30)
-------------------------
Two clocks, same sweep:
  * inside `upload_netnew_datasift.py`, after every nightly upload;
  * on its own — Task Scheduler "SiftStack Tier Sweep" runs
    `scripts/trestle_sweep.bat` daily at 07:00 and 13:00, every day.
The second one exists because the first only fires on nights something was
uploaded (never on weekends), while phones keep landing regardless — so
"02. Ready to Call" kept refilling with untiered numbers between uploads.

Trestle-invalid numbers (`is_valid` False) are tagged "Drop": they can never
score, and without a terminal tag the same phone re-surfaced every night.

Default run is a FREE AUDIT (no Trestle spend, no writes).

    python trestle_api_backfill.py                    # audit RTC + last 7 days
    python trestle_api_backfill.py --apply            # score + tag + set types
    python trestle_api_backfill.py --preset "02. Ready to Call" --apply
    python trestle_api_backfill.py --tag "NC Upload 2026-08-20" --apply
    python trestle_api_backfill.py --apply --no-types # tiers only
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
                  recent_days: int, county: str | None = None) -> dict:
    """Return {uuid: record} for every record in the audit scope.

    `county` narrows every search to one Property County (the API key is
    `property_county`, a plain string — a list value is a 400).
    """
    pool: dict[str, dict] = {}

    def _scoped(q: dict) -> dict:
        """Inject the county filter into a search query, if one was asked for."""
        if not county:
            return q
        q = json.loads(json.dumps(q))          # deep copy, leave caller's dict alone
        q.setdefault("must", {})["property_county"] = county
        return q

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
                rows = _search(h, _scoped(q))
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
            rows = _search(h, _scoped({"must": {"all_tags": [tu]}}))
            if rows:
                logger.info("Tag %r: %d record(s)", tg, len(rows))
            for rec in rows:
                pool.setdefault(rec["uuid"], rec)
    return pool


def find_untiered(h: dict, pool: dict,
                  props_out: dict | None = None) -> list[dict]:
    """Read each record's FULL phone list and return the untiered ones.

    `props_out`, when given, collects the full record JSON per UUID so the
    line-type pass can reuse these GETs instead of re-reading every record.
    """
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
        if props_out is not None:
            props_out[ru] = prop
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
                # street can be None on Incomplete records (no address) —
                # a None key crashes the sorted() report at the end.
                findings.append({"uuid": ru, "address": street or "(no address)",
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


# ── Line type (Mobile / Landline / VOIP) ────────────────────────────────────
# DataSift's CSV upload has only plain "Phone N" columns — no line-type column —
# so every phone we upload lands as UNKNOWN, while phones DataSift skip-traces
# itself and phones our DP scripts POST through the API (which send "type")
# carry a real one. Measured 2026-08-22: 164 of 300 phones in "02. Ready to
# Call" were UNKNOWN and every single one of them came in by CSV upload.
#
# Trestle hands us `line_type` on the very same call we already pay for the
# activity score, so filling this in is free — it reads from the score cache
# and never makes a Trestle call of its own.
DS_TYPES = ("MOBILE", "LANDLINE", "VOIP")


def ds_line_type(trestle_line_type: str | None) -> str | None:
    """Trestle line type -> DataSift's phone type enum (verified live: a PATCH
    of "VOIP" round-trips). Anything else (TollFree, Premium, blank) -> None,
    which leaves the phone alone rather than guessing."""
    lt = str(trestle_line_type or "").lower().replace(" ", "").replace("_", "")
    if "voip" in lt:                          # FixedVOIP / NonFixedVOIP
        return "VOIP"
    if "mobile" in lt or "wireless" in lt:
        return "MOBILE"
    if "landline" in lt or "fixedline" in lt:
        return "LANDLINE"
    return None


def fix_line_types(h: dict, props: dict, cache: dict, *,
                   apply: bool = False) -> dict:
    """Set Mobile/Landline/VOIP on phones sitting at UNKNOWN, from the Trestle
    score cache. Free (cache only). Returns a summary dict."""
    summary = {"records": 0, "phones": 0, "by_type": {}, "unresolved": 0,
               "failed": [], "detail": []}
    for ru, prop in props.items():
        addr = prop.get("address") or {}
        street = (addr.get("street") if isinstance(addr, dict) else str(addr))             or "(no address)"
        body, changes = {}, 0
        groups = [("owner", [prop["owner"]] if prop.get("owner") else []),
                  ("secondary_owners", prop.get("secondary_owners") or [])]
        for key, owners in groups:
            touched = False
            for ow in owners:
                for ph in (ow.get("phones") or []):
                    cur = str(ph.get("type") or "").upper()
                    if cur in DS_TYPES:
                        continue
                    cleaned = clean_phone(ph.get("number") or "")
                    want = ds_line_type(
                        (cache.get(cleaned) or {}).get("line_type"))
                    if not want:
                        summary["unresolved"] += 1
                        continue
                    ph["type"] = want
                    touched = True
                    changes += 1
                    summary["by_type"][want] = summary["by_type"].get(want, 0) + 1
                    summary["detail"].append((street, cleaned, want))
            if touched:
                body[key] = owners[0] if key == "owner" else owners
        if not changes:
            continue
        summary["records"] += 1
        summary["phones"] += changes
        if not apply:
            continue
        r = requests.patch(f"{API}/api/internal/property/{ru}/", headers=h,
                           data=json.dumps(body), timeout=30)
        if r.status_code not in (200, 202):
            logger.warning("  %s: type PATCH -> %s %s", street,
                           r.status_code, r.text[:120])
            summary["failed"].append((street, f"HTTP {r.status_code}"))
            continue
        # Verify by re-GET — a 200 that didn't stick is the known failure mode
        # (see project_pr_upgrade_silent_save_failure).
        vr = requests.get(f"{API}/api/internal/property/{ru}/", headers=h,
                          timeout=30)
        if vr.status_code != 200:
            summary["failed"].append((street, "verify GET failed"))
            continue
        live = vr.json().get("data") or vr.json()
        got = {}
        for ow in ([live["owner"]] if live.get("owner") else [])                 + (live.get("secondary_owners") or []):
            for ph in (ow.get("phones") or []):
                got[clean_phone(ph.get("number") or "")] =                     str(ph.get("type") or "").upper()
        stale = [(n, t) for (s, n, t) in summary["detail"]
                 if s == street and got.get(n) != t]
        if stale:
            summary["failed"].append((street, f"{len(stale)} phone(s) reverted"))
            logger.warning("  %s: %d phone type(s) did not stick: %s",
                           street, len(stale), stale[:3])
    return summary


def report_line_types(summary: dict, *, apply: bool) -> None:
    verb = "Set" if apply else "Would set"
    if not summary["phones"]:
        logger.info("LINE TYPES: every phone in scope already has one.")
        return
    logger.info("LINE TYPES: %s %d phone(s) on %d record(s) — %s",
                verb, summary["phones"], summary["records"],
                ", ".join(f"{k} {v}" for k, v in
                          sorted(summary["by_type"].items())))
    if summary["unresolved"]:
        logger.info("   %d UNKNOWN phone(s) left alone (no line type in the "
                    "Trestle cache)", summary["unresolved"])
    for street, why in summary["failed"]:
        logger.warning("   FAILED %-32s %s", street, why)


def _tier_sweep(*, h: dict, pool: dict, props: dict, apply: bool,
                max_cost: float, headless: bool) -> int:
    """Audit (and optionally fix) untiered phones. Returns a process exit code."""
    findings = find_untiered(h, pool, props)
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
        for e in errors:
            # Say WHY, not just "errored": a transient timeout / 5xx is retried
            # next run, and nothing else can be decided without the reason.
            logger.warning("  Trestle error on %s: %s %s", e.get("phone_number"),
                           e.get("error"), (e.get("detail") or "")[:80])
        for r in scored:
            if r.get("is_valid") is False:
                # Trestle says this is not a real phone number, so it can never
                # earn an activity score. Without a terminal tag it re-surfaces
                # as "untiered" on every sweep (305 S Greenbriar Rd looped for
                # 8 nights, 8/23-8/28) and the sweep exits 1 with "no taggable
                # results". "Drop" is the not-dialable tier, which is exactly
                # what an invalid number is.
                r["assigned_tag"] = "Drop"
            cache[r["phone_number"]] = r
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        results.extend(scored)
    results.extend(cache[p] for p in cached)

    n_tags = 0
    with TAGS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Phone Number", "Phone Tag"])
        for r in results:
            tag = r.get("assigned_tag") or ""
            if r.get("is_valid") is False and tag != "Drop":
                tag = "Drop"                      # older cache entries pre-fix
            if not has_tier([tag]):
                # "Unknown" (valid number, no score) is not a tier — writing
                # it would create a junk phone tag and still count as untiered.
                logger.warning("  %s: no tier from Trestle (%r) — left untagged",
                               r.get("phone_number"), tag)
                continue
            w.writerow([r["phone_number"], tag])
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


def run_sweep(*, preset: str | None = "02. Ready to Call",
              tags: list[str] | None = None, recent_days: int = 7,
              apply: bool = False, max_cost: float = 5.0,
              headless: bool = False, fix_types: bool = True,
              county: str | None = None) -> int:
    """Tier untiered phones, then fill in any missing Mobile/Landline/VOIP.

    The line-type pass is free (Trestle score cache only) and runs whether or
    not anything needed tiering — CSV-uploaded phones get a tier tag from this
    sweep but land with no line type at all, so the two gaps are independent.

    Importable so the nightly upload can call it directly.
    """
    h = headers(get_token())
    pool = collect_scope(h, preset or None, list(tags or []), recent_days,
                         county=county)
    logger.info("Scope: %d unique record(s)%s", len(pool),
                f" in {county}" if county else "")
    if not pool:
        logger.info("Nothing in scope.")
        return 0

    props: dict = {}
    rc = _tier_sweep(h=h, pool=pool, props=props, apply=apply,
                     max_cost=max_cost, headless=headless)
    if fix_types and props:
        # reload the cache: the tier pass above may have just scored phones,
        # and their line types are in those fresh results.
        summary = fix_line_types(h, props, load_cache(), apply=apply)
        report_line_types(summary, apply=apply)
        if summary["failed"] and rc == 0:
            rc = 1
    return rc


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
    ap.add_argument("--county",
                    help="narrow the whole sweep to one Property County "
                         "(e.g. Cabarrus) — lets you work one county at a time")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--no-types", action="store_true",
                    help="skip the free line-type (Mobile/Landline/VOIP) pass")
    args = ap.parse_args()
    return run_sweep(preset=args.preset, tags=args.tag,
                     recent_days=args.recent_days, apply=args.apply,
                     max_cost=args.max_cost, headless=args.headless,
                     fix_types=not args.no_types, county=args.county)


if __name__ == "__main__":
    raise SystemExit(main())
