"""Per-week Tracerfy spend cap.

Tracerfy charges 5 credits ($0.10) per HIT, 0 on miss. Without a cap,
a single misconfigured loop could burn through Oren's 1000-credit
purchase in one run. This module persists week-keyed spend to disk so
spend is honored across re-runs and across daily/weekly invocations.

Two thresholds (defaults; override via .env):
  TRACERFY_WEEKLY_BUDGET_USD=5   — hard stop; further Tracerfy calls
                                    are skipped once spend hits this
  TRACERFY_WARN_THRESHOLD_USD=2  — first time crossed, a [BUDGET WARN]
                                    line is emitted to stdout

Each hit costs 5 credits; the conversion is governed by
TRACERFY_CREDIT_USD (default 0.02 = $0.10 per hit).

Reset: the spend counter is keyed by ISO year+week, so the budget
automatically resets every Monday.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

_STATE_PATH = Path(__file__).parent.parent / "output" / ".tracerfy_spend.json"
_CREDITS_PER_HIT = 5
_DEFAULT_BUDGET_USD = 5.0
_DEFAULT_WARN_USD = 2.0
_DEFAULT_CREDIT_USD = 0.02


def _read_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _current_week_key() -> str:
    today = date.today()
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _credit_cost_usd() -> float:
    try:
        return float(os.getenv("TRACERFY_CREDIT_USD", "") or _DEFAULT_CREDIT_USD)
    except ValueError:
        return _DEFAULT_CREDIT_USD


def _weekly_budget_usd() -> float:
    try:
        return float(os.getenv("TRACERFY_WEEKLY_BUDGET_USD", "") or _DEFAULT_BUDGET_USD)
    except ValueError:
        return _DEFAULT_BUDGET_USD


def _warn_threshold_usd() -> float:
    try:
        return float(os.getenv("TRACERFY_WARN_THRESHOLD_USD", "") or _DEFAULT_WARN_USD)
    except ValueError:
        return _DEFAULT_WARN_USD


def current_week_spend() -> tuple[int, float]:
    """Return (credits_spent, dollars_spent) for the current ISO week."""
    state = _read_state()
    week = _current_week_key()
    credits = int(state.get(week, {}).get("credits", 0))
    dollars = credits * _credit_cost_usd()
    return (credits, dollars)


def can_spend(credits: int = _CREDITS_PER_HIT) -> bool:
    """True if spending `credits` more would keep us under the weekly cap."""
    _, dollars = current_week_spend()
    projected = dollars + (credits * _credit_cost_usd())
    return projected <= _weekly_budget_usd()


def record_hit(credits: int = _CREDITS_PER_HIT) -> tuple[bool, str]:
    """Record a Tracerfy hit (credits spent). Returns (warn_now, message)
    where warn_now is True iff this call is the first to cross the warn
    threshold this week — the caller should print a banner once.
    """
    state = _read_state()
    week = _current_week_key()
    bucket = state.setdefault(week, {"credits": 0, "hits": 0, "warned": False})
    before_dollars = int(bucket.get("credits", 0)) * _credit_cost_usd()
    bucket["credits"] = int(bucket.get("credits", 0)) + credits
    bucket["hits"] = int(bucket.get("hits", 0)) + 1
    after_dollars = int(bucket["credits"]) * _credit_cost_usd()
    warn_now = False
    msg = ""
    warn_thresh = _warn_threshold_usd()
    if not bucket.get("warned") and after_dollars >= warn_thresh and before_dollars < warn_thresh:
        bucket["warned"] = True
        warn_now = True
        msg = (
            f"[TRACERFY BUDGET WARN] week={week} spend=${after_dollars:.2f} "
            f"crossed ${warn_thresh:.2f} threshold (cap ${_weekly_budget_usd():.2f})"
        )
    _write_state(state)
    return (warn_now, msg)


def budget_summary() -> str:
    """One-line summary for daily-report consumption."""
    credits, dollars = current_week_spend()
    cap = _weekly_budget_usd()
    week = _current_week_key()
    return (
        f"Tracerfy this week ({week}): {credits} credits / "
        f"${dollars:.2f} of ${cap:.2f} cap"
    )
