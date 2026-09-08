"""Ty's phone-and-text scorecard, shared by the daily email and the weekly rollup.

Reads ONLY local files (never DataSift):
  output/kpi_daily_ledger.csv   per-day call/text counts (scripts/kpi_refresh.py, nightly)
  output/kpi_pool.json          how many records were actually worked (same refresh)
  output/sms_agent/sms_agent.db the two-way SMS agent's inbound replies + intents

Benchmarks are what Ty Garrett taught on Day 5 of the August-2026 Deal Flow
Challenge (2026-08-21, "the KPI workbook", one caller's first month), with the
July-2026 numbers kept where August didn't restate them. Source notes:
knowledge/5-day-deal-flow/notes/day-5-2026-08-21-key-teachings.md, sections 2-3,
and the "What changed since the July cohort" table.

The two rules the section is built around:
  1. Correct numbers are the KPI, not dials. Every ~20 right-party contacts on
     first-to-market data is a deal inside 6 months; not-interested records are
     20% of future deal volume; leads per deal fell to 5-15.
  2. A KPI that doesn't fire an action is worthless. So the section compares
     today against YOUR OWN trailing baseline and prints a flag with the action
     Ty/Phil prescribe, instead of only listing numbers.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
LEDGER = OUTPUT / "kpi_daily_ledger.csv"
POOL = OUTPUT / "kpi_pool.json"
SMS_DB = OUTPUT / "sms_agent" / "sms_agent.db"
TZ = ZoneInfo("America/New_York")

COUNT_FIELDS = ("dials", "answered", "noanswer", "conversations", "meaningful_conversations",
                "correct_numbers", "wrong_numbers", "dead_numbers", "dnc_numbers", "leads",
                "not_interested", "follow_ups", "appointments", "talk_seconds", "sms_sent",
                "sms_received", "records_touched")

# Ty's numbers. Keys ending in _band are (low, high).
TY = {
    "dials_per_correct_blended": 13.5,     # Aug: 13.5 dials per correct number, call + text
    "dials_per_correct_call_only": 21,     # Aug: 21 correct from calling alone in the sample month
    "dials_per_correct_2025": 32,          # the stale guide number ("Correct Numbers 32:1")
    "contact_rate_list": 0.17,             # Aug: 261 right-party contacts / 1,457 doors
    "text_share_of_correct": 0.50,         # Aug: texting supplies about half of all correct numbers
    "answer_rate_floor": 0.50,             # Jul: below 50% = skip-trace problem or spam problem
    "answer_rate_team_band": (0.60, 0.70), # Jul: Ty's team runs 60-70%
    "conversation_rate_band": (0.15, 0.20),  # guide: real two-way conversations, 15-20% of dials
    "correct_per_deal_ftm": 20,            # Aug: "every 20 of them is gonna be a deal" (6 months)
    "correct_per_deal_conservative_band": (50, 100),  # Jul: 50-100 correct -> 1 deal over 12 months
    "leads_per_deal_band": (5, 15),        # Aug: was 20-30; bulk era was 50-100
    "not_interested_deal_share": 0.20,     # Aug: 20% of not-interested become deal volume later
    "dial_floor_per_caller": 150,          # guide floor; Adriana ran ~172/day
    "records_per_caller_week_band": (250, 300),  # Aug: capacity on 20 numbers x 25 touches/day
    "dial_spike_share": 0.20,              # Phil: +20% dials in a day = you're calling a crappy list
}

# Which text replies prove the line reaches the owner. Joshua Goodwin, Day 5:
# "We will only commit a correct number if they say they're not interested in
# selling" - a bare "f*** off" could be anyone getting blasted. So a wrong-number
# or opt-out reply is not a contact; a no, a maybe, or a question about the
# house is.
TEXT_RIGHT_PARTY = {"NOT_INTERESTED", "INTERESTED", "ESCALATE"}
TEXT_INTERESTED = {"INTERESTED", "ESCALATE"}


# ---------------------------------------------------------------- loading

def load_ledger() -> dict[str, dict]:
    if not LEDGER.exists():
        return {}
    try:
        with open(LEDGER, encoding="utf-8", newline="") as fh:
            return {r["day"]: r for r in csv.DictReader(fh)}
    except Exception:
        return {}


def load_pool() -> dict:
    try:
        return json.loads(POOL.read_text(encoding="utf-8")) if POOL.exists() else {}
    except Exception:
        return {}


def window(rows: dict[str, dict], d_from: date, d_to: date) -> Counter:
    """Sum the ledger over [d_from, d_to]. Adds dial_days (days with a dial)
    and record_days (dial days where records_touched is known)."""
    t = Counter()
    lo, hi = d_from.isoformat(), d_to.isoformat()
    for day, r in rows.items():
        if lo <= day <= hi:
            for f in COUNT_FIELDS:
                t[f] += int(r.get(f) or 0)
            if int(r.get("dials") or 0) > 0:
                t["dial_days"] += 1
                if int(r.get("records_touched") or 0) > 0:
                    t["record_days"] += 1
    return t


def _local_date(iso: str) -> date | None:
    try:
        return datetime.fromisoformat(iso).astimezone(TZ).date()
    except Exception:
        return None


def text_channel(d_from: date, d_to: date) -> dict:
    """Inbound texts in the window, read from the SMS agent's own database.
    Distinct phones per bucket; `available` is False when the DB is missing."""
    out = {"available": False, "replies": 0, "right_party": 0, "interested": 0,
           "not_interested": 0, "wrong": 0, "opt_out": 0}
    if not SMS_DB.exists():
        return out
    try:
        c = sqlite3.connect(f"file:{SMS_DB.as_posix()}?mode=ro", uri=True)
        rows = c.execute("SELECT phone, intent, created_at FROM messages "
                         "WHERE direction='in'").fetchall()
        c.close()
    except Exception:
        return out
    seen = {k: set() for k in ("right_party", "interested", "not_interested", "wrong", "opt_out")}
    for phone, intent, created in rows:
        d = _local_date(created or "")
        if d is None or not (d_from <= d <= d_to):
            continue
        out["replies"] += 1
        i = (intent or "").upper()
        if i in TEXT_RIGHT_PARTY:
            seen["right_party"].add(phone)
        if i in TEXT_INTERESTED:
            seen["interested"].add(phone)
        if i == "NOT_INTERESTED":
            seen["not_interested"].add(phone)
        if i == "WRONG_NUMBER":
            seen["wrong"].add(phone)
        if i == "OPT_OUT":
            seen["opt_out"].add(phone)
    for k, s in seen.items():
        out[k] = len(s)
    out["available"] = True
    return out


# ---------------------------------------------------------------- math

def rates(t: Counter) -> dict:
    d, c = t["dials"], t["correct_numbers"]
    disp = c + t["wrong_numbers"] + t["dead_numbers"]
    return {
        "answer_rate": t["answered"] / d if d else None,
        "conv_rate": t["conversations"] / d if d else None,
        "dials_per_correct": d / c if c else None,
        "wrong_dead_share": (t["wrong_numbers"] + t["dead_numbers"]) / disp if disp else None,
        "dials_per_day": d / t["dial_days"] if t["dial_days"] else None,
        "records_per_day": t["records_touched"] / t["record_days"] if t["record_days"] else None,
    }


def pct(x: float | None, digits: int = 0) -> str:
    return "-" if x is None else f"{x * 100:.{digits}f}%"


def num(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def _day_label(d: date) -> str:
    return f"{d.strftime('%a')} {d.month}/{d.day}"


def anomaly_flags(focus: Counter | None, focus_day: date | None, wk: Counter,
                  base: Counter) -> list[str]:
    """Today (or the last dial day) against the four full weeks before this
    one. Each flag ends with the action Ty or Phil prescribes."""
    flags: list[str] = []
    b = rates(base)
    have_base = base["dial_days"] >= 3
    if focus is not None and focus_day is not None:
        f = rates(focus)
        day_lbl = _day_label(focus_day)
        if have_base and b["dials_per_day"] and focus["dials"] >= 40 and \
                focus["dials"] > b["dials_per_day"] * (1 + TY["dial_spike_share"]):
            flags.append(
                f"{day_lbl}: {focus['dials']} dials vs your usual {b['dials_per_day']:.0f}/day "
                f"(+{(focus['dials'] / b['dials_per_day'] - 1) * 100:.0f}%). Phil's tell for a bad "
                f"list: dials jump when numbers are dead. Check what got pushed into the call "
                f"presets and whether it's still first-to-market data.")
        if focus["dials"] >= 20 and f["answer_rate"] is not None and \
                f["answer_rate"] < TY["answer_rate_floor"]:
            flags.append(
                f"{day_lbl}: answer rate {pct(f['answer_rate'])} is under Ty's 50% floor. "
                f"That's a skip-trace problem or a spam-flagged caller ID. Check CallerIDRep "
                f"before dialing again.")
        disp = focus["correct_numbers"] + focus["wrong_numbers"] + focus["dead_numbers"]
        if have_base and disp >= 10 and f["wrong_dead_share"] is not None and \
                b["wrong_dead_share"] is not None and \
                f["wrong_dead_share"] > b["wrong_dead_share"] + 0.15:
            flags.append(
                f"{day_lbl}: {pct(f['wrong_dead_share'])} of dispositions were wrong or dead "
                f"numbers (your usual {pct(b['wrong_dead_share'])}). Dirty numbers: re-run "
                f"Trestle on this list before the next attempt.")
        if focus["dials"] >= 40 and focus["correct_numbers"] == 0:
            flags.append(
                f"{day_lbl}: {focus['dials']} dials and not one right-party contact. Ty: that's "
                f"the list, not the caller. Pull up which records were dialed.")
    w = rates(wk)
    if have_base and wk["dials"] >= 100 and w["dials_per_correct"] and b["dials_per_correct"] and \
            w["dials_per_correct"] > 2 * b["dials_per_correct"]:
        flags.append(
            f"This week it took {w['dials_per_correct']:.0f} dials per correct number vs your "
            f"usual {b['dials_per_correct']:.0f}. The list is burning out. Rotate to the next "
            f"list rather than pushing more dials into this one.")
    return flags


def deal_math(t30: Counter, text30: dict) -> list[str]:
    """Ty's Day-5 chain from right-party contacts to deals, on the window given."""
    lines: list[str] = []
    c, leads, ni = t30["correct_numbers"], t30["leads"], t30["not_interested"]
    lo, hi = TY["correct_per_deal_conservative_band"]
    if c:
        ftm = c / TY["correct_per_deal_ftm"]
        lines.append(
            f"{c} right-party contacts. Ty's ratio on first-to-market data is one deal per "
            f"{TY['correct_per_deal_ftm']} of those inside 6 months, so that's about {ftm:.1f} "
            f"deal{'s' if ftm >= 1.5 else ''} in the pipe "
            f"({c / hi:.1f}-{c / lo:.1f} at July's slower {lo}-{hi} per deal over a year).")
    else:
        lines.append("No right-party contacts logged, so the deal math is empty.")
    llo, lhi = TY["leads_per_deal_band"]
    if leads:
        lines.append(
            f"{leads} lead{'s' if leads != 1 else ''}. Ty now sees a deal every {llo}-{lhi} "
            f"leads (it used to be 20-30), so that's {leads / lhi:.1f}-{leads / llo:.1f} deals' "
            f"worth of leads.")
    else:
        lines.append(f"0 leads. Ty expects a deal every {llo}-{lhi} leads; a lead is any record "
                     f"moved to a lead status.")
    if ni:
        lines.append(
            f"{ni} not-interested banked. Ty: {TY['not_interested_deal_share'] * 100:.0f}% of "
            f"those become deal volume later, so ~{ni * TY['not_interested_deal_share']:.0f} of "
            f"them come back. Keep them in the rehash campaign; never delete.")
    if text30.get("available") and c:
        share = min(text30["right_party"] / c, 1.0)
        lines.append(
            f"Owners who replied to a text (a no, a maybe, or a question): {text30['right_party']}, "
            f"against {c} correct numbers logged, so texting is carrying roughly {pct(share)} of "
            f"the contact work. Ty's team gets about half from texts, and every one of those is a "
            f"dial the caller didn't have to make.")
    return lines


