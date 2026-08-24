"""Fetch the court's party list for every DP'd case we could not verify.

Feeds audit_wrong_person_20260822.py. That audit can only flag a wrong-person
match when the COURT names the person and gives an address, and on 2026-08-22
only 14 of 99 case-numbered DP'd records had that — the rest never had their
Beneficiaries fetched (the endpoint is IP-throttled to ~6 quick calls then one
per ~50s, so the nightly only ever gets through a slice).

This is the same discipline as nc_parties_topup.py — 55s waits, give up after 8
consecutive refusals, persist every answer the moment it lands so a kill costs
nothing. Two differences: it targets the DP'd population instead of the current
week, and it writes its own durable store as well as the shared cache, because
the shared cache expires in 18h and this audit runs on its own schedule.

Safe to kill and re-run: already-stored cases are skipped.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\backfill_court_parties_20260822.py --dry-run
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\backfill_court_parties_20260822.py

Env: NC_DPFETCH_MAX_CALLS (default 200), NC_DPFETCH_MAX_MINS (default 240)
Output: output/court_parties_dp_20260822.json  (case no -> parties)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from ecourts_case_api import CaseDetailClient  # noqa: E402
from parties_cache import cache_get, cache_put  # noqa: E402

MAX_CALLS = int(os.environ.get("NC_DPFETCH_MAX_CALLS", "200") or 200)
MAX_MINS = float(os.environ.get("NC_DPFETCH_MAX_MINS", "240") or 240)
GIVE_UP_AFTER = 8
THROTTLE_WAIT = 55

STORE = REPO / "output" / "court_parties_dp_20260822.json"
SRC = REPO / "output" / "dm_mailing_gap_20260822.csv"


def _log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def hex_map() -> dict[str, str]:
    """Case No. -> Odyssey case id (hex), latest FTM CSV wins."""
    m: dict[str, str] = {}
    for f in sorted(glob.glob(str(REPO / "output" / "nc_estates_ftm_*.csv")),
                    key=os.path.getmtime):
        try:
            fh = open(f, encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            r = csv.DictReader(fh)
            fl = r.fieldnames or []
            ck = next((c for c in fl if c.strip().lower().startswith("case no")), None)
            hk = next((c for c in fl if "hex" in c.lower()), None)
            if not (ck and hk):
                continue
            for row in r:
                c, h = (row.get(ck) or "").strip(), (row.get(hk) or "").strip()
                if c and h:
                    m[c] = h
    return m


def load_store() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    dry = "--dry-run" in sys.argv
    store = load_store()
    hexes = hex_map()
    _log(f"case->hex map: {len(hexes)};  already stored: {len(store)}")

    from audit_wrong_person_20260822 import court_people
    have = court_people()

    targets: list[tuple[str, str]] = []
    no_hex = 0
    for r in csv.DictReader(SRC.open(encoding="utf-8-sig")):
        case = r["Case No."].strip()
        if not case or not r["UUID"].strip() or case in store:
            continue
        if any(p["src"] == "Beneficiaries" for p in have.get(case, [])):
            continue          # court addresses already in the workbook
        hx = hexes.get(case)
        if not hx:
            no_hex += 1
            continue
        targets.append((case, hx))

    _log(f"{len(targets)} case(s) to ask the court; {no_hex} skipped (no Odyssey id "
         f"in any FTM CSV — older weeks / NSM10 rows)")
    targets = targets[:MAX_CALLS]
    if dry:
        for case, hx in targets[:20]:
            _log(f"  would fetch {case}")
        if len(targets) > 20:
            _log(f"  ... and {len(targets) - 20} more")
        return 0
    if not targets:
        return 0

    waf_path = REPO / "ecourts_waf_cookies.json"
    if not waf_path.exists():
        _log("no cached WAF cookie — cannot reach the court; exiting")
        return 1
    waf = json.loads(waf_path.read_text())
    client = CaseDetailClient(waf_token=waf["aws_waf_token"],
                              user_agent=waf.get("user_agent") or "Mozilla/5.0")

    deadline = time.time() + MAX_MINS * 60
    fetched = empty = gaveup = consec = 0
    for case, hx in targets:
        if time.time() > deadline:
            _log(f"wall-clock cap ({MAX_MINS:.0f} min) reached — stopping")
            break
        if consec >= GIVE_UP_AFTER:
            _log(f"{GIVE_UP_AFTER} refusals in a row — the court has cut us off; stopping")
            break

        parties = cache_get(hx) or []
        if parties:
            _log(f"  {case}: {len(parties)} parties from the warm cache")
        else:
            for attempt in range(3):
                parties = client.fetch_parties(hx, retries=0)
                if parties or not client.last_throttled:
                    break
                if time.time() + THROTTLE_WAIT > deadline:
                    break
                _log(f"  {case}: throttled — waiting {THROTTLE_WAIT}s "
                     f"(attempt {attempt + 1}/3)")
                time.sleep(THROTTLE_WAIT)

        if parties:
            cache_put(hx, parties)
            store[case] = [asdict(p) for p in parties]
            STORE.write_text(json.dumps(store, indent=1), encoding="utf-8")
            named = sum(1 for p in parties if p.addresses)
            fetched += 1
            consec = 0
            _log(f"  {case}: {len(parties)} parties ({named} with an address) stored")
        elif client.last_throttled:
            gaveup += 1
            consec += 1
            _log(f"  {case}: gave up (throttled)")
        else:
            empty += 1
            consec = 0
            _log(f"  {case}: court returned no parties")
        time.sleep(3)

    _log(f"done: {fetched} stored, {empty} empty, {gaveup} throttled give-ups, "
         f"of {len(targets)} attempted -> {STORE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
