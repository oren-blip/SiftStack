from __future__ import annotations
import json
import requests

URL = ("https://gis.rowancountync.gov/arcgis/rest/services/Public/MapViewer/"
       "MapServer/9/query")
F = "PARCEL_ID,PARENT_PIN,PIN,OWNNAME,OWN2,PROP_ADDRESS,TAXADD1,CITY,STATE,ZIPCODE,DEEDACRE,CALCACRE,TOT_VAL,DEEDBOOK,DEEDPAGE,DEEDYEAR,LEG_DESC,DATESOLD,SALE_AMT"

def q(where, limit=60, fields=F):
    r = requests.get(URL, params={"where": where, "outFields": fields,
                                  "returnGeometry": "false", "f": "json",
                                  "resultRecordCount": limit}, timeout=60)
    d = r.json()
    if "error" in d:
        print("ERR", json.dumps(d["error"])[:300]); return []
    return [x["attributes"] for x in d.get("features", [])]

def show(t, rows):
    print(f"\n=== {t} ({len(rows)}) ===")
    for a in rows:
        print(f"  {a.get('PARCEL_ID')!r:<16} PIN={a.get('PIN')} parent={a.get('PARENT_PIN')}")
        print(f"     {a.get('OWNNAME')} | {a.get('OWN2')}")
        print(f"     situs {a.get('PROP_ADDRESS')} | mail {a.get('TAXADD1')}, {a.get('CITY')} {a.get('STATE')} {a.get('ZIPCODE')}")
        print(f"     ac deed={a.get('DEEDACRE')} calc={a.get('CALCACRE')} val={a.get('TOT_VAL')} legal={a.get('LEG_DESC')}")
        print(f"     deed {a.get('DEEDBOOK')}/{a.get('DEEDPAGE')} yr {a.get('DEEDYEAR')}  sold={a.get('DATESOLD')} amt={a.get('SALE_AMT')}")

show("PARCEL_ID LIKE '421 083%'", q("PARCEL_ID LIKE '421 083%'"))
show("PARCEL_ID LIKE '421%' AND legal LIKE TR7", q("PARCEL_ID LIKE '421%' AND UPPER(LEG_DESC) LIKE '%TR7%'"))
show("owner REUBEN", q("UPPER(OWNNAME) LIKE '%REUBEN%' OR UPPER(OWN2) LIKE '%REUBEN%'"))
show("owner HEILIGH (all)", q("UPPER(OWNNAME) LIKE '%HEILIGH%' OR UPPER(OWN2) LIKE '%HEILIGH%'"))
show("PIN/parcel exact 421 0830003 variants",
     q("PARCEL_ID IN ('421 0830003','421 083','4210830003','421 0830002','421 0830004')"))
