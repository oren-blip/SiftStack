"""Serper: locate the Rowan County NC Register of Deeds online search portal."""
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
    "rod_portal": "Rowan County NC register of deeds online record search portal",
    "rod_overcash": '"Overcash" deed Rowan County NC "Chow" OR "heirs"',
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
            print(tag, "HTTP", r.status_code)
            continue
        data = r.json()
        f.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print("=====", tag, ":", q)
    for o in (data.get("organic") or [])[:8]:
        print(" -", o.get("title"), "|", o.get("link"))
        print("   ", (o.get("snippet") or "")[:200])
