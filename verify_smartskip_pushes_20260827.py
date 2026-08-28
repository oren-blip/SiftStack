"""Did every SmartSkip phone actually LAND? Read-only audit of all four pushes.

The pusher is rerun-safe via a run tag, which means a re-run SKIPS a tagged
record without ever re-checking its phones. That is correct for speed and wrong
for assurance - and on 2026-08-27 DataSift was caught truncating a record at 15
phones while still returning HTTP 200. So "0 phones would be added" on a dry run
is not proof; only reading each record back and looking for the numbers is.

Checks the RECORD (GET /property/{uuid}/), never the search index, which goes
stale after writes. Writes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402
from push_smartskip_group1_20260825 import (  # noqa: E402
    headers, digits, find_record, PUSH_TIERS)

SOURCES = [
    ("group 1  (court PR)", "smartskip_group1_court_pr_phones.json"),
    ("group 1b (court PR)", "smartskip_group1b_court_pr_phones.json"),
    ("group 3  (court PR)", "smartskip_group3_court_pr_phones.json"),
    ("group 4  (backup heirs)", "smartskip_group4_backup_heir_phones.json"),
]


def noop(*_a, **_k):
    pass


def main() -> int:
    h = headers(token())
    grand_want = grand_live = 0
    problems: list[str] = []

    for label, fname in SOURCES:
        path = REPO / "output" / fname
        if not path.exists():
            print(f"{label}: SOURCE MISSING {fname}")
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        want = live = 0
        norec = 0
        for e in entries:
            expect = [p["phone"] for p in e["phones"]
                      if p.get("tier") in PUSH_TIERS]
            if not expect:
                continue
            rec = find_record(h, e, noop)
            if not rec:
                norec += 1
                continue
            try:
                d = requests.get(f"{API}/api/internal/property/{rec['uuid']}/",
                                 headers=h, timeout=30).json()
            except Exception as exc:
                problems.append(f"{label} {e['case_no']}: GET failed {exc}")
                continue
            on = {digits(p.get("number"))
                  for p in ((d.get("owner") or {}).get("phones") or [])}
            miss = [n for n in expect if digits(n) not in on]
            want += len(expect)
            live += len(expect) - len(miss)
            if miss:
                problems.append(
                    f"{label} {e['case_no']} ({e['county']}): "
                    f"{len(miss)} of {len(expect)} ABSENT -> {miss} "
                    f"[record holds {len(on)} phones]")
        grand_want += want
        grand_live += live
        pct = (live / want * 100) if want else 100.0
        print(f"{label}: {live}/{want} phones present ({pct:.0f}%), "
              f"{norec} estate(s) not in DataSift")

    print(f"\nTOTAL: {grand_live}/{grand_want} phones verified on-record")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  {p}")
    else:
        print("no missing numbers - every pushed phone is on its record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
