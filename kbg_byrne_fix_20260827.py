"""One-off (Oren-approved 8/27): put Sidney Byrne + his VA home on the KBG
Pensacola Holding LLC buyer record, Enformion him at the VA anchor, Trestle-
score any phones, and push them tiered onto the record.

Anchor: 15006 Avening Pl, Midlothian, VA 23112 (Sunbiz officer address on
Lot 20 Canal Street LLC M25000004283, corroborated by Redfin).

Guards (all proven patterns):
- owner mailing lives at owner.address (owner.mailing_address is a silent no-op)
- last_name carries NO suffix ("Byrne", never "Byrne Jr")
- never write empty over existing; verify every write by re-GET
- Enformion: miss free, hit $0.35, capped by NC_ENFORMION_MAX_SPEND
- Trestle via src/phone_validator.process_phones; unscored numbers are KEPT
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402
from push_smartskip_group1_20260825 import headers  # noqa: E402
import enformion_client  # noqa: E402
import config  # noqa: E402
from phone_validator import process_phones, clean_phone  # noqa: E402

UUID = "9bd642d3-7001-4bd8-9e06-49e61ded02df"
MAIL = {"street": "15006 Avening Pl", "city": "Midlothian",
        "state": "VA", "postal_code": "23112"}

DRY = "--dry-run" in sys.argv


def main() -> int:
    h = headers(token())

    # ---- 1. owner fix ----
    d = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h,
                     timeout=30).json()
    owner = d.get("owner") or {}
    print(f"live owner: {owner.get('first_name')!r} {owner.get('last_name')!r} "
          f"mail={(owner.get('address') or {}).get('street')!r} "
          f"phones={len(owner.get('phones') or [])}")
    new_owner = copy.deepcopy(owner)
    new_owner["first_name"], new_owner["last_name"] = "Sidney", "Byrne"
    new_owner.setdefault("address", {})
    new_owner["address"].update(MAIL)

    # ---- 2. Enformion at the VA anchor ----
    res = None
    if enformion_client.enabled():
        res = enformion_client.person_search_phones(
            "Sidney", "Byrne", "Midlothian", "VA", "23112")
        print(f"Enformion: {'HIT' if res else 'miss'} "
              f"(spend this run ${enformion_client.spend_this_run():.2f})")
        if res:
            print(f"  matched: {res.get('matched_name')!r} "
                  f"deceased={res.get('is_deceased')}")
            print(f"  mobiles: {res.get('mobiles')}")
            print(f"  landlines: {res.get('landlines')}")
    else:
        print("Enformion disabled/creds missing — skipping")

    # ---- 3. Trestle-score + build phone adds ----
    adds: list[tuple[str, list[str]]] = []
    if res:
        mobiles = [str(n) for n in (res.get("mobiles") or [])]
        lands = [str(n) for n in (res.get("landlines") or [])]
        allnums = mobiles + lands
        scored: dict[str, dict] = {}
        if allnums and config.TRESTLE_API_KEY:
            pairs = [(n, clean_phone(n)) for n in allnums]
            results, errors = process_phones(pairs, config.TRESTLE_API_KEY)
            for r in results:
                num = "".join(c for c in str(r.get("phone_number") or "")
                              if c.isdigit())[-10:]
                if num:
                    scored[num] = r
            if errors:
                print(f"  Trestle errors: {len(errors)} (unscored numbers KEPT)")
        LINE_TYPES = {"mobile": "MOBILE", "landline": "LANDLINE",
                      "fixedvoip": "VOIP", "nonfixedvoip": "VOIP",
                      "voip": "VOIP"}
        for n in allnums:
            key = "".join(c for c in n if c.isdigit())[-10:]
            r = scored.get(key) or {}
            tier = r.get("assigned_tag")
            kind = "mobile" if n in mobiles else "landline"
            ptype = LINE_TYPES.get(str(r.get("line_type") or "").lower().replace("_", ""),
                                   "MOBILE" if kind == "mobile" else "LANDLINE")
            tags = [t for t in (tier, f"Enformion 8/27 {kind}") if t]
            if tier == "Drop":
                print(f"  {n}: Trestle Drop — not pushing")
                continue
            adds.append((key, tags, ptype))
            print(f"  push plan: {key} type={ptype} tags={tags} "
                  f"score={r.get('activity_score')}")

    existing = {"".join(c for c in str(p.get("number") or "") if c.isdigit())
                for p in (new_owner.get("phones") or [])}
    for num, tags, ptype in adds:
        if num in existing:
            print(f"  {num} already on record — skip")
            continue
        new_owner.setdefault("phones", []).append(
            {"number": num, "type": ptype, "tags": tags})

    if DRY:
        print(f"DRY: would PATCH owner -> Sidney Byrne, mail={MAIL}, "
              f"+{len(adds)} phones")
        return 0

    pr = requests.patch(f"{API}/api/internal/property/{UUID}/", headers=h,
                        data=json.dumps({"owner": new_owner}), timeout=30)
    print(f"PATCH owner -> {pr.status_code} {pr.text[:150]}")
    if pr.status_code not in (200, 202):
        return 1

    chk = requests.get(f"{API}/api/internal/property/{UUID}/", headers=h,
                       timeout=30).json()
    co = chk.get("owner") or {}
    nums = {"".join(c for c in str(p.get("number") or "") if c.isdigit())
            for p in (co.get("phones") or [])}
    print(f"verify: owner={co.get('first_name')} {co.get('last_name')} "
          f"mail={(co.get('address') or {}).get('street')!r} "
          f"city={(co.get('address') or {}).get('city')!r} "
          f"phones={sorted(nums)}")
    ok = (co.get("first_name") == "Sidney" and co.get("last_name") == "Byrne"
          and (co.get("address") or {}).get("street") == MAIL["street"]
          and all(n in nums for n, _, _ in adds))
    print("RESULT:", "OK" if ok else "CHECK BY HAND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
