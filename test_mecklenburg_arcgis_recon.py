"""Recon Mecklenburg County's tax foreclosure ArcGIS Experience app.

Goal: find the underlying FeatureServer URL the Experience renders from, so we
can hit JSON directly without Playwright. If found, query a few records and
report the field schema.

URL: https://experience.arcgis.com/experience/640b8534655c4397b75f1d5a9cbad201/

Strategy:
  1. Hit the experience page, find the experience config JSON (usually at
     /experience/<id>/manifest.json or embedded in the HTML).
  2. Find the data-source URLs (FeatureServer / MapServer endpoints).
  3. Query each REST endpoint with `?where=1=1&outFields=*&resultRecordCount=3&f=json`
     to dump the schema + sample rows.

Run:
    .venv\\Scripts\\python.exe test_mecklenburg_arcgis_recon.py
"""

import json
import re
import sys
from pathlib import Path

import requests

OUTPUT_DIR = Path("output/mecklenburg_recon")
EXPERIENCE_URL = "https://experience.arcgis.com/experience/640b8534655c4397b75f1d5a9cbad201/"
EXPERIENCE_ID = "640b8534655c4397b75f1d5a9cbad201"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9",
}


def fetch(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        print(f"  GET {url}  ->  {r.status_code}  ({len(r.content)} bytes)")
        return r
    except Exception as e:
        print(f"  GET {url}  ->  ERR {e}")
        return None


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Pull the experience landing HTML — its <script> tags often contain
    #    the experience config or at least references to it.
    print("\n[1] Loading experience landing page...")
    r = fetch(EXPERIENCE_URL)
    if not r or r.status_code != 200:
        print("FATAL: could not load experience page")
        return
    (OUTPUT_DIR / "01_experience.html").write_text(r.text, encoding="utf-8")

    # 2. Look for any FeatureServer / MapServer URLs in the HTML.
    print("\n[2] Searching HTML for FeatureServer/MapServer URLs...")
    server_urls = sorted(set(re.findall(
        r"https?://[A-Za-z0-9./\-_]+(?:FeatureServer|MapServer)(?:/\d+)?",
        r.text,
    )))
    print(f"  found {len(server_urls)} candidate(s):")
    for u in server_urls[:20]:
        print(f"    - {u}")

    # 3. Try common ArcGIS experience config endpoints.
    print("\n[3] Trying experience config endpoints...")
    config_data = None
    for candidate in [
        f"https://experience.arcgis.com/experience/{EXPERIENCE_ID}/config/config.json",
        f"https://experience.arcgis.com/experience/{EXPERIENCE_ID}/manifest.json",
    ]:
        r = fetch(candidate)
        if r and r.status_code == 200:
            try:
                config_data = r.json()
                (OUTPUT_DIR / f"02_{candidate.rsplit('/', 1)[-1]}").write_text(
                    json.dumps(config_data, indent=2), encoding="utf-8",
                )
                print(f"    ✓ parsed JSON from {candidate}")
                break
            except Exception:
                pass

    # 4. If experience config found, walk its data sources.
    extra_urls = set()
    if config_data:
        # Find every "url" string in the config JSON
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "url" and isinstance(v, str) and ("FeatureServer" in v or "MapServer" in v):
                        extra_urls.add(v)
                    walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    walk(x)
        walk(config_data)
        if extra_urls:
            print(f"\n[4] Found {len(extra_urls)} FeatureServer/MapServer URL(s) in config:")
            for u in sorted(extra_urls):
                print(f"    - {u}")

    candidate_urls = sorted(set(server_urls) | extra_urls)
    if not candidate_urls:
        print("\n  ! No FeatureServer URLs discovered. Manual inspection of the HTML may be needed.")
        return

    # 5. Probe each candidate FeatureServer — list its layers, fetch the
    #    first layer's schema + 3 sample rows.
    print(f"\n[5] Probing {len(candidate_urls)} FeatureServer/MapServer(s)...")
    for url in candidate_urls[:5]:
        print(f"\n  --- {url} ---")
        # Normalize: trim trailing /N to get the FeatureServer root
        root = re.sub(r"/\d+$", "", url)
        meta = fetch(f"{root}?f=json")
        if not meta or meta.status_code != 200:
            continue
        try:
            meta_json = meta.json()
        except Exception:
            continue

        slug = re.sub(r"[^\w]", "_", root)[-60:]
        (OUTPUT_DIR / f"03_meta_{slug}.json").write_text(
            json.dumps(meta_json, indent=2), encoding="utf-8",
        )
        layers = meta_json.get("layers", []) + meta_json.get("tables", [])
        print(f"    name: {meta_json.get('name') or meta_json.get('serviceDescription', '')[:80]}")
        print(f"    layers: {len(layers)}")
        for lyr in layers[:5]:
            print(f"      [{lyr.get('id')}] {lyr.get('name')!r}  ({lyr.get('geometryType', 'table')})")

        # Query layer 0 for schema + sample rows
        if layers:
            lyr_id = layers[0]["id"]
            q_url = f"{root}/{lyr_id}/query"
            q_params = {
                "where": "1=1", "outFields": "*", "resultRecordCount": "3",
                "returnGeometry": "false", "f": "json",
            }
            try:
                q = requests.get(q_url, params=q_params, headers=HEADERS, timeout=20)
                print(f"    sample query -> {q.status_code} ({len(q.content)} bytes)")
                if q.status_code == 200:
                    qj = q.json()
                    (OUTPUT_DIR / f"04_sample_{slug}_lyr{lyr_id}.json").write_text(
                        json.dumps(qj, indent=2), encoding="utf-8",
                    )
                    fields = qj.get("fields") or []
                    features = qj.get("features") or []
                    print(f"      fields: {len(fields)} — {[f['name'] for f in fields[:12]]}")
                    print(f"      sample rows: {len(features)}")
                    for feat in features[:2]:
                        attrs = feat.get("attributes", {})
                        # Show first ~6 non-null attributes
                        shown = [(k, v) for k, v in attrs.items() if v not in (None, "")][:6]
                        print(f"        {shown}")
            except Exception as e:
                print(f"    sample query ERR: {e}")

    print(f"\n=== Recon complete. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
