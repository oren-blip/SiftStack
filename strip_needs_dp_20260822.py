"""Remove the stale "Needs DP" tag from records already tagged "DP Complete".

19 records carried BOTH (found 2026-08-22 while attaching the research packs).
The effect is that a "Needs DP" working list shows properties whose research is
finished, so the queue reads longer than it is.

Only records holding BOTH tags are touched, and only the "Needs DP" tag is
removed -- nothing else on the record changes.

Every removal is verified with a direct GET of the record. DataSift's SEARCH
index lags writes, so a search-based check would report success on a write that
silently did not land.

Usage:
    python strip_needs_dp_20260822.py --dry-run   # list them, change nothing
    python strip_needs_dp_20260822.py             # strip + verify
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402

from build_dp_packs_20260822 import dp_complete_records, headers, token  # noqa: E402

API = "https://apiv2.reisift.io"
STALE = "Needs DP"
DONE = "DP Complete"
RESULTS = REPO / "output" / "strip_needs_dp_20260822.csv"


def get_prop(h: dict, uuid: str) -> dict | None:
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    return r.json() if r.status_code == 200 else None


def titles(rec: dict) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (rec.get("tags") or [])]


def run(dry: bool) -> int:
    tok = token()
    if not tok:
        print("DataSift login failed")
        return 1
    h = headers(tok)

    recs = dp_complete_records(h)
    print(f"{len(recs)} records tagged {DONE!r}; reading each one...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        details = list(ex.map(lambda r: (r, get_prop(h, r["uuid"])), recs))

    unread = [r for r, d in details if d is None]
    targets = [(r, d) for r, d in details
               if d is not None and STALE in titles(d) and DONE in titles(d)]
    print(f"carrying BOTH tags: {len(targets)}"
          + (f"   (could not read {len(unread)})" if unread else ""))
    for r, d in targets:
        a, o = r.get("address") or {}, r.get("owner") or {}
        print(f"   {(a.get('street') or '')[:32]:32} {(a.get('city') or '')[:13]:13} "
              f"{o.get('first_name', '')} {o.get('last_name', '')}")
    if dry:
        print("\ndry run - nothing changed")
        return 0
    if not targets:
        return 0

    rows, ok, fail = [], 0, 0
    for r, _ in targets:
        u = r["uuid"]
        a, o = r.get("address") or {}, r.get("owner") or {}
        resp = requests.post(f"{API}/api/internal/property/{u}/remove-tags/",
                             headers=h, json={"tags": [STALE]}, timeout=30)
        after = get_prop(h, u)
        now = titles(after) if after else []
        good = after is not None and STALE not in now and DONE in now
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        if not good:
            print(f"  FAIL {(a.get('street') or '')[:30]} -> HTTP {resp.status_code}; "
                  f"tags now {sorted(now)}")
        rows.append({"uuid": u, "street": a.get("street") or "",
                     "city": a.get("city") or "",
                     "owner": f"{o.get('first_name', '')} {o.get('last_name', '')}".strip(),
                     "http": resp.status_code,
                     "verified": "yes" if good else "NO",
                     "tags_after": "|".join(sorted(now))})

    with RESULTS.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\ndone {_dt.datetime.now():%Y-%m-%d %H:%M}: "
          f"{ok} stripped + verified, {fail} failed")
    print(f"results: {RESULTS}")
    return 0 if fail == 0 else 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    raise SystemExit(run(ap.parse_args().dry_run))


if __name__ == "__main__":
    main()
