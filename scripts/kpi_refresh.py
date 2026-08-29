"""Nightly KPI ledger top-up for the daily email's PHONES THIS WEEK section.

1. Validates the kpi-engine skill's saved DataSift token (~48h life); if dead,
   logs in headlessly (same login path the uploader uses) and saves a fresh one.
2. Pulls the trailing 3 days of call activity (called records only) and upserts
   output/kpi_daily_ledger.csv via scripts/weekly_kpis.py.

Called best-effort from daily_report.py (KPI_EMAIL=0 skips it there). Safe to
run by hand: python scripts/kpi_refresh.py [--days N]
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

TOKEN_FILE = ROOT / ".claude" / "skills" / "kpi-engine" / "scripts" / "reisift_token.txt"


def token_alive(tok: str) -> bool:
    import requests
    h = {"accept": "application/json", "authorization": f"Bearer {tok}",
         "origin": "https://app.reisift.io", "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0"}
    try:
        return requests.get("https://apiv2.reisift.io/api/internal/user/",
                            headers=h, timeout=20).status_code == 200
    except Exception:
        return False


def fresh_token_via_login() -> str | None:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="trailing days to re-pull (default 3)")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    tok = TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else ""
    if not tok or not token_alive(tok):
        print("[kpi] token dead — headless login for a fresh one", file=sys.stderr)
        tok = fresh_token_via_login()
        if not tok:
            print("[kpi] login failed — skipping KPI refresh this run", file=sys.stderr)
            return 1
        TOKEN_FILE.write_text(tok, encoding="utf-8")

    from weekly_kpis import _load_pull_kpis, save_status_vocabulary, upsert_ledger
    tz = ZoneInfo("America/New_York")
    today = datetime.datetime.now(tz).date()
    day_from = (today - datetime.timedelta(days=args.days - 1)).isoformat()
    pk = _load_pull_kpis()
    res = pk.pull(tok, day_from, today.isoformat(), tz, pk.load_benchmarks())
    upsert_ledger(res["daily"])
    save_status_vocabulary(res)
    print(f"[kpi] ledger refreshed for {day_from}..{today}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
