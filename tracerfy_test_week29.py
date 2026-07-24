"""One-off test: Tracerfy the no-phone Week-29 records; report hit rate + new numbers.

Pulls the no-phone records from the DataSift export, drops non-person rows
("Heirs"/"Estate") and duplicate PRs, traces each PR by their MAILING (residence)
address via Tracerfy's batch API, and reports how many got phones. Writes results
to output/tracerfy_week29_results.csv for a possible DataSift upload.
"""
import csv, io, re, sys, time
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()
import requests
import config as cfg

TRACE_URL = "https://tracerfy.com/v1/api/trace/"
QUEUE_URL = "https://tracerfy.com/v1/api/queue/"
PHONE_FIELDS = ["primary_phone","mobile_1","mobile_2","mobile_3","mobile_4",
                "mobile_5","landline_1","landline_2","landline_3"]
EMAIL_FIELDS = ["email_1","email_2","email_3","email_4","email_5"]

def digits(s): return re.sub(r"\D","",s or "")

def main():
    if not cfg.TRACERFY_API_KEY:
        print("NO TRACERFY_API_KEY set"); return
    ex = list(csv.DictReader(open("output/phone_enrichment_export.csv", encoding="utf-8-sig")))
    phone_cols = [c for c in ex[0].keys() if re.fullmatch(r"Phone \d", c)]
    nophone = [r for r in ex if not any(digits(r.get(c)) for c in phone_cols)]

    rows, seen = [], set()
    skipped_nonperson = []
    for r in nophone:
        first = (r.get("First Name") or "").strip()
        last = (r.get("Last Name") or "").strip()
        if first.lower() in ("heirs", "estate", "estate of") or first.lower().startswith("estate"):
            skipped_nonperson.append(f"{first} {last}"); continue
        addr = (r.get("Mailing address") or "").strip()
        city = (r.get("Mailing city") or "").strip()
        state = (r.get("Mailing state") or "").strip() or "NC"
        zp = (r.get("Mailing zip5") or r.get("Mailing zip") or "").strip()[:5]
        key = (first.lower(), last.lower(), addr.lower())
        if not (first and last and addr) or key in seen:
            continue
        seen.add(key)
        rows.append({"first_name": first, "last_name": last, "address": addr,
                     "city": city, "state": state, "zip": zp})

    print(f"no-phone records: {len(nophone)} | non-person skipped: {len(skipped_nonperson)} {skipped_nonperson}")
    print(f"unique persons to trace: {len(rows)}  (~${len(rows)*0.02:.2f})\n")

    # Match the working payload in tracerfy_skip_tracer.batch_skip_trace exactly:
    # include the mail_* columns (blank) and all column-mapping keys.
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["first_name","last_name","address","city","state","zip",
                "mail_address","mail_city","mail_state"])
    for r in rows:
        w.writerow([r["first_name"], r["last_name"], r["address"], r["city"],
                    r["state"], r["zip"], "", "", ""])

    resp = requests.post(TRACE_URL,
        headers={"Authorization": f"Bearer {cfg.TRACERFY_API_KEY}"},
        data={"first_name_column":"first_name","last_name_column":"last_name",
              "address_column":"address","city_column":"city","state_column":"state",
              "zip_column":"zip","mail_address_column":"mail_address",
              "mail_city_column":"mail_city","mail_state_column":"mail_state",
              "mailing_zip_column":"zip"},
        files={"csv_file": ("skip_trace_batch.csv", buf.getvalue(), "text/csv")}, timeout=30)
    if resp.status_code == 402:
        print("402 INSUFFICIENT CREDITS:", resp.text[:300]); return
    resp.raise_for_status()
    qid = resp.json().get("queue_id")
    print(f"submitted queue_id={qid}; polling...")

    records = None
    for attempt in range(72):
        time.sleep(5)
        rr = requests.get(f"{QUEUE_URL}{qid}",
                          headers={"Authorization": f"Bearer {cfg.TRACERFY_API_KEY}"}, timeout=15)
        rr.raise_for_status(); d = rr.json()
        if isinstance(d, list): records = d; break
        st = d.get("status","")
        if st == "failed": print("job failed"); return
        if st == "completed": records = d.get("records", []); break
        if attempt % 6 == 5: print(f"  ...processing ({(attempt+1)*5}s)")
    if records is None:
        print("timed out"); return

    # match + report
    idx = {(r["first_name"].lower(), r["last_name"].lower()): r for r in rows}
    out = []
    matched = phones_total = emails_total = 0
    for rec in records:
        f = (rec.get("first_name") or "").strip().lower()
        l = (rec.get("last_name") or "").strip().lower()
        ph = [rec.get(x).strip() for x in PHONE_FIELDS if (rec.get(x) or "").strip()]
        em = [rec.get(x).strip() for x in EMAIL_FIELDS if (rec.get(x) or "").strip()]
        base = idx.get((f, l), {})
        if ph or em: matched += 1
        phones_total += len(ph); emails_total += len(em)
        out.append({"first_name": rec.get("first_name",""), "last_name": rec.get("last_name",""),
                    "phones": " | ".join(ph), "n_phones": len(ph),
                    "emails": " | ".join(em), "address": base.get("address","")})

    with open("output/tracerfy_week29_results.csv","w",newline="",encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=["first_name","last_name","phones","n_phones","emails","address"])
        wr.writeheader(); wr.writerows(out)

    print(f"\n=== RESULTS ===")
    print(f"submitted: {len(rows)} | records returned: {len(records)}")
    print(f"got >=1 phone or email: {matched}/{len(rows)}  ({100*matched/max(len(rows),1):.0f}% hit rate)")
    print(f"total phones found: {phones_total} | total emails: {emails_total}")
    print(f"\nper-person (name | #phones | phones):")
    for o in sorted(out, key=lambda x: -x["n_phones"]):
        print(f"  {o['first_name']:12} {o['last_name']:16} {o['n_phones']} {o['phones'][:50]}")
    print("\nsaved -> output/tracerfy_week29_results.csv")

if __name__ == "__main__":
    main()