def vs_ty_rows(t: Counter, text: dict, pool: dict) -> list[tuple[str, str, str, str]]:
    """(metric, you, Ty, how to read it) for one window."""
    r = rates(t)
    rows: list[tuple[str, str, str, str]] = []
    rows.append(("Dials per correct number", num(r["dials_per_correct"]),
                 f"{TY['dials_per_correct_blended']} blended, {TY['dials_per_correct_call_only']} call-only",
                 f"lower is better; 2025 was {TY['dials_per_correct_2025']}"))
    if text.get("available") and t["correct_numbers"]:
        share = min(text["right_party"] / t["correct_numbers"], 1.0)
        rows.append(("Share of contacts coming from texts (owner replies / correct numbers)",
                     pct(share), "about half", "texts run as their own 4-day channel"))
    worked = int(pool.get("worked_30d") or 0)
    if worked and t["correct_numbers"]:
        rows.append(("Contact rate (correct numbers / records worked)",
                     f"{pct(t['correct_numbers'] / worked)}  ({t['correct_numbers']} / {worked})",
                     f"{pct(TY['contact_rate_list'])}  (261 / 1,457)",
                     "Ty's August headline number"))
    lo, hi = TY["answer_rate_team_band"]
    rows.append(("Answer rate", pct(r["answer_rate"]),
                 f"{pct(lo)}-{pct(hi)}; under {pct(TY['answer_rate_floor'])} = spam or skip-trace problem",
                 "ours counts voicemail pickups, so it reads high"))
    clo, chi = TY["conversation_rate_band"]
    rows.append(("Conversations (60s+) per dial", pct(r["conv_rate"]),
                 f"{pct(clo)}-{pct(chi)}; under {pct(clo)} = list or number quality",
                 "not effort"))
    rows.append(("Dials per dial day", num(r["dials_per_day"], 0),
                 f"{TY['dial_floor_per_caller']} floor per caller", "Adriana ran ~172"))
    if r["records_per_day"]:
        wlo, whi = TY["records_per_caller_week_band"]
        rows.append(("Records touched per dial day", num(r["records_per_day"], 0),
                     f"{wlo}-{whi} per caller per WEEK",
                     "Phil: size the week's list to what you can touch in a day"))
    return rows


