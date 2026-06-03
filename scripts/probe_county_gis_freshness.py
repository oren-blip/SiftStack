"""Probe each NC county GIS endpoint we query for evidence of stale data.

Cabarrus's Tax_Parcels_Full was ~4 years stale on ownership (caught in
audit: bailey 26E000574-120's 2626 BARR RD still showed previous owner
WHITE NELLIE S from before the 2021 sale). This script checks each
county's main endpoint for:
  - Service catalog (other layers we might be missing)
  - Last-update / modification metadata if exposed
  - Sample query for a known recent transaction (if possible)

Doesn't modify anything; just prints findings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from nc_gis_lookup import _ARCGIS_CONFIG


def probe_endpoint(county: str, url: str) -> dict:
    """Return discovery info for one county GIS layer."""
    out = {"county": county, "url": url, "warnings": []}

    # Layer metadata
    try:
        r = requests.get(url, params={"f": "json"}, timeout=15)
        meta = r.json() if r.status_code == 200 else {}
    except Exception as e:
        out["warnings"].append(f"layer-meta-fetch-failed: {e}")
        return out

    out["layer_name"] = meta.get("name", "?")
    out["editing_info"] = meta.get("editingInfo", {})
    out["max_record_count"] = meta.get("maxRecordCount")
    out["geometry_type"] = meta.get("geometryType", "")

    # Service catalog (look for sibling layers that might be fresher)
    base = url.rsplit("/MapServer", 1)[0].rsplit("/FeatureServer", 1)[0]
    services_root = base.rsplit("/", 1)[0]
    try:
        r2 = requests.get(services_root, params={"f": "json"}, timeout=15)
        catalog = r2.json() if r2.status_code == 200 else {}
        siblings = []
        for s in (catalog.get("services") or []):
            sn = s.get("name", "")
            # Look for parcel-related siblings
            if any(k in sn.lower() for k in ("parcel", "tax", "property", "reval", "ownership")):
                siblings.append({"name": sn, "type": s.get("type")})
        out["sibling_parcel_services"] = siblings
    except Exception as e:
        out["warnings"].append(f"catalog-fetch-failed: {e}")

    # Quick count query
    try:
        r3 = requests.get(url + "/query", params={
            "where": "1=1", "returnCountOnly": "true", "f": "json"
        }, timeout=15)
        count = r3.json().get("count", "?")
        out["total_parcel_count"] = count
    except Exception as e:
        out["warnings"].append(f"count-failed: {e}")

    return out


def main() -> int:
    findings = []
    for county_key, cfg in _ARCGIS_CONFIG.items():
        if county_key == "mecklenburg":
            # Different endpoint shape (polaris3g JSON API, not ArcGIS REST)
            continue
        f = probe_endpoint(county_key.title(), cfg["url"])
        findings.append(f)

    print("=" * 80)
    print("NC COUNTY GIS FRESHNESS PROBE")
    print("=" * 80)
    for f in findings:
        print(f"\n--- {f['county']} ---")
        print(f"  URL:              {f['url']}")
        print(f"  Layer name:       {f.get('layer_name')!r}")
        print(f"  Total parcels:    {f.get('total_parcel_count')}")
        edit = f.get("editing_info") or {}
        if edit.get("lastEditDate"):
            from datetime import datetime, timezone
            ts = edit["lastEditDate"] / 1000.0
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                print(f"  Last edit date:   {dt.isoformat()}")
            except Exception:
                print(f"  Last edit date:   raw={edit['lastEditDate']}")
        else:
            print(f"  Last edit date:   (not exposed)")
        sibs = f.get("sibling_parcel_services") or []
        if sibs:
            print(f"  Sibling services found ({len(sibs)}):")
            for s in sibs:
                marker = " <-- current" if s["name"].endswith(f['layer_name']) or f.get('layer_name', '') in s["name"] else ""
                print(f"    {s['name']:50} {s['type']}{marker}")
        if f.get("warnings"):
            print(f"  Warnings: {f['warnings']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
