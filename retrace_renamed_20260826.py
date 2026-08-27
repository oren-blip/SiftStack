"""Re-trace the RENAMED court-PR records so phones belong to the named person.

Oren approved 8/26. The renamed records' phones were skip-traced against the
OLD identity (usually the decedent's household at the property). Now that the
owner is the court PR at the court's mailing address, a fresh DataSift skip
trace (unlimited plan) pulls the right person's numbers.

Two phases:
    python retrace_renamed_20260826.py --tag      # API: stamp the scope tag on
                                                  # the renamed rows, verify
    python retrace_renamed_20260826.py --trace    # UI: Records -> filter by the
                                                  # tag -> Send To -> Skip Trace
                                                  # (retries while tag indexes)

Scope tag isolates EXACTLY the renamed rows — the "Court Mailing Applied" tag
also covers already-named records whose phones are fine and don't need
re-tracing. Skip trace via tag filter aborts rather than tracing wide
(skip_trace_records' own guard), so a not-yet-indexed tag is a clean retry.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as _dt
import json
import sys
import time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
SCOPE_TAG = "Court PR Retrace 2026-08"
SWEEP_CSV = REPO / "output" / "court_mailing_sweep_20260826.csv"
DO_TAG = "--tag" in sys.argv
DO_TRACE = "--trace" in sys.argv

ROUNDS = 5
WAIT_S = 480  # 8 min between filter-failed retries (tag indexing lag)


def targets() -> dict[str, str]:
    """Case No. -> UUID for every RENAMED row the sweep located."""
    out = {}
    for r in csv.DictReader(open(SWEEP_CSV, encoding="utf-8-sig")):
        if (r.get("Renamed") or "") == "yes" and (r.get("UUID") or "").strip():
            out[r["Case No."]] = r["UUID"].strip()
    return out


def headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


def tag_phase(h: dict, tgts: dict[str, str]) -> int:
    ok = fail = 0
    for case, uuid in tgts.items():
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, data=json.dumps({"tags": [SCOPE_TAG]}),
                          timeout=30)
        v = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30)
        d = v.json() if v.status_code == 200 else {}
        d = d.get("data") or d.get("result") or d
        tags = [t.get("title") if isinstance(t, dict) else str(t)
                for t in (d.get("tags") or [])]
        good = SCOPE_TAG in tags
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        print(f"  {case}  add-tags {r.status_code}  verified "
              f"{'OK' if good else 'MISSING'}")
    print(f"\ntagged {ok}/{len(tgts)}  (tag: {SCOPE_TAG!r})")
    return 0 if fail == 0 else 1


async def trace_phase(n_expected: int) -> int:
    import os
    from playwright.async_api import async_playwright
    from datasift_uploader import login, skip_trace_records

    for rnd in range(1, ROUNDS + 1):
        print(f"\n--- skip-trace attempt {rnd}/{ROUNDS} "
              f"at {_dt.datetime.now():%H:%M:%S} ---")
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            if not ok:
                print("login failed")
                await b.close()
                return 1
            res = await skip_trace_records(page, "PROBATE",
                                           filter_tag=SCOPE_TAG)
            await b.close()
        print(f"  result: {res}")
        if res.get("success"):
            print(f"\nSkip trace submitted for the {n_expected} renamed records "
                  "— processing runs in DataSift's background (Activity tab).")
            return 0
        if res.get("reason") != "filter_failed":
            print("\nNon-retryable failure — inspect the screenshot in logs/.")
            return 1
        if rnd < ROUNDS:
            print(f"  tag not filterable yet — waiting {WAIT_S // 60} min")
            time.sleep(WAIT_S)
    print("\nTag never became filterable — run the trace by hand "
          f"(Records -> tag {SCOPE_TAG!r} -> Send To -> Skip Trace).")
    return 1


def main() -> int:
    tgts = targets()
    print(f"renamed targets: {len(tgts)}")
    if not (DO_TAG or DO_TRACE):
        for c, u in tgts.items():
            print(f"  {c}  {u}")
        print("\npass --tag and/or --trace")
        return 0
    rc = 0
    if DO_TAG:
        rc = tag_phase(headers(token()), tgts)
        if rc:
            return rc
    if DO_TRACE:
        rc = asyncio.run(trace_phase(len(tgts)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
