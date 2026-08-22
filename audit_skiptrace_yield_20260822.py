"""Is DataSift's paid skip trace earning its keep on rows that ALREADY have a phone?

WHY: src/nc_datasift_export.py stamps the per-upload "Skip Trace <stamp> W##"
tag on EVERY non-placeholder row, so rows that already carry a Tracerfy /
Enformion / court-PDF number get paid-traced (~$0.15 each) anyway. The 5 Day
Challenge teaches exactly this multi-source order, but Ty is on the $97
unlimited add-on where the re-trace is free; this account is pay-per-record.

This measures the yield: for each traced upload, how many already-phoned rows
gained a NEW number, and how many of those numbers Trestle scored Dial First
or Dial Second (the only tiers Oren dials).

FREE + READ-ONLY: tag list + record search + record GETs. No writes, no Trestle.

    python audit_skiptrace_yield_20260822.py            # all Skip Trace tags
    python audit_skiptrace_yield_20260822.py --since 2026-08-01
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from trestle_api_backfill import API, get_token, headers, tag_texts, _search  # noqa: E402

OUT = REPO / "output"
DS_TRACE_COST = 0.15          # per record, per datasift_uploader.skip_trace_records
GOOD_TIERS = ("dial first", "dial second")


def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 10 else ""


def norm_street(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def csv_for_tag(tag: str) -> Path | None:
    """'Skip Trace 2026-08-21 175040 W34' -> the CSV that stamped it."""
    m = re.search(r"(\d{4}-\d{2}-\d{2}) (\d{6})(?: W(\d+))?", tag)
    if not m:
        return None
    date, time, wk = m.group(1), m.group(2), m.group(3)
    pat = (f"nc_estates_ftm_{date}_{time}_*week{wk}_datasift_upload_NETNEW.csv"
           if wk else f"nc_estates_ftm_{date}_{time}_*_datasift_upload_NETNEW.csv")
    hits = sorted(OUT.glob(pat))
    if not hits:  # some uploads shipped the full file, not the NETNEW cut
        hits = sorted(OUT.glob(pat.replace("_NETNEW", "")))
    return hits[0] if hits else None


def read_upload(path: Path) -> dict:
    """street -> {'phones': set, 'src': 'enformion'|'court'|'pipeline'|'none'}"""
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            street = norm_street(r.get("Property Street Address"))
            if not street:
                continue
            phones = {norm_phone(r.get(f"Phone {i}", "")) for i in range(1, 10)}
            phones.discard("")
            tags = {t.strip().lower() for t in (r.get("Tags") or "").split(",")}
            src = ("court" if "court-verified-phone" in tags else
                   "enformion" if "enformion-phone" in tags else
                   "pipeline" if phones else "none")
            rows[street] = {"phones": phones, "src": src}
    return rows


def record_phones(h: dict, uuid: str) -> tuple[str, dict]:
    """-> (normalized street, {phone: [tag titles]}) for the live record."""
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        return "", {}
    prop = r.json().get("data") or r.json()
    addr = prop.get("address") or {}
    street = addr.get("street") if isinstance(addr, dict) else str(addr)
    owners = ([prop["owner"]] if prop.get("owner") else []) + \
             (prop.get("secondary_owners") or [])
    out = {}
    for ow in owners:
        for ph in (ow.get("phones") or []):
            n = norm_phone(ph.get("number") or ph.get("phone") or "")
            if n:
                out[n] = tag_texts(ph.get("tags"))
    return norm_street(street), out


def all_trace_tags(h: dict, since: str) -> dict:
    """{tag title: uuid} for every 'Skip Trace <date> ...' tag on/after `since`."""
    found, offset = {}, 0
    while True:
        r = requests.get(f"{API}/api/internal/tag/", headers=h,
                         params={"limit": 200, "offset": offset}, timeout=30)
        if r.status_code != 200:
            break
        rows = r.json().get("results") or []
        for t in rows:
            title = (t.get("title") or "").strip()
            if not title.startswith("Skip Trace "):
                continue
            m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
            if m and m.group(1) >= since:
                found[title] = t.get("uuid")
        if len(rows) < 200:
            break
        offset += 200
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01",
                    help="only trace tags stamped on/after this date")
    a = ap.parse_args()

    h = headers(get_token())
    tmap = all_trace_tags(h, a.since)
    print(f"{len(tmap)} Skip Trace tag(s) on/after {a.since}\n")

    tot = {"had": 0, "had_gain": 0, "had_new": 0, "had_good": 0,
           "none": 0, "none_gain": 0, "none_new": 0, "none_good": 0,
           "unmatched": 0}
    detail = []

    for tag in sorted(tmap):
        cpath = csv_for_tag(tag)
        if not cpath:
            print(f"  {tag}: no source CSV found - skipped")
            continue
        up = read_upload(cpath)
        recs = _search(h, {"must": {"all_tags": [tmap[tag]]}})
        if not recs:
            print(f"  {tag}: 0 records carry this tag - skipped")
            continue
        per = {k: 0 for k in tot}
        for rec in recs:
            street, now = record_phones(h, rec["uuid"])
            row = up.get(street)
            if row is None:
                per["unmatched"] += 1
                continue
            before = row["phones"]
            added = {n: t for n, t in now.items() if n not in before}
            good = sum(1 for t in added.values()
                       if any(g in " | ".join(t).lower() for g in GOOD_TIERS))
            k = "had" if before else "none"
            per[k] += 1
            if added:
                per[f"{k}_gain"] += 1
            per[f"{k}_new"] += len(added)
            per[f"{k}_good"] += good
            if before and added:
                detail.append({"tag": tag, "street": street, "src": row["src"],
                               "had": len(before), "added": len(added),
                               "dial_1_2": good})
        for k in per:
            tot[k] += per[k]
        print(f"  {tag}\n"
              f"    already-phoned {per['had']:>3} traced -> {per['had_gain']} gained, "
              f"{per['had_new']} new #, {per['had_good']} Dial 1/2   |   "
              f"phoneless {per['none']:>3} -> {per['none_gain']} gained, "
              f"{per['none_new']} new #, {per['none_good']} Dial 1/2")

    print("\n" + "=" * 78)
    print("ALREADY HAD A PHONE AT UPLOAD (the redundant spend)")
    print(f"  records paid-traced : {tot['had']}  (~${tot['had'] * DS_TRACE_COST:,.2f})")
    print(f"  gained >=1 number   : {tot['had_gain']}"
          f"  ({tot['had_gain'] / max(tot['had'], 1) * 100:.0f}%)")
    print(f"  new numbers total   : {tot['had_new']}")
    print(f"  of those Dial 1/2   : {tot['had_good']}"
          f"   -> ${tot['had'] * DS_TRACE_COST / max(tot['had_good'], 1):,.2f}"
          f" per dialable number")
    print("\nNO PHONE AT UPLOAD (the justified spend, for contrast)")
    print(f"  records paid-traced : {tot['none']}  (~${tot['none'] * DS_TRACE_COST:,.2f})")
    print(f"  gained >=1 number   : {tot['none_gain']}"
          f"  ({tot['none_gain'] / max(tot['none'], 1) * 100:.0f}%)")
    print(f"  new numbers total   : {tot['none_new']}   Dial 1/2: {tot['none_good']}")
    print(f"\n  records tagged but not matched to a CSV row: {tot['unmatched']}")

    if detail:
        p = OUT / "skiptrace_yield_20260822.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
            w.writeheader()
            w.writerows(detail)
        print(f"  per-record detail -> {p}")


if __name__ == "__main__":
    main()
