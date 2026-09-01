"""Repair SmartSkip phone types mislabeled LANDLINE — found 2026-09-01.

WHAT WENT WRONG
---------------
push_smartskip_group1_20260825.py maps a phone's type as
    "MOBILE" if "mobile" in line_type else "LANDLINE"
so an EMPTY line_type — and every VOIP — lands as LANDLINE. The group 3,
group 4 and 8/27 queue builders read the SmartSkip review CSVs, which carry
no line-type column, so they sent line_type "" for every phone. Net effect
measured against the Trestle score cache: ~489 phones stamped LANDLINE that
are really Mobile (424) or VOIP (60+). The daily tier sweep cannot heal them
because fix_line_types() only touches UNKNOWN.

WHAT THIS SCRIPT DOES
---------------------
For every estate in the five SmartSkip push files, it finds the record (same
finder + owner guard as the push), then re-stamps `type` from the Trestle
score cache on phones that BOTH:
  * carry the "SmartSkip" phone tag (only our pushes set that), AND
  * have a cached Trestle line_type that maps to a DataSift enum.
Phones without a cached type are left alone, never guessed. Cache-only — $0.

GUARDS
------
  * an owner already holding MORE than 15 phones is never PATCHed — the API
    persists only the first 15 entries of the phones array and silently drops
    the rest (measured 2026-08-27, re-confirmed 2026-08-31), so a PATCH there
    would DELETE phones. Those records are listed for UI repair instead;
  * deep-copy + type-field-only edits — numbers, tags, labels untouched;
  * every write verified by re-GET (the search index lies; property GET
    does not);
  * rerun-safe by nature: a corrected phone no longer differs from the cache.

Run:
    python fix_smartskip_line_types_20260901.py              # dry run, writes nothing
    python fix_smartskip_line_types_20260901.py --apply      # repair + verify
    python fix_smartskip_line_types_20260901.py --limit 5 --apply

Log: logs/fix_smartskip_line_types_20260901.log
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import sys
import time as _time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402

# Reuse the push script's proven pieces: auth headers, the record finder with
# its owner guard, and the street normalizers it depends on.
from push_smartskip_group1_20260825 import (  # noqa: E402
    API, digits, find_record, headers, token,
)
from trestle_api_backfill import ds_line_type  # noqa: E402

APPLY = "--apply" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

SOURCES = [
    REPO / "output" / "smartskip_group1_court_pr_phones.json",
    REPO / "output" / "smartskip_group1b_court_pr_phones.json",
    REPO / "output" / "smartskip_group3_court_pr_phones.json",
    REPO / "output" / "smartskip_group4_backup_heir_phones.json",
    REPO / "output" / "smartskip_queue_heir_phones_20260827.json",
]
CACHE = REPO / "output" / ".trestle_score_cache.json"
LOG = REPO / "logs" / "fix_smartskip_line_types_20260901.log"

# The API owner-PATCH persists only the FIRST 15 phones and truncates the rest
# silently at HTTP 200 — an owner past 15 must not be written through this path.
PHONE_CAP = 15


def tag_titles(tags) -> set[str]:
    return {t.get("title") if isinstance(t, dict) else str(t)
            for t in (tags or [])}


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = LOG.open("a", encoding="utf-8")

    def out(text: str) -> None:
        print(text)
        log.write(text + "\n")
        log.flush()

    cache = json.loads(CACHE.read_text(encoding="utf-8"))

    # One entry per estate. The same case can appear in more than one push
    # file (a queue estate later re-pushed); identity is all we need here, so
    # first occurrence wins.
    entries, seen_cases = [], set()
    for src in SOURCES:
        if not src.exists():
            out(f"missing source (skipped): {src.name}")
            continue
        for e in json.loads(src.read_text(encoding="utf-8")):
            if e["case_no"] in seen_cases:
                continue
            seen_cases.add(e["case_no"])
            entries.append(e)
    if LIMIT:
        entries = entries[:LIMIT]

    out(f"\n===== run at {_dt.datetime.now()} apply={APPLY} — "
        f"{len(entries)} estate(s) from {len(SOURCES)} push file(s)")
    h = headers(token())

    fixed = would_fix = records_touched = skipped = capped = 0
    by_type: dict[str, int] = {}
    failures: list[str] = []
    cap_list: list[str] = []

    for e in entries:
        out(f"\n=== {e['case_no']} {e['county']} | {e['decedent']}")
        rec = find_record(h, e, out)
        if not rec:
            skipped += 1
            continue
        uuid = rec.get("uuid")
        r = requests.get(f"{API}/api/internal/property/{uuid}/",
                         headers=h, timeout=30)
        if r.status_code != 200:
            out(f"  GET {uuid} -> {r.status_code} — SKIP")
            skipped += 1
            continue
        d = r.json()

        body, changes, wanted = {}, 0, {}
        groups = [("owner", [d["owner"]] if d.get("owner") else []),
                  ("secondary_owners", d.get("secondary_owners") or [])]
        for key, owners_src in groups:
            owners = copy.deepcopy(owners_src)
            touched = False
            for ow in owners:
                phones = ow.get("phones") or []
                todo = []
                for ph in phones:
                    if "SmartSkip" not in tag_titles(ph.get("tags")):
                        continue
                    num = digits(ph.get("number") or "")
                    want = ds_line_type((cache.get(num) or {}).get("line_type"))
                    cur = str(ph.get("type") or "").upper()
                    if not want or cur == want:
                        continue
                    todo.append((ph, num, cur, want))
                if not todo:
                    continue
                if len(phones) > PHONE_CAP:
                    # PATCHing this owner would silently delete phones 16+.
                    capped += len(todo)
                    cap_list.append(f"{e['case_no']} ({len(phones)} phones, "
                                    f"{len(todo)} to fix)")
                    out(f"  owner holds {len(phones)} phones (> {PHONE_CAP}) — "
                        f"NOT PATCHed, {len(todo)} phone(s) need the UI: "
                        + ", ".join(f"{n} {c or 'UNKNOWN'}->{w}"
                                    for _, n, c, w in todo))
                    continue
                for ph, num, cur, want in todo:
                    out(f"  {num}: {cur or 'UNKNOWN'} -> {want}")
                    ph["type"] = want
                    wanted[num] = want
                    by_type[want] = by_type.get(want, 0) + 1
                    changes += 1
                    touched = True
            if touched:
                body[key] = owners[0] if key == "owner" else owners

        if not changes:
            out("  nothing to fix on this record")
            continue
        would_fix += changes
        if not APPLY:
            continue

        pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                            data=json.dumps(body), timeout=30)
        if pr.status_code not in (200, 202):
            out(f"  PATCH -> {pr.status_code} {pr.text[:120]} — FAILED")
            failures.append(f"{e['case_no']}: HTTP {pr.status_code}")
            continue
        # Verify by re-GET — HTTP 200 with nothing saved is a known DataSift
        # failure mode; only a read-back proves the write.
        vr = requests.get(f"{API}/api/internal/property/{uuid}/",
                          headers=h, timeout=30)
        if vr.status_code != 200:
            failures.append(f"{e['case_no']}: verify GET {vr.status_code}")
            continue
        live = vr.json()
        got = {}
        for ow in ([live["owner"]] if live.get("owner") else []) \
                + (live.get("secondary_owners") or []):
            for ph in (ow.get("phones") or []):
                got[digits(ph.get("number") or "")] = \
                    str(ph.get("type") or "").upper()
        stale = {n: w for n, w in wanted.items() if got.get(n) != w}
        if stale:
            out(f"  VERIFY FAILED — did not stick: {stale}")
            failures.append(f"{e['case_no']}: {len(stale)} phone(s) reverted")
            continue
        out(f"  verified: {changes} phone type(s) set")
        fixed += changes
        records_touched += 1
        _time.sleep(0.5)

    verb = "fixed" if APPLY else "would fix"
    out(f"\n===== SUMMARY: {verb} {would_fix if not APPLY else fixed} phone(s)"
        + (f" on {records_touched} record(s)" if APPLY else "")
        + f" — " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items()))
        + f" | estates skipped (no record match): {skipped}"
        + f" | phones needing UI (owner > {PHONE_CAP} phones): {capped}")
    if cap_list:
        out("over-cap records for UI repair: " + "; ".join(cap_list))
    if failures:
        out("FAILURES: " + "; ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
