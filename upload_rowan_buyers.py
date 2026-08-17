"""One-off: upload the 118 Rowan cash-buyer A-list into DataSift.

Approved by Oren 2026-08-15 ("Yes, upload + skip trace"). Flow:
  1. Build the upload CSV from the A-list + Enformion address-lookup results
     (24 LLCs resolved to humans; 41 LLC/trusts unresolved until the free
     Enformion tier resets Sept 1; 53 individuals parsed LAST-FIRST-MIDDLE
     from the county GIS owner format).
  2. Wizard upload into a NEW "Cash Buyers" list. Uniform tags: "cash buyers"
     + batch tag "Buyer Upload 2026-08-15" (skip-trace scope).
  3. Check the prepaid balance (user/ API). Below $15 -> skip the paid trace.
  4. DataSift skip trace scoped to the batch tag (reuses the netnew retry
     loop — a new tag can take ~35 min to become filterable).
  5. API PATCH status -> "buyer" on every uploaded record (canary + verify;
     never write empty over existing).
  6. Trestle tier step on the batch tag after the trace settles.

NO text touches — those are seller scripts; these records are buyers.
"""
from __future__ import annotations

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

from datasift_uploader import login, upload_csv
from upload_netnew_datasift import _skip_trace_week

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("buyer_upload")

API = "https://apiv2.reisift.io"
A_LIST = REPO / "output" / "rowan_mill_dispo_buyers_A_list_2026-08-15.csv"
ENFORMION = REPO / "output" / "rowan_buyers_enformion_2026-08-15.json"
UPLOAD_CSV = REPO / "output" / "rowan_buyers_datasift_upload_2026-08-15.csv"
CALL_SHEET = REPO / "output" / "rowan_mill_dispo_buyers_CALL_SHEET_2026-08-15.csv"

LIST_NAME = "Cash Buyers"
BATCH_TAG = "Buyer Upload 2026-08-15"
TAGS = ["cash buyers"]
PULL_DATE = "08/15/2026"
BALANCE_FLOOR = 15.0
SUFFIXES = {"JR", "SR", "II", "III", "IV"}


def parse_gis_person(name: str) -> tuple[str, str]:
    """County GIS owner format is LAST FIRST MIDDLE [SUFFIX] -> (first, last)."""
    toks = [t for t in re.split(r"\s+", name.strip()) if t]
    toks = [t for t in toks if t.upper().rstrip(".") not in SUFFIXES]
    if len(toks) >= 2:
        return toks[1], toks[0]
    return "", toks[0] if toks else ""


def split_mailing(mail: str) -> tuple[str, str, str, str]:
    """'141 WARRIOR CT, CHINA GROVE, NC, 28023-7807' -> street, city, st, zip."""
    parts = [p.strip() for p in mail.split(",") if p.strip()]
    street = parts[0] if parts else ""
    city = state = zc = ""
    for p in parts[1:]:
        if re.fullmatch(r"[A-Z]{2}", p):
            state = p
        elif re.fullmatch(r"\d{5}(-\d{4})?", p):
            zc = p[:5]
        else:
            city = p
    return street, city, state, zc


def build_csvs() -> list[dict]:
    enf = json.loads(ENFORMION.read_text(encoding="utf-8")) if ENFORMION.exists() else {}
    rows_out, call_rows = [], []
    with A_LIST.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["Buyer Name"]
            street, city, state, zc = split_mailing(r["Mailing Address"])
            if not street or not city:
                logger.warning("Skipping %r — unparseable mailing %r", name,
                               r["Mailing Address"])
                continue
            e = enf.get(name) or {}
            if r["Entity"] == "Y":
                first = e.get("primary_first") or ""
                last = e.get("primary_last") or name  # unresolved: entity in Last
                contact_src = ("Enformion address lookup"
                               if e.get("primary_last") else "unresolved")
            else:
                first, last = parse_gis_person(name)
                contact_src = "county deed record"
            residents = "; ".join(
                f"{p['first']} {p['last']} ({p['age']})".strip()
                for p in (e.get("residents") or [])[:5])
            note = (f"CASH BUYER (Rowan sweep 8/2026): {r['Purchases (18mo)']} "
                    f"purchase(s) since 2/2025, avg ${int(r['Avg Price']):,}, "
                    f"last {r['Last Buy']}. Bought: {r['Property Addresses'][:400]}. ")
            if r["Entity"] == "Y":
                note += f"Entity: {name}. Contact source: {contact_src}. "
            if residents:
                note += f"Mailing-address residents: {residents}. "
            if r["Sister LLCs (same mailing)"]:
                note += f"Sister entities: {r['Sister LLCs (same mailing)'][:150]}."
            rows_out.append({
                "Property Street Address": street.title(),
                "Property City": city.title(),
                "Property State": state or "NC",
                "Property ZIP Code": zc,
                "Owner First Name": first.title() if first else "",
                "Owner Last Name": last.title() if last else "",
                "Tags": ", ".join(TAGS),
                "Notes": note.strip(),
            })
            call_rows.append({
                "Buyer Name": name, "Contact First": first.title(),
                "Contact Last": last.title(), "Contact Source": contact_src,
                "Mailing Address": r["Mailing Address"],
                "Purchases (18mo)": r["Purchases (18mo)"],
                "Salisbury Buys": r["Salisbury Buys"],
                "Avg Price": r["Avg Price"], "Last Buy": r["Last Buy"],
                "Score": r["Score"], "Residents": residents,
                "Property Addresses": r["Property Addresses"],
            })
    with UPLOAD_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    with CALL_SHEET.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(call_rows[0].keys()))
        w.writeheader()
        w.writerows(call_rows)
    named = sum(1 for c in call_rows if c["Contact First"])
    logger.info("Built %s (%d rows, %d with a human first name) + call sheet %s",
                UPLOAD_CSV.name, len(rows_out), named, CALL_SHEET.name)
    return rows_out


