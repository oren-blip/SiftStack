"""Weekly KPI rollup on top of the kpi-engine skill's pull_kpis.py.

Runs ONE pull over the whole date range (each worked record's activity log is
read once), then:
  1. Upserts per-day rows into output/kpi_daily_ledger.csv  — the daily email
     reads this ledger so it never has to re-pull DataSift itself.
  2. Renders a by-ISO-week markdown report (output/kpi_weekly_<from>_<to>.md).

Usage:
    python scripts/weekly_kpis.py --from 2026-01-01              # since January
    python scripts/weekly_kpis.py --refresh-days 3               # nightly ledger top-up (fast)

Token: the kpi-engine skill's reisift_token.txt (~48h). Refresh headlessly with
the same login the uploader uses if it has expired (see scripts/kpi_refresh.py).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = ROOT / ".claude" / "skills" / "kpi-engine" / "scripts"
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
LEDGER = ROOT / "output" / "kpi_daily_ledger.csv"

LEDGER_FIELDS = ["day", "dials", "answered", "noanswer", "conversations",
                 "meaningful_conversations", "correct_numbers", "wrong_numbers",
                 "dead_numbers", "dnc_numbers", "leads", "not_interested",
                 "follow_ups", "appointments", "talk_seconds", "sms_sent",
                 "sms_received", "records_touched"]


def _load_pull_kpis(called_only: bool = True):
    spec = importlib.util.spec_from_file_location("pull_kpis", SKILL_SCRIPTS / "pull_kpis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if called_only:
        # The account has ~20K records "updated" since January (pipeline tag
        # patches, sold-sweep, uploads) but only ~2.5K that were ever CALLED.
        # Restrict candidates to attempts>=1 so we don't read 20K activity
        # logs to find the phone work. Filter key learned from the account's
        # own filter presets: predictivecall_attempts [min, max|null].
        import time as _time

        def search_called(token, day_from, day_to_excl):
            out, offset, limit = [], 0, 200
            while True:
                body = {"limit": limit, "offset": offset, "ordering": "-list_count",
                        "query": {"must": {"property_type": "clean",
                                           "updated": [day_from, day_to_excl],
                                           "predictivecall_attempts": [1, None]}}}
                for attempt in range(3):  # the API 400s transiently sometimes
                    try:
                        r = mod.req(token, "/api/internal/property/", method="POST",
                                    body=body, method_override="GET")
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        _time.sleep(5 * (attempt + 1))
                rows = r.get("results") or r.get("data") or []
                out.extend(rows)
                total = r.get("count", len(out))
                offset += limit
                if offset >= total or not rows or offset > 20000:
                    break
            return out

        mod.search_updated = search_called
    return mod


def load_ledger() -> dict[str, dict]:
    rows = {}
    if LEDGER.exists():
        with open(LEDGER, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r["day"]] = r
    return rows


def upsert_ledger(daily: dict[str, dict], covered_from: str = "", covered_to: str = "") -> None:
    """Write the pulled days into the ledger. Days inside [covered_from,
    covered_to] with no activity get a zero row, so the ledger's last day is
    the last day the refresh actually looked at (a quiet weekend is not a
    missed refresh)."""
    rows = load_ledger()
    if covered_from and covered_to:
        day = datetime.date.fromisoformat(covered_from)
        end = datetime.date.fromisoformat(covered_to)
        daily = dict(daily)
        while day <= end:
            daily.setdefault(day.isoformat(), {})
            day += datetime.timedelta(days=1)
    for day, d in daily.items():
        rows[day] = {"day": day, **{f: int(d.get(f, 0) or 0) for f in LEDGER_FIELDS[1:]}}
        # pull_kpis keeps the day's touched records as a set; the ledger stores the count
        rows[day]["records_touched"] = len(d.get("records") or ())
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for day in sorted(rows):
            w.writerow({f: rows[day].get(f, 0) for f in LEDGER_FIELDS})


def week_key(day: str) -> tuple[int, int]:
    d = datetime.date.fromisoformat(day)
    iso = d.isocalendar()
    return (iso.year, iso.week)


def week_bounds(year: int, week: int) -> tuple[str, str]:
    mon = datetime.date.fromisocalendar(year, week, 1)
    return mon.isoformat(), (mon + datetime.timedelta(days=6)).isoformat()


def fmt_hms(sec: int) -> str:
    h, r = divmod(int(sec), 3600)
    m, _ = divmod(r, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def pct(n, d) -> str:
    return f"{n / d * 100:.0f}%" if d else "-"


def weekly_rollup(daily_rows: dict[str, dict]) -> list[dict]:
    weeks: dict[tuple[int, int], dict] = defaultdict(
        lambda: {**{f: 0 for f in LEDGER_FIELDS[1:]}, "dial_days": 0})
    for day, d in daily_rows.items():
        wk = weeks[week_key(day)]
        for f in LEDGER_FIELDS[1:]:
            wk[f] += int(d.get(f, 0) or 0)
        if int(d.get("dials", 0) or 0) > 0:
            wk["dial_days"] += 1
    out = []
    for (y, w) in sorted(weeks):
        mon, sun = week_bounds(y, w)
        out.append({"year": y, "week": w, "from": mon, "to": sun, **weeks[(y, w)]})
    return out


def render_weekly_md(weeks: list[dict], day_from: str, day_to: str) -> str:
    """By-ISO-week table in Ty's vocabulary (correct numbers are the KPI), then
    the whole range against his August-2026 benchmarks and the deal math."""
    from collections import Counter
    import kpi_model as km

    def text_for(wk: dict) -> dict:
        return km.text_channel(datetime.date.fromisoformat(wk["from"]),
                               datetime.date.fromisoformat(wk["to"]))

    lines = [f"# Weekly KPIs, {day_from} to {day_to}", "",
             "Correct numbers are the KPI (Ty, Day 5): every ~20 right-party contacts on "
             "first-to-market data is a deal inside 6 months. Conv% = calls of 60s+ per dial. "
             "'via text' = numbers the owner confirmed by replying to a text (from the SMS agent, "
             "Aug 25 2026 on).", "",
             "| Wk | Mon-Sun | Days | Dials | Ans% | Conv% | Correct | via text | Dials/corr | "
             "Wrong+dead | NI | Leads | Texts out/in | Talk |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for wk in weeks:
        for f in LEDGER_FIELDS[1:]:
            tot[f] += wk[f]
        tot["dial_days"] += wk["dial_days"]
        tx = text_for(wk)
        via = (str(tx["right_party"]) if tx["available"] and (wk["correct_numbers"] or tx["right_party"])
               else "-")
        replies = wk["sms_received"] or (tx["replies"] if tx["available"] else 0)
        dpc = f"{wk['dials'] / wk['correct_numbers']:.1f}" if wk["correct_numbers"] else "-"
        lines.append(
            f"| W{wk['week']:02d} | {wk['from'][5:]} to {wk['to'][5:]} | {wk['dial_days']} | {wk['dials']} | "
            f"{pct(wk['answered'], wk['dials'])} | {pct(wk['conversations'], wk['dials'])} | "
            f"**{wk['correct_numbers']}** | {via} | {dpc} | "
            f"{wk['wrong_numbers'] + wk['dead_numbers']} | {wk['not_interested']} | {wk['leads']} | "
            f"{wk['sms_sent']}/{replies} | {fmt_hms(wk['talk_seconds'])} |")

    t = tot
    d_from, d_to = datetime.date.fromisoformat(day_from), datetime.date.fromisoformat(day_to)
    tx_all = km.text_channel(d_from, d_to)
    dpc_all = f"{t['dials'] / t['correct_numbers']:.1f}" if t["correct_numbers"] else "-"
    per_day = f" ({t['dials'] / t['dial_days']:.0f}/day)" if t["dial_days"] else ""
    lines += ["",
              f"**Totals:** {t['dials']} dials over {t['dial_days']} dial days{per_day}, "
              f"{t['answered']} answered ({pct(t['answered'], t['dials'])}), "
              f"{t['conversations']} conversations ({pct(t['conversations'], t['dials'])} of dials), "
              f"**{t['correct_numbers']} correct numbers** ({dpc_all} dials each), "
              f"{t['wrong_numbers'] + t['dead_numbers']} wrong/dead, {t['not_interested']} not interested, "
              f"{t['leads']} leads, talk {fmt_hms(t['talk_seconds'])}, "
              f"{t['sms_sent']} texts out / {t['sms_received'] or tx_all.get('replies', 0)} in."]

    lines += ["", "## Vs Ty's August-2026 benchmarks (whole range)", "",
              "| Metric | You | Ty | Read it as |", "|---|---|---|---|"]
    for metric, you, ty, read in km.vs_ty_rows(t, tx_all, {}):
        lines.append(f"| {metric} | **{you}** | {ty} | {read} |")

    lines += ["", "## Deal math (whole range)", ""]
    for line in km.deal_math(t, tx_all):
        lines.append(f"- {line}")
    lines += ["", "Definitions: a correct number is a phone whose final status in the window is "
              "CORRECT (set by the caller, or by the SMS agent when the owner replies). A lead is a "
              "record whose final status in the window is a lead status. Statuses are counted by "
              "final state, so a lead later marked not-interested inside one pull counts once, as NI."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly KPI rollup (uses kpi-engine skill)")
    ap.add_argument("--from", dest="day_from", default="2026-01-01")
    ap.add_argument("--to", dest="day_to")
    ap.add_argument("--refresh-days", type=int, metavar="N",
                    help="only pull the trailing N days and upsert the ledger (nightly mode)")
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--ledger-only", action="store_true",
                    help="no pull; re-render the weekly report from the existing ledger")
    args = ap.parse_args()

    tz = ZoneInfo(args.tz)
    today = datetime.datetime.now(tz).date()
    day_to = args.day_to or today.isoformat()
    day_from = args.day_from
    if args.refresh_days:
        day_from = (today - datetime.timedelta(days=args.refresh_days - 1)).isoformat()

    if args.ledger_only:
        rows = load_ledger()
        rows = {d: r for d, r in rows.items() if day_from <= d <= day_to}
    else:
        pk = _load_pull_kpis()
        token = pk.get_token()
        res = pk.pull(token, day_from, day_to, tz, pk.load_benchmarks())
        upsert_ledger(res["daily"], day_from, day_to)
        print(f"[ledger] upserted {len(res['daily'])} day(s) into {LEDGER}", file=sys.stderr)
        if args.refresh_days:
            return 0  # nightly mode: ledger update is the whole job
        rows = {d: r for d, r in load_ledger().items() if day_from <= d <= day_to}

    weeks = weekly_rollup(rows)
    md = render_weekly_md(weeks, day_from, day_to)
    out = ROOT / "output" / f"kpi_weekly_{day_from}_{day_to}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[saved] {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
