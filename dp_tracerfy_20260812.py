"""One-shot: Tracerfy phone trace for the 2026-08-12 DP sweep alternates.

Phase-2 deep prospecting (per the standing workflow): obit/GIS-confirmed family
contacts who aren't reachable through DataSift's owner trace get Tracerfy'd at
$0.02/record. All four addresses are county-GIS deed/tax-mailing confirmed.
"""
from __future__ import annotations

import csv
import io
import sys
import time

sys.path.insert(0, "src")
import requests
from dotenv import load_dotenv

load_dotenv()
import config as cfg

TARGETS = [
    # (case, first, last, address, city, state, zip)
    ("26E000808-790", "Dale", "Mahaffey", "207 Brushy Creek Rd", "Union Grove", "NC", "28689"),
    ("26E000492-540", "Gary", "Grahl", "4907 Stagecoach Rd", "Iron Station", "NC", "28080"),
    ("26E002853-590", "Beth", "Hatcher", "5705 Verducci Ln", "Waxhaw", "NC", "28173"),
    ("26E002853-590", "Katarina", "Ward", "11234 Pointer Ridge Dr", "Charlotte", "NC", "28214"),
]


def main() -> int:
    if not cfg.TRACERFY_API_KEY:
        print("no TRACERFY_API_KEY")
        return 1
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["first_name", "last_name", "address", "city", "state",
                "zip", "mail_address", "mail_city", "mail_state"])
    for _, first, last, addr, city, state, zc in TARGETS:
        w.writerow([first, last, addr, city, state, zc, "", "", ""])
    resp = requests.post(
        "https://tracerfy.com/v1/api/trace/",
        headers={"Authorization": f"Bearer {cfg.TRACERFY_API_KEY}"},
        data={"first_name_column": "first_name", "last_name_column": "last_name",
              "address_column": "address", "city_column": "city",
              "state_column": "state", "zip_column": "zip",
              "mail_address_column": "mail_address", "mail_city_column": "mail_city",
              "mail_state_column": "mail_state", "mailing_zip_column": "zip"},
        files={"csv_file": ("dp_batch.csv", buf.getvalue(), "text/csv")},
        timeout=30,
    )
    print("submit ->", resp.status_code)
    if resp.status_code != 200:
        print(resp.text[:400])
        return 1
    qid = resp.json().get("queue_id")
    print("queue:", qid)
    for attempt in range(60):
        time.sleep(5)
        r = requests.get(f"https://tracerfy.com/v1/api/queue/{qid}",
                         headers={"Authorization": f"Bearer {cfg.TRACERFY_API_KEY}"},
                         timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            if data.get("status") == "failed":
                print("job failed")
                return 1
            if data.get("status") != "completed":
                continue
            records = data.get("records", [])
        else:
            continue
        for rec in records:
            print("\n---", rec.get("first_name"), rec.get("last_name"))
            for k, v in rec.items():
                if v and any(t in k.lower() for t in ("phone", "email", "mobile", "landline")):
                    print(f"   {k}: {v}")
        import json as _json
        with open("output/dp_tracerfy_20260812_results.json", "w", encoding="utf-8") as f:
            _json.dump(records, f, indent=1)
        print("\nsaved -> output/dp_tracerfy_20260812_results.json")
        return 0
    print("timed out")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
