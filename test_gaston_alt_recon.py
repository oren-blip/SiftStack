"""Alternative Gaston Gazette legal-notice sources after mypublicnotices.com
went dead. Try the Gannett classifieds platform + a few other candidates.
"""

import re
import socket
from pathlib import Path

import requests

H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

OUT = Path("output/gaston_alt_recon")
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [
    # Gannett classifieds platform (research agent listed)
    "https://classifieds.gannettclassifieds.com/marketplace/gas/category/legals/notice-to-creditors",
    "https://classifieds.gannettclassifieds.com/marketplace/gas/",
    "https://classifieds.gannettclassifieds.com/marketplace/gas/category/legals/",
    "https://classifieds.gannettclassifieds.com/marketplace/gas/category/legals/foreclosure",
    # Gaston Gazette direct
    "https://www.gastongazette.com/legals/",
    "https://www.gastongazette.com/public-notices/",
    "https://www.gastongazette.com/legalnotices/",
    # column.us — does Gaston have a subdomain?
    "https://gastongazette.column.us/search",
    # Other classifieds platforms
    "https://classifieds.gastongazette.com/",
    "https://placeanad.gastongazette.com/",
]

for url in TARGETS:
    host = url.split("/")[2]
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        ip = "DNS-FAIL"
    print(f"\n=== {url}")
    print(f"  DNS({host}) = {ip}")
    if ip == "DNS-FAIL":
        continue
    try:
        r = requests.get(url, headers=H, timeout=15, allow_redirects=True)
    except Exception as e:
        print(f"  REQ ERR: {e}")
        continue
    print(f"  status={r.status_code}  len={len(r.text)}  final={r.url}")
    if r.status_code != 200 or len(r.text) < 1000:
        continue
    # Strip
    text = r.text
    name = re.sub(r"[^\w.-]+", "_", url.replace("://", "_"))[-80:]
    (OUT / f"{name}.html").write_text(text, encoding="utf-8")
    body = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", text, flags=re.IGNORECASE)
    body = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
    print(f"  text body: {len(body)} chars")
    print(f"  Foreclosure: {body.lower().count('foreclosure')}")
    print(f"  Notice to Creditors: {body.lower().count('notice to creditors')}")
    print(f"  Trustee: {body.lower().count('trustee')}")
    print(f"  Gaston: {body.count('Gaston')}")
    detail_links = re.findall(r'href="([^"]*(?:Detail|Notice|Ad|legals?)[^"]*)"', text, re.IGNORECASE)
    print(f"  detail-like links: {len(detail_links)}  sample: {detail_links[:3]}")
