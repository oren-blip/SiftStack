"""Reconcile the Charlotte buyer upload and set status=buyer.

The upload wizard SILENTLY DROPS rows whose address will not geocode (PO Boxes
are the usual casualty), so uploaded-row count must always be checked against
the batch-tag record count. Audit by default; --apply sets the status.

    python reconcile_buyer_upload_20260904.py
    python reconcile_buyer_upload_20260904.py --apply
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
from get_ds_token import get_token

API = "https://apiv2.reisift.io"
CSV = Path("output/charlotte_buyers_NETNEW_2026-09-04.csv")
BATCH_TAG = "Buyer Prospector 2026-09-04"
STATUS = "buyer"


def norm(s):
    s = str(s).lower()
    # DataSift stores the suite GLUED to the street ("6201 Fairview Rdste 200"),
    # so a \b before "ste" never matches on the stored side. Do not require it.
    s = re.sub(r"(ste|suite|unit|apt|#)\s*\S+$", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def query_by_tag(h, tag_id):
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": {"must": {"any_tags": [tag_id]}}}, timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out += rows
        if len(rows) < 200: break
        offset += 200
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="set property status to buyer")
    a = ap.parse_args()
    h = {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}
    tags = requests.get(f"{API}/api/internal/tag/?limit=500", headers=h, timeout=30).json()
    tags = tags.get("results") or tags.get("data") or []
    tag = next((t for t in tags if str(t.get("title", "")).strip().lower() == BATCH_TAG.lower()), None)
    if not tag:
        print(f"batch tag '{BATCH_TAG}' not found yet - upload may still be processing")
        return 1
    recs = query_by_tag(h, tag["uuid"])
    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8-sig")))
    print(f"CSV rows uploaded: {len(rows)}")
    print(f"records carrying '{BATCH_TAG}': {len(recs)}")
    idx = {}
    for p in recs:
        addr = p.get("address") or {}
        idx[norm(addr.get("street"))] = p
    missing = [r for r in rows if norm(r["Property Street Address"]) not in idx]
    if missing:
        print(f"\nSILENTLY DROPPED by the wizard: {len(missing)}")
        for r in missing:
            print(f"  {r['Property Street Address']}, {r['Property City']} {r['Property State']} "
                  f"{r['Property ZIP Code']}  ({r['Owner First Name']} {r['Owner Last Name']})")
    else:
        print("\nall rows landed - nothing dropped")
    def _st(p):
        v = p.get("status") or p.get("property_status")
        return (v.get("title") if isinstance(v, dict) else v) or ""
    need = [p for p in recs if _st(p).lower() != STATUS]
    print(f"\nrecords needing status='{STATUS}': {len(need)}")
    if not a.apply:
        print("(audit only - re-run with --apply to set status)")
        return 0
    ok = fail = 0
    for p in need:
        u = p["uuid"]
        r = requests.patch(f"{API}/api/internal/property/{u}/", headers=h,
                           json={"status": STATUS}, timeout=30)
        if r.status_code in (200, 202):
            v = requests.get(f"{API}/api/internal/property/{u}/", headers=h, timeout=30)
            vd = v.json().get("data") or v.json()
            got = vd.get("status") or vd.get("property_status")
            got = got.get("title") if isinstance(got, dict) else got
            if got == STATUS: ok += 1
            else: fail += 1; print(f"  VERIFY FAIL {u}: status is {got!r}")
        else:
            fail += 1; print(f"  HTTP {r.status_code} {u}: {r.text[:120]}")
    print(f"\nstatus set: {ok} ok, {fail} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
