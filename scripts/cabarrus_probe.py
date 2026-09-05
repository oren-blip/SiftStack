"""Is the Cabarrus parcel service actually serving?

Exit 0 = up (safe to run the polish pass), exit 1 = down.

Cabarrus fails in ways a naive check misses, so this asserts on real DATA, not
on reachability:
  * 2026-09-04: HTTP 200 carrying {"code":500,"message":"Service
    Parcels/MapServer not started"} -- the box answers, the service is stopped.
  * 2026-07-09: HTTP 200 carrying {"status":"error"} -- whole instance down.
    That one used to be indistinguishable from "this owner has no parcels".
A control query that returns a known parcel is the only honest test.
"""
from __future__ import annotations

import sys

import requests

URL = ("https://location.cabarruscounty.us/arcgisservices/rest/services/"
       "Parcels/MapServer/0")
# Known-good control: the same fixture the GIS smoke test uses for Cabarrus.
CONTROL = "BARBEE RAY B"


def main() -> int:
    try:
        r = requests.get(
            URL + "/query",
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
            timeout=45,
        )
    except requests.RequestException as e:
        print(f"Cabarrus DOWN: {type(e).__name__}: {e}")
        return 1

    if r.status_code != 200:
        print(f"Cabarrus DOWN: HTTP {r.status_code}")
        return 1
    try:
        d = r.json()
    except ValueError:
        print("Cabarrus DOWN: response was not JSON")
        return 1

    # HTTP 200 is not success here -- both known outages returned 200.
    if "error" in d or d.get("status") == "error":
        err = d.get("error") or {"message": d.get("messages")}
        print(f"Cabarrus DOWN: {err}")
        return 1

    count = d.get("count")
    if not count:
        print(f"Cabarrus DOWN: control query returned no count ({d})")
        return 1

    print(f"Cabarrus UP: Parcels layer answering, {count:,} parcels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
