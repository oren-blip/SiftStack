"""Q5 pilot, 2026-08-19: DP on the '10. No Response DM --> DP' preset.

Takes the 12 most-mailed status-blank records (dm attempts desc), and for each:
  1. GET the live DataSift record (existing phones, custom fields -> Case No.)
  2. Enformion PersonSearch on the DM anchored to their mailing address
     (shared free-plan quota — STOPS at first quota/auth error)
  3. Trestle-scores every NEW phone in one batch (litigator suppression on)

READ-ONLY against DataSift. Results -> output/dp_nsm10_20260819/results.json.
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

from dp_nsm10_discover_20260819 import API, get_token, headers  # noqa: E402
from enformion_client import person_search_phones  # noqa: E402
from phone_validator import clean_phone, process_phones  # noqa: E402
import os  # noqa: E402

OUT = REPO / "output" / "dp_nsm10_20260819"
OUT.mkdir(parents=True, exist_ok=True)
N_PILOT = 12
ENTITY_WORDS = ("heirs", "department", "llc", "trust", "estate of", "church")


def is_entity(ow: dict) -> bool:
    name = f"{ow.get('first_name','')} {ow.get('last_name','')}".lower()
    return any(w in name for w in ENTITY_WORDS) or not (ow.get("first_name") and ow.get("last_name"))


def main() -> int:
    recs = json.loads((REPO / "output" / "nsm10_discover_20260819" /
                       "records_final.json").read_text(encoding="utf-8"))
    work = [r for r in recs if not r.get("status")]
    work.sort(key=lambda r: -(r.get("directmail_attempts") or 0))

    picked, seen_owner = [], set()
    for r in work:
        ow = r.get("owner") or {}
        key = ((ow.get("first_name") or "").lower(), (ow.get("last_name") or "").lower())
        if is_entity(ow) or key in seen_owner:
            continue
        seen_owner.add(key)
        picked.append(r)
        if len(picked) >= N_PILOT:
            break
    print(f"pilot batch: {len(picked)} records")

    h = headers(get_token())
    results = []
    quota_dead = False
    for r in picked:
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
        cf = {}
        for f in (d.get("custom_fields") or d.get("customfields") or []):
            t = (f.get("title") or f.get("name") or "") if isinstance(f, dict) else ""
            v = f.get("value") if isinstance(f, dict) else None
            if t:
                cf[t] = v
        case_no = next((str(v) for k, v in cf.items()
                        if "case" in k.lower() and v), "")
        county = next((str(v) for k, v in cf.items()
                       if "county" in k.lower() and v), "")

        entry = {
            "uuid": uuid, "property": label,
            "prop_state": a.get("state"), "prop_zip": a.get("zip5") or a.get("postal_code"),
            "dm_first": ow.get("first_name"), "dm_last": ow.get("last_name"),
            "dm_mail": f"{mail.get('street','')}, {mail.get('city','')} {mail.get('state','')} {mail.get('zip5') or mail.get('postal_code','')}",
            "dm_attempts": r.get("directmail_attempts"),
            "case_no": case_no, "county": county,
            "existing_phones": sorted(existing),
            "lists": [l.get("title") if isinstance(l, dict) else str(l) for l in (d.get("lists") or [])],
            "tags": [t.get("title") if isinstance(t, dict) else str(t) for t in (d.get("tags") or [])],
        }

        if quota_dead:
            entry["enformion"] = "skipped — quota wall hit earlier"
            results.append(entry)
            continue
        ef = person_search_phones(ow.get("first_name") or "", ow.get("last_name") or "",
                                  mail.get("city") or "", mail.get("state") or "NC",
                                  mail.get("zip5") or (mail.get("postal_code") or "")[:5])
        if ef is None:
            entry["enformion"] = None
            print(f"  {label}: DM {ow.get('first_name')} {ow.get('last_name')} -> Enformion MISS")
        else:
            entry["enformion"] = ef
            new = [p for p in (ef.get("mobiles") or []) + (ef.get("landlines") or [])
                   if "".join(c for c in p if c.isdigit())[-10:] not in existing]
            entry["new_phones"] = new
            print(f"  {label}: DM {ow.get('first_name')} {ow.get('last_name')} -> "
                  f"matched {ef.get('matched_name')!r} deceased={ef.get('is_deceased')} "
                  f"mobiles={ef.get('mobiles')} landlines={ef.get('landlines')} "
                  f"new={len(new)} existing={len(existing)}")
        results.append(entry)

    # Trestle-score every NEW phone in one batch
    to_score = []
    for e in results:
        for p in (e.get("new_phones") or []):
            to_score.append((f"{e['dm_first']} {e['dm_last']} @ {e['property']}", clean_phone(p)))
    print(f"\nTrestle: scoring {len(to_score)} new phone(s) (~${len(to_score) * 0.015:.2f})")
    if to_score:
        key = os.environ["TRESTLE_API_KEY"]
        scored, errors = process_phones(to_score, key, add_litigator=True)
        by_num = {r.get("phone_number") or r.get("phone"): r for r in scored}
        for e in results:
            e["scored"] = []
            for p in (e.get("new_phones") or []):
                c = clean_phone(p)
                r = by_num.get(c, {})
                e["scored"].append({
                    "phone": c, "score": r.get("activity_score"),
                    "line_type": r.get("line_type"),
                    "litigator": r.get("litigator_risk", r.get("is_litigator_risk")),
                })
        for err in errors:
            print("  trestle err:", err)

    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
