"""Q5 full run, 2026-08-19 PM: DP on ALL remaining '10. No Response DM --> DP'
records (Oren approved paid Enformion — Starter plan — same evening).

Everything status-blank in records_final.json that is NOT already in
results.json (the 12-record pilot). Entity owners (Heirs/LLC/govt) are
recorded with enformion="entity — needs manual heir research" and skipped.
Same flow as the pilot: live record GET -> Enformion PersonSearch anchored to
the DM's mailing -> Trestle-score new phones in ONE batch (litigator check on).

READ-ONLY against DataSift. Appends into output/dp_nsm10_20260819/results.json
(the push script reads that file and is rerun-safe).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests
from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from dp_nsm10_discover_20260819 import API, get_token, headers  # noqa: E402
from dp_nsm10_pilot_20260819 import is_entity  # noqa: E402
from enformion_client import person_search_phones  # noqa: E402
from phone_validator import clean_phone, process_phones  # noqa: E402

OUT = REPO / "output" / "dp_nsm10_20260819"
RESULTS = OUT / "results.json"


def main() -> int:
    recs = json.loads((REPO / "output" / "nsm10_discover_20260819" /
                       "records_final.json").read_text(encoding="utf-8"))
    done = json.loads(RESULTS.read_text(encoding="utf-8"))
    done_uuids = {e["uuid"] for e in done}
    work = [r for r in recs if not r.get("status") and r["uuid"] not in done_uuids]
    work.sort(key=lambda r: -(r.get("directmail_attempts") or 0))
    print(f"remaining records: {len(work)}")

    h = headers(get_token())
    new_entries = []
    n_hit = n_miss = n_entity = 0
    for i, r in enumerate(work):
        uuid = r["uuid"]
        a = r.get("address") or {}
        label = f"{a.get('street','?')}, {a.get('city','?')}"
        d = {}
        try:
            resp = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
            if resp.status_code == 200:
                d = resp.json()
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: detail GET failed {e}")
        ow = d.get("owner") or r.get("owner") or {}
        mail = ow.get("address") or {}
        existing = {"".join(c for c in str(p.get("number") or "") if c.isdigit())[-10:]
                    for p in (ow.get("phones") or [])}
        entry = {
            "uuid": uuid, "property": label,
            "prop_state": a.get("state"), "prop_zip": a.get("zip5") or a.get("postal_code"),
            "dm_first": ow.get("first_name"), "dm_last": ow.get("last_name"),
            "dm_mail": f"{mail.get('street','')}, {mail.get('city','')} {mail.get('state','')} {mail.get('zip5') or mail.get('postal_code','')}",
            "dm_attempts": r.get("directmail_attempts"),
            "existing_phones": sorted(existing),
        }
        if is_entity(ow):
            entry["enformion"] = "entity — needs manual heir research"
            n_entity += 1
            print(f"  {label}: ENTITY owner {ow.get('first_name')!r} {ow.get('last_name')!r} — skipped")
            new_entries.append(entry)
            continue
        ef = person_search_phones(ow.get("first_name") or "", ow.get("last_name") or "",
                                  mail.get("city") or "", mail.get("state") or "NC",
                                  mail.get("zip5") or (mail.get("postal_code") or "")[:5])
        if ef is None:
            entry["enformion"] = None
            n_miss += 1
            print(f"  [{i+1}/{len(work)}] {label}: {ow.get('first_name')} {ow.get('last_name')} -> MISS")
        else:
            entry["enformion"] = ef
            new = [p for p in (ef.get("mobiles") or []) + (ef.get("landlines") or [])
                   if "".join(c for c in p if c.isdigit())[-10:] not in existing]
            entry["new_phones"] = new
            n_hit += 1
            print(f"  [{i+1}/{len(work)}] {label}: {ow.get('first_name')} {ow.get('last_name')} -> "
                  f"{ef.get('matched_name')!r} deceased={ef.get('is_deceased')} new={len(new)}")
        new_entries.append(entry)

    to_score = []
    for e in new_entries:
        for p in (e.get("new_phones") or []):
            to_score.append((f"{e['dm_first']} {e['dm_last']} @ {e['property']}", clean_phone(p)))
    print(f"\nEnformion: {n_hit} hits, {n_miss} misses, {n_entity} entities")
    print(f"Trestle: scoring {len(to_score)} new phone(s) (~${len(to_score) * 0.015:.2f})")
    if to_score:
        key = os.environ["TRESTLE_API_KEY"]
        scored, errors = process_phones(to_score, key, add_litigator=True)
        by_num = {x.get("phone_number") or x.get("phone"): x for x in scored}
        for e in new_entries:
            if not e.get("new_phones"):
                continue
            e["scored"] = []
            for p in e["new_phones"]:
                c = clean_phone(p)
                x = by_num.get(c, {})
                e["scored"].append({
                    "phone": c, "score": x.get("activity_score"),
                    "line_type": x.get("line_type"),
                    "litigator": x.get("litigator_risk", x.get("is_litigator_risk")),
                })
        for err in errors:
            print("  trestle err:", err)

    RESULTS.write_text(json.dumps(done + new_entries, indent=1), encoding="utf-8")
    print(f"\nresults.json now holds {len(done) + len(new_entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
