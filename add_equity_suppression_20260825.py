"""Suppress Low Equity + Negative Equity from the 12 NSM marketing presets.

Why (2026-08-25): Ty's Day 2 universal suppression stack, item 3 -- "Low and
negative equity lists. The sub-20-percent equity band loses money on average.
This now includes FTM records."  Live demo at [01:04:34]: "you'll see I'm
excluding low equity and negative equity. We'd never want that to be in here."

Implemented as a LIST exclusion, not an equity-percent filter, and that choice
is load-bearing. Ty [00:26:33]: "if you put just a flat equity filter without
unknowns, you're... probably missing out on, like, half of transactions."  A
record only lands on DataSift's "Low Equity"/"Negative Equity" list when the
equity is KNOWN and low, so excluding the lists keeps every unknown-equity
record in the flows for free. A numeric equity_percent range would not.

    Low Equity        755e2d53-...   5,404 records
    Negative Equity   9bf29511-...   1,951 records   (5,413 unique across both)

Merged into each preset's filters.must.must_not.any_lists, alongside whatever
exclusions are already there (Sold, Do Not Market, Return Mail...).

Measured before writing this: only 5 records leak today, because the NSM lane is
gated to (Courthouse Data OR Priority 1) AND (Probate OR PROBATE OR Free & Clear)
-- and Free & Clear is 100% equity by definition. This rule is forward insurance:
0 of the 552 Priority 1 records are low-equity now, but the 5,413 that are sit in
bulk SiftMap data, which is exactly what enters the lane when the Priority 1 gate
opens for the vacant stack.

    python add_equity_suppression_20260825.py            # dry run, writes nothing
    python add_equity_suppression_20260825.py --apply    # patch + verify by re-GET

Originals are backed up to output/preset_backup_equity_20260825.json before any
PATCH. Every PATCH is verified by re-reading the preset (DataSift's search index
is stale after writes -- never trust the write response).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
NSM_FOLDER = "921333f1-0d77-4398-a7ed-4d4cea8cabe7"   # the "00."-"11." lane
LOW_EQUITY = "755e2d53-2c75-43c8-88cf-eb2f38d103fd"   # list "Low Equity"
NEG_EQUITY = "9bf29511-0645-4b1d-8346-239edc619cda"   # list "Negative Equity"
EQUITY_LISTS = (LOW_EQUITY, NEG_EQUITY)
BACKUP = REPO / "output" / "preset_backup_equity_20260825.json"
NSM_NAME = re.compile(r"^\d{2}\.")


def headers() -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
            "user-agent": "Mozilla/5.0", "authorization": f"Bearer {token()}",
            "content-type": "application/json"}


# Keys the UI translates before sending (relative date tokens, "all") that the
# raw API rejects. Dropped only to COUNT -- never touched when patching.
_UNCOUNTABLE = ("property_type", "last_direct_mailed", "last_updated_date")


def count(h: dict, query: dict) -> tuple[int | str, bool]:
    """Records matching a filter body -> (count, approximate?)."""
    def ask(q):
        return requests.post(f"{API}/api/internal/property/",
                             headers={**h, "x-http-method-override": "GET"},
                             json={"limit": 1, "offset": 0, "query": q}, timeout=90)

    r = ask(query)
    if r.status_code == 200:
        return r.json().get("count"), False
    trimmed = copy.deepcopy(query)
    must = trimmed.get("must") or {}
    if any(k in must for k in _UNCOUNTABLE):
        for k in _UNCOUNTABLE:
            must.pop(k, None)
        r = ask(trimmed)
        if r.status_code == 200:
            return r.json().get("count"), True
    return f"HTTP {r.status_code}", False


def with_equity_excluded(filters: dict) -> dict:
    """Return a copy of a preset's filters with the equity lists excluded."""
    out = copy.deepcopy(filters)
    must = out.setdefault("must", {})
    mn = must.setdefault("must_not", {})
    lists = list(mn.get("any_lists") or [])
    for uid in EQUITY_LISTS:
        if uid not in lists:
            lists.append(uid)
    mn["any_lists"] = lists
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually PATCH the presets (default: dry run)")
    args = ap.parse_args()

    h = headers()
    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h,
                     params={"limit": 300}, timeout=60)
    r.raise_for_status()
    presets = r.json().get("results") or r.json().get("data") or []
    targets = [p for p in presets
               if p.get("folder") == NSM_FOLDER
               and NSM_NAME.match((p.get("title") or ""))]
    targets.sort(key=lambda p: p.get("title") or "")
    print(f"{len(targets)} marketing presets in the NSM folder\n")

    originals, plan = {}, []
    for p in targets:
        name = p.get("title")
        uid = p.get("uuid") or p.get("id")
        det = requests.get(f"{API}/api/internal/filter-preset/{uid}/",
                           headers=h, timeout=30).json()
        det = det.get("data") or det
        originals[name] = det
        before_f = det.get("filters") or {}
        after_f = with_equity_excluded(before_f)
        before_c, approx_b = count(h, {"must": (before_f.get("must") or {})})
        after_c, approx_a = count(h, {"must": (after_f.get("must") or {})})
        drop = (before_c - after_c) if isinstance(before_c, int) and isinstance(after_c, int) else "?"
        note = "  (approx -- preset holds UI-only tokens)" if (approx_b or approx_a) else ""
        plan.append((name, uid, det, after_f, before_c, after_c, drop))
        print(f"  {name:30s} {str(before_c):>7s} -> {str(after_c):>7s}   removes {drop}{note}")

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(originals, indent=1), encoding="utf-8")
    print(f"\noriginals backed up -> {BACKUP}")

    if not args.apply:
        print("\nDRY RUN -- nothing changed. Re-run with --apply to patch.")
        return 0

    print("\napplying...")
    ok = fail = 0
    for name, uid, det, after_f, _b, _a, _d in plan:
        body = {"title": det.get("title"), "filters": after_f,
                "folder": det.get("folder"), "type": det.get("type"),
                "quick_filter": det.get("quick_filter")}
        pr = requests.patch(f"{API}/api/internal/filter-preset/{uid}/",
                            headers=h, json=body, timeout=30)
        if pr.status_code not in (200, 202):
            print(f"  FAIL {name}: HTTP {pr.status_code} {pr.text[:160]}")
            fail += 1
            continue
        # verify by re-reading -- never trust the write response
        vd = requests.get(f"{API}/api/internal/filter-preset/{uid}/",
                          headers=h, timeout=30).json()
        vd = vd.get("data") or vd
        mn = ((vd.get("filters") or {}).get("must") or {}).get("must_not") or {}
        saved = mn.get("any_lists") or []
        missing = [u for u in EQUITY_LISTS if u not in saved]
        if not missing:
            print(f"  ok   {name}  (verified on reload)")
            ok += 1
        else:
            print(f"  FAIL {name}: saved but rule missing on reload ({len(missing)} list(s))")
            fail += 1
    print(f"\n{ok} patched and verified, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
