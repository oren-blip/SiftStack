"""Trace the new Escambia buyer principals (2026-09-03).

Enformion PersonSearch (address-anchored, $0.35/match, capped) for the 10
decision-makers with no public phone, then Trestle-score every number
(cache-first from output/.trestle_score_cache.json) and merge with the
already-published office phones. Output: one skip-trace-ready call sheet.

Nothing touches DataSift.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")

import enformion_client  # noqa: E402
from phone_validator import clean_phone, process_phones  # noqa: E402

CACHE_PATH = REPO / "output" / ".trestle_score_cache.json"
OUT_PATH = REPO / "output" / "pensacola_new_buyers_call_sheet_2026-09-03.csv"

# (buyer entity, person, first, last, city, state, zip)
TRACE_TARGETS = [
    ("Alpine Trust & Properties", "Charles Contreras", "Charles", "Contreras", "Deerfield Beach", "FL", "33441"),
    ("True Haven / The Friendly Home Buyer", "Jared Sandel", "Jared", "Sandel", "Winter Haven", "FL", "33881"),
    ("C2C Homes", "Robert Seidler", "Robert", "Seidler", "Miami Beach", "FL", "33139"),
    ("Home Discounters", "Stan Zimmerman", "Stan", "Zimmerman", "Delray Beach", "FL", "33483"),
    ("Hamby Housing / Oak House", "Michael Hamby", "Michael", "Hamby", "Pensacola", "FL", "32502"),
    ("Martins Acquisitions", "Braden Martin", "Braden", "Martin", "Cantonment", "FL", "32533"),
    ("Irby Ventures", "Jared Irby", "Jared", "Irby", "Mobile", "AL", "36693"),
    ("First Nest", "Victor Naar", "Victor", "Naar", "Boca Raton", "FL", "33433"),
    ("NestVestors FL", "Nestor Rodriguez", "Nestor", "Rodriguez", "Miami", "FL", "33156"),
    ("Florida Investors Capital (capital side)", "Vincent Cassidy", "Vincent", "Cassidy", "Tampa", "FL", "33611"),
]

# Publicly published numbers from the 9/2 research (no trace needed).
KNOWN_PHONES = [
    ("Sandy Buys Pensacola / East Hill Restorations", "Sandy Blanton", "8509355036", "office (Team Sandy Blanton Realty)"),
    ("Sandy Buys Pensacola / East Hill Restorations", "Sandy Blanton", "8505549544", "published cell"),
    ("Cornerstone Properties of NWF", "Jansen McLendon", "8509722061", "office (cornerstonenwf.com)"),
    ("Panhandle Real Estate Investments", "Peyton Saluto", "8507782212", "office (thepanhandlehomebuyer.com)"),
    ("Father Daughter Properties / FD Builds", "Jessica Ford", "8506053331", "BBB listing"),
    ("Bay to Gulf Holdings (wholesaler)", "Christopher Smith", "8134763199", "BBB listing"),
    ("850 Property Consulting", "Jonathan Graham", "8508241332", "JGraham Contracting"),
    ("Bay Living (ops side)", "Edward Thornburg", "8139577383", "office (baylivinginc.com)"),
    ("Fowey Investments (LAND buyer)", "Nicholas Ralph-Ortueta", "2392994464", "foweyinvestments.com"),
]


def main() -> None:
    rows = []  # (buyer, person, phone10, source_note)

    print("=== Enformion trace (address-anchored) ===")
    for buyer, person, first, last, city, state, zc in TRACE_TARGETS:
        res = enformion_client.person_search_phones(first, last, city, state, zc)
        if not res:
            print(f"  MISS  {person:<20} ({buyer})")
            continue
        if res.get("is_deceased"):
            print(f"  SKIP  {person:<20} flagged deceased — verify by hand")
            continue
        got = res.get("mobiles", []) + res.get("landlines", [])
        print(f"  HIT   {person:<20} {len(got)} phones (matched: {res.get('matched_name','?')})")
        for n in got:
            d = "".join(c for c in n if c.isdigit())[-10:]
            if len(d) == 10:
                rows.append((buyer, person, d, "Enformion 2026-09-03"))

    spend = enformion_client.spend_this_run()
    print(f"Enformion spend this run: ${spend:.2f}")

    for buyer, person, num, note in KNOWN_PHONES:
        rows.append((buyer, person, num, note))

    # De-dupe on (person, phone)
    seen = set()
    deduped = []
    for r in rows:
        k = (r[1], r[2])
        if k not in seen:
            seen.add(k)
            deduped.append(r)
    rows = deduped

    # ── Trestle scoring: cache first, API for the rest ────────────────────
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    need = [n for _, _, n, _ in rows if n not in cache]
    need = list(dict.fromkeys(need))
    print(f"=== Trestle: {len(rows)} numbers, {len(rows) - len(need)} cached, "
          f"{len(need)} new (~${len(need) * 0.015:.2f}) ===")
    if need:
        api_key = os.environ.get("TRESTLE_API_KEY", "")
        if not api_key:
            print("No TRESTLE_API_KEY — new numbers left unscored (kept).")
        else:
            results, errors = process_phones(
                [(n, clean_phone(n)) for n in need], api_key, add_litigator=True)
            for r in results:
                d = "".join(c for c in str(r.get("phone_number", "")) if c.isdigit())[-10:]
                if len(d) == 10:
                    cache[d] = {
                        "phone_number": d,
                        "activity_score": str(r.get("activity_score", "")),
                        "line_type": r.get("line_type", ""),
                        "carrier": r.get("carrier", ""),
                        "is_valid": str(r.get("is_valid", "")),
                        "is_prepaid": str(r.get("is_prepaid", "")),
                        "assigned_tag": r.get("assigned_tag", r.get("tier", "")),
                        "is_litigator_risk": r.get("is_litigator_risk"),
                    }
            if errors:
                print(f"  {len(errors)} Trestle errors (numbers kept unscored)")
            CACHE_PATH.write_text(json.dumps(cache, indent=1))

    # ── Write the call sheet, best numbers first ──────────────────────────
    tier_rank = {"Dial First": 0, "Dial Second": 1, "Dial Third": 2,
                 "Dial Fourth": 3, "": 4, None: 4, "Drop": 5, "Litigator - DNC": 6}
    out = []
    for buyer, person, num, note in rows:
        c = cache.get(num, {})
        tag = c.get("assigned_tag", "")
        if c.get("is_litigator_risk") in (True, "True"):
            tag = "Litigator - DNC"
        out.append({
            "Buyer": buyer, "Person": person,
            "Phone": f"({num[:3]}) {num[3:6]}-{num[6:]}",
            "Line Type": c.get("line_type", ""),
            "Score": c.get("activity_score", ""),
            "Tier": tag or "(unscored - keep)",
            "Source": note,
        })
    out.sort(key=lambda r: (tier_rank.get(r["Tier"].split(" (")[0], 4)
                            if r["Tier"] != "(unscored - keep)" else 4,
                            r["Buyer"]))
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {len(out)} rows -> {OUT_PATH}")
    print(f"TOTAL COST: Enformion ${spend:.2f} + Trestle ~${len(need) * 0.015:.2f}")


if __name__ == "__main__":
    main()