# ---------------------------------------------------------------- build

def build(today: date | None = None) -> dict | None:
    """Everything the email/rollup needs, or None when there is nothing to show
    (no ledger, or no dials this week and last)."""
    today = today or datetime.now(TZ).date()
    rows = load_ledger()
    if not rows:
        return None
    monday = today - timedelta(days=today.weekday())
    wk = window(rows, monday, today)
    lw = window(rows, monday - timedelta(days=7), monday - timedelta(days=1))
    if not wk["dials"] and not lw["dials"]:
        return None

    focus_day = None
    for i in range(0, 8):
        d = today - timedelta(days=i)
        r = rows.get(d.isoformat())
        if r and int(r.get("dials") or 0) > 0:
            focus_day = d
            break
    focus = window(rows, focus_day, focus_day) if focus_day else None
    base_from, base_to = monday - timedelta(days=28), monday - timedelta(days=1)
    base = window(rows, base_from, base_to)
    d30_from = today - timedelta(days=29)
    t30 = window(rows, d30_from, today)
    pool = load_pool()

    periods = []
    if focus is not None:
        lbl = "Today" if focus_day == today else _day_label(focus_day)
        periods.append({"label": lbl, "t": focus, "text": text_channel(focus_day, focus_day),
                        "per_day": False})
    periods.append({"label": "This week", "t": wk, "text": text_channel(monday, today),
                    "per_day": False})
    periods.append({"label": "Last week", "t": lw,
                    "text": text_channel(monday - timedelta(days=7), monday - timedelta(days=1)),
                    "per_day": False})
    if base["dial_days"]:
        periods.append({"label": "4-wk avg per dial day", "t": base,
                        "text": text_channel(base_from, base_to), "per_day": True})
    text30 = text_channel(d30_from, today)
    ledger_through = max(rows) if rows else ""
    stale_note = ""
    if ledger_through and (today - date.fromisoformat(ledger_through)).days > 2:
        stale_note = (f"Numbers only current through {ledger_through}; the KPI refresh "
                      f"hasn't run since.")
    return {
        "today": today,
        "periods": periods,
        "t30": t30,
        "text30": text30,
        "pool": pool,
        "vs_ty": vs_ty_rows(t30, text30, pool),
        "deal_math": deal_math(t30, text30),
        "flags": anomaly_flags(focus, focus_day, wk, base),
        "stale_note": stale_note,
        "ledger_through": ledger_through,
    }


