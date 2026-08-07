"""Track DataSift skip-trace spend against the $97/mo unlimited-plan threshold.

WHY: the account is on Professional ($149/mo) with NO skip-trace add-on, so every
skip trace is billed per record against a prepaid balance. DataSift exposes no
usage report, so spend is derived by sampling the balance (`user/` API) over time:
a DROP in balance is spend; a RISE is a top-up (recorded, not counted as spend).

Oren's standing ask: tell him when the MONTHLY run-rate approaches $97 — that is
the price of the unlimited add-on, above which upgrading is the cheaper option.

Usage:
    python skiptrace_spend.py              # sample the balance + print the report
    python skiptrace_spend.py --report     # print the report without sampling
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "src")
import requests
from dotenv import load_dotenv

load_dotenv()

LEDGER = Path("output") / ".skiptrace_spend.json"
UNLIMITED_PLAN_COST = 97.0
API = "https://apiv2.reisift.io/api/internal/user/"


def _token() -> str | None:
    """Fresh token from a headless login (same path the uploader uses)."""
    import asyncio
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                             os.environ.get("DATASIFT_PASSWORD", ""))
            tok = await page.evaluate("() => localStorage.getItem('rs_token')") if ok else None
            await b.close()
            return tok
    return asyncio.run(go())


def _balance(tok: str) -> float | None:
    h = {"Accept": "application/json", "Authorization": f"Bearer {tok}",
         "X-REISIFT-UI-VERSION": "2022.02.01.7"}
    try:
        return float(requests.get(API, headers=h, timeout=25).json().get("balance"))
    except Exception as e:  # noqa: BLE001
        print(f"balance read failed: {e}")
        return None


def _load() -> list[dict]:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8")).get("samples", [])
    except (OSError, ValueError):
        return []


def _save(samples: list[dict]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"samples": samples}, indent=1), encoding="utf-8")
    tmp.replace(LEDGER)


def report(samples: list[dict]) -> None:
    if len(samples) < 2:
        print("Not enough samples yet — run this after each skip trace to build history.")
        if samples:
            print(f"  latest balance: ${samples[-1]['balance']:.2f} at {samples[-1]['ts']}")
        return
    month = datetime.now().strftime("%Y-%m")
    spend = topups = 0.0
    for a, b in zip(samples, samples[1:]):
        if not b["ts"].startswith(month):
            continue
        d = a["balance"] - b["balance"]
        if d > 0:
            spend += d
        else:
            topups += -d
    first = datetime.fromisoformat(samples[0]["ts"])
    days = max(1, (datetime.now() - max(first, datetime.now().replace(day=1))).days)
    projected = spend / days * 30 if days else spend
    bal = samples[-1]["balance"]

    print(f"\n=== DataSift skip-trace spend — {month} ===")
    print(f"  current balance   : ${bal:.2f}")
    print(f"  spent this month  : ${spend:.2f}   (top-ups seen: ${topups:.2f})")
    print(f"  projected 30-day  : ${projected:.2f}")
    print(f"  unlimited add-on  : ${UNLIMITED_PLAN_COST:.2f}/mo")
    if projected >= UNLIMITED_PLAN_COST:
        print("  >>> AT/OVER THE LINE — the $97 unlimited add-on is now the CHEAPER option.")
    elif projected >= UNLIMITED_PLAN_COST * 0.75:
        print("  >>> APPROACHING $97 (75%+) — tell Oren; upgrading is close to worthwhile.")
    else:
        pct = projected / UNLIMITED_PLAN_COST * 100 if UNLIMITED_PLAN_COST else 0
        print(f"  >>> well under the line ({pct:.0f}% of $97) — stay on pay-per-record.")
    if bal < 10:
        print(f"  !!! BALANCE LOW (${bal:.2f}) — top up or skip traces will start failing.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="report only, don't sample")
    ap.add_argument("--note", default="", help="label this sample (e.g. 'after wk32 trace')")
    args = ap.parse_args()
    samples = _load()
    if not args.report:
        tok = _token()
        if not tok:
            print("could not log in — no sample taken")
            report(samples)
            return
        bal = _balance(tok)
        if bal is None:
            report(samples)
            return
        samples.append({"ts": datetime.now().isoformat(timespec="seconds"),
                        "balance": bal, "note": args.note})
        _save(samples)
        print(f"sampled: ${bal:.4f}  {args.note}")
    report(samples)


if __name__ == "__main__":
    main()
