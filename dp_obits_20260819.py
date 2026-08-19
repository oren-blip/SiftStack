"""Serper obituary sweep for the 8/19 DP batch. READ-ONLY. Results cached."""
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, r"d:\SiftStack")
try:
    from dotenv import load_dotenv
    load_dotenv(r"d:\SiftStack\.env")
except Exception:
    pass

CACHE = Path(r"d:\SiftStack\output\dp_enformion_20260819")
KEY = os.environ["SERPER_API_KEY"]

QUERIES = {
    "obit_gregory": '"William Anthony Gregory" OR "William A. Gregory" obituary Charlotte NC',
    "obit_adams": '"Boyd Adams" obituary Charlotte NC',
    "obit_dunlap": '"Query Dunlap" obituary Charlotte',
    "obit_zion": '"Kenneth Zion" obituary Matthews NC',
    "obit_overcash": '"Jessie Overcash" obituary China Grove NC',
    "obit_archie": '"James Archie" obituary Salisbury NC',
}

for tag, q in QUERIES.items():
    f = CACHE / f"{tag}.json"
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
        print(f"[{tag}] cache hit")
    else:
        r = requests.post("https://google.serper.dev/search",
                          headers={"X-API-KEY": KEY, "Content-Type": "application/json"},
                          json={"q": q, "num": 10}, timeout=30)
        print(f"[{tag}] HTTP {r.status_code}")
        if r.status_code != 200:
            continue
        data = r.json()
        f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"===== {tag}: {q}")
    for o in (data.get("organic") or [])[:6]:
        print(" -", o.get("title"))
        print("   ", o.get("link"))
        print("   ", (o.get("snippet") or "").replace("\n", " ")[:300])
    print()