def period_cells(p: dict) -> dict:
    """One period as display strings (per-dial-day averages when p['per_day'])."""
    t, tx = p["t"], p["text"]
    r = rates(t)
    n = t["dial_days"] if p["per_day"] and t["dial_days"] else 1

    def cnt(v: int) -> str:
        return f"{v / n:.0f}" if p["per_day"] else str(v)

    via_text = "-"
    if tx.get("available") and (t["correct_numbers"] or tx["right_party"]):
        via_text = cnt(tx["right_party"])
    replies = t["sms_received"] or tx.get("replies", 0)
    return {
        "label": p["label"], "dials": cnt(t["dials"]), "answer": pct(r["answer_rate"]),
        "convos": cnt(t["conversations"]), "correct": cnt(t["correct_numbers"]),
        "via_text": via_text, "dials_per_correct": num(r["dials_per_correct"]),
        "wrong_dead": cnt(t["wrong_numbers"] + t["dead_numbers"]),
        "ni": cnt(t["not_interested"]), "leads": cnt(t["leads"]),
        "texts": f"{cnt(t['sms_sent'])}/{cnt(replies)}",
        "talk_min": f"{t['talk_seconds'] // 60 // n}m",
    }


HEADERS = ["", "Dials", "Ans%", "Convos", "Correct", "via text", "Dials/corr",
           "Wrong+dead", "NI", "Leads", "Texts out/in"]
