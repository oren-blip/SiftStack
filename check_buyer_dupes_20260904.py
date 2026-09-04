"""Pre-upload check for the Charlotte buyer batch: does the target list exist,
and which rows already exist in DataSift? READ-ONLY - writes nothing."""
from __future__ import annotations
import os, re, sys, csv
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv()
API = "https://apiv2.reisift.io"
CSV = Path("output/charlotte_buyers_datasift_upload_2026-09-04.csv")

def token() -> str | None:
    t = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if t: return t
    try:
        from get_ds_token import get_token
        return get_token()
    except Exception as e:
        print("token helper failed:", e); return None

def main() -> int:
    tk = token()
    if not tk: print("NO TOKEN - cannot check"); return 2
    h = {"Authorization": f"Bearer {tk}", "Content-Type": "application/json"}
    r = requests.get(f"{API}/api/internal/list/?limit=500", headers=h, timeout=30)
    print("list endpoint:", r.status_code)
    if r.status_code == 200:
        items = r.json().get("results") or r.json().get("data") or []
        names = [i.get("title") or i.get("name") for i in items]
        print("lists:", len(names))
        for n in names:
            if n and re.search(r"buyer", str(n), re.I): print("   BUYER LIST:", n)
    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8-sig")))
    print(f"\nCSV rows: {len(rows)}")
    def norm(s): return re.sub(r"[^a-z0-9]", "", str(s).lower())
    dupes = miss = 0
    for row in rows:
        q = f"{row['Property Street Address']} {row['Property City']} {row['Property State']} {row['Property ZIP Code']}"
        rr = requests.post(f"{API}/api/internal/property/", headers=h,
                           json={"query": {"search": q}, "limit": 5}, timeout=30)
        if rr.status_code != 200:
            print(f"  search HTTP {rr.status_code} for {q[:50]}"); continue
        res = rr.json().get("results") or rr.json().get("data") or []
        hit = None
        for p in res:
            a = p.get("address") or {}
            if norm(a.get("street") or "") == norm(row["Property Street Address"]) and \
               str(a.get("zip") or "")[:5] == row["Property ZIP Code"]:
                hit = p; break
        if hit:
            dupes += 1
            o = (hit.get("owner") or {})
            print(f"  EXISTS: {row['Property Street Address']}, {row['Property City']} -> "
                  f"{o.get('first_name','')} {o.get('last_name','')} | status={hit.get('property_status')} | uuid={hit.get('uuid')}")
        else:
            miss += 1
    print(f"\nalready in DataSift: {dupes} | net-new: {miss}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
