"""Verify the 3 held-back buyers landed AND that the pre-existing records sharing
those addresses still have their original owners (the merge-overwrite risk)."""
from __future__ import annotations
import sys, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dstok import token

API = "https://apiv2.reisift.io"
GUARD = {
    "993859c3-1601-403f-a5a0-a9f3f4bad433": ("Gary", "Quigg", "2308 Kannapolis Hwy"),
    "67420fbb-90ca-4f7b-9c5c-9df7f01c3a08": ("John", "Sears", "2339 Odell School Rd Ste A"),
    "c58b98a8-104f-48e1-b162-08bb42de0205": ("Lee", "Lewis", "1800 Camden Rd Ste 107-240"),
    "5787d69c-0f31-4003-b9ac-a201913a89c6": ("Matthew", "Gallo", "1800 Camden Rd"),
}
WANT = [("Joshua B", "Swart"), ("Todd", "Brockmann"), ("Jon", "Devine")]
TAG = "Buyer Prospector 2026-09-04 B"


def main() -> int:
    h = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}
    tags, off = [], 0
    while True:
        j = requests.get(f"{API}/api/internal/tag/?limit=200&offset={off}", headers=h, timeout=30).json()
        r = j.get("results") or []
        tags += r
        if len(r) < 200: break
        off += 200
    t = next((x for x in tags if str(x.get("title", "")).strip() == TAG), None)
    if not t:
        print(f"batch tag {TAG!r} not visible yet - still processing"); return 1
    q = requests.post(f"{API}/api/internal/property/", headers={**h, "x-http-method-override": "GET"},
                      json={"limit": 50, "query": {"must": {"any_tags": [t["uuid"]]}}}, timeout=60).json()
    recs = q.get("results", [])
    print(f"records tagged {TAG!r}: {len(recs)} (expected 3)")
    got = set()
    for p in recs:
        d = requests.get(f"{API}/api/internal/property/{p['uuid']}/", headers=h, timeout=30).json()
        d = d.get("data") or d
        o = d.get("owner") or {}
        a = d.get("address") or {}
        got.add((o.get("first_name"), o.get("last_name")))
        print(f"  {o.get('first_name')} {o.get('last_name'):<12} {a.get('street'):<30} status={d.get('status')!r}")
    for w in WANT:
        print(f"  {'OK  ' if w in got else 'MISS'} {w[0]} {w[1]}")
    print("\n=== guard: pre-existing owners at the shared addresses ===")
    bad = 0
    for u, (f, l, st) in GUARD.items():
        d = requests.get(f"{API}/api/internal/property/{u}/", headers=h, timeout=30).json()
        d = d.get("data") or d
        o = d.get("owner") or {}
        now = (o.get("first_name"), o.get("last_name"))
        ok = now == (f, l)
        if not ok: bad += 1
        print(f"  {'OK  ' if ok else 'OVERWRITTEN'} {st:<30} {now[0]} {now[1]}"
              f"{'' if ok else f'  (was {f} {l})'}")
    print("\nOWNERS INTACT" if not bad else f"\n{bad} RECORD(S) OVERWRITTEN - restore needed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
