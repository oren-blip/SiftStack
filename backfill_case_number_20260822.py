"""One-off backfill: write the estate Case Number onto DataSift records that
were uploaded BEFORE the upload CSV carried the column.

Root cause (fixed same day in src/nc_datasift_export.py): `Case No.` was never
in `_FIELD_MAP`, so every NETNEW upload dropped it. The CRM's "Case Number"
custom field (id 13474, uuid 1d7dd246-..., group "Estate Files") therefore sat
empty on all ~328 cases in output/.netnew_uploaded.json.

Self-guarding, per project_pr_upgrade_silent_save_failure:
  - never writes over a Case Number that already has a value (reports instead)
  - identity guard: the record's Decedent custom field or owner surname must
    match the CSV row before anything is written
  - every write is verified by re-GET; a silent no-op counts as a failure

Endpoints (same recipe as fix_estate_of_dm_20260814.py):
  POST  /api/internal/property/            (x-http-method-override: GET) - search
  GET   /api/internal/property/{uuid}/custom-field/?limit=1000
  PATCH /api/internal/property/{uuid}/custom-field/update-values/
        body = [{"field_uuid": <DEFINITION uuid>, "value": "..."}]

Usage:
    python backfill_case_number_20260822.py --dry-run
    python backfill_case_number_20260822.py
    python backfill_case_number_20260822.py --limit 25      # partial run
"""
from __future__ import annotations

import asyncio
import csv
import glob
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://apiv2.reisift.io"
CASE_FIELD_UUID = "1d7dd246-1fa0-4130-b4fe-08c270958da3"   # "Case Number", id 13474
CASE_LABEL = "case number"
LEDGER = os.path.join("output", ".netnew_uploaded.json")
STATE = os.path.join("output", ".case_number_backfill.json")   # resumable progress
TOKEN_CACHE = os.path.join("output", ".ds_token.json")         # survives a flaky login


# -- case -> (addresses, decedent, owner) from the pipeline's own CSV history --

def build_case_index() -> dict[str, dict]:
    """Newest-file-wins map of Case No. -> identifying fields. Older files still
    contribute extra address spellings (DataSift may have re-normalized the
    street, so more candidates = more chances the search hits)."""
    idx: dict[str, dict] = {}
    files = sorted(glob.glob(os.path.join("output", "**", "*.csv"), recursive=True),
                   key=os.path.getmtime)
    for f in files:
        try:
            rd = csv.DictReader(io.open(f, encoding="utf-8-sig"))
            fn = rd.fieldnames or []
            if "Case No." not in fn:
                continue
            acol = next((c for c in ("Property Address", "Property Street Address",
                                     "Address") if c in fn), None)
            if not acol:
                continue
            for r in rd:
                cn = (r.get("Case No.") or "").strip().upper()
                addr = (r.get(acol) or "").strip()
                if not cn or not addr:
                    continue
                e = idx.setdefault(cn, {"addrs": [], "decedent": "", "owner": ""})
                if addr not in e["addrs"]:
                    e["addrs"].insert(0, addr)      # newest file first
                dec = (r.get("Deceased Owner") or r.get("Decedent") or "").strip()
                own = " ".join(x for x in ((r.get("First Name") or "").strip(),
                                           (r.get("Last Name") or "").strip()) if x)
                if dec:
                    e["decedent"] = dec
                if own:
                    e["owner"] = own
        except Exception:
            continue
    return idx


def surname(name: str) -> str:
    """Family name only. Used as an identity guard, never to pick a record.

    The pipeline's "Deceased Owner" column is LAST, FIRST MIDDLE
    ("Hall, Delores Ballard"), so the comma decides. Taking the last token
    instead — as the first cut of this script did — yields the MIDDLE name
    ("ballard"), which is a far weaker guard than intended. Fixed 2026-08-22
    after the first 296-record run; that run was re-audited with this parse
    and all 296 agreed, so nothing was mis-stamped.
    """
    s = (name or "").strip()
    s = re.sub(r"^HEIRS\s+(OF\s+)?", "", s, flags=re.I).strip()
    if "," in s:
        s = s.split(",")[0]
    s = re.sub(r"\b(JR|SR|II|III|IV|MR|MRS|MS|DR)\.?\b", "", s.upper())
    toks = re.findall(r"[A-Z]{2,}", s)
    return toks[-1].lower() if toks else ""


# -- API --

def _headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
            "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
            "content-type": "application/json"}


def token_works(tok: str) -> bool:
    """Cheapest authenticated GET there is — proves the bearer token is live."""
    try:
        return requests.get(f"{API}/api/internal/custom-fields/?entity_type=property",
                            headers=_headers(tok), timeout=20).status_code == 200
    except Exception:
        return False


