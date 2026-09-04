"""Backfill the missing `Case ID (hex)` so the court can be asked about old rows.

THE GAP (found 2026-09-03): 360 workbook rows carry a Case No. but no
`Case ID (hex)` -- 79 of them still "Heirs of". The hex is Odyssey's internal
256-char record id, and it is the ONLY key the Parties OData endpoint accepts
(`Parties('{hex}')`). `backfill_pr_from_parties` in fix_addresses_and_prep.py
requires it:

    targets = [r for r in rows if _blank_pr(r) and (r.get("Case ID (hex)") or "").strip()]

So a row without the hex has NEVER been asked about and never will be, no matter
how many nights it sits there. 60 of the 79 are Week 21, the founding backfill
week that predates hex capture.

backfill_case_numbers_from_ecourts.py already extracts the hex during its search
-- but it only runs on BLANK-Case-No rows and never writes the hex to the column.
This closes that hole from the other side.

Search method: by CASE NUMBER, not decedent name. Tyler's Smart Search field is
"Record Number or Name", and a case-number search returns exactly one row (probed
2026-09-03 on 3 counties, 1/1 each). That avoids the name search's status=Pending
filter and date window, both of which are wrong for old cases now Disposed.

Two phases:
  1. hex backfill  -- portal search per case, writes `Case ID (hex)`
  2. PR upgrade    -- Parties OData for rows still "Heirs of", fills PR +
                      mailing + Beneficiaries. Throttled and budgeted; hex is
                      saved first so a re-run resumes for free.

    python backfill_case_hex_20260903.py                    # dry run
    python backfill_case_hex_20260903.py --apply
    python backfill_case_hex_20260903.py --apply --all-rows --parties-max 40
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from playwright.async_api import async_playwright  # noqa: E402

from consolidate_weeks import auto_pick_weekly_files  # noqa: E402
from ecourts_case_api import CaseDetail, CaseDetailClient  # noqa: E402
from ecourts_scraper import (  # noqa: E402
    CASE_TYPE_BY_NOTICE_TYPE, PORTAL_URL, SMART_SEARCH_URL, _DEFAULT_UA,
    _is_waf_gate, _load_cached_waf_cookie, _navigate_to_smart_search,
    _open_advanced_filters, _parse_results, _select_only_county,
    _set_case_type, _set_date_range, _set_search_criteria,
    _solve_and_inject_waf, _submit_search,
)

WIDE_START, WIDE_END = "01/01/2024", "12/31/2026"


def _is_heirs(r: dict) -> bool:
    return ((r.get("First Name") or "").strip().lower() == "heirs"
            or (r.get("Personal Representative") or "").strip().lower().startswith("heirs of"))


# Columns this script writes. The early weeks predate most of them -- Week 21's
# CSV has 31 columns and NO "Case ID (hex)" or "Match Reason" at all. csv
# DictWriter(extrasaction="ignore") drops unknown keys SILENTLY, so the first
# run of this script recovered 58 hex ids and threw every one away on write --
# on precisely the week that needed them most (60 of the 79 targets). Any
# missing column is appended to the header instead.
_WRITES = ("Case ID (hex)", "Personal Representative", "First Name", "Last Name",
           "Mailing Address", "Mailing City", "Mailing State", "Mailing Zip",
           "Beneficiaries", "Match Reason")


def _read(p: Path) -> tuple[list[str], list[dict]]:
    with p.open(newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        fields, rows = list(r.fieldnames or []), list(r)
    added = [c for c in _WRITES if c not in fields]
    if added:
        fields += added
        for row in rows:
            for c in added:
                row.setdefault(c, "")
        print(f"  ({p.name}: added missing column(s) {', '.join(added)})")
    return fields, rows


def _write(p: Path, fields: list[str], rows: list[dict]) -> None:
    with p.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_MINIMAL,
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


async def _lookup_hex(page, county: str, case_no: str) -> str:
    """One Smart Search by case number. Returns the hex, or ''."""
    await page.goto(SMART_SEARCH_URL, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(1200)
    await _open_advanced_filters(page)
    try:
        await _set_search_criteria(page, case_no)
        await _set_case_type(page, CASE_TYPE_BY_NOTICE_TYPE["probate"])
        # Deliberately NO status filter: Week-21 cases have moved to Disposed.
        await _set_date_range(page, WIDE_START, WIDE_END)
        await _select_only_county(page, county)
        if not await _submit_search(page):
            return ""
        results = await _parse_results(page, county, "probate")
    except Exception as e:  # noqa: BLE001
        print(f"      search failed ({type(e).__name__}: {e})")
        return ""
    want = case_no.strip().upper()
    for n in results:
        if (n.case_number or "").strip().upper() == want:
            return getattr(n, "_roa_id", "") or ""
    if results:
        print(f"      {len(results)} result(s) but none matched {case_no}")
    return ""


def _nightly_running() -> str:
    """The nightly build owns eCourts AND rewrites these same weekly CSVs.

    Learned the hard way 2026-09-03: this script ran at 17:00, the exact minute
    nc_daily_run.bat started its scrape, and the portal stopped rendering Smart
    Search after 4 attempts -- Odyssey is IP-throttled and the nightly had the
    session. Worse, both processes write the picked weekly CSVs. Refuse rather
    than race.

    NOT via pipeline_lock's `pid_alive`: nc_daily_run.bat re-execs itself under
    scripts/keep_awake.py, so the pid recorded in the lock is the ORIGINAL
    cmd.exe, which exits immediately. The lock read reports pid_alive=false
    while the run is very much alive. The log is authoritative instead: a
    "started" line with no matching "done" line after it means still running.
    """
    log = REPO / "logs" / "nc_daily_run.log"
    if not log.exists():
        return ""
    try:
        text = log.read_bytes()[-400_000:].decode("ascii", "replace")
    except OSError:
        return ""
    last_start = text.rfind("=== Daily run started")
    if last_start < 0:
        return ""
    tail = text[last_start:]
    if "=== Daily run done" in tail or "Daily run aborted" in tail \
            or "Daily run skipped" in tail:
        return ""
    line = tail.split("\n", 1)[0].strip()
    return f"nightly build still running -- {line}"


async def main_async(args) -> int:
    busy = _nightly_running()
    if busy and not args.force:
        print(f"REFUSING TO RUN: {busy}")
        print("The nightly build owns the eCourts session and rewrites these "
              "same CSVs.\nWait for it to finish (usually ~3h) or pass --force.")
        return 1

    picked = auto_pick_weekly_files(include_archived=True)
    files: dict[Path, tuple[list[str], list[dict]]] = {}
    targets: list[tuple[Path, dict]] = []
    for (_y, _w), path in sorted(picked.items()):
        fields, rows = _read(path)
        files[path] = (fields, rows)
        for r in rows:
            if (r.get("Case No.") or "").strip() and not (r.get("Case ID (hex)") or "").strip():
                if args.all_rows or _is_heirs(r):
                    targets.append((path, r))

    scope = "all rows" if args.all_rows else "Heirs rows only"
    print(f"Weeks scanned            : {len(files)}")
    print(f"Rows missing Case ID(hex): {len(targets)}  ({scope})")
    if args.limit:
        targets = targets[:args.limit]
        print(f"Limited to               : {len(targets)}")
    mode = "APPLY" if args.apply else "DRY RUN (writes nothing)"
    print(f"Mode                     : {mode}\n")
    if not targets:
        return 0
    if not args.apply:
        for path, r in targets[:20]:
            print(f"  would look up {r.get('Case No.'):18} {r.get('County'):13} "
                  f"{(r.get('Deceased Owner') or '')[:34]}")
        if len(targets) > 20:
            print(f"  ... and {len(targets) - 20} more")
        print("\nDRY RUN -- re-run with --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    found = 0
    waf_token, ua = "", _DEFAULT_UA

    # -- Phase 1: hex via portal case-number search ------------------------
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                        user_agent=_DEFAULT_UA)
        cached = _load_cached_waf_cookie()
        if cached:
            await ctx.close()
            ua = cached.get("user_agent") or _DEFAULT_UA
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                            user_agent=ua)
            await ctx.add_cookies([{
                "name": "aws-waf-token", "value": cached["aws_waf_token"],
                "domain": ".tylertech.cloud", "path": "/", "httpOnly": False,
                "secure": True, "sameSite": "Lax"}])
        ctx.set_default_timeout(60_000)
        page = await ctx.new_page()
        # The portal intermittently stalls on first load (2026-09-03 run 1 died
        # here after a clean probe minutes earlier). Retry rather than lose the
        # whole pass.
        for attempt in range(1, 4):
            try:
                await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  portal load attempt {attempt}/3 failed ({type(e).__name__})")
                if attempt == 3:
                    raise
                await page.wait_for_timeout(5000)
        await page.wait_for_timeout(2000)
        if await _is_waf_gate(page):
            print("WAF gate -- solving via CapSolver")
            ctx, page = await _solve_and_inject_waf(browser, ctx, page)
        await _navigate_to_smart_search(page)
        cookies = await ctx.cookies("https://portal-nc.tylertech.cloud/")
        wc = next((c for c in cookies if c["name"] == "aws-waf-token"), None)
        waf_token = wc["value"] if wc else ""

        print("-- Phase 1: hex lookup --")
        for i, (path, r) in enumerate(targets, 1):
            case_no = (r.get("Case No.") or "").strip()
            county = (r.get("County") or "").strip()
            print(f"  [{i}/{len(targets)}] {case_no:18} {county:13} "
                  f"{(r.get('Deceased Owner') or '')[:30]}")
            hexid = await _lookup_hex(page, county, case_no)
            if hexid:
                r["Case ID (hex)"] = hexid
                found += 1
                print(f"      -> hex {hexid[:24]}...")
            else:
                print("      -> not found in eCourts")
            if i % 10 == 0:   # checkpoint so a crash never loses progress
                for p, (f, rws) in files.items():
                    _write(p, f, rws)
        await browser.close()

    for p, (f, rws) in files.items():
        bak = p.with_suffix(p.suffix + f".bak_{stamp}")
        if not bak.exists():
            shutil.copy2(p, bak)
        _write(p, f, rws)
    print(f"\nPhase 1 done: {found}/{len(targets)} hex ids recovered.\n")

    # -- Phase 2: ask the court for a PR now that we can -------------------
    upgradable = [(p, r) for p, r in targets
                  if (r.get("Case ID (hex)") or "").strip() and _is_heirs(r)]
    upgradable = upgradable[:args.parties_max]
    print(f"-- Phase 2: Parties API for {len(upgradable)} newly-reachable "
          f"'Heirs of' row(s) (budget {args.parties_max}) --")
    if not waf_token:
        print("  no WAF token -- skipping Parties phase (re-run to retry)")
    else:
        client = CaseDetailClient(waf_token=waf_token, user_agent=ua)
        upgraded = benes = 0
        for i, (path, r) in enumerate(upgradable, 1):
            case_no = (r.get("Case No.") or "").strip()
            print(f"  [{i}/{len(upgradable)}] {case_no}")
            try:
                parties = client.fetch_parties((r.get("Case ID (hex)") or "").strip(),
                                               retries=3)
            except Exception as e:  # noqa: BLE001
                print(f"      Parties failed ({type(e).__name__}: {e})")
                continue
            if not parties:
                print("      no parties returned")
                continue
            detail = CaseDetail(case_id=r.get("Case ID (hex)", ""), parties=parties)
            ex = detail.executor
            if ex:
                full = " ".join(filter(None, [ex.first_name, ex.last_name])).strip() or ex.full_name
                if full:
                    r["Personal Representative"] = full
                    r["First Name"] = ex.first_name
                    r["Last Name"] = ex.last_name
                    addr = ex.first_address
                    # Never blank over an existing value
                    # (project_pr_upgrade_silent_save_failure).
                    if not addr.is_blank():
                        line = " ".join(filter(None, [addr.line1, addr.line2])).strip()
                        if line:
                            r["Mailing Address"] = line
                        if addr.city:
                            r["Mailing City"] = addr.city
                        if addr.state:
                            r["Mailing State"] = addr.state
                        if addr.zip:
                            r["Mailing Zip"] = addr.zip
                    mr = (r.get("Match Reason") or "").strip()
                    if "hex-backfill-parties" not in mr:
                        r["Match Reason"] = (mr + "; " if mr else "") + "hex-backfill-parties"
                    upgraded += 1
                    print(f"      *** PR: {full}  @ {r.get('Mailing Address', '')}")
                    # A healed contact that is only local never reaches the CRM
                    # on its own -- the upload ledger blocks re-upload, so the
                    # record keeps its old (often WRONG) owner forever. The
                    # first run of this script healed 15 and queued none of
                    # them, which is exactly why Oren "wasn't seeing new court
                    # PRs in the workflow". Consumer: pr_upgrade_step --queued.
                    try:
                        from fix_addresses_and_prep import queue_pr_push
                        queue_pr_push(r)
                    except Exception as e:  # noqa: BLE001
                        print(f"      (queue failed: {e})")
            if not (r.get("Beneficiaries") or "").strip():
                names = [p.full_name for p in parties if p.full_name and p is not ex]
                if names:
                    r["Beneficiaries"] = "; ".join(dict.fromkeys(names))
                    benes += 1
                    print(f"      benes: {r['Beneficiaries'][:80]}")
            if i % 5 == 0:
                for p, (f, rws) in files.items():
                    _write(p, f, rws)
            time.sleep(2)
        for p, (f, rws) in files.items():
            _write(p, f, rws)
        print(f"\nPhase 2 done: {upgraded} PR upgrade(s), {benes} beneficiary fill(s).")

    print(f"\nBackups: *.bak_{stamp}")
    if args.consolidate:
        import subprocess
        print("\nRebuilding workbook...")
        rr = subprocess.run([sys.executable, "consolidate_weeks.py"], cwd=str(REPO),
                            capture_output=True, text=True)
        print(rr.stdout[-1500:] or rr.stderr[-1500:])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all-rows", action="store_true",
                    help="every row missing the hex, not just 'Heirs of' ones")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parties-max", type=int, default=25,
                    help="Parties calls this run (throttled ~1/min when hot)")
    ap.add_argument("--consolidate", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="run even while the nightly pipeline lock is held")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
