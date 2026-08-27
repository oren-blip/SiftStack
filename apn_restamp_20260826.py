"""One-shot follow-up to apn_gap_fix_20260826: three corrections found while
verifying today's 9 stamps against live county GIS + the per-county parcel
field conventions (reference_county_parcel_id_fields):

1. Dellinger 26E000340-540 (0 Wehunt Store Rd, Lincolnton): stamped the
   Lincoln PIN 2664704111 from a pre-correction Week 22 file; Lincoln's
   published id is PARCELID -> 11958 (GIS-verified owner "DELLINGER MARY A
   (HEIRS OF)"). PIN kept in the value we replace only.
2. Bess 26E000658-350 (0 Westway Dr, Gastonia): stamped the Gaston PIN
   3554147365 from a pre-correction Week 21 file; Gaston's published id is
   PID -> 139820. NOTE: live GIS shows that parcel now owned by RAMIREZ
   MORALES MIRIAM VERONICA (619 Westway Dr) — the estate lot appears SOLD
   post-filing. Parcel stamped for identification; the sold call is Oren's.
3. Francis 26E000455-540 (Green Leaf Ln, Denver): blank parcel; Lincoln
   PARCELID 88873 — Oren's own hand-entered APN for this exact case (the
   case that drove the 7/23 Lincoln PIN->PARCELID field switch).

Each patch verifies the live owner surname first and re-GETs after.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from trestle_api_backfill import API, get_token, headers

OUT = REPO / "output" / "apn_gap_20260826"

# (surname, street fragment, expected current parcel or "", new parcel)
FIXES = [
    ("dellinger", "wehunt store", "2664704111", "11958"),
    ("bess", "westway", "3554147365", "139820"),
    ("francis", "green leaf", "", "88873"),
]


def _uuid_index() -> dict[str, str]:
    """street-fragment -> uuid from today's scouted full records (the search
    index lags writes — never search for records we already hold)."""
    recs = json.loads((OUT / "records_full.json").read_text(encoding="utf-8"))
    out = {}
    for surname, frag, _old, _new in FIXES:
        for r in recs:
            street = ((r.get("address") or {}).get("street") or "").lower()
            last = ((r.get("owner") or {}).get("last_name") or "").lower()
            if frag in street and surname in last:
                out[frag] = r.get("uuid")
                break
    return out


def main() -> int:
    h = headers(get_token())
    uuids = _uuid_index()
    fail = 0
    for surname, frag, old, new in FIXES:
        uuid = uuids.get(frag)
        if not uuid:
            print(f"!! {surname}/{frag}: uuid not in records_full.json — skipped")
            fail += 1
            continue
        d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h,
                         timeout=30).json()
        live = str(d.get("parcel_id") or "").strip()
        owner_last = ((d.get("owner") or {}).get("last_name") or "").lower()
        if surname not in owner_last:
            print(f"!! {surname}: live owner {owner_last!r} mismatch — skipped")
            fail += 1
            continue
        if old and live != old:
            print(f"!! {surname}: live parcel {live!r} != expected {old!r} — skipped")
            fail += 1
            continue
        if not old and live:
            print(f"== {surname}: already has parcel {live!r} — skipped")
            continue
        pr = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                            data=json.dumps({"parcel_id": new, "apn": new}),
                            timeout=30)
        got = ""
        if pr.status_code in (200, 202):
            got = str(requests.get(f"{API}/api/internal/property/{uuid}/",
                                   headers=h, timeout=30).json()
                      .get("parcel_id") or "").strip()
        if got == new:
            print(f"OK {surname}: {live or '(blank)'} -> {new}")
        else:
            print(f"!! {surname}: PATCH {pr.status_code}, read back {got!r}")
            fail += 1
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
