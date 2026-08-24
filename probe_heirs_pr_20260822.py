"""READ-ONLY probe: does the court name a PR for our stuck "Heirs of" rows?

Background: backfill_case_numbers_from_ecourts.py carried an inverted guard
that blocked every "Heirs of <Decedent>" -> real-PR upgrade (fixed 8/22,
see project_parties_api_throttle_heirs_of). 72 rows across weeks 24-34 are
still nameless. This asks the court about each one and reports what it has.

Writes NOTHING to DataSift and mutates no pipeline CSV. It does warm
output/.nc_parties_cache.json, so every answer it lands is a throttle slot
the nightly polish no longer has to spend.

Usage:
  python probe_heirs_pr_20260822.py --dry-run   # list targets, no network
  python probe_heirs_pr_20260822.py             # run it
Env knobs:
  NC_PROBE_MAX_CALLS (default 200)  cap on court calls
  NC_PROBE_MAX_MINS  (default 330)  wall-clock cap
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ecourts_case_api import CaseDetail, CaseDetailClient  # noqa: E402
from parties_cache import cache_get, cache_put, prune  # noqa: E402

MAX_CALLS = int(os.environ.get("NC_PROBE_MAX_CALLS", "200") or 200)
MAX_MINS = float(os.environ.get("NC_PROBE_MAX_MINS", "330") or 330)
GIVE_UP_AFTER = int(os.environ.get("NC_PROBE_GIVE_UP_AFTER", "4") or 4)
THROTTLE_WAIT = 55      # matches the observed ~50s window + margin
WAIT_ATTEMPTS = int(os.environ.get("NC_PROBE_WAIT_ATTEMPTS", "2") or 2)
# Verdicts that are a real answer from the court - never re-asked on a rerun.
# "COURT RETURNED NOTHING" is deliberately NOT here: an empty parties list is
# filing-lag or the throttle lying, and must be retried (parties_cache rule).
SETTLED = {
    "PR FOUND",
    "PR FOUND - but occupied, review before marketing",
    "CONTACT ONLY (not a formal PR)",
    "COURT HAS NO PR",
}

# FIXED paths, deliberately NOT date-stamped. This job runs one throttle
# window per hour and routinely spans midnight; a datetime.now() stamp made
# the 00:44 window write a brand-new file instead of resuming the report
# (harmless that once — the parties cache re-derived the earlier rows for
# free — but it orphans the run and the driver stops watching the old path).
OUT_CSV = Path("output") / "heirs_pr_probe.csv"
LOG_PATH = Path("logs") / "heirs_pr_probe.log"
_LOG_FH = None


def _log(msg: str) -> None:
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    if _LOG_FH:
        _LOG_FH.write(line + "\n")
        _LOG_FH.flush()


def _norm_addr(s: str) -> str:
    """Loose address key - enough to spot 'PR lives at the property'."""
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(STREET|ST|ROAD|RD|DRIVE|DR|LANE|LN|AVENUE|AVE|COURT|CT|"
               r"CIRCLE|CIR|PLACE|PL|BOULEVARD|BLVD|TRAIL|TRL|WAY|HIGHWAY|HWY)\b", " ", s)
    s = re.sub(r"\b(NORTH|SOUTH|EAST|WEST|NE|NW|SE|SW|N|S|E|W)\b", " ", s)
    return " ".join(s.split())


def latest_per_week() -> dict:
    """Newest polished datasift CSV per ISO week."""
    byweek = {}
    for p in Path("output").glob("nc_estates_ftm_*_week*_datasift.csv"):
        m = re.search(r"_week(\d+)_", p.name)
        if not m:
            continue
        w = int(m.group(1))
        if w not in byweek or p.stat().st_mtime > byweek[w].stat().st_mtime:
            byweek[w] = p
    return byweek


def collect_targets() -> list:
    """Heirs-of rows across every week, deduped by hex case id."""
    targets = []
    seen = set()
    for w, path in sorted(latest_per_week().items()):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                pr = (r.get("Personal Representative") or "").strip()
                if not pr.lower().startswith("heirs of"):
                    continue
                hx = (r.get("Case ID (hex)") or "").strip()
                if hx and hx in seen:
                    continue
                if hx:
                    seen.add(hx)
                targets.append({
                    "week": w,
                    "hex": hx,
                    "Case No.": (r.get("Case No.") or "").strip(),
                    "County": (r.get("County") or "").strip(),
                    "Decedent": (r.get("Deceased Owner") or "").strip(),
                    "Current PR": pr,
                    "Property": (r.get("Property Address") or "").strip(),
                    "Property City": (r.get("Property City") or "").strip(),
                    "DM Name": (r.get("DM Name") or "").strip(),
                    "DM Relationship": (r.get("DM Relationship") or "").strip(),
                    "source": path.name,
                })
    return targets


def summarize(t: dict, parties: list) -> dict:
    """Turn a parties list into the report row."""
    detail = CaseDetail(case_id=t["hex"], parties=parties)
    ex = detail.executor
    row = dict(t)
    row.pop("source", None)
    row["Parties"] = len(parties)
    row["Guardianship"] = "YES" if detail.is_guardianship else ""
    if ex is None:
        row["Court PR"] = ""
        row["Court Role"] = ""
        row["PR Mailing"] = ""
        row["Occupied?"] = ""
        row["Verdict"] = "COURT HAS NO PR"
    else:
        name = " ".join(filter(None, [ex.first_name, ex.last_name])).strip() or ex.full_name
        addr = ex.first_address
        mailing = "" if addr.is_blank() else ", ".join(
            filter(None, [" ".join(filter(None, [addr.line1, addr.line2])).strip(),
                          addr.city, addr.state, addr.zip]))
        role = (ex.connection_type or "").strip()
        formal = CaseDetail._normalize_role(role) not in CaseDetail._FALLBACK_CONTACT_TYPES
        occupied = bool(addr.line1) and _norm_addr(addr.line1) == _norm_addr(t["Property"])
        row["Court PR"] = name
        row["Court Role"] = role
        row["PR Mailing"] = mailing
        row["Occupied?"] = "YES - PR lives at the property" if occupied else ""
        if not formal:
            row["Verdict"] = "CONTACT ONLY (not a formal PR)"
        elif occupied:
            row["Verdict"] = "PR FOUND - but occupied, review before marketing"
        else:
            row["Verdict"] = "PR FOUND"
    row["Beneficiaries"] = " | ".join(
        (" ".join(filter(None, [b.first_name, b.last_name])).strip() or b.full_name)
        for b in detail.beneficiaries)
    return row


def main() -> int:
    global _LOG_FH
    dry = "--dry-run" in sys.argv
    LOG_PATH.parent.mkdir(exist_ok=True)
    _LOG_FH = open(LOG_PATH, "a", encoding="utf-8")

    prior = {}
    if OUT_CSV.exists():
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                key = (r.get("hex") or "").strip() or (r.get("Case No.") or "").strip()
                if key:
                    prior[key] = r
        settled = sum(1 for r in prior.values() if (r.get("Verdict") or "") in SETTLED)
        _log(f"resuming: {len(prior)} row(s) in {OUT_CSV.name}, {settled} already settled")

    targets = collect_targets()
    no_hex = [t for t in targets if not t["hex"]]
    live = [t for t in targets if t["hex"]]
    _log(f"Heirs-of rows found: {len(targets)}  (with hex: {len(live)}, "
         f"no hex - cannot ask the court: {len(no_hex)})")
    for t in no_hex:
        _log(f"  NO HEX (skipped): {t['Case No.']} {t['County']} {t['Decedent']}")

    dropped = prune()
    if dropped:
        _log(f"pruned {dropped} expired cache entries")

    done = [t for t in live if (prior.get(t["hex"], {}).get("Verdict") or "") in SETTLED]
    live = [t for t in live if (prior.get(t["hex"], {}).get("Verdict") or "") not in SETTLED]
    if done:
        _log(f"already settled in a prior window (skipped): {len(done)}")
    warm = [t for t in live if cache_get(t["hex"]) is not None]
    cold = [t for t in live if cache_get(t["hex"]) is None]
    _log(f"already cached (free): {len(warm)}   need the court: {len(cold)}")

    if dry:
        for t in cold[:MAX_CALLS]:
            _log(f"  would fetch {t['Case No.']:<16} {t['County']:<12} {t['Decedent']}")
        return 0

    results = []
    for t in warm:
        results.append(summarize(t, cache_get(t["hex"]) or []))

    cold = cold[:MAX_CALLS]
    if cold:
        waf_path = Path("ecourts_waf_cookies.json")
        if not waf_path.exists():
            _log("no cached WAF cookie - cannot reach the court; exiting")
            return 1
        waf = json.loads(waf_path.read_text())
        client = CaseDetailClient(waf_token=waf["aws_waf_token"],
                                  user_agent=waf.get("user_agent") or "Mozilla/5.0")
        deadline = time.time() + MAX_MINS * 60
        fetched = giveups = 0
        consec = 0
        for i, t in enumerate(cold, 1):
            if time.time() > deadline:
                _log(f"wall-clock cap ({MAX_MINS:.0f} min) reached - stopping")
                break
            if consec >= GIVE_UP_AFTER:
                _log(f"{GIVE_UP_AFTER} refusals in a row - the court cut us off; stopping")
                break
            parties = []
            for attempt in range(WAIT_ATTEMPTS):
                parties = client.fetch_parties(t["hex"], retries=0)
                if parties or not client.last_throttled:
                    break
                if time.time() + THROTTLE_WAIT > deadline:
                    break
                _log(f"  [{i}/{len(cold)}] {t['Case No.']}: throttled - waiting "
                     f"{THROTTLE_WAIT}s (attempt {attempt + 1}/{WAIT_ATTEMPTS})")
                time.sleep(THROTTLE_WAIT)
            if parties:
                cache_put(t["hex"], parties)
                fetched += 1
                consec = 0
                row = summarize(t, parties)
                results.append(row)
                _log(f"  [{i}/{len(cold)}] {t['Case No.']}: {row['Verdict']}"
                     + (f" -> {row['Court PR']} ({row['Court Role']})" if row["Court PR"] else ""))
            elif client.last_throttled:
                giveups += 1
                consec += 1
                _log(f"  [{i}/{len(cold)}] {t['Case No.']}: gave up (throttled)")
            else:
                consec = 0
                r = dict(t)
                r.pop("source", None)
                r.update({"Parties": 0, "Verdict": "COURT RETURNED NOTHING"})
                results.append(r)
                _log(f"  [{i}/{len(cold)}] {t['Case No.']}: court returned no parties")
            time.sleep(3)
        _log(f"court calls: {fetched} answered, {giveups} throttled give-ups, "
             f"{len(cold)} attempted")

    cols = ["week", "Case No.", "County", "Decedent", "Verdict", "Court PR",
            "Court Role", "PR Mailing", "Occupied?", "Property", "Property City",
            "Current PR", "DM Name", "DM Relationship", "Beneficiaries",
            "Guardianship", "Parties", "hex"]
    # Merge: this window's answers win, everything settled earlier survives.
    merged = dict(prior)
    for r in results:
        merged[(r.get("hex") or "").strip() or (r.get("Case No.") or "").strip()] = r
    results = list(merged.values())

    def _sort_key(r):
        # week arrives as int on fresh rows and str on rows reloaded from
        # the CSV — normalise or sorted() raises and we lose the report.
        try:
            wk = int(r.get("week") or 0)
        except (TypeError, ValueError):
            wk = 0
        return ((r.get("Verdict") or ""), wk)

    OUT_CSV.parent.mkdir(exist_ok=True)
    tmp = OUT_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(results, key=_sort_key):
            w.writerow(r)
    os.replace(tmp, OUT_CSV)   # atomic — the old report survives any crash above

    tally = {}
    for r in results:
        tally[r.get("Verdict") or "?"] = tally.get(r.get("Verdict") or "?", 0) + 1
    _log("=" * 60)
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        _log(f"  {v:>3}  {k}")
    unanswered = sum(1 for r in results
                     if (r.get("Verdict") or "") not in SETTLED) + len(no_hex)
    if unanswered > 0:
        _log(f"  {unanswered:>3}  STILL OPEN (throttled/no-hex - rerun to finish)")
    _log(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
