"""DP 26E002931-590 step 5: Trestle-score the Thompson household phones
(all from Heather Roe Thompson's record; twins' records carry no phones)."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

from phone_validator import clean_phone, process_phones  # noqa: E402

RAW = [
    "(678) 200-0883",  # wireless, conn=True
    "(704) 507-7444",  # wireless, conn=True
    "(770) 507-7444",  # landline, conn=True (area-code twin of above)
    "(704) 948-6403",  # landline, conn=True (Charlotte-era)
    "(704) 948-6405",  # landline, conn=True
    "(770) 507-4787",  # landline, conn=True
    "(770) 474-2388",  # landline, conn=True
]

phones = [(r, clean_phone(r)) for r in RAW]
results, errors = process_phones(phones, os.environ["TRESTLE_API_KEY"], add_litigator=True)

print(f"{'PHONE':<16}{'SCORE':<7}{'TIER':<22}{'TYPE':<12}{'LIT':<6}VALID")
for r in sorted(results, key=lambda x: -(x["activity_score"] or 0)):
    print(f"{r['phone_number']:<16}{str(r['activity_score']):<7}{str(r['assigned_tag']):<22}"
          f"{str(r['line_type']):<12}{str(r['is_litigator_risk']):<6}{r['is_valid']}")
for e in errors:
    print("ERR:", e)