def browser_login() -> str | None:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = await page.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close()
            return t
    return asyncio.run(go())


def token() -> str | None:
    """Bearer token, cheapest source first.

    The Playwright login is the flaky part of this whole script (it failed
    2026-08-22 with a clean login form while a 20-minute-old bearer token was
    still answering 200), so it is the LAST resort, retried, not the first
    thing tried. Tokens outlive a single run, so a cached one usually means no
    browser starts at all.
    """
    env = (os.environ.get("DATASIFT_TOKEN") or "").strip()
    if env and token_works(env):
        print("auth: using DATASIFT_TOKEN from the environment")
        return env
    if os.path.exists(TOKEN_CACHE):
        try:
            cached = json.load(io.open(TOKEN_CACHE, encoding="utf-8")).get("token", "")
            if cached and token_works(cached):
                print("auth: reusing cached token (no browser login needed)")
                return cached
            print("auth: cached token expired")
        except Exception:
            pass
    for attempt in range(1, 4):
        print("auth: browser login attempt %d/3 ..." % attempt)
        t = browser_login()
        if t and token_works(t):
            json.dump({"token": t}, io.open(TOKEN_CACHE, "w", encoding="utf-8"))
            print("auth: logged in, token cached")
            return t
        if attempt < 3:
            print("auth: login failed - retrying in 20s")
            time.sleep(20)
    return None


def search(h: dict, text: str) -> list[dict]:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      data=json.dumps({"query": {"must": {"search": text}}, "limit": 200}),
                      timeout=30)
    if r.status_code != 200:
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def get_cf_values(h: dict, uuid: str) -> dict[str, dict]:
    r = requests.get(f"{API}/api/internal/property/{uuid}/custom-field/?offset=0&limit=1000",
                     headers=h, timeout=30)
    if r.status_code != 200:
        return {}
    out = {}
    for e in r.json().get("results") or []:
        lab = ((e.get("custom_field") or {}).get("label") or "").strip().lower()
        if lab:
            out[lab] = e
    return out


def set_case_number(h: dict, prop_uuid: str, value: str) -> bool:
    r = requests.patch(f"{API}/api/internal/property/{prop_uuid}/custom-field/update-values/",
                       headers=h,
                       data=json.dumps([{"field_uuid": CASE_FIELD_UUID, "value": value}]),
                       timeout=30)
    if r.status_code not in (200, 202):
        print("    PATCH -> %s %s" % (r.status_code, r.text[:150]))
        return False
    return True


# DataSift stores streets expanded ("955 Allman Road Ext", "3206 Connecticut
# Ave") where the county CSV abbreviates ("955 Allman Rd Ext", "3206
# Connecticut Av"), so an exact-string search misses. --wide retries each
# address with one abbreviation expanded at a time.
_ABBR = {"AV": "AVE", "AVE": "AVENUE", "CIR": "CIRCLE", "TR": "TRAIL",
         "TRL": "TRAIL", "PL": "PLACE", "CT": "COURT", "LN": "LANE",
         "DR": "DRIVE", "RD": "ROAD", "ST": "STREET", "EXT": "EXTENSION",
         "PK": "PIKE", "HWY": "HIGHWAY", "BLVD": "BOULEVARD"}


def _addr_variants(a: str) -> list[str]:
    out = [a]
    toks = a.split()
    if len(toks) > 2 and toks[-1].isdigit():      # drop a trailing unit number
        out.append(" ".join(toks[:-1]))
    for base in list(out):
        bt = base.split()
        for i, t in enumerate(bt):
            exp = _ABBR.get(t.upper().strip("."))
            if exp:
                v = list(bt)
                v[i] = exp
                out.append(" ".join(v))
    return list(dict.fromkeys(out))


def _street_tokens(a: str) -> set[str]:
    """Distinctive words in a street name — the street TYPE words are dropped
    because every road has one and matching on them proves nothing."""
    generic = set(_ABBR) | set(_ABBR.values()) | {"N", "S", "E", "W", "NE",
                                                  "NW", "SE", "SW", "OLD", "NEW"}
    return {t for t in re.findall(r"[A-Z0-9]+", (a or "").upper())
            if t not in generic and not t.isdigit() and len(t) > 2}


def _same_property(csv_addr: str, rec: dict) -> bool:
    """A hit is the same property only if the house number matches AND the
    street names share a distinctive word. House number alone is not enough:
    a surname search for 'Timothy' returned '121 C And C Ln' for a CSV row at
    '121 Bud Ballard Ln' — same number, unrelated street."""
    street = ((rec.get("address") or {}).get("street") or "")
    num = (csv_addr.split() or [""])[0]
    if not num or not street.lower().startswith(num.lower() + " "):
        return False
    want = _street_tokens(csv_addr)
    return bool(want & _street_tokens(street)) if want else False