def api_headers(tok: str) -> dict:
    return {"content-type": "application/json", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}"}


def check_balance(tok: str) -> float | None:
    h = {"Accept": "application/json", "Authorization": f"Bearer {tok}",
         "X-REISIFT-UI-VERSION": "2022.02.01.7"}
    try:
        return float(requests.get(f"{API}/api/internal/user/", headers=h,
                                  timeout=25).json().get("balance"))
    except Exception as e:  # noqa: BLE001
        logger.warning("balance read failed: %s", e)
        return None


def find_uuid(h: dict, street: str) -> str | None:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        return None
    hits = [rec for rec in r.json().get("results", [])
            if (rec.get("address") or {}).get("street", "").strip().lower()
            == street.strip().lower()]
    return hits[0].get("uuid") if len(hits) == 1 else None


def set_status_buyer(tok: str, rows: list[dict]) -> tuple[int, int]:
    """PATCH status -> 'buyer' on each uploaded record. Canary + verify."""
    h = api_headers(tok)
    done = failed = 0
    for i, r in enumerate(rows):
        street = r["Property Street Address"]
        uuid = find_uuid(h, street)
        if not uuid:
            logger.warning("%s: no unique record found — status not set", street)
            failed += 1
            continue
        g = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30)
        if g.status_code != 200:
            failed += 1
            continue
        cur = g.json().get("status")
        cur_title = (cur.get("title") if isinstance(cur, dict) else cur) or ""
        if str(cur_title).strip().lower() == "buyer":
            done += 1
            continue
        p = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"status": "buyer"}, timeout=30)
        chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                           timeout=30)
        new = chk.json().get("status") if chk.status_code == 200 else None
        new_title = (new.get("title") if isinstance(new, dict) else new) or ""
        if p.status_code in (200, 202) and str(new_title).strip().lower() == "buyer":
            done += 1
        else:
            failed += 1
            logger.error("%s: status PATCH did not verify (HTTP %d, status now %r)",
                         street, p.status_code, new_title)
            if i == 0:
                logger.error("Canary failed — ABORTING remaining status PATCHes.")
                return done, failed + len(rows) - 1
        if (done + failed) % 25 == 0:
            logger.info("status progress: %d ok / %d failed of %d",
                        done, failed, len(rows))
    return done, failed


async def main() -> int:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2

    rows = build_csvs()
    if len(rows) < 100:
        logger.error("Only %d rows built — expected ~118. Aborting.", len(rows))
        return 2

    traced = False
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("Login failed")
                return 1
            tok = await page.evaluate("() => localStorage.getItem('rs_token')")

            bal = check_balance(tok)
            logger.info("Prepaid balance before upload: %s",
                        f"${bal:.2f}" if bal is not None else "unknown")

            logger.info("Uploading %d buyers into new list %r...", len(rows), LIST_NAME)
            result = await upload_csv(page, UPLOAD_CSV, mode="add",
                                      list_name=LIST_NAME, existing_list=False,
                                      finish=True, pull_date=PULL_DATE,
                                      extra_tags=[BATCH_TAG],
                                      tags_override=TAGS)
            if not result.get("success"):
                logger.error("Upload failed: %s", result.get("message"))
                return 1
            logger.info("Upload committed. %s", result.get("message", ""))

            if bal is not None and bal < BALANCE_FLOOR:
                logger.warning("Balance $%.2f is under the $%.2f floor — SKIPPING "
                               "the paid skip trace. Records are uploaded; trace "
                               "by hand after topping up.", bal, BALANCE_FLOOR)
            else:
                traced = await _skip_trace_week(page, LIST_NAME, BATCH_TAG, 90)

            # Status -> buyer AFTER the trace-start loop: by then the import
            # has fully settled, so record search finds every row.
            done, failed = set_status_buyer(tok, rows)
            logger.info("Status 'buyer': %d set/confirmed, %d failed.", done, failed)

            bal2 = check_balance(tok)
            if bal is not None and bal2 is not None:
                logger.info("Balance after: $%.2f (spend so far $%.2f — trace "
                            "results keep billing as they land).", bal2, bal - bal2)
        finally:
            await browser.close()

    if traced:
        logger.info("Waiting 10 min for trace results, then Trestle tier step "
                    "(tag=%r)...", BATCH_TAG)
        await asyncio.sleep(600)
        try:
            from trestle_tier_step import run as tier_run
            rc = await tier_run(BATCH_TAG, dry_run=False, headless=True)
            logger.info("Trestle tier step exit code %d%s", rc,
                        "" if rc == 0 else " — run by hand: python "
                        f"trestle_tier_step.py with tag {BATCH_TAG!r}")
        except Exception as e:  # noqa: BLE001
            logger.error("Tier step failed (%s) — run by hand later.", e)
    else:
        logger.warning("Skip trace did not start — tier step skipped. Trace by "
                       "hand: Records -> tag %r -> Send To -> Skip Trace.", BATCH_TAG)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
