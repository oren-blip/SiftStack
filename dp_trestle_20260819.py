"""Trestle-score the deduped 8/19 DP dial list via phone_validator.process_phones
(the cache-compatible path — see dp-skill-script-gotchas). ~20 numbers ≈ $0.30.
Results saved to output/dp_trestle_20260819.json."""
import json
import os
import sys

sys.path.insert(0, r"d:\SiftStack\src")
try:
    from dotenv import load_dotenv
    load_dotenv(r"d:\SiftStack\.env")
except Exception:
    pass

from phone_validator import clean_phone, process_phones  # noqa: E402

# (owner label, raw phone) — deduped across signers
DIAL = [
    ("Gregory: Michael Kyle Gregory (son, AT property)", "7045601527"),
    ("Gregory: Michael Kyle Gregory landline", "7046970610"),
    ("Gregory: household landline", "7043929157"),
    ("Adams: Marianne Wagnon (widow, AT property)", "7043407961"),
    ("Adams: Marianne Wagnon alt", "7043407962"),
    ("Adams: John Taylor Adams (son, Guthrie OK)", "9158759999"),
    ("Adams: John Taylor Adams voip", "9152199517"),
    ("Dunlap: Stephen Russel Dunlap (son, S Chesterfield VA)", "7047137391"),
    ("Dunlap: Stephen Russel Dunlap alt", "7047060890"),
    ("Dunlap: Judy Ann Dunlap (kin, at/near property) NEW", "7044491342"),
    ("Dunlap: Aretha Mic Dunlap (daughter, Charlotte)", "7049091302"),
    ("Dunlap: Aretha Mic Dunlap alt", "9802261496"),
    ("Zion: Christopher George Zion (son, Asheville) CONFIRMED", "7045721093"),
    ("Overcash: Kathryn S Dixon (tax contact, China Grove)", "7046407591"),
    ("Overcash: Kathryn S Dixon landline", "7048570662"),
    ("Overcash: Timothy Dale Overcash (son, Concord)", "7047874789"),
    ("Overcash: Timothy Dale Overcash alt", "7044256644"),
    ("Archie: Eboni R Archie (tax contact, Salisbury)", "2024009396"),
    ("Archie: Eboni R Archie alt", "2025849144"),
]

key = os.environ["TRESTLE_API_KEY"]
phones = [(label, clean_phone(num)) for label, num in DIAL]
results, errors = process_phones(phones, key, add_litigator=True)

by_num = {r.get("phone_number") or r.get("phone"): r for r in results}
out = []
for label, num in DIAL:
    c = clean_phone(num)
    r = by_num.get(c, {})
    row = {"label": label, "phone": c,
           "score": r.get("activity_score"), "tier": r.get("tier"),
           "line_type": r.get("line_type"),
           "litigator": r.get("litigator_risk") if "litigator_risk" in r else r.get("is_litigator_risk")}
    out.append(row)
    print(f"{c}  score={row['score']!s:>4}  {row['tier']!s:<12} {row['line_type']!s:<10} lit={row['litigator']!s:<5} {label}")

if errors:
    print("\nerrors:")
    for e in errors:
        print(" ", e)

with open(r"d:\SiftStack\output\dp_trestle_20260819.json", "w", encoding="utf-8") as f:
    json.dump({"results": out, "errors": errors, "raw": results}, f, indent=1)
print("\nsaved output/dp_trestle_20260819.json")