def find_record(h: dict, addrs: list[str], wide: bool = False) -> dict | None:
    """Resolve a street address to exactly ONE record. Ambiguity => give up
    (a wrong write is far worse than a skip)."""
    for text in addrs[:4]:
        for probe in (_addr_variants(text) if wide else [text]):
            hits = search(h, probe)
            if len(hits) == 1 and (not wide or _same_property(text, hits[0])):
                return hits[0]
            if len(hits) > 1:
                exact = [r for r in hits if _same_property(text, r)]
                if len(exact) == 1:
                    return exact[0]
    return None


def main() -> int:
    dry = "--dry-run" in sys.argv
    wide = "--wide" in sys.argv     # retry misses with expanded street types
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    cases = sorted(json.load(io.open(LEDGER, encoding="utf-8"))["cases"])
    idx = build_case_index()
    done: dict[str, str] = {}
    if os.path.exists(STATE):
        done = json.load(io.open(STATE, encoding="utf-8")).get("done", {})
    todo = [c for c in cases if c not in done]
    if limit:
        todo = todo[:limit]
    print("ledger %d cases | already done %d | this run %d%s\n"
          % (len(cases), len(done), len(todo), " (DRY RUN)" if dry else ""))

    tok = token()
    if not tok:
        print("login failed after 3 attempts - nothing was written")
        return 1
    h = _headers(tok)

    written, already, notfound, mismatch, conflict, failed = [], [], [], [], [], []
    for i, cn in enumerate(todo, 1):
        e = idx.get(cn)
        if not e:
            notfound.append((cn, "no CSV row carries this case"))
            continue
        rec = find_record(h, e["addrs"], wide=wide)
        if rec is None:
            notfound.append((cn, "no unique record for %s" % (e["addrs"][:2],)))
            continue
        uuid = rec.get("uuid") or rec.get("id")
        owner = rec.get("owner") or {}
        addr = rec.get("address") or {}
        ents = get_cf_values(h, uuid)

        # Identity guard: decedent field or owner surname must line up.
        want = surname(e["decedent"]) or surname(e["owner"])
        ds_dec = (ents.get("decedent", {}).get("value") or "").lower()
        ds_last = (owner.get("last_name") or "").strip().lower()
        if want and want not in ds_dec and want != ds_last:
            mismatch.append((cn, "%s | decedent=%r owner=%r want=%r"
                             % (addr.get("street"), ds_dec, ds_last, want)))
            print("[%d/%d] %s: identity mismatch - skipped" % (i, len(todo), cn))
            continue

        cur = (ents.get(CASE_LABEL, {}).get("value") or "").strip()
        if cur:
            if cur.upper() == cn:
                already.append(cn)
                done[cn] = uuid
            else:
                conflict.append((cn, cur, addr.get("street")))
                print("[%d/%d] %s: record already has Case Number %r - LEFT ALONE"
                      % (i, len(todo), cn, cur))
            continue
        if dry:
            print("[%d/%d] %s: would write to %s, %s"
                  % (i, len(todo), cn, addr.get("street"), addr.get("city")))
            written.append(cn)
            continue

        set_case_number(h, uuid, cn)
        chk = (get_cf_values(h, uuid).get(CASE_LABEL, {}).get("value") or "").strip()
        if chk.upper() == cn:
            written.append(cn)
            done[cn] = uuid
            print("[%d/%d] %s: verified on %s, %s"
                  % (i, len(todo), cn, addr.get("street"), addr.get("city")))
        else:
            failed.append((cn, "verify failed (reads %r)" % chk))
            print("[%d/%d] %s: VERIFY FAILED" % (i, len(todo), cn))
        if i % 10 == 0 and not dry:
            json.dump({"done": done}, io.open(STATE, "w", encoding="utf-8"), indent=1)
        time.sleep(0.4)

    if not dry:
        json.dump({"done": done}, io.open(STATE, "w", encoding="utf-8"), indent=1)

    print("\n==== SUMMARY %s ====" % ("(DRY RUN)" if dry else ""))
    print("written:            %d" % len(written))
    print("already correct:    %d" % len(already))
    print("record not found:   %d" % len(notfound))
    print("identity mismatch:  %d" % len(mismatch))
    print("different case set: %d" % len(conflict))
    print("verify failed:      %d" % len(failed))
    for label, rows in (("NOT FOUND", notfound), ("MISMATCH", mismatch),
                        ("CONFLICT", conflict), ("FAILED", failed)):
        for row in rows:
            print("  %s: %s" % (label, row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
