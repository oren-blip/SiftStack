"""Recon Catawba + Lincoln + Rowan annual delinquent-tax PDF pages.

Goals:
  - Confirm the landing pages are reachable
  - Find direct PDF URLs for the most recent year (2026 ideally, or 2025)
  - Sample a small portion of one PDF to confirm we can parse it
"""

import re
from pathlib import Path

import requests

H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}

OUT = Path("output/county_pdf_recon")
OUT.mkdir(parents=True, exist_ok=True)


TARGETS = [
    # Catawba: research said catawbacountync.gov/docs/tax/delinquent-advertisement-list-hdr-2026/
    ("catawba", "Catawba", [
        "https://catawbacountync.gov/docs/tax/delinquent-advertisement-list-hdr-2026/",
        "https://catawbacountync.gov/docs/tax/delinquent-advertisement-list-hdr-2025/",
        "https://catawbacountync.gov/county-services/tax/delinquent-tax-lists/",
        "https://catawbacountync.gov/county-services/tax/",
    ]),
    # Lincoln: 2024 PDF was at lincolncountync.gov/DocumentCenter/View/23797
    ("lincoln", "Lincoln", [
        "https://www.lincolncountync.gov/80/Collection",
        "https://www.lincolncountync.gov/DocumentCenter/Index/23",  # tax doc center
        "https://www.lincolncountync.gov/2368/Foreclosures",
    ]),
    # Rowan: rowancountync.gov/1525/Delinquent-Taxpayer-Lists
    ("rowan", "Rowan", [
        "https://www.rowancountync.gov/1525/Delinquent-Taxpayer-Lists",
        "https://www.rowancountync.gov/201/Tax-Collector",
    ]),
]


def fingerprint(slug: str, county: str, url: str) -> str:
    """GET the URL, save HTML, return body text."""
    print(f"\n  --> {url}")
    try:
        r = requests.get(url, headers=H, timeout=20, allow_redirects=True)
    except Exception as e:
        print(f"      ERR: {e}")
        return ""
    print(f"      status={r.status_code}  len={len(r.text)}  final={r.url}")
    if r.status_code != 200:
        return ""
    if r.headers.get("Content-Type", "").startswith("application/pdf"):
        # Direct PDF — save it
        fname = OUT / f"{slug}_{url.rsplit('/', 1)[-1] or 'doc'}.pdf"
        fname.write_bytes(r.content)
        print(f"      PDF saved: {fname}  ({len(r.content)} bytes)")
        return ""
    name = re.sub(r"[^\w.-]+", "_", url.replace("://", "_"))[-80:]
    (OUT / f"{slug}_{name}.html").write_text(r.text, encoding="utf-8")
    # Find PDF links
    pdf_links = sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.IGNORECASE)))
    print(f"      .pdf links: {len(pdf_links)}")
    for p in pdf_links[:8]:
        print(f"        - {p}")
    # Look for DocumentCenter / View links (CivicPlus pattern)
    doc_links = sorted(set(re.findall(
        r'href="(/?DocumentCenter/View/\d+[^"]*)"', r.text, re.IGNORECASE,
    )))
    print(f"      DocumentCenter/View links: {len(doc_links)}")
    for p in doc_links[:8]:
        print(f"        - {p}")
    # Catawba-style /docs/ pattern
    docs_links = sorted(set(re.findall(
        r'href="(/?[^"]*?/docs/[^"]+)"', r.text, re.IGNORECASE,
    )))
    if docs_links:
        print(f"      /docs/ links: {len(docs_links)}")
        for p in docs_links[:8]:
            print(f"        - {p}")
    return r.text


def main() -> None:
    for slug, county, urls in TARGETS:
        print(f"\n=== {county} ({slug}) ===")
        for url in urls:
            fingerprint(slug, county, url)


if __name__ == "__main__":
    main()
