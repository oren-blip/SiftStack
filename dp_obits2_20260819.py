"""Serper round 2: Adams survivors paragraph + Archie Noble&Kelsey James +
Dunlap/Zion alternate phrasing. Cached."""
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
    "obit_adams2": '"Boyd C. Adams" obituary survived wife',
    "obit_adams3": '"Boyd Adams" Charlotte "Marianne"',
    "obit_archie2": '"James Archie" "Noble & Kelsey" obituary',
    "obit_archie3": '"James E. Archie" obituary NC',
    "obit_dunlap2": '"Dunlap" obituary Charlotte "Query"',
    "obit_zion2": '"Zion" obituary 2026 Matthews OR Charlotte "Kenneth"',
}

for tag, q in QUERIES.items():
    f = CACHE / f"{tag}.json"
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
    else:
        r = requests.post("https://google.serper.dev/search",
                          headers={"X-API-KEY": KEY, "Content-Type": "application/json"},
                          json={"q": q, "num": 10}, timeout=30)
        if r.status_code != 200:
            print(f"[{tag}] HTTP {r.status_code}")
            continue
        data = r.json()
        f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"===== {tag}: {q}")
    for o in (data.get("organic") or [])[:5]:
        print(" -", o.get("title"), "|", o.get("link"))
        print("   ", (o.get("snippet") or "").replace("\n", " ")[:320])
    print()
