"""Grade the 9/4 Enformion matches before anything is pushed anywhere.

Only 5 of 20 came back with the search email ON the record. The other 15 were matched by
surname from an email-anchored search, i.e. Enformion fell back to the name - and 9 of
those landed far outside the Pensacola area (WI, CA, MD, AZ, APO, KY, NH...). A wrong
person's phones must not reach the sheet as "verified", let alone DataSift.

  high   = email on the Enformion record, OR first+last match with a Pensacola-area address
  low    = surname-only match with an out-of-area address (phones kept but flagged UNVERIFIED)
  reject = returned first name differs from the Facebook name (Desmond -> Chekitha)
"""
import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent
CSV_PATH = REPO / "output" / "pensacola_fb_cash_buyers_2026-09-04.csv"
AUDIT = REPO / "output" / "pensacola_fb_buyer_trace_2026-09-04.json"
AREA = ("pensacola", "milton", "pace,", "cantonment", "gulf breeze", "navarre", "destin", "fort walton",
        "niceville", "crestview", "mobile, al", "daphne", "fairhope", "foley")

audit = {a["name"]: a for a in json.loads(AUDIT.read_text(encoding="utf-8")) if a["result"] == "hit"}
rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig", newline="")))
for r in rows:
    r.setdefault("Trace Confidence", "")
    name = re.sub(r"\s*[-–].*$", "", r["Name"]).strip()
    a = audit.get(name)
    if not a:
        continue
    fb_first = name.split()[0].lower()
    m_first = (a["matched_name"].split() or [""])[0].lower()
    addr = (a["address"].get("fullAddress") or "").lower()
    in_area = any(c in addr for c in AREA)
    email_on_record = "email on record" in a["how"]
    first_ok = m_first == fb_first or m_first[:3] == fb_first[:3] or (fb_first, m_first) in {
        ("billy", "william"), ("becky", "rebecca"), ("mehdi", "mohamed"), ("bob", "robert"), ("rob", "robert")}
    if not first_ok:
        r["Trace Confidence"] = f"REJECTED - Enformion returned {a['matched_name']}"
        r["Phones"] = ""
        r["Phone Tiers"] = ""
        r["Traced Address"] = ""
        r["Trace Note"] = f"trace rejected 9/4 (returned {a['matched_name']})"
        flags = [f for f in r["Flags"].split("; ") if f]
        flags.append("trace rejected - wrong person")
        r["Flags"] = "; ".join(flags)
        continue
    if email_on_record:
        r["Trace Confidence"] = "high - email on Enformion record"
    elif in_area:
        r["Trace Confidence"] = "high - name match + Pensacola-area address"
    else:
        r["Trace Confidence"] = "LOW - surname-only match, address outside the area"
        flags = [f for f in r["Flags"].split("; ") if f]
        flags.append("phones UNVERIFIED (trace matched by name only, out of area)")
        r["Flags"] = "; ".join(flags)

with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
from collections import Counter
print(Counter(r["Trace Confidence"].split(" -")[0] for r in rows if r["Trace Confidence"]))
for r in rows:
    if r["Trace Confidence"]:
        print(f"  {r['Trace Confidence'][:44]:<44} {r['Name'][:24]:<24} {r['Traced Address'][:40]}")
