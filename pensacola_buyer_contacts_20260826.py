"""Clean the Pensacola buyer campaign's contact data.

DataSift auto-appended household contacts on upload. That append is keyed to
the ADDRESS, not the person, so it drags in whoever else is tied to the
building: Heartland's downtown Mobile office came back with "Cotton" emails,
Kenneth Monie's house with "Hout". Oren is calling and emailing these buyers,
not mailing them, so contact accuracy is the whole job.

Two passes:
  PHONES  Trestle-score every number (cache first, so re-runs are ~free) and
          write the Phone Number | Phone Tag CSV that DataSift's
          "Tag phones by phone number" import consumes. Numbers that cannot be
          scored KEEP no tag rather than being marked bad — unscored is
          unknown, not dead.
  EMAILS  Score each address against the buyer's own name and entity. Clear
          mismatches are REMOVED from the record via an owner round-trip
          PATCH, verified by re-GET. Anything plausible stays: a nickname or
          initials local-part is far more likely the buyer than noise, and
          deleting a real address costs more than keeping a doubtful one.

--apply writes to DataSift; default is a dry run that only reports.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from playwright.async_api import async_playwright
from datasift_uploader import login, upload_phone_tags
import phone_validator as pv
import fix_buyer_records_20260815 as fx

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pcola_contacts")

API = "https://apiv2.reisift.io"
BATCH_TAG = "IB Pensacola 2026-08-26"
TAGS_CSV = REPO / "output" / "pensacola_phone_tags_2026-08-26.csv"
REPORT = REPO / "output" / "pensacola_contact_audit_2026-08-26.csv"

# Extra name tokens per buyer that a bare first/last split would miss:
# entity words, spouses on title, and the known trade-name domains.
EXTRA_TOKENS = {
    "Sidney Byrne": {"kbg", "byrne", "baine"},
    "Heartland Buys": {"heartland", "heartlandbuys"},
    "Eric Rivera": {"rivera", "dr.construction", "drconstruction"},
    "Brett Wolfe": {"wolfe", "berman"},          # Jill Wolfe / Berman on title
    "Kenneth Monie": {"monie"},                   # Stephanie Monie on title
    "Robert Schweigert": {"schweigert", "buildpensacola"},
    "Charlotte Richardson": {"richardson", "lottie", "holdthis"},
    "Andrew Williams": {"williams"},
    "Ashton Baker": {"baker", "guyer"},
    "Yamile Strautman": {"strautman", "yamil"},
    "Derrick Smith": {"smith"},
    "Cheri Conkle": {"conkle"},
    "Mark Vu": {"vu"},
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def email_matches(email: str, first: str, last: str, extra: set[str]) -> bool:
    """True when the address plausibly belongs to this buyer.

    Deliberately generous. The cost of dropping the buyer's real address is a
    lost deal; the cost of keeping a doubtful one is one bounced email.
    """
    local, _, domain = email.lower().partition("@")
    lp, dom = norm(local), norm(domain)
    f, l = norm(first), norm(last)
    if l and len(l) >= 4 and (l in lp or l in dom):
        return True
    if f and len(f) >= 4 and f in lp:
        return True
    # first-initial + surname, and surname + first-initial
    if f and l and len(l) >= 3 and (f[0] + l) in lp:
        return True
    for tok in extra:
        t = norm(tok)
        if t and len(t) >= 4 and (t in lp or t in dom):
            return True
    return False


def fetch_batch(h: dict) -> list[dict]:
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"search": BATCH_TAG, "limit": 500}, timeout=30)
    tid = next(x["uuid"] for x in r.json()["results"]
               if x["title"] == BATCH_TAG)
    rows = requests.post(f"{API}/api/internal/property/",
                         headers={**h, "x-http-method-override": "GET"},
                         json={"limit": 200,
                               "query": {"must": {"any_tags": [tid]}}},
                         timeout=30).json()["results"]
    return [requests.get(f"{API}/api/internal/property/{x['uuid']}/",
                         headers=h, timeout=30).json() for x in rows]


async def get_token() -> str:
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        pg = await (await b.new_context()).new_page()
        try:
            if not await login(pg, os.environ.get("DATASIFT_EMAIL", ""),
                               os.environ.get("DATASIFT_PASSWORD", "")):
                raise RuntimeError("DataSift login failed")
            return await pg.evaluate("() => localStorage.getItem('rs_token')")
        finally:
            await b.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write to DataSift (default: dry run)")
    ap.add_argument("--max-spend", type=float, default=2.00,
                    help="Trestle ceiling for NEW scores this run")
    args = ap.parse_args()

    tok = await get_token()
    h = fx.api_headers(tok)
    recs = fetch_batch(h)
    logger.info("Campaign records: %d", len(recs))

    # ── collect ───────────────────────────────────────────────────────────
    phones: list[tuple[str, str]] = []
    audit: list[dict] = []
    for rec in recs:
        o = rec.get("owner") or {}
        first = o.get("first_name") or ""
        last = o.get("last_name") or ""
        who = f"{first} {last}".strip()
        extra = EXTRA_TOKENS.get(who, set())
        for p in (o.get("phones") or []):
            n = re.sub(r"\D", "", p.get("number") or "")[-10:]
            if len(n) == 10:
                phones.append((p.get("number") or n, n))
        keep, drop = [], []
        for e in (o.get("emails") or []):
            (keep if email_matches(e, first, last, extra) else drop).append(e)
        audit.append({"uuid": rec["uuid"], "who": who,
                      "street": (rec.get("address") or {}).get("street", ""),
                      "keep": keep, "drop": drop, "owner": o})

    uniq = list(dict.fromkeys(p[1] for p in phones))
    logger.info("Phones: %d unique | Emails: %d keep, %d mismatched",
                len(uniq), sum(len(a["keep"]) for a in audit),
                sum(len(a["drop"]) for a in audit))

    # ── phones: Trestle score (cache-first) ───────────────────────────────
    key = os.environ.get("TRESTLE_API_KEY", "")
    if not key:
        logger.error("No TRESTLE_API_KEY — cannot score phones")
        return 1
    cache_path = REPO / "output" / ".trestle_score_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    fresh = [n for n in uniq if n not in cache]
    est = len(fresh) * 0.015
    logger.info("Trestle: %d cached, %d new (~$%.2f)",
                len(uniq) - len(fresh), len(fresh), est)
    if est > args.max_spend:
        logger.error("Estimated $%.2f exceeds --max-spend $%.2f — aborting",
                     est, args.max_spend)
        return 1

    tiers: dict[str, str] = {}
    for n in uniq:
        if n in cache:
            t = cache[n].get("assigned_tag") or ""
            if t:
                tiers[n] = t
    if fresh:
        results, errors = pv.process_phones([(n, n) for n in fresh], key)
        for r in results:
            n = r["phone_number"]
            tiers[n] = r["assigned_tag"]
            cache[n] = {"assigned_tag": r["assigned_tag"],
                        "activity_score": r["activity_score"],
                        "line_type": r["line_type"]}
        if errors:
            logger.warning("%d phone(s) could not be scored — left untagged",
                           len(errors))
        cache_path.write_text(json.dumps(cache), encoding="utf-8")

    with TAGS_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Phone Number", "Phone Tag"])
        for n, t in sorted(tiers.items()):
            if t:
                w.writerow([n, t])
    logger.info("Phone tags CSV: %s (%d tagged)", TAGS_CSV, len(tiers))

    # ── report ────────────────────────────────────────────────────────────
    with REPORT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Buyer", "Street", "Emails Kept", "Emails Removed",
                    "Phones", "Dial First", "Dial Second"])
        for a in audit:
            ph = [re.sub(r"\D", "", p.get("number") or "")[-10:]
                  for p in (a["owner"].get("phones") or [])]
            d1 = [n for n in ph if tiers.get(n) == "Dial First"]
            d2 = [n for n in ph if tiers.get(n) == "Dial Second"]
            w.writerow([a["who"], a["street"], "; ".join(a["keep"]),
                        "; ".join(a["drop"]), len(ph),
                        "; ".join(d1), "; ".join(d2)])
    logger.info("Audit report: %s", REPORT)

    for a in audit:
        if a["drop"]:
            logger.info("%-20s keep %d | remove %s", a["who"], len(a["keep"]),
                        ", ".join(a["drop"]))

    if not args.apply:
        logger.info("DRY RUN — nothing written. Re-run with --apply.")
        return 0

    # ── apply: strip mismatched emails (verified by re-GET) ───────────────
    ok = fail = 0
    for a in audit:
        if not a["drop"]:
            continue
        o = dict(a["owner"])
        o["emails"] = a["keep"]
        requests.patch(f"{API}/api/internal/property/{a['uuid']}/", headers=h,
                       json={"owner": o}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{a['uuid']}/",
                           headers=h, timeout=30).json()
        got = [e.lower() for e in ((chk.get("owner") or {}).get("emails") or [])]
        good = all(e.lower() not in got for e in a["drop"])
        ok += good
        fail += (not good)
        logger.info("%-20s emails -> %s (%d kept)", a["who"],
                    "OK" if good else "FAIL", len(got))
    logger.info("Email cleanup: %d ok, %d fail", ok, fail)

    # ── apply: push dial tiers ────────────────────────────────────────────
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        pg = await (await b.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(pg, os.environ.get("DATASIFT_EMAIL", ""),
                               os.environ.get("DATASIFT_PASSWORD", "")):
                logger.error("Login failed for tag upload")
                return 1
            up = await upload_phone_tags(pg, TAGS_CSV)
            logger.info("Phone tag upload: %s", up.get("message"))
            if not up.get("success"):
                return 2
        finally:
            await b.close()
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
