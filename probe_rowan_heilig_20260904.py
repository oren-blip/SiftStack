"""READ-ONLY: Rowan GIS probe for the Adolphus Rd / Heiligh parcel."""
from __future__ import annotations
import json, sys
from pathlib import Path
import requests

URL = ("https://gis.rowancountync.gov/arcgis/rest/services/Public/MapViewer/"
       "MapServer/9/query")
FIELDS = "PARCEL_ID,OWNNAME,OWN2,PROP_ADDRESS,TAXADD1,CITY,STATE,ZIPCODE,DEEDACRE,CALCACRE,TOT_VAL,NEIGCLAS,DEEDYEAR,LEG_DESC,DEEDBOOK,DEEDPAGE"

def q(where, fields=FIELDS, limit=25):
    p = {"where": where, "outFields": fields, "returnGeometry": "false",
         "f": "json", "resultRecordCount": limit}
    r = requests.get(URL, params=p, timeout=60)
    try:
        d = r.json()
    except Exception:
        print("HTTP", r.status_code, r.text[:300]); return []
    if "error" in d:
        print("ERR", json.dumps(d["error"])[:400]); return []
    return [f["attributes"] for f in d.get("features", [])]

def show(title, rows):
    print(f"\n=== {title}  ({len(rows)}) ===")
    for a in rows:
        print(f"  PARCEL_ID={a.get('PARCEL_ID')!r}")
        print(f"    owner  : {a.get('OWNNAME')} | {a.get('OWN2')}")
        print(f"    situs  : {a.get('PROP_ADDRESS')}")
        print(f"    mailing: {a.get('TAXADD1')}, {a.get('CITY')} {a.get('STATE')} {a.get('ZIPCODE')}")
        print(f"    acres  : deed={a.get('DEEDACRE')} calc={a.get('CALCACRE')}  val={a.get('TOT_VAL')}  neig={a.get('NEIGCLAS')}")
        print(f"    legal  : {a.get('LEG_DESC')}  deed {a.get('DEEDBOOK')}/{a.get('DEEDPAGE')} yr {a.get('DEEDYEAR')}")

show("exact parcel '421 0830003'", q("PARCEL_ID = '421 0830003'"))
show("parcel LIKE '421%083%'", q("PARCEL_ID LIKE '421%083%'"))
show("owner LIKE HEILIG", q("UPPER(OWNNAME) LIKE '%HEILIG%' OR UPPER(OWN2) LIKE '%HEILIG%'", limit=50))
show("situs LIKE ADOLPHUS", q("UPPER(PROP_ADDRESS) LIKE '%ADOLPHUS%'", limit=50))
