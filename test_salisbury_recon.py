"""Recon Salisbury Post AdHunter classifieds for Rowan foreclosure notices.

Research described this as 'classic server-rendered HTML with pagination,
very scrape-friendly, no login/CAPTCHA' — verify before building.

Class 2600 = Public Notices in AdHunter.
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
}

OUT = Path("output/salisbury_recon")
OUT.mkdir(parents=True, exist_ok=True)

for url in [
    "https://marketplace.salisburypost.com/AdHunter/SalisburyPost/Home/Search?majorClass=2600",
    "https://marketplace.salisburypost.com/AdHunter/SalisburyPost/",
    "https://marketplace.salisburypost.com/AdHunter/SalisburyPost/Home/Index",
]:
    print(f"\n=== {url} ===")
    try:
        r = requests.get(url, headers=H, timeout=20, allow_redirects=True)
    except Exception as e:
        print(f"  ERR: {e}")
        continue
    print(f"  status={r.status_code}  len={len(r.text)}  final={r.url}")
    text = r.text
    name = re.sub(r"[^\w.-]+", "_", url.split("/")[-1] or "root")
    (OUT / f"{name}.html").write_text(text, encoding="utf-8")
    # Strip scripts + tags to get clean body
    body = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", text, flags=re.IGNORECASE)
    body = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    (OUT / f"{name}_text.txt").write_text(body, encoding="utf-8")
    # Markers
    print(f"  text body len: {len(body)}")
    print(f"  has 'Foreclosure': {body.lower().count('foreclosure')}")
    print(f"  has 'Notice to Creditors': {body.lower().count('notice to creditors')}")
    print(f"  has 'Trustee': {body.lower().count('trustee')}")
    print(f"  has 'Rowan': {body.count('Rowan')}")
    # Count outbound ad links
    ad_links = re.findall(r'href="(/AdHunter/[^"]+(?:Ad|Detail|View)[^"]*)"', text, re.IGNORECASE)
    print(f"  ad-detail links: {len(ad_links)}  sample: {ad_links[:3]}")
    # Money / dates
    money = re.findall(r"\$[\d,]+\.\d{2}", body)
    dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", body)
    addrs = re.findall(
        r"\b\d{2,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+"
        r"(?:St|Ave|Rd|Dr|Ln|Ct|Cir|Way|Blvd|Pkwy|Pl|Hwy|Highway)\b",
        body,
    )
    print(f"  dates: {len(dates)}  money: {len(money)}  addrs: {len(addrs)}")
    if addrs[:3]:
        print(f"  sample addrs: {addrs[:3]}")
