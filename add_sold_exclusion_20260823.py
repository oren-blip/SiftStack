"""Add a hard "never market a sold property" rule to the 12 NSM marketing presets.

Why (2026-08-23): Oren asked for Ty's SiftMap "recently sold auto-add" (Day 2,
~1:20:00). That toggle is gated behind the SiftMap Pro add-on ($297/mo, not
subscribed) — the toggle renders `react-toggle--disabled` in the Add-Records
modal. But the suppression Ty gets from it can be had for free and with LESS
machinery: instead of tag -> sequence -> status, the preset itself excludes
anything DataSift shows as sold.

Measured before writing this: 42 properties with a sale date since 2023-01-01
were sitting inside the live marketing presets (12 of them in "02. Ready to
Call"), because NOT ONE of the 25 presets mentions Sold in any form.

The rule added to each preset's filters.must.must_not:
    last_sold : ["2023-01-01", null]      <- open-ended on purpose; a fixed end
                                             date would silently rot
    any_tags  : [... , <"Sold" tag uuid>] <- belt and braces, merged with any
                                             exclusions already there

Open-ended range verified against the API: ["2023-01-01", null] == the explicit
range, and relative tokens ("44-months"/"today") are REJECTED for this field.

    python add_sold_exclusion_20260823.py            # dry run, writes nothing
    python add_sold_exclusion_20260823.py --apply    # patch + verify by re-GET

Originals are backed up to output/preset_backup_20260823.json before any PATCH.
Every PATCH is verified by re-reading the preset (DataSift's search index is
stale after writes — never trust the write response).
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
SOLD_TAG = "51b4206b-8f00-44a0-a2f7-1c40942b92b7"     # tag "Sold"
SOLD_SINCE = "2023-01-01"                             # Ty's cutoff, Oren's call
BACKUP = REPO / "output" / "preset_backup_20260823.json"
NSM_NAME = re.compile(r"^\d{2}\.")


def headers() -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
            "user-agent": "Mozilla/5.0", "authorization": f"Bearer {token()}",
            "content-type": "application/json"}


# Keys the UI translates before sending (relative date tokens, "all") that the
# raw API rejects. Dropped only to COUNT — never touched when patching.
_UNCOUNTABLE = ("property_type", "last_direct_mailed", "last_updated_date")


def count(h: dict, query: dict) -> tuple[int | str, bool]:
    """Records matching a filter body -> (count, approximate?).

    Some stored presets hold UI-side tokens ("72-months", property_type "all")
    that the raw API refuses. For those we drop the offending key and flag the
    count as approximate; the delta from the sold rule is still meaningful.
    """
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


def with_sold_excluded(filters: dict) -> dict:
    """Return a copy of a preset's filters with the sold rule merged in."""
    out = copy.deepcopy(filters)
    must = out.setdefault("must", {})
    mn = must.setdefault("must_not", {})
    mn["last_sold"] = [SOLD_SINCE, None]
    tags = list(mn.get("any_tags") or [])
    if SOLD_TAG not in tags:
        tags.append(SOLD_TAG)
    mn["any_tags"] = tags
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
        after_f = with_sold_excluded(before_f)
        before_c, approx_b = count(h, {"must": (before_f.get("must") or {})})
        after_c, approx_a = count(h, {"must": (after_f.get("must") or {})})
        drop = (before_c - after_c) if isinstance(before_c, int) and isinstance(after_c, int) else "?"
        note = "  (approx — preset holds UI-only tokens)" if (approx_b or approx_a) else ""
        plan.append((name, uid, det, after_f, before_c, after_c, drop))
        print(f"  {name:30s} {str(before_c):>7s} -> {str(after_c):>7s}   removes {drop}{note}")

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(originals, indent=1), encoding="utf-8")
    print(f"\noriginals backed up -> {BACKUP}")

    if not args.apply:
        print("\nDRY RUN — nothing changed. Re-run with --apply to patch.")
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
        # verify by re-reading — never trust the write response
        vd = requests.get(f"{API}/api/internal/filter-preset/{uid}/",
                          headers=h, timeout=30).json()
        vd = vd.get("data") or vd
        mn = ((vd.get("filters") or {}).get("must") or {}).get("must_not") or {}
        has_date = mn.get("last_sold") == [SOLD_SINCE, None]
        has_tag = SOLD_TAG in (mn.get("any_tags") or [])
        if has_date and has_tag:
            print(f"  ok   {name}  (verified on reload)")
            ok += 1
        else:
            print(f"  FAIL {name}: saved but rule missing on reload "
                  f"(date={has_date} tag={has_tag})")
            fail += 1
    print(f"\n{ok} patched and verified, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
