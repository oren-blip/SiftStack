"""Recon mypublicnotices.com/gastongazette for Gaston foreclosure + probate.

Research described this as 'older HTML/ASP, often crawlable but limited
search. No login.' Verify.
"""

import re
from pathlib import Path

import requests

H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

OUT = Path("output/mypublicnotices_recon")
OUT.mkdir(parents=True, exist_ok=True)

for url in [
    "http://www.mypublicnotices.com/gastongazette/",
    "https://www.mypublicnotices.com/gastongazette/",
    "http://www.mypublicnotices.com/GastonGazette/Search.asp",
    "https://publicnotices.mypublicnotices.com/gastongazette/",
]:
    print(f"\n=== {url} ===")
    try:
        r = requests.get(url, headers=H, timeout=20, allow_redirects=True)
    except Exception as e:
        print(f"  ERR: {e}")
        continue
    print(f"  status={r.status_code}  len={len(r.text)}  final={r.url}")
    name = re.sub(r"[^\w.-]+", "_", url.replace("://", "_"))[-80:]
    text = r.text
    (OUT / f"{name}.html").write_text(text, encoding="utf-8")
    # Strip
    body = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", text, flags=re.IGNORECASE)
    body = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    (OUT / f"{name}.txt").write_text(body, encoding="utf-8")
    print(f"  text body: {len(body)} chars")
    # Markers
    print(f"  Foreclosure: {body.lower().count('foreclosure')}")
    print(f"  Notice to Creditors: {body.lower().count('notice to creditors')}")
    print(f"  Trustee: {body.lower().count('trustee')}")
    print(f"  Gaston: {body.count('Gaston')}")
    # Links suggesting detail pages
    detail_links = re.findall(r'href="([^"]*(?:Detail|Notice|Ad|ad|notice|detail)[^"]*)"', text, re.IGNORECASE)
    print(f"  detail-like links: {len(detail_links)}  sample: {detail_links[:3]}")
    # Forms
    forms = re.findall(r'<form[^>]*action="([^"]+)"', text, re.IGNORECASE)
    print(f"  forms: {forms[:3]}")
    # Show first 300 chars of body
    print(f"  body[:300]: {body[:300]!r}")
