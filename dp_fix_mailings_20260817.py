"""One-shot: repair the last two pre-8/14-fix vacant-lot mailings in DataSift.

2026-08-17 DP runs (Oren approved; packs in output/reports/):

  26E002931-590 Thompson (uuid from Oren's open record page):
      mailing 'Mt Holly-Huntersville Rd' -> 122 Gold Bridge Xing, Canton GA
      30114. PR "Chase Thompson" = WILLIAM Chase Thompson (b.7/2001), twin
      of Chandler; both + mother Heather Roe Thompson at that address.
      NOTE: the record's existing 5 phones / 5 emails are a lot-anchored
      wrong-person trace - prune by hand; real household line 770-474-2388.

  26E001011-350 Lineberger ('0 Ike Lynch Rd' Dallas NC, Week 31):
      mailing -> 436 Ike Lynch Rd, Dallas NC 28034 and contact -> sole
      remainderman Larry Dean Lineberger (nephew; Gaston CAMA cards list
      REMAINDERMAN: LINEBERGER LARRY DEAN on all 3 parcels; no probate
      needed - life estate). Phone 704-922-7693 (Trestle 30).

Same guarded recipe as fix_mailings_20260814.py: API-only, owner object
round-tripped in full, never blank over existing, verify by re-GET.
Ricardo 26E001058-350 is NOT here - its lot belongs to a stranger
(decedent's brother); record is a delete candidate, Oren's call.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

API = "https://apiv2.reisift.io"

# Tee every print to a log file so Claude can read the outcome directly
# (Oren can't easily copy terminal output).
_LOG = open(REPO / "logs" / "dp_fix_mailings_20260817.log", "a", encoding="utf-8")
_stdout_write = sys.stdout.write


def _tee(text):
    _stdout_write(text)
    _LOG.write(text)
    _LOG.flush()


sys.stdout.write = _tee
_stderr_write = sys.stderr.write


def _tee_err(text):
    _stderr_write(text)
    _LOG.write(text)
    _LOG.flush()


sys.stderr.write = _tee_err  # tracebacks land in the log too
import datetime as _dt  # noqa: E402
print(f"\n===== run at {_dt.datetime.now()} =====")

# (case, uuid or None, search street, owner-last must contain, new mailing,
#  new first/last or None)
FIXES = [
    ("26E002931-590", "20fc7378-4590-4b59-9e6b-ea7e8442cdbe", None, "thompson",
     {"street": "122 Gold Bridge Xing", "city": "Canton", "state": "GA",
      "postal_code": "30114"}, None),
    ("26E001011-350", None, "0 Ike Lynch Rd", "lineberger",
     {"street": "436 Ike Lynch Rd", "city": "Dallas", "state": "NC",
      "postal_code": "28034"}, ("Larry Dean", "Lineberger")),
]


def token() -> str | None:
    # Fast path: token pasted from Oren's own logged-in Chrome session
    # (F12 console on app.reisift.io -> localStorage.getItem('rs_token')).
    # Headless Playwright login bounced to a fresh login form on 8/17
    # (same flaky pattern as 2026-07-31), so browser token beats it.
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t:
        print("using DS_TOKEN from environment (browser session token)")
        return t
    # Next: harvest the token from Chrome's Local Storage on disk (Oren is
    # logged into app.reisift.io in Chrome; no DevTools needed).
    try:
        from get_ds_token import get_token
        t = get_token()
        if t:
            return t
        print("no working token in Chrome storage — falling back to Playwright login")
    except Exception as e:
        print(f"Chrome token harvest failed ({e}) — falling back to Playwright login")
    import logging
    logging.basicConfig(level=logging.INFO)  # show NET: POST lines on failure
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            t = (await page.evaluate("() => localStorage.getItem('rs_token')")
                 if ok else None)
            await b.close()
            return t
    return asyncio.run(go())


def find_uuid(h: dict, street: str, owner_frag: str) -> str | None:
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"query": {"must": {"search": street}}}, timeout=30)
    if r.status_code != 200:
        print(f"  search {street!r} -> HTTP {r.status_code}")
        return None
    hits = [rec for rec in r.json().get("results", [])
            if ((rec.get("address") or {}).get("street") or "").strip().lower()
            == street.strip().lower()
            and owner_frag in ((rec.get("owner") or {}).get("last_name") or "").lower()]
    if len(hits) != 1:
        print(f"  search {street!r} owner *{owner_frag}*: {len(hits)} matches — SKIP")
        return None
    return hits[0].get("uuid")


def fix_one(h: dict, case: str, uuid: str | None, street: str | None,
            owner_frag: str, mail: dict, rename) -> bool:
    print(f"\n=== {case} -> mail {mail['street']}")
    if not uuid:
        uuid = find_uuid(h, street, owner_frag)
        if not uuid:
            return False
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        print(f"  GET -> {r.status_code} — SKIP")
        return False
    d = r.json()
    owner = d.get("owner") or {}
    oaddr = owner.get("address") or {}
    print(f"  live: prop={((d.get('address') or {}).get('street'))!r} "
          f"owner={owner.get('first_name')} {owner.get('last_name')} "
          f"mail={oaddr.get('street')!r} {oaddr.get('city')!r}")
    if owner_frag not in (owner.get("last_name") or "").lower():
        print("  owner mismatch — SKIP")
        return False
    cur_mail = (oaddr.get("street") or "").strip()
    if cur_mail and cur_mail[0].isdigit() and not cur_mail.startswith("0 "):
        print(f"  mailing {cur_mail!r} already a real numbered address — SKIP")
        return False

    new_owner = copy.deepcopy(owner)
    new_owner.setdefault("address", {})
    new_owner["address"].update(mail)
    if rename and rename[0] and rename[1]:
        new_owner["first_name"], new_owner["last_name"] = rename
    pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                        data=json.dumps({"owner": new_owner}), timeout=30)
    print(f"  PATCH -> {pr.status_code} {pr.text[:150]}")
    if pr.status_code not in (200, 202):
        return False
    chk = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    cd = chk.json() if chk.status_code == 200 else {}
    co = cd.get("owner") or {}
    ca = co.get("address") or {}
    ok = (ca.get("street") or "").strip().lower() == mail["street"].lower()
    print(f"  verify: owner={co.get('first_name')} {co.get('last_name')} "
          f"mail={ca.get('street')!r} {ca.get('city')!r} {ca.get('postal_code')!r}")
    print(f"  RESULT: {'OK' if ok else 'MISMATCH — check by hand'}")
    return ok


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}
    done = sum(1 for spec in FIXES if fix_one(h, *spec))
    print(f"\n{done}/{len(FIXES)} records fixed.")
    return 0 if done == len(FIXES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
