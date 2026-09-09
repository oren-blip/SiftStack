"""Retire finished "Needs DP" markers, every night.

The tag is stamped at upload time on any row whose contact is the placeholder
"Heirs of <Decedent>" -- it is the deep-prospecting to-do list, nothing more.
No filter preset references it (checked against all 25 on 2026-09-09), so it
never gates marketing; its only job is telling Oren which estates still have no
identified human.

Until now NOTHING took it off. Court-PR renames (pr_upgrade_step), deep
prospecting pushes, and hand edits in the UI all put a real person on the
record and left the marker and its overdue task behind. By 2026-09-09 that was
39 tagged records, 11 of them already owned by a real person -- one with ten
dialable numbers -- and 32 overdue reminders. Oren's call that day: keep it as
a pure to-do marker, and make it clear itself.

This sweep is the catch-all: it does not care WHICH path put the name there.
Every tagged record is re-read, and the marker comes off only where a real
contact now exists. A record still owned by "Heirs X" keeps its tag -- that is
the deliberate hold under the court-PR-beats-DP-guess rule, and stripping it
there would push a placeholder into a call queue.

    python needs_dp_sweep.py             # read-only, prints what it would do
    python needs_dp_sweep.py --apply     # clear them

Off-switch for the nightly:  set NC_NEEDS_DP_SWEEP=0
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import logging
import os
import sys
from pathlib import Path

import requests

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from needs_dp_clear import (  # noqa: E402
    API, NEEDS_DP_TAG, clear, get_property, is_placeholder, open_tasks, owner_name,
)

logger = logging.getLogger("needs_dp_sweep")
OUT = REPO / "output" / "needs_dp_sweep_last.csv"


def _headers(tok: str) -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7",
            "authorization": f"Bearer {tok}", "content-type": "application/json"}


def _token() -> str:
    """DS_TOKEN if set, else a Playwright login (the repo's usual fallback)."""
    tok = (os.environ.get("DS_TOKEN") or "").strip().strip('"')
    if tok:
        return tok
    from datasift_uploader import login
    from playwright.async_api import async_playwright

    async def go() -> str:
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            page = await (await b.new_context()).new_page()
            try:
                ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                                 os.environ.get("DATASIFT_PASSWORD", ""))
                return (await page.evaluate("() => localStorage.getItem('rs_token')")
                        if ok else "") or ""
            finally:
                await b.close()
    return asyncio.run(go())


def _tag_uuid(h: dict, title: str) -> str:
    # The tag list paginates at 10 unless a limit is passed -- the same trap
    # that made the status endpoint look like it held 10 of its 28 rows.
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"limit": 500}, timeout=30)
    r.raise_for_status()
    for t in (r.json().get("results") or r.json().get("data") or []):
        if (t.get("title") or "") == title:
            return t["uuid"]
    raise RuntimeError(f"tag {title!r} not found")


def _tagged(h: dict, tag_id: str) -> list[dict]:
    out, offset = [], 0
    while True:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"limit": 200, "offset": offset,
                                "query": {"must": {"any_tags": [tag_id]}}},
                          timeout=60)
        r.raise_for_status()
        rows = r.json().get("results", [])
        out.extend(rows)
        if len(rows) < 200:
            return out
        offset += 200


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually clear (default is a read-only preview)")
    args = ap.parse_args()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    tok = _token()
    if not tok:
        logger.error("Needs DP sweep: DataSift login failed — skipped.")
        return 1
    h = _headers(tok)
    try:
        recs = _tagged(h, _tag_uuid(h, NEEDS_DP_TAG))
    except (requests.RequestException, RuntimeError, ValueError) as e:
        logger.error("Needs DP sweep: could not list tagged records (%s) — skipped.", e)
        return 1

    logger.info("Needs DP sweep: %d record(s) carry the marker.", len(recs))
    cleared, held, problems, rows = 0, 0, 0, []
    for rec in recs:
        uuid = rec.get("uuid")
        if not uuid:
            continue
        live = get_property(h, uuid)
        if live is None:
            logger.warning("  could not read record %s — left alone", uuid[:8])
            problems += 1
            continue
        name = owner_name(live)
        street = ((live.get("address") or {}).get("street") or "").strip()
        if is_placeholder(name) or not name:
            held += 1
            continue
        changed, why = clear(h, uuid, dry_run=not args.apply)
        logger.info("  %-34s %s", street[:34], why)
        rows.append({"uuid": uuid, "street": street, "owner": name,
                     "action": "cleared" if changed else "preview" if not args.apply else "FAILED",
                     "detail": why})
        if changed:
            cleared += 1
        elif args.apply:
            problems += 1

    if rows:
        with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    still_open = sum(len(open_tasks(h, r["uuid"])) for r in recs
                     if r.get("uuid") and is_placeholder(owner_name(r)))
    verb = "cleared" if args.apply else "would clear"
    logger.info("Needs DP sweep %s: %d %s, %d still awaiting research"
                "%s. (%s)", dt.date.today().isoformat(), cleared, verb, held,
                f", {problems} problem(s)" if problems else "",
                f"{still_open} open task(s) on the research queue")
    if not args.apply and cleared == 0 and rows:
        logger.info("  read-only preview — re-run with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
