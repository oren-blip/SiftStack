"""Recon Mecklenburg County's year-round delinquent-bill search.

URL: https://taxbill.co.mecklenburg.nc.us/publicwebaccess/BillDelinquentSearch.aspx
This is an ASP.NET WebForms page (same vendor pattern as tnpublicnotice.com).
Goal: confirm reachability, find form fields, document result structure.
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

URL = "https://taxbill.co.mecklenburg.nc.us/publicwebaccess/BillDelinquentSearch.aspx"
OUT = Path("output/mecktax_recon")
OUT.mkdir(parents=True, exist_ok=True)


def fingerprint(name: str, url: str) -> str:
    print(f"\n=== {url} ===")
    try:
        r = requests.get(url, headers=H, timeout=20, allow_redirects=True)
    except Exception as e:
        print(f"  ERR: {e}")
        return ""
    print(f"  status={r.status_code}  len={len(r.text)}  final={r.url}")
    if r.status_code != 200:
        return ""
    (OUT / f"{name}.html").write_text(r.text, encoding="utf-8")
    # Catalog the form fields
    inputs = re.findall(r'<input[^>]+name="([^"]+)"[^>]*(?:type="([^"]+)")?', r.text)
    selects = re.findall(r'<select[^>]+name="([^"]+)"', r.text)
    print(f"  inputs ({len(inputs)}):")
    for n, t in inputs[:20]:
        print(f"    name={n!r:<55} type={t!r}")
    print(f"  selects ({len(selects)}):")
    for n in selects[:10]:
        print(f"    name={n!r}")
    # Look for grid / table indicators
    tables = re.findall(r"<table[^>]+id=\"([^\"]+)\"", r.text)
    print(f"  table ids: {tables[:8]}")
    # Look for ASP.NET viewstate
    viewstate = "__VIEWSTATE" in r.text
    print(f"  has __VIEWSTATE: {viewstate}")
    return r.text


def main() -> None:
    text = fingerprint("01_search_form", URL)
    if not text:
        print("\n  Could not fetch the form page.")
        return

    # Quick textual sniff
    body = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    (OUT / "01_search_form.txt").write_text(body[:8000], encoding="utf-8")
    print(f"\n  Visible body (first 1000 chars):\n  {body[:1000]!r}")


if __name__ == "__main__":
    main()
