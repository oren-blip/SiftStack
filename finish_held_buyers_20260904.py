"""Finish the 3 held-back buyers.

Two MERGED onto existing records - correctly, as it turns out: those records
already list the incoming entity as a SISTER ENTITY, so they are the same
operation, not unrelated businesses sharing an office.
  2308 Kannapolis Hwy -> Gary Quigg, sister entity "Straight Path Real Estate Solutions Llc"
  2339 Odell Ste A    -> John Sears, sister entity "Journey Capital Llc"
One created a new record: Todd Brockmann (Wickenden Partners).
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dstok import token

API = "https://apiv2.reisift.io"
WORK = {
    "993859c3-1601-403f-a5a0-a9f3f4bad433": {
        "label": "2308 Kannapolis Hwy (Gary Quigg / Spres Fund 3)",
        "tags": ["Charlotte Metro Buyer", "Charlotte REI FB Group"],
        "marker": "Straight Path 9/2026",
        "desc": (" | Straight Path 9/2026 (Buyer Prospector): sister entity STRAIGHT PATH REAL "
                 "ESTATE SOLUTIONS LLC made 125 purchases in the last 6 months across Cabarrus, "
                 "Gaston, Iredell, Rowan, Union - flipper, 167 tracked acquisitions, avg $105,353, "
                 "latest Aug 2026. Contact: Joshua B Swart, Registered Agent / President "
                 "(NC SOS, active since 2017). Posts as a buyer in the Charlotte REI Facebook group."),
        "status": None,
    },
    "67420fbb-90ca-4f7b-9c5c-9df7f01c3a08": {
        "label": "2339 Odell Ste A (John Sears / J2 Land)",
        "tags": ["Charlotte Metro Buyer"],
        "marker": "Journey 9/2026",
        "desc": (" | Journey 9/2026 (Buyer Prospector): sister entity JOURNEY INVESTMENT GROUP LLC "
                 "made 10 purchases in the last 6 months in Cabarrus - buy-and-hold, 32 tracked "
                 "acquisitions, latest Jul 2026. Contact: Jon Devine, Registered Agent (NC SOS, active)."),
        "status": None,
    },
}
NEW_RECORD_OWNER = ("Todd", "Brockmann")
NEW_TAGS = ["Charlotte Metro Buyer"]
BATCH_TAG = "Buyer Prospector 2026-09-04 B"


def get(h, u):
    d = requests.get(f"{API}/api/internal/property/{u}/", headers=h, timeout=30).json()
    return d.get("data") or d


def tag_titles(d):
    return [t if isinstance(t, str) else t.get("title") for t in (d.get("tags") or [])]


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    h = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    for u, spec in WORK.items():
        d = get(h, u)
        have = tag_titles(d)
        need = [t for t in spec["tags"] if t not in have]
        desc = str(d.get("description") or "")
        add = spec["desc"] if spec["marker"] not in desc else ""
        print(f"{spec['label']}\n  tags to add: {need or 'none'} | description: {'append' if add else 'already noted'}")
        if not a.apply:
            continue
        if need:
            requests.post(f"{API}/api/internal/property/{u}/add-tags/", headers=h,
                          json={"tags": need}, timeout=30)
        if add:
            requests.patch(f"{API}/api/internal/property/{u}/", headers=h,
                           json={"description": (desc + add)[:4000]}, timeout=30)
        c = get(h, u); o = c.get("owner") or {}
        print(f"  verify: tags={all(t in tag_titles(c) for t in spec['tags'])} "
              f"desc={spec['marker'] in str(c.get('description'))} "
              f"owner still {o.get('first_name')} {o.get('last_name')} status={c.get('status')!r}")

    # the one genuinely new record
    tags, off = [], 0
    while True:
        j = requests.get(f"{API}/api/internal/tag/?limit=200&offset={off}", headers=h, timeout=30).json()
        r = j.get("results") or []
        tags += r
        if len(r) < 200: break
        off += 200
    bt = next((t for t in tags if str(t.get("title", "")).strip() == BATCH_TAG), None)
    q = requests.post(f"{API}/api/internal/property/", headers={**h, "x-http-method-override": "GET"},
                      json={"limit": 50, "query": {"must": {"any_tags": [bt["uuid"]]}}}, timeout=60).json()
    for p in q.get("results", []):
        d = get(h, p["uuid"]); o = d.get("owner") or {}
        if (o.get("first_name"), o.get("last_name")) != NEW_RECORD_OWNER:
            continue
        need = [t for t in NEW_TAGS if t not in tag_titles(d)]
        need_status = (d.get("status") or "") != "buyer"
        print(f"\nTodd Brockmann (Wickenden Partners)\n  tags to add: {need or 'none'} | "
              f"status needs set: {need_status}")
        if not a.apply:
            break
        if need:
            requests.post(f"{API}/api/internal/property/{p['uuid']}/add-tags/", headers=h,
                          json={"tags": need}, timeout=30)
        if need_status:
            requests.patch(f"{API}/api/internal/property/{p['uuid']}/", headers=h,
                           json={"status": "buyer"}, timeout=30)
        c = get(h, p["uuid"])
        print(f"  verify: tags={all(t in tag_titles(c) for t in NEW_TAGS)} status={c.get('status')!r}")
        break
    if not a.apply:
        print("\n(dry run - re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
