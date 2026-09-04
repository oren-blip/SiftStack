"""Find records with GOOD PHONES that NO NSM preset can see.

Oren, 2026-09-04, on Ariel Lucci (6 phones, 5 Dial First, invisible):
"this is the type of record I worry about. I want to find any like these and
pull them back to the start of the NSM flow."

Method -- set difference, not guesswork:
  1. read the 10 live NSM filter presets from /api/internal/filter-preset/
  2. run each preset's OWN filter body against the record API and collect uuids
  3. build the universe: Courthouse Data records that have at least one phone
  4. orphans = universe minus everything any preset can see
  5. re-read each orphan and say WHY it is invisible, and whether it is worth
     rescuing (a Dial First/Second number on board)

Why a record goes dark, from the real "02. Ready to Call" body:
    must:      phone>=1, tag in (Courthouse Data, Priority 1),
               list in (Probate, PROBATE, Free & Clear),
               predictivecall_attempts == 0
    must_not:  tags (Sold, Dead Area, Not Buy Box),
               lists (Low Equity, Negative Equity),
               last_sold >= 2023-01-01
So a record dies if it is tagged Sold / Dead Area / Not Buy Box, sits in Low or
Negative Equity, has ALREADY been called (attempts > 0 drops it out of Ready to
Call), or -- Ariel Lucci's case -- belongs to NO list at all.

READ-ONLY. Writes a CSV, changes nothing.

    python find_nsm_orphans_20260904.py
    python find_nsm_orphans_20260904.py --all-data   # not just Courthouse Data
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from audit_rename_gap_20260822 import API, token  # noqa: E402

OUT = REPO / "output" / "nsm_orphans_20260904.csv"
GOOD_TIERS = ("Dial First", "Dial Second")


def hdr(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


# Keys the UI resolves before sending (relative-date tokens, "all") that the raw
# API rejects with HTTP 400. Same list as add_equity_suppression_20260825.
_UNCOUNTABLE = ("property_type", "last_direct_mailed", "last_updated_date")


def _retry(fn, what: str, tries: int = 4):
    """This API drops long connections (ConnectionReset 10054) — see
    [[project_text_touch_step]]. Retry rather than lose a 2,000-record pass."""
    import time
    for n in range(1, tries + 1):
        try:
            return fn()
        except requests.exceptions.RequestException as e:
            if n == tries:
                print(f"    ({what}: giving up after {tries} tries — {type(e).__name__})")
                return None
            time.sleep(2 * n)
    return None


def search_all(h: dict, query: dict, cap: int = 40000) -> tuple[list[dict], bool]:
    """Every record matching a filter body (paginated).

    Returns (rows, approximated). A preset whose body carries an _UNCOUNTABLE
    key 400s outright; rather than score it as "sees 0" -- which would count all
    its records as invisible and massively overstate the orphan list -- retry
    with those keys dropped and flag the result as approximate.
    """
    def ask(q, offset, page):
        return _retry(lambda: requests.post(
            f"{API}/api/internal/property/",
            headers={**h, "x-http-method-override": "GET"},
            data=json.dumps({"limit": page, "offset": offset, "query": q}),
            timeout=120), f"search offset {offset}")

    approximated = False
    probe = ask(query, 0, 1)
    if probe is not None and probe.status_code == 400:
        trimmed = copy.deepcopy(query)
        must = trimmed.get("must") or {}
        dropped = [k for k in _UNCOUNTABLE if k in must]
        for k in dropped:
            must.pop(k, None)
        if dropped:
            probe = ask(trimmed, 0, 1)
            if probe is not None and probe.status_code == 200:
                query, approximated = trimmed, True
                print(f"    (dropped {', '.join(dropped)} to make it countable)")

    out, offset, page = [], 0, 500
    while offset < cap:
        r = ask(query, offset, page)
        if r is None or r.status_code != 200:
            code = r.status_code if r is not None else "conn-fail"
            print(f"    (HTTP {code} at offset {offset} — stopping)")
            break
        d = r.json()
        rows = d.get("results") or d.get("data") or []
        out.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return out, approximated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-data", action="store_true",
                    help="whole account, not just Courthouse Data")
    args = ap.parse_args()

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = hdr(tok)

    # -- name maps -------------------------------------------------------
    names: dict[str, str] = {}
    for ep in ("tag", "list"):
        r = requests.get(f"{API}/api/internal/{ep}/?limit=500", headers=h, timeout=60)
        if r.status_code == 200:
            d = r.json()
            for i in (d.get("results") or d.get("data") or []):
                names[str(i.get("uuid"))] = i.get("title") or i.get("name") or "?"
    tag_id = {v: k for k, v in names.items()}

    # -- presets ---------------------------------------------------------
    r = requests.get(f"{API}/api/internal/filter-preset/", headers=h, timeout=60).json()
    presets = r.get("results") or r.get("data") or r
    print(f"NSM presets: {len(presets)}")

    seen: set[str] = set()
    for p in presets:
        det = requests.get(f"{API}/api/internal/filter-preset/{p['uuid']}/",
                           headers=h, timeout=60).json()
        det = det.get("data", det)
        filters = det.get("filters") or {}
        rows, approx = search_all(h, filters)
        ids = {x.get("uuid") for x in rows if x.get("uuid")}
        seen |= ids
        flag = "  (approx)" if approx else ""
        print(f"  {(p.get('title') or p.get('name'))[:34]:34} sees {len(ids):5}{flag}")
    print(f"\nrecords visible to at least one preset: {len(seen)}")

    # -- universe --------------------------------------------------------
    q: dict = {"must": {"phone": 1}}
    if not args.all_data:
        ch = tag_id.get("Courthouse Data")
        if ch:
            q["must"]["any_tags"] = [ch]
    universe, _ = search_all(h, q)
    print(f"universe (has a phone{'' if args.all_data else ', Courthouse Data'}): {len(universe)}")

    orphan_ids = [x for x in universe if x.get("uuid") not in seen]
    print(f"ORPHANS (no preset can see them): {len(orphan_ids)}")
    if not orphan_ids:
        return 0

    # -- explain each ----------------------------------------------------
    rows, why_c, rescue = [], collections.Counter(), 0
    for i, x in enumerate(orphan_ids, 1):
        u = x.get("uuid")
        resp = _retry(lambda: requests.get(f"{API}/api/internal/property/{u}/",
                                           headers=h, timeout=30), f"GET {u[:8]}")
        if resp is None or resp.status_code != 200:
            continue
        d = resp.json()
        d = d.get("data", d)
        o = d.get("owner") or {}
        phones = o.get("phones") or []
        tiers = collections.Counter()
        for ph in phones:
            for t in (ph.get("tags") or []):
                tiers[str(t)] += 1
        good = sum(tiers.get(t, 0) for t in GOOD_TIERS)
        tags = sorted(str(t) for t in (d.get("tags") or []))
        lists = sorted(str(l) for l in (d.get("lists") or []))
        why = []
        for blocker in ("Sold", "Dead Area", "Not Buy Box", "Do Not Market", "Do Not Mail"):
            if blocker in tags:
                why.append(f"tag:{blocker}")
        for bad in ("Low Equity", "Negative Equity"):
            if bad in lists:
                why.append(f"list:{bad}")
        if not lists:
            why.append("NO LIST")
        if (d.get("predictivecall_attempts") or 0) > 0:
            why.append(f"called {d['predictivecall_attempts']}x")
        if not why:
            why.append("other")
        for w in why:
            why_c[w] += 1
        if good:
            rescue += 1
        rows.append({
            "uuid": u,
            "Owner": " ".join(filter(None, [o.get("first_name") or "", o.get("last_name") or ""])).strip(),
            "Property": (d.get("address") or {}).get("street") or "",
            "City": (d.get("address") or {}).get("city") or "",
            "Phones": len(phones), "Dial First/Second": good,
            "Status": d.get("status") or "", "Lists": ", ".join(lists),
            "Tags": ", ".join(tags), "Mailed": d.get("directmail_attempts") or 0,
            "Calls": d.get("predictivecall_attempts") or 0,
            "Why invisible": "; ".join(why),
        })
        if i % 50 == 0:
            print(f"  ...explained {i}/{len(orphan_ids)}")

    rows.sort(key=lambda r: -r["Dial First/Second"])
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n=== why they are invisible ===")
    for k, v in why_c.most_common():
        print(f"  {v:5}  {k}")
    print(f"\nWORTH RESCUING (has a Dial First/Second number): {rescue}")
    print("\ntop 15 by good phones:")
    for r in rows[:15]:
        print(f"  {r['Dial First/Second']:2} good / {r['Phones']:2} ph   "
              f"{r['Owner'][:22]:22} {r['Property'][:26]:26} {r['Why invisible'][:46]}")
    print(f"\nFull detail: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
