"""Pull ALL GIS fields for the Overcash (146 139) and Archie (024 039)
parcels — deed book/page refs, sale dates, legal descriptions."""
import json

import requests

URL = "https://gis.rowancountync.gov/arcgis/rest/services/Public/MapViewer/MapServer/9/query"
for label, pid in [("Overcash 1250 Chow Dr", "146 139"),
                   ("Archie 100 W Broad St", "024 039")]:
    r = requests.get(URL, params={"where": f"PARCEL_ID = '{pid}'",
                                  "outFields": "*", "returnGeometry": "false",
                                  "f": "json"}, timeout=60)
    feats = (r.json() or {}).get("features") or []
    print(f"===== {label} ({pid}): {len(feats)} feature(s)")
    for f in feats:
        attrs = f.get("attributes") or {}
        for k, v in attrs.items():
            if v not in (None, "", " "):
                print(f"  {k} = {v}")
