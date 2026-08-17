"""One-off: finish the 2026-08-15 Rowan cash-buyer upload.

1. PATCH owner names onto the 39 LLC records resolved by Enformion AFTER the
   upload (Starter upgrade): first/last = the human, company = the entity.
   Only touches records whose owner has no first_name yet (never overwrite).
2. Retry status -> 'buyer' on records the first pass couldn't match: candidate
   resolution is tag-aware (must carry the 'Buyer Upload 2026-08-15' tag)
   instead of requiring a globally-unique street match.
3. Export the call sheet v2 with the phones/emails/dial tags DataSift's skip
   trace + Trestle tier step have landed on each record.

Canary rule: first PATCH of each kind must verify by re-GET or the rest abort.
Never writes an empty value over an existing one.
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
from datasift_uploader import login

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fix_buyers")

API = "https://apiv2.reisift.io"
BATCH_TAG = "Buyer Upload 2026-08-15"
A_LIST = REPO / "output" / "rowan_mill_dispo_buyers_A_list_2026-08-15.csv"
ENFORMION = REPO / "output" / "rowan_buyers_enformion_2026-08-15.json"
UPLOAD = REPO / "output" / "rowan_buyers_datasift_upload_2026-08-15.csv"
CALL_SHEET_V2 = REPO / "output" / "rowan_mill_dispo_buyers_CALL_SHEET_v2_2026-08-15.csv"


def norm_street(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def api_headers(tok: str) -> dict:
    return {"content-type": "application/json", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}"}


_SUFFIX_ABBR = {"DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "BOULEVARD": "BLVD",
                "HIGHWAY": "HWY", "STREET": "ST", "AVENUE": "AVE",
                "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL", "SUITE": "STE",
                "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S", "EAST": "E",
                "WEST": "W"}


def street_key(s: str) -> str:
    """Abbreviation-insensitive compact street key."""
    toks = [_SUFFIX_ABBR.get(t, t) for t in norm_street(s).split()]
    return "".join(toks)


def fetch_batch_records(h: dict) -> list[dict]:
    """All records carrying the batch tag, via the preset query grammar."""
    r = requests.get(f"{API}/api/internal/tag/", headers={k: v for k, v in h.items()
                     if k != "x-http-method-override"},
                     params={"search": BATCH_TAG, "limit": 10}, timeout=30)
    tag_id = None
    for t in (r.json().get("results") or r.json().get("data") or []):
        if (t.get("title") or "") == BATCH_TAG:
            tag_id = t.get("uuid")
    if not tag_id:
        raise RuntimeError(f"tag {BATCH_TAG!r} not found via tag/ API")
    out, offset, limit = [], 0, 200
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": limit, "offset": offset,
                                "query": {"must": {"any_tags": [tag_id]}}},
                          timeout=30)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < limit or offset > 2000:
            break
        offset += limit
    logger.info("Batch-tagged records fetched: %d", len(out))
    return out


def find_batch_record(h: dict, street: str, cache: dict) -> dict | None:
    """Match a mailing street against the pre-fetched batch records; return
    the FULL record (fresh GET) so PATCH verifies see current state."""
    if "_by_key" not in cache:
        cache["_by_key"] = {}
        for rec in fetch_batch_records(h):
            k = street_key((rec.get("address") or {}).get("street", ""))
            cache["_by_key"].setdefault(k, []).append(rec["uuid"])
    key = street_key(street)
    uuids = cache["_by_key"].get(key)
    if not uuids:
        # unit-suffix drop fallback ("...Dr 1599" stored as "...Dr")
        cands = [v for k, v in cache["_by_key"].items()
                 if len(k) >= 10 and (key.startswith(k) or k.startswith(key))]
        uuids = cands[0] if len(cands) == 1 else None
    if not uuids or len(set(uuids)) != 1:
        return None
    g = requests.get(f"{API}/api/internal/property/{uuids[0]}/", headers=h,
                     timeout=30)
    return g.json() if g.status_code == 200 else None


def main_sync(tok: str) -> None:
    h = api_headers(tok)
    enf = json.loads(ENFORMION.read_text(encoding="utf-8"))
    with A_LIST.open(newline="", encoding="utf-8") as f:
        alist = list(csv.DictReader(f))
    with UPLOAD.open(newline="", encoding="utf-8-sig") as f:
        uprows = {norm_street(r["Property Street Address"]): r
                  for r in csv.DictReader(f)}

    rec_cache: dict = {}
    name_ok = name_fail = stat_ok = stat_fail = 0
    name_canary_checked = False
    sheet_rows = []

    # The 6 importer-dropped rows were re-uploaded 8/15 with cleaned
    # addresses (fix_buyer_missing6_20260815.py) — match those records
    # by their fixed street, not the raw GIS mailing.
    fixed_streets = {
        "Young Samuel Adams": "116 S Main St",
        "Young Samuel": "116 S Main St",
        "High Rock Home Buyers Llc": "116 S Main St Ste C",
        "The Mln Living Trust": "7335 US Highway 52",
        "Heavenly Homes J K Llc": "5610 Comiskey Aly",
        "Trishul Properties Llc": "2440 Statesville Blvd",
    }

    for a in alist:
        buyer = a["Buyer Name"]
        street = fixed_streets.get(buyer) or a["Mailing Address"].split(",")[0].strip()
        rec = find_batch_record(h, street, rec_cache)
        if rec is None:
            logger.warning("%s (%s): no unique batch-tagged record", buyer, street)
            sheet_rows.append({"Buyer Name": buyer, "Record": "NOT FOUND",
                               "Mailing Address": a["Mailing Address"],
                               "Score": a["Score"]})
            continue
        uuid = rec["uuid"]
        owner = rec.get("owner") or {}
        e = enf.get(buyer) or {}

        # ── 1. owner-name PATCH for post-upload Enformion resolutions ──
        want_first = (e.get("primary_first") or "").title()
        want_last = (e.get("primary_last") or "").title()
        cur_first = (owner.get("first_name") or "").strip()
        cur_last = (owner.get("last_name") or "").strip()
        is_entity_row = a["Entity"] == "Y"
        needs_name = (is_entity_row and want_first and want_last
                      and not cur_first
                      and cur_last.lower() != want_last.lower())
        if needs_name:
            new_owner = dict(owner)
            new_owner["first_name"] = want_first
            new_owner["last_name"] = want_last
            if not (owner.get("company") or "").strip():
                new_owner["company"] = buyer
            p = requests.patch(f"{API}/api/internal/property/{uuid}/",
                               headers=h, json={"owner": new_owner}, timeout=30)
            chk = requests.get(f"{API}/api/internal/property/{uuid}/",
                               headers=h, timeout=30).json()
            got = chk.get("owner") or {}
            if (p.status_code in (200, 202)
                    and (got.get("first_name") or "").strip().lower() == want_first.lower()
                    and (got.get("last_name") or "").strip().lower() == want_last.lower()):
                logger.info("%s: owner set to %s %s (company %r)", buyer,
                            want_first, want_last, got.get("company"))
                name_ok += 1
                rec = chk
                owner = got
            else:
                logger.error("%s: owner PATCH did not verify (HTTP %d, owner now "
                             "%s %s)", buyer, p.status_code,
                             got.get("first_name"), got.get("last_name"))
                name_fail += 1
                if not name_canary_checked:
                    logger.error("Owner-name canary failed — aborting remaining "
                                 "name PATCHes (status + sheet still run).")
                    enf = {}  # disables further name patches
            name_canary_checked = True

        # ── 2. status -> buyer where still missing ──
        cur_status = rec.get("status")
        cur_title = (cur_status.get("title") if isinstance(cur_status, dict)
                     else cur_status) or ""
        if str(cur_title).strip().lower() != "buyer":
            p = requests.patch(f"{API}/api/internal/property/{uuid}/",
                               headers=h, json={"status": "buyer"}, timeout=30)
            chk = requests.get(f"{API}/api/internal/property/{uuid}/",
                               headers=h, timeout=30).json()
            new = chk.get("status")
            new_t = (new.get("title") if isinstance(new, dict) else new) or ""
            if str(new_t).strip().lower() == "buyer":
                stat_ok += 1
                rec = chk
            else:
                stat_fail += 1
                logger.error("%s: status retry failed (HTTP %d, now %r)",
                             buyer, p.status_code, new_t)

        # ── 3. call-sheet row with live phones/emails/dial tags ──
        owner = rec.get("owner") or {}
        phones = owner.get("phones") or []
        tags = [t.get("name") if isinstance(t, dict) else t
                for t in rec.get("tags", [])]
        dial_tags = [t for t in tags if t.lower().startswith("dial")
                     or "litigator" in t.lower()]
        sheet_rows.append({
            "Buyer Name": buyer,
            "Contact": f"{owner.get('first_name') or ''} "
                       f"{owner.get('last_name') or ''}".strip(),
            "Company": owner.get("company") or "",
            "Phones": "; ".join(
                f"{p.get('number')} ({(p.get('type') or '?').lower()}"
                f"{', connected' if p.get('is_connected') else ''})"
                for p in phones[:5]),
            "Emails": "; ".join((owner.get("emails") or [])[:3]),
            "Dial Tags": "; ".join(dial_tags),
            "Record": "OK",
            "Mailing Address": a["Mailing Address"],
            "Purchases (18mo)": a["Purchases (18mo)"],
            "Salisbury Buys": a["Salisbury Buys"],
            "Avg Price": a["Avg Price"],
            "Last Buy": a["Last Buy"],
            "Score": a["Score"],
        })

    cols = ["Buyer Name", "Contact", "Company", "Phones", "Emails", "Dial Tags",
            "Record", "Mailing Address", "Purchases (18mo)", "Salisbury Buys",
            "Avg Price", "Last Buy", "Score"]
    with CALL_SHEET_V2.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sheet_rows)

    with_phone = sum(1 for r in sheet_rows if r.get("Phones"))
    logger.info("Owner names: %d set, %d failed. Status retry: %d set, %d failed.",
                name_ok, name_fail, stat_ok, stat_fail)
    logger.info("Call sheet v2: %d rows, %d with phones -> %s",
                len(sheet_rows), with_phone, CALL_SHEET_V2.name)


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
    main_sync(tok)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
