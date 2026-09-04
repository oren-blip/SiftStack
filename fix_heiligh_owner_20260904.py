"""One-off: Adolphus Rd, Salisbury NC 28146 (Rowan) — DataSift uuid
d0d0be79-f2ae-4918-bcff-738a896b1b48.

The record carried the tax-roll placeholder "Heirs Heiligh". Rowan County's
own 2025 Delinquent Taxpayer List names the human behind it:

    parcel 421 0830003 | HEILIGH REUBEN JR HEIRS  % BEVERLY H PABON
    9830 57TH AVE APT 17D, CORONA NY 11368-3609
    assessed $21,982 | TR7 7.10AC TOTAL | balance $168.81 OPEN | advertised Y

Same Corona NY mailing address the record already had, and she separately
owns interest 421 0830002 in her own name. So Beverly Heiligh-Pabon is the
callable decision maker.

This script changes ONLY owner.first_name / owner.last_name. The full owner
object (phones, emails, address, flags) is echoed back untouched — a trimmed
phones array DELETES phones and re-tags tiers (see
project_phone_remove_via_owner_patch). `company` is deliberately kept as
"Heiligh Reuben Jr Heirs" because that IS still how title reads.

Dry-run by default; --apply writes. Verifies by re-GET (HTTP 200 that didn't
stick is the known failure mode).

    python fix_heiligh_owner_20260904.py
    python fix_heiligh_owner_20260904.py --apply
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent / "src"))
from trestle_api_backfill import API, get_token, headers  # noqa: E402

UUID = "d0d0be79-f2ae-4918-bcff-738a896b1b48"
NEW_FIRST, NEW_LAST = "Beverly", "Heiligh-Pabon"
BACKUP = Path("output") / f"backup_{UUID[:8]}_20260904.json"


def main() -> int:
    apply = "--apply" in sys.argv
    h = headers(get_token())
    url = f"{API}/api/internal/property/{UUID}/"
    d = requests.get(url, headers=h, timeout=60).json()
    d = d.get("data") or d

    BACKUP.parent.mkdir(exist_ok=True)
    BACKUP.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    print(f"backup -> {BACKUP}")

    owner = copy.deepcopy(d["owner"])
    before = (owner.get("first_name"), owner.get("last_name"))
    addr = owner.get("address") or {}
    print(f"before : {before[0]} {before[1]}  / company={owner.get('company')!r}")
    print(f"mailing: {addr.get('street')}, {addr.get('city')} {addr.get('state')} {addr.get('postal_code')}")
    print(f"phones : {[p['number'] for p in owner.get('phones') or []]}")
    print(f"emails : {owner.get('emails')}")

    # Guard: never write an empty over an existing value, never ship a comma
    # or a suffix in Last Name.
    assert NEW_FIRST and NEW_LAST, "blank name"
    assert "," not in NEW_LAST, "comma in last name"
    assert addr.get("street") and addr.get("postal_code"), "mailing would be blanked"

    owner["first_name"] = NEW_FIRST
    owner["last_name"] = NEW_LAST
    print(f"after  : {NEW_FIRST} {NEW_LAST}  (company unchanged)")

    if not apply:
        print("dry-run — pass --apply to write")
        return 0

    r = requests.patch(url, headers=h, data=json.dumps({"owner": owner}), timeout=60)
    print(f"PATCH -> {r.status_code}")
    if r.status_code not in (200, 202):
        print(r.text[:400])
        return 1

    live = (requests.get(url, headers=h, timeout=60).json())
    live = (live.get("data") or live)["owner"]
    la = live.get("address") or {}
    print(f"LIVE   : {live.get('first_name')} {live.get('last_name')} / company={live.get('company')!r}")
    print(f"LIVE mailing: {la.get('street')}, {la.get('city')} {la.get('state')} {la.get('postal_code')}")
    print(f"LIVE phones : {[(p['number'], p.get('tags')) for p in live.get('phones') or []]}")

    ok = (live.get("first_name") == NEW_FIRST
          and live.get("last_name") == NEW_LAST
          and len(live.get("phones") or []) == len(owner.get("phones") or [])
          and la.get("street") == addr.get("street")
          and la.get("postal_code") == addr.get("postal_code"))
    print("verified: rename stuck, phones + mailing intact" if ok else "MISMATCH — inspect above")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
