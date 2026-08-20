"""Q5 finalize: regenerate the NSM step-10 DP report from the MERGED
results.json (pilot 12 + full run), and append dp_log rows for entries not
yet logged. Idempotent — safe to rerun.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(r"d:\SiftStack")
RESULTS = REPO / "output" / "dp_nsm10_20260819" / "results.json"
REPORT = REPO / "output" / "reports" / "DP_NSM10_NoResponse_20260819.md"
DP_LOG = REPO / "dp_log.csv"

CITY_COUNTY = {"Conover": "Catawba", "Hickory": "Catawba", "Claremont": "Catawba",
    "Newton": "Catawba", "Maiden": "Catawba", "Catawba": "Catawba", "Terrell": "Catawba",
    "Gastonia": "Gaston", "Dallas": "Gaston", "Stanley": "Gaston", "Belmont": "Gaston",
    "Mount Holly": "Gaston", "Cherryville": "Gaston", "Salisbury": "Rowan",
    "China Grove": "Rowan", "Gold Hill": "Rowan", "Woodleaf": "Rowan",
    "Statesville": "Iredell", "Mooresville": "Iredell", "Troutman": "Iredell",
    "Harmony": "Iredell", "Stony Point": "Iredell", "Kannapolis": "Cabarrus",
    "Concord": "Cabarrus", "Harrisburg": "Cabarrus", "Midland": "Cabarrus",
    "Mount Pleasant": "Cabarrus", "Charlotte": "Mecklenburg", "Mint Hill": "Mecklenburg",
    "Huntersville": "Mecklenburg", "Lincolnton": "Lincoln", "Denver": "Lincoln",
    "Vale": "Lincoln"}


def tier(score):
    if score is None:
        return None
    s = int(score)
    if s >= 81:
        return "Dial First"
    if s >= 61:
        return "Dial Second"
    if s >= 41:
        return "Dial Third"
    if s >= 21:
        return "Dial Fourth"
    return None


def county_of(e) -> str:
    city = e["property"].split(",")[-1].strip()
    return e.get("county") or CITY_COUNTY.get(city, "?")


def main() -> int:
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    n_dial = sum(1 for e in res if any(tier(s.get("score"))
                 for s in (e.get("scored") or [])))
    n_miss = sum(1 for e in res if e.get("enformion") is None)
    n_entity = sum(1 for e in res
                   if isinstance(e.get("enformion"), str) and "entity" in e["enformion"])
    n_phones = sum(len(e.get("scored") or []) for e in res)

    lines = ["# DP — NSM Step 10 \"No Response DM --> DP\" (full run, 2026-08-19)", "",
             "Preset: Courthouse Data tag, Probate lists, 6-8 mail attempts, 4+ call",
             "attempts, no phone ever Correct, not Do-Not-Market, no status set.",
             "",
             f"**{len(res)} records DP'd** — {n_dial} got dialable new numbers, "
             f"{n_miss} Enformion misses, {n_entity} entity owners (manual heir research). "
             f"{n_phones} new phones Trestle-scored, litigator check on.",
             "",
             "Push: `dp_push_nsm10_20260819.py` (rerun-safe; adds tiered phones + DP Complete tag).",
             ""]

    def sort_key(e):
        best = max((s.get("score") or 0 for s in (e.get("scored") or [])), default=-1)
        return -best
    for e in sorted(res, key=sort_key):
        lines.append(f"## {e['dm_first']} {e['dm_last']} — {e['property']} ({county_of(e)})")
        lines.append(f"- DataSift record: `{e['uuid']}` | mail attempts: {e['dm_attempts']} | "
                     f"existing phones (never Correct): {len(e.get('existing_phones') or [])}")
        lines.append(f"- DM mailing: {e['dm_mail']}")
        ef = e.get("enformion")
        if isinstance(ef, dict):
            lines.append(f"- Enformion match: {ef.get('matched_name')!r}, deceased={ef.get('is_deceased')}")
            if ef.get("is_deceased"):
                lines.append("- **DM DECEASED — do not dial; needs heir-of-heir research**")
        elif isinstance(ef, str):
            lines.append(f"- {ef}")
        else:
            lines.append("- Enformion: no confident match at this mailing address")
        plan = sorted((e.get("scored") or []), key=lambda s: -(s.get("score") or 0))
        if plan:
            lines.append("- Dial plan (new numbers):")
            for s in plan:
                t = tier(s.get("score")) or "Drop (skip)"
                lit = " **LITIGATOR - DNC**" if s.get("litigator") else ""
                lines.append(f"    - {s['phone']}  score {s.get('score')}  {s.get('line_type')}  -> **{t}**{lit}")
        elif isinstance(ef, dict):
            lines.append("- No new phones beyond what the record already had.")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {REPORT} ({len(res)} entries)")

    # dp_log: append entries not yet present (key = "NSM10 <street>")
    with DP_LOG.open(newline="", encoding="utf-8-sig") as f:
        logged = {r["Case No."] for r in csv.DictReader(f)}
    today = date.today().isoformat()
    added = 0
    with DP_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for e in res:
            key = f"NSM10 {e['property'].split(',')[0]}"
            if key in logged:
                continue
            ef = e.get("enformion")
            n_good = sum(1 for s in (e.get("scored") or []) if tier(s.get("score")))
            best = max((s.get("score") or 0 for s in (e.get("scored") or [])), default=0)
            if isinstance(ef, str):
                outcome, note = "open", "Entity owner — needs manual heir research"
            elif ef is None:
                outcome, note = "partial", "Enformion no confident match at DM mailing"
            elif isinstance(ef, dict) and ef.get("is_deceased"):
                outcome, note = "open", "DM reported DECEASED — heir-of-heir research needed"
            elif n_good:
                outcome = "resolved"
                note = f"{n_good} dialable new phone(s), best score {best}"
            else:
                outcome, note = "partial", "Matched but no dialable new phones"
            w.writerow([today, 34, key, county_of(e),
                        f"{e['dm_first']} {e['dm_last']} (DM, no-response)", "API", outcome,
                        "output/reports/DP_NSM10_NoResponse_20260819.md",
                        f"NSM step-10 re-trace: {note}. Push: dp_push_nsm10_20260819.py"])
            added += 1
    print(f"dp_log: appended {added} row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
