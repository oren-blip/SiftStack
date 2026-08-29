"""Lead counting in the KPI puller (feeds the daily email's PHONES THIS WEEK).

Runs offline: DataSift's record search and activity log are stubbed, so the
assertions are about the counting rules only.

    python tests/test_kpi_lead_counting.py      # or: pytest tests/test_kpi_lead_counting.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("America/New_York")


def load():
    spec = importlib.util.spec_from_file_location(
        "pull_kpis", ROOT / ".claude" / "skills" / "kpi-engine" / "scripts" / "pull_kpis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def status_event(uuid: str, ts: str, pair: list[str]) -> dict:
    """A property.status.updated log entry as the API returns it (UTC stamp)."""
    return {"event_type": "property.status.updated", "resource": uuid,
            "timestamp": ts, "payload": {"property": {"status": pair}},
            "author_extra_info": {"email": "caller@example.com",
                                  "first_name": "Test", "last_name": "Caller"}}


def run(mod, records: dict[str, dict], day_from: str, day_to: str) -> dict:
    """records: uuid -> {"status": current, "events": [...]}"""
    mod.search_updated = lambda token, a, b: [
        {"uuid": u, "address": u, "status": r["status"]} for u, r in records.items()]
    mod.get_logs = lambda token, uuid: records[uuid]["events"]
    return mod.pull("tok", day_from, day_to, TZ, mod.load_benchmarks())


def test_lead_status_spelling_is_normalised():
    """'Cold Lead', 'cold_lead' and 'COLD LEAD' are the same status."""
    mod = load()
    recs = {
        "a": {"status": "Cold Lead",
              "events": [status_event("a", "2026-08-24 15:00:00", ["", "Cold Lead"])]},
        "b": {"status": "cold_lead",
              "events": [status_event("b", "2026-08-24 15:00:00", ["", "cold_lead"])]},
        "c": {"status": "HOT LEAD",
              "events": [status_event("c", "2026-08-24 15:00:00", ["", "HOT LEAD"])]},
    }
    res = run(mod, recs, "2026-08-24", "2026-08-26")
    assert res["account_totals"]["leads"] == 3, res["account_totals"]
    assert res["daily"]["2026-08-24"]["leads"] == 3
    assert not res["unmatched_statuses"], res["unmatched_statuses"]


def test_lead_keeps_its_day_after_being_re_dispositioned():
    """Monday's lead survives Wednesday's 'not interested' on the same record.

    The nightly refresh re-pulls the trailing days and rewrites those ledger
    rows, so crediting the record's window-final status erased the lead.
    """
    mod = load()
    recs = {"a": {"status": "not_interested", "events": [
        status_event("a", "2026-08-24 15:00:00", ["", "Warm Lead"]),
        status_event("a", "2026-08-26 15:00:00", ["Warm Lead", "not_interested"]),
    ]}}
    res = run(mod, recs, "2026-08-24", "2026-08-26")
    assert res["daily"]["2026-08-24"]["leads"] == 1, res["daily"]
    assert res["daily"]["2026-08-26"]["not_interested"] == 1, res["daily"]
    assert res["account_totals"]["status_changes"] == 2


def test_reversed_status_pair_is_detected_from_the_current_status():
    """Payload [new, old] with one event per record still reads the new one."""
    mod = load()
    recs = {"a": {"status": "Hot Lead", "events": [
        status_event("a", "2026-08-24 15:00:00", ["Hot Lead", "new_lead"])]}}
    res = run(mod, recs, "2026-08-24", "2026-08-26")
    assert res["account_totals"]["leads"] == 1
    assert res["status_vocabulary"] == {"Hot Lead": 1}, res["status_vocabulary"]


def test_unmatched_statuses_are_reported_not_swallowed():
    """A status nobody recognises is named, so '0 leads' is explainable."""
    mod = load()
    recs = {"a": {"status": "Ghosting Lead", "events": [
        status_event("a", "2026-08-24 15:00:00", ["", "Ghosting Lead"])]}}
    res = run(mod, recs, "2026-08-24", "2026-08-26")
    assert res["account_totals"]["leads"] == 0
    assert res["account_totals"]["status_changes"] == 1
    assert res["unmatched_statuses"] == {"Ghosting Lead": 1}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
