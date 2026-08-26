"""Ty's remaining two suppressions: dead areas + off-buy-box structure types.

Day 2 universal suppression stack items 4 and 5 (equity was item 3, done
2026-08-25; sold is item 2, done 2026-08-23). Approved by Oren 2026-08-25:
the 5-zip roster only, one-time sweep now with a quarterly refresh (no
nightly wiring). Commercial-Vacant Land was kept on 8/25 and REVERSED to
suppressed on 8/26 -- commercial-zoned vacant land is out of the buy box.

DEAD ZIPS -- Market Finder measured <=1 investor transaction in 6 months
(Ty's bar), verified in-footprint (the zip's primary county is one we
market -- border-sliver zips like Mocksville 27028 read 0 in the Iredell
view but their real market lives in Davie County; those are NOT dead):

    28689  Union Grove   (Iredell)
    28101  McAdenville   (Gaston)
    28041  Faith         (Rowan)
    28006  Alexis        (Gaston)
    28072  Granite Quarry(Rowan)

STRUCTURE -- keep-set is Oren's buy box: Single Family, Mobile/Manufactured,
Vacant Land (except commercial-zoned), Residential
(General/Single), and NULL/blank (unknown is not bad -- same philosophy as
the equity-list exclusion; DataSift enrich fills these over time). Anything
else -- townhouse, condo, commercial, restaurant, patio home, ... -- is
tagged. Two passes:
  1. account-wide, by exact structure_type= query for every KNOWN drop value
     (the filter API takes one exact string per query, so we loop);
  2. a full detail scan of the marketing lane (tags Courthouse Data OR
     Priority 1) to catch vocabulary we have not seen -- search results do
     not carry structure_type, so this is one GET per record (~40 min).
     Scan results are cached to output/structure_scan_20260826.json so
     --apply does not re-scan.

The records-filter API has NO zip key and NO multi-value structure key
(probed 2026-08-25), so both suppressions ride on tags -- the same
mechanism as Sold:

    "Dead Area"     on records in the 5 zips
    "Not Buy Box"   on records with a known off-buy-box structure_type

and every NSM preset excludes both via must_not.any_tags (run
add_suppression_tags_to_presets after the sweep, or --patch-presets here).

Zip targeting: must.search is FUZZY (searching "28041" also returns a
Salisbury record), so every hit is verified client-side against
address.zip5 before it is touched.

    python suppress_dead_areas_20260826.py                 # dry run, writes nothing
    python suppress_dead_areas_20260826.py --skip-scan     # dry run, known values only
    python suppress_dead_areas_20260826.py --apply         # tag + verify sample
    python suppress_dead_areas_20260826.py --apply --patch-presets

Tagging route: POST /property/{uuid}/add-tags/ with TITLES (the proven
push_sold_tags.py shape). Property-PATCH of tags is a known silent no-op --
never used here. Plan is always written to output/dead_area_plan_20260826.csv.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
NSM_FOLDER = "921333f1-0d77-4398-a7ed-4d4cea8cabe7"
NSM_NAME = re.compile(r"^\d{2}\.")
TAG_DEAD = "Dead Area"
TAG_STRUCT = "Not Buy Box"
CH = "ebca979e-1586-438d-b0ab-1b7c87f778a7"   # tag "Courthouse Data"
P1 = "dbdf7002-e251-4cdd-b6c0-894f5c734861"   # tag "Priority 1"

DEAD_ZIPS = {"28689": "Union Grove (Iredell)",
             "28101": "McAdenville (Gaston)",
             "28041": "Faith (Rowan)",
             "28006": "Alexis (Gaston)",
             "28072": "Granite Quarry (Rowan)"}

# Known off-buy-box structure_type values (exact strings, from 2026-08-25
# vocabulary probe). The lane scan catches values not on this list.
DROP_VALUES = ["Townhouse", "Townhouse (Residential)",
               "Condominium Unit (Residential)",
               "Duplex (2 units, any combination)",
               "Commercial (General)", "Restaurant", "Patio Home",
               "Mobile Home Park, Trailer Park",
               # 2026-08-26: Oren reversed the 8/25 keep -- commercial-zoned
               # vacant land is out of the buy box after all
               "Commercial-Vacant Land", "commercial-vacant land"]

# keep-rules for the lane scan (lowercase substring match). Tuned against the
# real lane vocabulary 2026-08-26: "modular" keeps Modular/Pre-Fabricated Homes
# (same class as manufactured); "rural" keeps Rural Residence / Rural/
# Agricultural Residence (single-family houses on rural land); "use not
# specified" keeps Parcels With Improvements, Use Not Specified (unknown is
# not bad -- could be houses). "Mobile Home Park, Trailer Park" is commercial,
# not a manufactured home -- explicit drop overriding the "mobile home" keep.
KEEP_SUBSTRINGS = ("single family", "mobile home", "manufactured", "modular",
                   "vacant land", "residential (general", "rural",
                   "use not specified")
DROP_OVERRIDES = ("mobile home park", "commercial-vacant land",
                  "commercial - vacant land")

PLAN = REPO / "output" / "dead_area_plan_20260826.csv"
SCAN_CACHE = REPO / "output" / "structure_scan_20260826.json"


def headers() -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
            "user-agent": "Mozilla/5.0", "authorization": f"Bearer {token()}",
            "content-type": "application/json"}


S = requests.Session()


def search(h: dict, query: dict, limit: int, offset: int) -> dict:
    for i in range(5):
        try:
            r = S.post(f"{API}/api/internal/property/",
                       headers={**h, "x-http-method-override": "GET"},
                       json={"limit": limit, "offset": offset, "query": query},
                       timeout=90)
            if r.status_code == 200:
                return r.json()
            return {}
        except requests.RequestException:
            time.sleep(2 * (i + 1))   # DataSift drops connections under load
    return {}


def detail(h: dict, uuid: str) -> dict:
    for i in range(4):
        try:
            r = S.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
            if r.status_code == 200:
                d = r.json()
                return d.get("data") or d
            return {}
        except requests.RequestException:
            time.sleep(1 + i)
    return {}


def page_all(h: dict, query: dict) -> list[dict]:
    total = search(h, query, 1, 0).get("count") or 0
    out, off = [], 0
    while off < total:
        recs = search(h, query, 100, off).get("results") or []
        if not recs:
            break
        out.extend(recs)
        off += 100
    return out


def keep_structure(value: str | None) -> bool:
    if not value or not str(value).strip():
        return True                     # unknown is not bad
    v = str(value).lower()
    if any(s in v for s in DROP_OVERRIDES):
        return False
    return any(s in v for s in KEEP_SUBSTRINGS)


def find_dead_zip_records(h: dict) -> list[dict]:
    """search is fuzzy -- every hit is verified against address.zip5."""
    hits, seen = [], set()
    for z, place in DEAD_ZIPS.items():
        for rec in page_all(h, {"must": {"search": z}}):
            a = rec.get("address") or {}
            zip5 = a.get("zip5") or (a.get("postal_code") or "")[:5]
            if zip5 != z or rec["uuid"] in seen:
                continue
            seen.add(rec["uuid"])
            hits.append({"uuid": rec["uuid"], "tag": TAG_DEAD,
                         "reason": f"zip {z} = {place}, <=1 investor deal/6mo",
                         "street": a.get("street"), "city": a.get("city"), "zip": zip5})
    return hits


def find_known_structure_records(h: dict) -> list[dict]:
    hits = []
    for val in DROP_VALUES:
        for rec in page_all(h, {"must": {"structure_type": val}}):
            a = rec.get("address") or {}
            hits.append({"uuid": rec["uuid"], "tag": TAG_STRUCT,
                         "reason": f"structure_type = {val}",
                         "street": a.get("street"), "city": a.get("city"),
                         "zip": a.get("zip5")})
    return hits


def scan_lane_structures(h: dict) -> list[dict]:
    """Detail-scan the marketing lane for off-buy-box values NOT in
    DROP_VALUES. ~0.7s/record; cached across runs."""
    if SCAN_CACHE.exists():
        print(f"  using cached lane scan {SCAN_CACHE.name} "
              f"(delete it to re-scan)")
        cached = json.loads(SCAN_CACHE.read_text(encoding="utf-8"))
        # keep-rules may have been tuned since the scan ran -- re-classify.
        # (Rules can only WIDEN the keep-set safely: a record the old rules
        # kept is absent from this cache, so catch newly-dropped values via
        # DROP_VALUES in pass 2 instead.)
        out = []
        for r in cached:
            m = re.match(r"structure_type = (.*) \(lane scan\)$", r["reason"])
            val = m.group(1) if m else None
            if val is not None and keep_structure(val):
                continue                # value is kept under the tuned rules
            out.append(r)
        if len(out) != len(cached):
            print(f"  rules re-applied: {len(cached)} cached hits -> {len(out)}")
        return out
    lane = page_all(h, {"must": {"any_tags": [CH, P1]}})
    print(f"  lane scan: {len(lane)} records, one detail GET each...")
    hits, vocab = [], {}
    for i, rec in enumerate(lane, 1):
        if i % 250 == 0:
            print(f"    {i}/{len(lane)}  ({len(hits)} flagged so far)")
        d = detail(h, rec["uuid"])
        st = d.get("structure_type")
        vocab[st or "(null)"] = vocab.get(st or "(null)", 0) + 1
        if keep_structure(st) or st in DROP_VALUES:
            continue                    # kept, or already caught by pass 1
        a = rec.get("address") or {}
        hits.append({"uuid": rec["uuid"], "tag": TAG_STRUCT,
                     "reason": f"structure_type = {st} (lane scan)",
                     "street": a.get("street"), "city": a.get("city"),
                     "zip": a.get("zip5")})
    print("  lane structure vocabulary:")
    for v, n in sorted(vocab.items(), key=lambda x: -x[1]):
        marker = "" if keep_structure(None if v == "(null)" else v) else "  << DROP"
        print(f"    {n:5d}  {v}{marker}")
    SCAN_CACHE.write_text(json.dumps(hits, indent=1), encoding="utf-8")
    return hits


def add_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    for i in range(3):
        try:
            r = S.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                       headers=h, json={"tags": titles}, timeout=30)
            return r.status_code in (200, 201, 202, 204)
        except requests.RequestException:
            time.sleep(1 + i)
    return False


def tag_uuid_by_title(h: dict, title: str) -> str | None:
    r = S.get(f"{API}/api/internal/tag/", headers=h, params={"limit": 1000},
              timeout=60)
    for t in (r.json().get("results") or r.json().get("data") or []):
        if (t.get("title") or "").strip().lower() == title.lower():
            return t.get("uuid") or t.get("id")
    return None


def patch_presets(h: dict) -> int:
    """Add both suppression tags to must_not.any_tags on the 12 NSM presets."""
    tag_uuids = []
    for title in (TAG_DEAD, TAG_STRUCT):
        u = tag_uuid_by_title(h, title)
        if not u:
            print(f"  preset patch ABORTED: tag {title!r} does not exist yet "
                  f"(run --apply first so add-tags/ creates it)")
            return 1
        tag_uuids.append(u)
    r = S.get(f"{API}/api/internal/filter-preset/", headers=h,
              params={"limit": 300}, timeout=60)
    targets = [p for p in (r.json().get("results") or r.json().get("data") or [])
               if p.get("folder") == NSM_FOLDER and NSM_NAME.match(p.get("title") or "")]
    fail = 0
    for p in sorted(targets, key=lambda p: p.get("title") or ""):
        uid = p.get("uuid") or p.get("id")
        det = S.get(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                    timeout=30).json()
        det = det.get("data") or det
        filters = copy.deepcopy(det.get("filters") or {})
        mn = filters.setdefault("must", {}).setdefault("must_not", {})
        tags = list(mn.get("any_tags") or [])
        for u in tag_uuids:
            if u not in tags:
                tags.append(u)
        mn["any_tags"] = tags
        body = {"title": det.get("title"), "filters": filters,
                "folder": det.get("folder"), "type": det.get("type"),
                "quick_filter": det.get("quick_filter")}
        pr = S.patch(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                     json=body, timeout=30)
        # verify by re-reading -- never trust the write response
        vd = S.get(f"{API}/api/internal/filter-preset/{uid}/", headers=h,
                   timeout=30).json()
        vd = vd.get("data") or vd
        saved = (((vd.get("filters") or {}).get("must") or {})
                 .get("must_not") or {}).get("any_tags") or []
        ok = pr.status_code in (200, 202) and all(u in saved for u in tag_uuids)
        print(f"  {'ok  ' if ok else 'FAIL'} {det.get('title')}")
        fail += 0 if ok else 1
    return fail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually tag the records (default: dry run)")
    ap.add_argument("--skip-scan", action="store_true",
                    help="skip the ~40min lane detail scan (known values only)")
    ap.add_argument("--patch-presets", action="store_true",
                    help="after tagging, exclude both tags from the 12 NSM presets")
    args = ap.parse_args()
    h = headers()

    print("phase 1: dead zips")
    dead = find_dead_zip_records(h)
    for r in dead:
        print(f"  {r['zip']}  {r['street']}, {r['city']}")
    print(f"  -> {len(dead)} records")

    print("\nphase 2: off-buy-box structure (known values, account-wide)")
    struct = find_known_structure_records(h)
    print(f"  -> {len(struct)} records")

    if not args.skip_scan:
        print("\nphase 3: lane detail scan (unknown vocabulary)")
        struct += scan_lane_structures(h)

    plan = dead + struct
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    with PLAN.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["uuid", "tag", "reason", "street",
                                           "city", "zip"])
        w.writeheader()
        w.writerows(plan)
    print(f"\nplan: {len(plan)} taggings -> {PLAN}")

    if not args.apply:
        print("DRY RUN -- nothing changed. Re-run with --apply to tag.")
        return 0

    print("\napplying tags...")
    ok = fail = 0
    for r in plan:
        if add_tags(h, r["uuid"], [r["tag"]]):
            ok += 1
        else:
            print(f"  FAIL {r['uuid']}  {r['street']}")
            fail += 1
    print(f"{ok} tagged, {fail} failed")

    # verify a sample by re-read (search index is stale; property GET is not)
    sample = plan[:5]
    for r in sample:
        d = detail(h, r["uuid"])
        # detail tags come back as plain title strings
        titles = {t.get("title") if isinstance(t, dict) else str(t)
                  for t in (d.get("tags") or [])}
        print(f"  verify {r['street']}: {'OK' if r['tag'] in titles else 'MISSING'}")

    if args.patch_presets:
        print("\npatching NSM presets...")
        fail += patch_presets(h)
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
