"""Cold-case court check: ask eCourts about stuck rows in ARCHIVED weeks.

WHY THIS EXISTS (2026-09-03, Oren: "should we keep polishing the week longer so
we solve more cases?").

Today the court is asked about a case only while its ISO week is live -- roughly
9 nightly passes for a Monday filing, 3 for a Friday one, then the week is
archived on the Wednesday after it closes and nothing ever asks again (the
30-day window after that hunts Will/Application PDFs only, not the Parties list).

Extending the archive window was the obvious fix and is the WRONG one. An
un-archived week costs ~1h45m of polish EVERY night. Measured over the last 12
nightly runs: average 222 min against a 270-min budget, with two runs already
blowing it (338 min on 8/25, 278 min on 8/31). One extra live week would push
the average to ~327 min, so the budget killer would start chopping the back half
-- workbook, DataSift upload, morning report -- on most nights.

The insight: the expensive part of a polish is re-running GIS / Zillow /
LandPortal on rows that are already finished. Asking the court is the CHEAP part
-- the Parties OData endpoint is free, just throttled. So this job does ONLY the
cheap part, for ONLY the rows that are still stuck.

Scope: rows in archived weeks whose Personal Representative is blank or still
"Heirs of ...", that have a `Case ID (hex)` (without it the court cannot be
asked at all -- see backfill_case_hex_20260903.py). Sized 2026-09-03 at 151
stuck rows, 71 of them already hex-ready.

Runs OUTSIDE the nightly budget -- give it its own Task Scheduler entry (e.g.
weekends, or twice a week) so it never competes with nc_daily_run.bat. It
refuses to start while the nightly is up.

Healed rows are written back to the frozen weekly CSV AND queued for a DataSift
push via queue_pr_push(), so the CRM gets the real contact instead of keeping a
dead "Heirs" placeholder.

    python nc_cold_case_parties.py                     # dry run, shows the queue
    python nc_cold_case_parties.py --apply
    python nc_cold_case_parties.py --apply --max-calls 40 --max-age-days 120
    python nc_cold_case_parties.py --apply --consolidate
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from consolidate_weeks import auto_pick_weekly_files  # noqa: E402
from ecourts_case_api import CaseDetail, CaseDetailClient  # noqa: E402
from iso_week_archive import get_archived_weeks  # noqa: E402
from nightly_guard import refuse_if_nightly  # noqa: E402


def _stuck(r: dict) -> bool:
    pr = (r.get("Personal Representative") or "").strip().lower()
    return (not pr) or pr.startswith("heirs of")


def _age_days(r: dict) -> int:
    s = (r.get("File Date") or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return (datetime.now() - datetime.strptime(s, fmt)).days
        except ValueError:
            continue
    return -1


# See backfill_case_hex_20260903.py: the early weeks' CSVs predate several of
# these columns (Week 21 has 31, no "Match Reason"), and DictWriter drops
# unknown keys silently. Append rather than lose the write.
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


def _dropped_cases() -> set[str]:
    out: set[str] = set()
    try:
        with (REPO / "manual_drops.txt").open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.add(line.replace(",", " ", 1).split(None, 1)[0].upper())
    except OSError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-calls", type=int, default=40,
                    help="Parties calls this run (throttled ~1/min when hot)")
    ap.add_argument("--max-age-days", type=int, default=0,
                    help="skip filings older than this (0 = no limit)")
    ap.add_argument("--consolidate", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if refuse_if_nightly(args.force):
        return 1

    archived = get_archived_weeks()

    def _is_archived(year: int, week: int) -> bool:
        probe = next(iter(archived), None)
        return ((year, week) in archived) if isinstance(probe, tuple) else (week in archived)

    dropped = _dropped_cases()
    files: dict[Path, tuple[list[str], list[dict]]] = {}
    targets: list[tuple[Path, dict, int]] = []
    no_hex = 0
    for (year, week), path in sorted(auto_pick_weekly_files(include_archived=True).items()):
        if not _is_archived(year, week):
            continue          # live weeks are already asked every night
        fields, rows = _read(path)
        files[path] = (fields, rows)
        for r in rows:
            if not _stuck(r):
                continue
            if (r.get("Case No.") or "").strip().upper() in dropped:
                continue
            if not (r.get("Case ID (hex)") or "").strip():
                no_hex += 1
                continue
            age = _age_days(r)
            if args.max_age_days and age > args.max_age_days:
                continue
            targets.append((path, r, age))

    # Freshest first: a 3-week-old filing is likelier to have just been
    # appointed than a 15-week-old one, and the call budget is the scarce thing.
    targets.sort(key=lambda t: (t[2] if t[2] >= 0 else 10**6))

    print(f"Archived weeks scanned          : {len(files)}")
    print(f"Stuck rows (blank/'Heirs of' PR): {len(targets) + no_hex}")
    print(f"  askable now (have the hex)    : {len(targets)}")
    print(f"  BLOCKED (no hex)              : {no_hex}"
          f"   <- run backfill_case_hex_20260903.py first")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN (writes nothing)'}"
          f"   budget: {args.max_calls} call(s)\n")
    if not targets:
        return 0

    todo = targets[:args.max_calls]
    if not args.apply:
        for path, r, age in todo[:25]:
            print(f"  would ask {r.get('Case No.'):18} {r.get('County'):13} "
                  f"filed {age:4}d ago  {(r.get('Deceased Owner') or '')[:30]}")
        if len(todo) > 25:
            print(f"  ... and {len(todo) - 25} more this run")
        print("\nDRY RUN -- re-run with --apply.")
        return 0

    waf_path = REPO / "ecourts_waf_cookies.json"
    if not waf_path.exists():
        print("No cached WAF cookie -- run the nightly scrape first.")
        return 1
    import json
    waf = json.loads(waf_path.read_text())
    client = CaseDetailClient(waf_token=waf["aws_waf_token"],
                              user_agent=waf.get("user_agent") or "Mozilla/5.0")

    from fix_addresses_and_prep import queue_pr_push

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    healed = benes = silent = failed = 0
    by_age: dict[str, int] = {}
    for i, (path, r, age) in enumerate(todo, 1):
        case = (r.get("Case No.") or "").strip()
        print(f"  [{i}/{len(todo)}] {case:18} filed {age}d ago")
        try:
            parties = client.fetch_parties((r.get("Case ID (hex)") or "").strip(), retries=3)
        except Exception as e:  # noqa: BLE001
            print(f"      call failed ({type(e).__name__}: {e})")
            failed += 1
            continue
        if not parties:
            silent += 1
            print("      court still names nobody")
            continue
        detail = CaseDetail(case_id=r.get("Case ID (hex)", ""), parties=parties)
        ex = detail.executor
        if ex:
            full = " ".join(filter(None, [ex.first_name, ex.last_name])).strip() or ex.full_name
            if full:
                r["Personal Representative"] = full
                r["First Name"], r["Last Name"] = ex.first_name, ex.last_name
                addr = ex.first_address
                # Never blank over an existing value.
                if not addr.is_blank():
                    line = " ".join(filter(None, [addr.line1, addr.line2])).strip()
                    if line:
                        r["Mailing Address"] = line
                    for key, val in (("Mailing City", addr.city),
                                     ("Mailing State", addr.state),
                                     ("Mailing Zip", addr.zip)):
                        if val:
                            r[key] = val
                mr = (r.get("Match Reason") or "").strip()
                if "cold-case-parties" not in mr:
                    r["Match Reason"] = (mr + " | " if mr else "") + "cold-case-parties"
                healed += 1
                bucket = ("<=30d" if age <= 30 else "31-60d" if age <= 60
                          else "61-90d" if age <= 90 else ">90d")
                by_age[bucket] = by_age.get(bucket, 0) + 1
                print(f"      *** PR {full}  @ {r.get('Mailing Address', '')}")
                queue_pr_push(r)
        if not (r.get("Beneficiaries") or "").strip():
            names = [p.full_name for p in parties if p.full_name and p is not ex]
            if names:
                r["Beneficiaries"] = "; ".join(dict.fromkeys(names))
                benes += 1
        if i % 5 == 0:
            for p, (f, rws) in files.items():
                _write(p, f, rws)
        time.sleep(2)

    for p, (f, rws) in files.items():
        bak = p.with_suffix(p.suffix + f".bak_{stamp}")
        if not bak.exists():
            shutil.copy2(p, bak)
        _write(p, f, rws)

    asked = len(todo)
    print(f"\nasked {asked}  ->  {healed} PR(s) recovered, {benes} beneficiary "
          f"fill(s), {silent} still nameless, {failed} call failure(s)")
    if asked:
        print(f"YIELD: {healed / asked:.0%} of cold cases the court can now name.")
    if by_age:
        print("by filing age:", ", ".join(f"{k}={v}" for k, v in sorted(by_age.items())))
    print(f"\nBackups: *.bak_{stamp}")
    if healed:
        print("Healed contacts queued for DataSift -- run: "
              "python pr_upgrade_step.py --queued")
    if args.consolidate:
        import subprocess
        print("\nRebuilding workbook...")
        rr = subprocess.run([sys.executable, "consolidate_weeks.py"], cwd=str(REPO),
                            capture_output=True, text=True)
        print(rr.stdout[-1200:] or rr.stderr[-1200:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
