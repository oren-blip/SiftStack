"""Trestle scoring, wave 2 (Scearce/Keener/Courteau signers). ~8 numbers ≈ $0.12."""
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

DIAL = [
    ("Scearce: Cheryl P Scearce (widow co-trustee, AT property)", "7047986425"),
    ("Keener: Jeffrey S Lawson (son, 7030 Martin Mill Rd)", "8282440250"),
    ("Keener: Jeffrey Lawson home landline", "8283227030"),
    ("Courteau: Everette William Courteau (son, Acworth GA)", "3365492756"),
    ("Courteau: Everette landline", "7709749132"),
    ("Courteau: Robert Clinton Courteau (son, S Chesterfield VA)", "8046472756"),
    ("Courteau: Robert Clinton alt", "8046517860"),
    ("Courteau: Robert Clinton alt2", "8049129919"),
]

key = os.environ["TRESTLE_API_KEY"]
phones = [(label, clean_phone(num)) for label, num in DIAL]
results, errors = process_phones(phones, key, add_litigator=True)
by_num = {r.get("phone_number") or r.get("phone"): r for r in results}
out = []
for label, num in DIAL:
    c = clean_phone(num)
    r = by_num.get(c, {})
    row = {"label": label, "phone": c, "score": r.get("activity_score"),
           "line_type": r.get("line_type"),
           "litigator": r.get("litigator_risk") if "litigator_risk" in r else r.get("is_litigator_risk")}
    out.append(row)
    print(f"{c}  score={row['score']!s:>4}  {row['line_type']!s:<10} lit={row['litigator']!s:<5} {label}")
for e in errors:
    print("err:", e)
json.dump({"results": out, "errors": errors},
          open(r"d:\SiftStack\output\dp_trestle2_20260819.json", "w", encoding="utf-8"), indent=1)
print("saved output/dp_trestle2_20260819.json")
