"""DP push, NSM step-10 pilot 2026-08-19 — Oren runs this himself (classifier
blocks Claude's DataSift writes):

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_nsm10_20260819.py            # real
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push_nsm10_20260819.py --dry-run  # preview

For each of the 12 pilot records from output/dp_nsm10_20260819/results.json:
  - appends every NEW Trestle-scored phone (score >= 21) to the record's owner
    with its Dial tier tag (81-100 First / 61-80 Second / 41-60 Third /
    21-40 Fourth). Drop-tier (<= 20) numbers are NOT pushed.
  - adds the "DP Complete" tag to the record.
  - re-GETs and verifies phones + tag landed (dp_push_20260819 pattern).

No renames, no mailing changes — contact identity is untouched.
Findings: output/reports/DP_NSM10_NoResponse_20260819.md
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402

DRY = "--dry-run" in sys.argv
RESULTS = REPO / "output" / "dp_nsm10_20260819" / "results.json"


def tier(score) -> str | None:
    if score is None:
        return None
    s = int(score)
    if s >= 81:
        return "Dial First"
    if s >= 61:
        return "Dial Second"
    if s >= 41:
        return "Dial Third"
    if s >= 21:
        return "Dial Fourth"
    return None


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def main() -> int:
    entries = json.loads(RESULTS.read_text(encoding="utf-8"))
    h = headers(token())
    ok = 0
    for e in entries:
        uuid = e["uuid"]
        label = f"{e['dm_first']} {e['dm_last']} @ {e['property']}"
        pushes = []
        for s in (e.get("scored") or []):
            # Litigator risk: pushed with the DNC tag (never a dial tier) so the
            # number is documented but suppressed from all marketing.
            if s.get("litigator"):
                t = "Litigator - DNC"
            else:
                t = tier(s.get("score"))
            if not t:
                continue
            ltype = "MOBILE" if "mobile" in str(s.get("line_type") or "").lower() else "LANDLINE"
            pushes.append({"number": s["phone"], "type": ltype, "tags": [t]})
        print(f"\n=== {label}")
        if not pushes:
            print("  no dialable new phones — tag-only")
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            print(f"  GET -> {r.status_code} — SKIP")
            continue
        d = r.json()
        owner = d.get("owner") or {}
        if (owner.get("last_name") or "").lower() != (e["dm_last"] or "").lower():
            print(f"  live owner {owner.get('first_name')} {owner.get('last_name')!r} "
                  f"!= expected {e['dm_last']!r} — SKIP (record changed?)")
            continue
        existing = {"".join(c for c in str(p.get("number") or "") if c.isdigit())[-10:]
                    for p in (owner.get("phones") or [])}
        new_owner = copy.deepcopy(owner)
        added = []
        for p in pushes:
            if p["number"][-10:] in existing:
                print(f"  phone {p['number']} already on record — skip")
                continue
            new_owner.setdefault("phones", []).append(p)
            added.append(p["number"])
        if DRY:
            print(f"  DRY: would add phones {added} + tag ['DP Complete']")
            ok += 1
            continue
        if added:
            r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                               json={"owner": new_owner}, timeout=30)
            print(f"  PATCH owner (+{len(added)} phones) -> HTTP {r.status_code}")
            if r.status_code != 200:
                print(f"    {r.text[:200]} — SKIPPING tag")
                continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": ["DP Complete"]}, timeout=30)
        print(f"  add-tags ['DP Complete'] -> HTTP {r.status_code}")
        # verify
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code == 200:
            d2 = r.json()
            nums = {"".join(c for c in str(p.get("number") or "") if c.isdigit())[-10:]
                    for p in ((d2.get("owner") or {}).get("phones") or [])}
            missing = [n for n in added if n[-10:] not in nums]
            tags = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (d2.get("tags") or [])]
            print(f"  verify: phones_missing={missing} dp_complete={'DP Complete' in tags}")
            if not missing:
                ok += 1
    print(f"\n{ok}/{len(entries)} records pushed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