_KEYS = ["label", "dials", "answer", "convos", "correct", "via_text", "dials_per_correct",
         "wrong_dead", "ni", "leads", "texts"]


def render_text(k: dict, condensed: bool = False) -> list[str]:
    """The plain-text section. condensed=True is the email body (no definitions,
    no 'read it as' asides); the full report keeps everything."""
    widths = [24, 6, 6, 7, 8, 9, 11, 11, 4, 6, 13]

    def row(cells: list[str]) -> str:
        return "  " + "".join((c.ljust(w) if i == 0 else c.rjust(w))
                              for i, (c, w) in enumerate(zip(cells, widths)))

    out = ["PHONES & TEXTS — TY'S SCORECARD", row(HEADERS)]
    for p in k["periods"]:
        c = period_cells(p)
        out.append(row([c[key] for key in _KEYS]))
    if not condensed:
        out.append("  Correct = phones newly marked CORRECT in DataSift (by the caller, or by the "
                   "SMS agent on an owner reply). via text = owners who replied to a text that "
                   "day. Convos = calls of 60s+. Dials/corr = dials per correct number.")
    out.append("  Vs Ty (your last 30 days against what he showed on Day 5, Aug 21 2026):")
    for metric, you, ty, read in k["vs_ty"]:
        tail = "" if condensed else f"   ({read})"
        out.append(f"    {metric}: {you}   |   Ty: {ty}{tail}")
    out.append("  Deal math (last 30 days):")
    for line in k["deal_math"]:
        out.append(f"    {line}")
    if k["flags"]:
        out.append("  *** FLAGS — Ty: a KPI that doesn't fire an action is worthless ***")
        for fl in k["flags"]:
            out.append(f"    - {fl}")
    if k["stale_note"]:
        out.append(f"  ({k['stale_note']})")
    out.append("")
    return out


if __name__ == "__main__":
    m = build()
    print("\n".join(render_text(m)) if m else "nothing to show")
