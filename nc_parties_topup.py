"""Midday eCourts Parties top-up — warm the cache while the throttle is idle.

The court's Parties endpoint answers ~6 quick calls then one per ~50s,
per IP (project_parties_api_throttle_heirs_of). The 5 PM nightly needs
far more answers than one evening window supplies, so this job harvests
a SECOND window around noon: it re-asks the court about the current
week's unresolved cases and stores every answer in
output/.nc_parties_cache.json (see src/parties_cache.py). The evening
polish reads that cache first — each hit saves a ~55s throttle slot.

Never touches any CSV. Safe to kill at any moment (each answer is
persisted as it lands). Skips same-day filings (court hasn't indexed
their parties yet) exactly like the nightly does.

Targets, in priority order (capped by NC_TOPUP_MAX_CALLS, default 40):
  1. Latest polished weekly CSV: rows with a blank / "Heirs of" PR
     (nameless leads — worst gap, same rule as backfill_pr_from_parties)
  2. Latest polished weekly CSV: rows with a named PR but blank
     Beneficiaries (never actually asked — the Week 31 lesson)
  3. Latest merged weekly CSV: rows with no Parcel ID (Step 0.64's
     decedent-address fallback re-asks these EVERY night)

Usage:
  python nc_parties_topup.py            # normal run
  python nc_parties_topup.py --dry-run  # list targets, no network
Env knobs:
  NC_TOPUP_MAX_CALLS  (default 40)   cap on court calls this run
  NC_TOPUP_MAX_MINS   (default 45)   wall-clock cap
  NC_PARTIES_MIN_AGE_DAYS (default 1) same-day-filing skip, shared with polish
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from csv import DictReader
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ecourts_case_api import CaseDetailClient  # noqa: E402
from parties_cache import cache_get, cache_put, prune  # noqa: E402

MAX_CALLS = int(os.environ.get("NC_TOPUP_MAX_CALLS", "40") or 40)
MAX_MINS = float(os.environ.get("NC_TOPUP_MAX_MINS", "45") or 45)
MIN_AGE_DAYS = int(os.environ.get("NC_PARTIES_MIN_AGE_DAYS", "1") or 1)
GIVE_UP_AFTER = 8       # consecutive throttled cases -> the court has cut us off
THROTTLE_WAIT = 55      # seconds; matches the observed ~50s window + margin


def _log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def _too_young(row: dict) -> bool:
    if MIN_AGE_DAYS <= 0:
        return False
    s = (row.get("File Date") or "").strip()
    filed = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            filed = datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
            break
        except ValueError:
            continue
    if filed is None:
        return False
    return (datetime.now().date() - filed).days < MIN_AGE_DAYS


def _latest(pattern: str) -> Path | None:
    files = sorted(Path("output").glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(DictReader(f))


def collect_targets() -> list[tuple[str, str, str]]:
    """[(case_no, hex, why)] deduped by hex, priority order preserved."""
    merged = _latest("nc_estates_ftm_*_week*_merged.csv")
    if merged is None:
        _log("no merged weekly CSV in output/ — nothing to do")
        return []
    week = re.search(r"_week(\d+)_", merged.name)
    polished = None
    if week:
        polished = _latest(f"nc_estates_ftm_*_week{week.group(1)}_dm_enriched.csv") \
            or _latest(f"nc_estates_ftm_*_week{week.group(1)}_datasift.csv")
    _log(f"merged:   {merged.name}")
    _log(f"polished: {polished.name if polished else '(none)'}")

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(row: dict, why: str) -> None:
        hx = (row.get("Case ID (hex)") or "").strip()
        if not hx or hx in seen or _too_young(row):
            return
        if cache_get(hx) is not None:
            return  # already warm
        seen.add(hx)
        out.append(((row.get("Case No.") or "?").strip(), hx, why))

    if polished is not None:
        rows = _read(polished)
        for r in rows:
            pr = (r.get("Personal Representative") or "").strip().lower()
            if (not pr) or pr.startswith("heirs of"):
                add(r, "no PR")
        for r in rows:
            if not (r.get("Beneficiaries") or "").strip():
                add(r, "no beneficiaries")
    for r in _read(merged):
        if not (r.get("Parcel ID") or "").strip():
            add(r, "no parcel")
    return out


def main() -> int:
    dry = "--dry-run" in sys.argv
    dropped = prune()
    if dropped:
        _log(f"pruned {dropped} expired cache entries")
    targets = collect_targets()
    _log(f"{len(targets)} case(s) need the court"
         + (f"; doing {MAX_CALLS} this run" if len(targets) > MAX_CALLS else ""))
    targets = targets[:MAX_CALLS]
    if dry:
        for case_no, hx, why in targets:
            _log(f"  would fetch {case_no}  ({why})")
        return 0
    if not targets:
        return 0

    waf_path = Path("ecourts_waf_cookies.json")
    if not waf_path.exists():
        _log("no cached WAF cookie — cannot reach the court; exiting")
        return 0
    waf = json.loads(waf_path.read_text())
    client = CaseDetailClient(waf_token=waf["aws_waf_token"],
                              user_agent=waf.get("user_agent") or "Mozilla/5.0")

    deadline = time.time() + MAX_MINS * 60
    fetched = throttled_giveups = 0
    consec = 0
    for case_no, hx, why in targets:
        if time.time() > deadline:
            _log(f"wall-clock cap ({MAX_MINS:.0f} min) reached — stopping")
            break
        if consec >= GIVE_UP_AFTER:
            _log(f"{GIVE_UP_AFTER} refusals in a row — the court has cut us off; stopping")
            break
        parties = []
        for attempt in range(3):
            parties = client.fetch_parties(hx, retries=0)
            if parties or not client.last_throttled:
                break
            if time.time() + THROTTLE_WAIT > deadline:
                break
            _log(f"  {case_no}: throttled — waiting {THROTTLE_WAIT}s "
                 f"(attempt {attempt + 1}/3)")
            time.sleep(THROTTLE_WAIT)
        if parties:
            cache_put(hx, parties)
            fetched += 1
            consec = 0
            _log(f"  {case_no}: {len(parties)} parties cached  ({why})")
        elif client.last_throttled:
            throttled_giveups += 1
            consec += 1
            _log(f"  {case_no}: gave up (throttled)")
        else:
            consec = 0  # real empty answer — court has no parties yet; not cached
            _log(f"  {case_no}: court returned no parties (not cached, retried tonight)")
        time.sleep(3)

    _log(f"done: {fetched} cached, {throttled_giveups} throttled give-ups, "
         f"{len(targets)} attempted — evening polish reads the cache for free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
