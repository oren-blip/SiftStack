"""READ-ONLY: Rowan GIS owner lookup by situs address for the two DataFlik
'Heirs' records (Overcash @ 1250 Chow Dr China Grove, Archie @ 100 Cedar St
Salisbury)."""
import json

import requests

URL = "https://gis.rowancountync.gov/arcgis/rest/services/Public/MapViewer/MapServer/9/query"
FIELDS = "OWNNAME,OWN2,TAXADD1,CITY,STATE,ZIPCODE,PARCEL_ID,PROP_ADDRESS,DEEDYEAR,TOT_VAL,NEIGCLAS,DEEDACRE"

for label, where in [("Archie-surname search", "OWNNAME LIKE 'ARCHIE %'"),
                     ("Archie heirs", "OWNNAME LIKE '%ARCHIE%HEIRS%' OR OWN2 LIKE '%ARCHIE%'"),
                     ("100 Cedar situs", "PROP_ADDRESS LIKE '%100 CEDAR%'")]:
    r = requests.get(URL, params={
        "where": where,
        "outFields": FIELDS, "returnGeometry": "false", "f": "json"}, timeout=60)
    feats = (r.json() or {}).get("features") or []
    print(f"===== {label}: {len(feats)} parcel(s)")
    for f in feats:
        print(json.dumps(f.get("attributes"), indent=1))
