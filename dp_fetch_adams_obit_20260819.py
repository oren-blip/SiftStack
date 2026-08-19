"""Fetch the Boyd Adams obituary (csofcharlotte.com 403'd the plain fetcher)."""
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.google.com/"}

for url in ("https://www.csofcharlotte.com/obituary/Boyd-Adams",
            "https://webcache.googleusercontent.com/search?q=cache:csofcharlotte.com/obituary/Boyd-Adams"):
    try:
        r = requests.get(url, headers=H, timeout=30)
        print(url, "->", r.status_code, len(r.text))
        if r.status_code == 200:
            text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            i = text.lower().find("boyd")
            print(text[max(0, i - 100): i + 2500])
            break
    except Exception as e:  # noqa: BLE001
        print(url, "ERR", e)
