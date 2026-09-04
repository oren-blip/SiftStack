"""Local dedup of the Charlotte buyer batch against records already tagged
'cash buyers' in DataSift. READ-ONLY."""
from __future__ import annotations
import os, re, sys, csv, json
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
from get_ds_token import get_token

API = "https://apiv2.reisift.io"
CSV = Path("output/charlotte_buyers_datasift_upload_2026-09-04.csv")


def norm(s: str) -> str:
    s = str(s).lower()
    s = re.sub(r"\b(ste|suite|unit|apt|#)\s*\S+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def main() -> int:
    h = {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}
    tags = requests.get(f"{API}/api/internal/tag/?limit=500", headers=h, timeout=30).json()
    tags = tags.get("results") or tags.get("data") or []
    tag = next((t for t in tags if str(t.get("title", "")).lower() == "cash buyers"), None)
    if not tag:
        print("no 'cash buyers' tag found"); return 2
    print("cash buyers tag:", tag["uuid"])
    existing, offset = [], 0
    for _ in range(20):
        body = {"query": {"must": {"any_tags": [tag["uuid"]]}}, "limit": 200, "offset": offset}
        # POST /property/ CREATES a record; the x-http-method-override header makes it a query
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json=body, timeout=60)
        if r.status_code != 200:
            print("query HTTP", r.status_code, r.text[:200]); break
        j = r.json()
        res = j.get("results") or j.get("data") or []
        existing += res
        print(f"  page: +{len(res)} (total {len(existing)} of {j.get('count')})")
        if len(res) < 200: break
        offset += 200
    Path("output/_ds_cash_buyers_snapshot.json").write_text(json.dumps(existing, indent=1), encoding="utf-8")
    idx = {}
    for p in existing:
        a = p.get("address") or {}
        # stored shape is {street, city, zip5, postal_code, state} - there is NO "zip" key
        z = str(a.get("zip5") or a.get("postal_code") or "")[:5]
        idx[(norm(a.get("street")), z)] = p
        idx[(norm(a.get("street")), norm(a.get("city")))] = p   # zip-independent fallback
    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8-sig")))
    dupes, net = [], []
    for row in rows:
        k = (norm(row["Property Street Address"]), row["Property ZIP Code"])
        k2 = (norm(row["Property Street Address"]), norm(row["Property City"]))
        hit = idx.get(k) or idx.get(k2)
        (dupes if hit else net).append((row, hit))
    print(f"\nCSV rows {len(rows)} | already tagged cash buyers: {len(dupes)} | net-new: {len(net)}")
    for row, p in dupes:
        o = (p.get("owner") or {})
        print(f"  DUP {row['Property Street Address']:<34} {row['Owner First Name']} {row['Owner Last Name']}"
              f"  -> existing owner: {o.get('first_name','')} {o.get('last_name','')} status={p.get('property_status')}")
    with (Path("output/charlotte_buyers_NETNEW_2026-09-04.csv")).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader()
        for row, _ in net: w.writerow(row)
    print("\n-> output/charlotte_buyers_NETNEW_2026-09-04.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
