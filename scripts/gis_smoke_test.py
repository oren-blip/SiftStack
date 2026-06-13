"""GIS smoke test — alert when a county's parcel data silently drifts.

Background: Catawba and Gaston both went 1+ year stale on their snapshot
endpoints without any obvious signal — the only way we caught it was a
hand audit. This script makes that catchable in seconds.

How it works: gis_smoke_fixtures.json holds 1-N hand-verified cases per
county (decedent → address → expected owner / PIN). Each fixture is
queried via lookup_by_address. PASS = at least one hit returned AND
(owner_contains matches OR expected_pid matches). FAIL = silent drift,
investigate before trusting tonight's run.

Wire into nc_daily_run.bat as a guardrail step. Exit 1 on any FAIL so
the batch surfaces the warning instead of burying it in the log.

Usage:
    python scripts/gis_smoke_test.py            # all fixtures
    python scripts/gis_smoke_test.py --county Gaston
    python scripts/gis_smoke_test.py --strict   # exit 1 if any fixture skipped
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nc_gis_lookup import lookup_by_address  # noqa: E402


FIXTURES_PATH = Path(__file__).parent / "gis_smoke_fixtures.json"
DEFAULT_EXPIRES_DAYS = 180


def _load_fixtures() -> list[dict]:
    raw = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return raw.get("fixtures", [])


def _is_expired(fixture: dict, today: date) -> bool:
    verified_on = fixture.get("verified_on")
    if not verified_on:
        return False
    try:
        verified = datetime.strptime(verified_on, "%Y-%m-%d").date()
    except ValueError:
        return False
    max_age = fixture.get("expires_after_days", DEFAULT_EXPIRES_DAYS)
    return (today - verified).days > max_age


def _owner_strings_from_hits(hits: list[dict]) -> list[str]:
    """Flatten every plausible owner-name field across hits into uppercase strings."""
    owner_field_candidates = [
        "CURR_NAME1", "CURR_NAME2",     # Gaston live
        "AcctName1", "AcctName2",        # Cabarrus
        "OwnerName", "OWNER_NAME",       # generic ArcGIS
        "Name1", "Name2",                # Lincoln/Iredell-ish
        "OWN_NAME", "owner",
    ]
    out: list[str] = []
    for h in hits:
        for f in owner_field_candidates:
            v = h.get(f)
            if v:
                out.append(str(v).upper())
    return out


def _pid_strings_from_hits(hits: list[dict]) -> list[str]:
    pid_field_candidates = ["PIN", "ParcelID", "ParcelId", "PARID", "PARCEL", "PARCEL_ID", "PARCELID"]
    out: list[str] = []
    for h in hits:
        for f in pid_field_candidates:
            v = h.get(f)
            if v:
                out.append(str(v).upper())
    return out


def run_fixture(fixture: dict) -> tuple[str, str]:
    """Return (status, message) where status is PASS / FAIL / SKIP."""
    fid = fixture.get("id", "?")
    county = fixture.get("county", "")
    address = fixture.get("address", "")
    owner_contains = (fixture.get("owner_contains") or "").upper()
    expected_pid = (fixture.get("expected_pid") or "").upper()

    if not (county and address):
        return "SKIP", f"{fid}: missing county/address"

    try:
        hits = lookup_by_address(address, county)
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{fid}: lookup raised {type(e).__name__}: {e}"

    if not hits:
        return "FAIL", f"{fid}: lookup_by_address({address!r}, {county!r}) returned 0 hits"

    owners = _owner_strings_from_hits(hits)
    pids = _pid_strings_from_hits(hits)

    owner_ok = (not owner_contains) or any(owner_contains in o for o in owners)
    pid_ok = (not expected_pid) or any(expected_pid in p for p in pids)

    if owner_ok and pid_ok:
        snippet = owners[0][:60] if owners else "(no owner field)"
        return "PASS", f"{fid}: matched owner=[{snippet}] pid=[{pids[0] if pids else '?'}]"

    reasons = []
    if not owner_ok:
        sample = owners[0][:60] if owners else "(empty)"
        reasons.append(f"owner expected {owner_contains!r} but got {sample!r}")
    if not pid_ok:
        sample = pids[0] if pids else "(empty)"
        reasons.append(f"pid expected {expected_pid!r} but got {sample!r}")
    return "FAIL", f"{fid}: " + "; ".join(reasons)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", help="Run fixtures only for this county")
    ap.add_argument("--strict", action="store_true",
                    help="Treat SKIPs (expired fixtures, missing data) as failures")
    args = ap.parse_args()

    fixtures = _load_fixtures()
    if args.county:
        wanted = args.county.lower()
        fixtures = [f for f in fixtures if f.get("county", "").lower() == wanted]

    if not fixtures:
        print("[SMOKE] no fixtures to run")
        return 0

    today = date.today()
    results: list[tuple[str, str]] = []
    for fx in fixtures:
        if _is_expired(fx, today):
            results.append(("SKIP", f"{fx.get('id','?')}: fixture expired (verified_on {fx.get('verified_on')})"))
            continue
        results.append(run_fixture(fx))

    print("=" * 70)
    print("GIS SMOKE TEST")
    print("=" * 70)
    for status, msg in results:
        marker = {"PASS": "[OK]  ", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, "[?]   ")
        print(f"  {marker} {msg}")

    n_pass = sum(1 for s, _ in results if s == "PASS")
    n_fail = sum(1 for s, _ in results if s == "FAIL")
    n_skip = sum(1 for s, _ in results if s == "SKIP")
    print()
    print(f"Summary: {n_pass} pass, {n_fail} fail, {n_skip} skip")

    if n_fail:
        return 1
    if args.strict and n_skip:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
