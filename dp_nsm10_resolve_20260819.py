"""Q5 step 2 (READ-ONLY): resolve the preset-10 UUIDs (tags/lists/statuses),
re-run the record query with the status exclusion expanded the way the UI
does, and write the true candidate list to CSV for DP.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")
from dp_nsm10_discover_20260819 import API, OUT, get_token, headers  # noqa: E402

TAG_ANY = "ebca979e-1586-438d-b0ab-1b7c87f778a7"
TAG_NOT = "8f42d2cd-96ce-4ec8-93ec-138a299d2cf8"
LISTS = ["0090b829-6ca1-46f2-9ab7-57c450abfefb",
         "25d1e297-2125-4233-a2f5-ba01101c01c9",
         "59f21f53-2a0d-4dba-aa3b-20fa7ebe8b8d"]


def name_of(h, kind, uuid):
    r = requests.get(f"{API}/api/internal/{kind}/{uuid}/", headers=h, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return d.get("title") or d.get("name") or "?"
    return f"HTTP {r.status_code}"


def main() -> int:
    h = headers(get_token())
    print("any_tags tag:", name_of(h, "tag", TAG_ANY))
    print("must_not tag:", name_of(h, "tag", TAG_NOT))
    for l in LISTS:
        print("list:", l[:8], name_of(h, "list", l))

    # account's property statuses (to expand the 'all' exclusion)
    statuses = []
    for route in ("property-status", "status", "propertystatus"):
        r = requests.get(f"{API}/api/internal/{route}/", headers=h,
                         params={"limit": 100}, timeout=30)
        if r.status_code == 200:
            rows = r.json().get("results") or r.json().get("data") or r.json()
            if isinstance(rows, list) and rows:
                statuses = rows
                print(f"statuses via {route}: "
                      + ", ".join(str(s.get("title") or s.get("name") or s) for s in rows))
                break
    status_ids = [s.get("uuid") or s.get("id") or s.get("slug") for s in statuses
                  if isinstance(s, dict)]

    query = {
        "must": {
            "any_tags": [TAG_ANY],
            "any_lists": LISTS,
            "directmail_attempts": [6, 8],
            "predictivecall_attempts": [4, None],
            "must_not": {
                "all_tags": [TAG_NOT],
                "any_phone_status": ["CORRECT", "CORRECT_DNC"],
                "any_property_status": status_ids or ["all"],
            },
        }
    }
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset, "query": query},
                          timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    print(f"\nTRUE preset-10 match count: {len(out)}")
    (OUT / "records_true.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    with (OUT / "nsm10_candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "street", "city", "state", "zip", "owner_first",
                    "owner_last", "status", "dm_attempts", "call_attempts",
                    "lists", "tags", "n_phones"])
        for rec in out:
            a = rec.get("address") or {}
            ow = rec.get("owner") or {}
            tags = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (rec.get("tags") or [])]
            lists = [l.get("title") if isinstance(l, dict) else str(l)
                     for l in (rec.get("lists") or [])]
            w.writerow([rec.get("uuid"), a.get("street"), a.get("city"),
                        a.get("state"), a.get("zip_code") or a.get("zip"),
                        ow.get("first_name"), ow.get("last_name"),
                        rec.get("status"), rec.get("directmail_attempts"),
                        rec.get("predictivecall_attempts"),
                        "|".join(lists), "|".join(tags),
                        len(ow.get("phones") or [])])
    for rec in out:
        a = rec.get("address") or {}
        ow = rec.get("owner") or {}
        print(f"  {a.get('street','?'):30} {a.get('city','?'):15} "
              f"{ow.get('first_name','')} {ow.get('last_name','')}  "
              f"status={rec.get('status')} dm={rec.get('directmail_attempts')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
