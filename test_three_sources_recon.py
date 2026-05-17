"""Recon Mecktimes, Kania, Zacchaeus in a single pass.

For each:
  - Confirm HTTP reachability + status / size / final URL
  - Detect framework markers (Cloudflare, Wix, WordPress, React, Next.js)
  - Count NC target counties mentioned
  - Count address-like patterns
  - For Kania: also enumerate per-county subpage URLs
  - For Mecktimes: try with full browser headers (it 403s without)
"""

import re

import requests

OUTPUTS = "output/three_sources_recon"
import pathlib
pathlib.Path(OUTPUTS).mkdir(parents=True, exist_ok=True)

H = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
NC = r"\b(Cabarrus|Catawba|Gaston|Iredell|Lincoln|Mecklenburg|Rowan)\b"
ADDR = r"\d{2,5}\s+[A-Z][A-Za-z]+\s+(?:St|Ave|Rd|Dr|Ln|Ct|Cir|Way|Blvd|Pkwy|Pl)\b"


def fingerprint(name: str, url: str, save_html: bool = False) -> requests.Response | None:
    try:
        r = requests.get(url, headers=H, timeout=20, allow_redirects=True)
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None
    markers = []
    txt = r.text
    if "cloudflare" in txt.lower(): markers.append("cloudflare")
    if "turnstile" in txt.lower(): markers.append("turnstile")
    if "recaptcha" in txt.lower(): markers.append("recaptcha")
    if "<table" in txt.lower(): markers.append(f"tables={txt.lower().count('<table')}")
    if "__NEXT_DATA__" in txt: markers.append("nextjs")
    if "wix" in txt.lower(): markers.append("wix")
    if "wp-content" in txt or "wordpress" in txt.lower(): markers.append("wordpress")
    if "react" in txt.lower(): markers.append("react")
    counties = sorted(set(re.findall(NC, txt)))
    addrs = re.findall(ADDR, txt)
    print(f"  [{r.status_code}] {len(txt):>7}b  final={r.url}")
    print(f"        markers: {markers}")
    print(f"        counties: {counties}   addrs: {len(addrs)}  sample: {addrs[:3]}")
    if save_html:
        path = pathlib.Path(OUTPUTS) / f"{name}.html"
        path.write_text(txt, encoding="utf-8")
        print(f"        saved: {path}")
    return r


def main() -> None:
    print("\n=== MECKTIMES (Mecklenburg legals — needs browser headers) ===")
    for url in [
        "https://publicnotices.mecktimes.com/",
        "https://mecktimes.com/public-notice/",
        "https://publicnotices.mecktimes.com/search",
    ]:
        fingerprint("mecktimes_" + url.rsplit("/", 1)[-1] or "root", url, save_html=True)

    print("\n=== KANIA (tax foreclosure aggregator) ===")
    r = fingerprint("kania_root", "https://kanialawfirm.com/tax-foreclosures/foreclosure-listings/", save_html=True)
    if r:
        # Enumerate per-county listing pages
        urls = sorted(set(re.findall(r'href="([^"]*tax-foreclosures[^"]*)"', r.text)))
        county_pages = [u for u in urls if re.search(NC, u, re.IGNORECASE)]
        print(f"        per-county listing URLs ({len(county_pages)}):")
        for u in county_pages:
            print(f"          - {u}")
        # Inspect one county page (Mecklenburg) to find table structure
        if county_pages:
            meck = next((u for u in county_pages if "mecklenburg" in u.lower()), None)
            if meck:
                if meck.startswith("/"):
                    meck = "https://kanialawfirm.com" + meck
                print(f"\n        Drilling into Mecklenburg listing: {meck}")
                rr = fingerprint("kania_mecklenburg", meck, save_html=True)
                if rr:
                    # Find table headers
                    headers = re.findall(r"<th[^>]*>([^<]+)</th>", rr.text, re.IGNORECASE)
                    print(f"        Table headers: {headers[:20]}")

    print("\n=== ZACCHAEUS (Wix-hosted listings) ===")
    fingerprint("zacchaeus_listings", "https://www.zls-nc.com/listings", save_html=True)
    # Try per-county subpages
    for slug in ["cabarrus-county", "catawba-county", "iredell-county"]:
        fingerprint(f"zacchaeus_{slug}", f"https://www.zls-nc.com/{slug}", save_html=True)


if __name__ == "__main__":
    main()
