"""READ-ONLY: deed/parcel detail for the 4 DataFlik heirs records."""
import json
import sys

import requests

sys.path.insert(0, r"d:\SiftStack")
from get_ds_token import get_token  # noqa: E402

SP = r"C:\Users\omark\AppData\Local\Temp\claude\d--SiftStack\af1ee3b6-0466-4829-81e9-9f81b3c9c339\scratchpad"
tok = get_token()
h = {"authorization": f"Bearer {tok}", "accept": "application/json",
     "origin": "https://app.reisift.io", "referer": "https://app.reisift.io/",
     "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0"}
d = json.load(open(SP + r"\heirs_detail.json", encoding="utf-8"))
for nm in ("Heirs Overcash", "Heirs Archie", "Heirs Miller", "Heirs Heiligh"):
    rec = [r for r in d if r["owner_name"] == nm][0]
    full = requests.get(f"https://apiv2.reisift.io/api/internal/property/{rec['uuid']}/",
                        headers=h, timeout=30).json()
    print("=====", nm, "@", rec["street"], rec["city"])
    for k in ("parcel_id", "apn", "deed", "legal_description", "owned_since",
              "last_sold", "last_sale_price", "estimate_value", "structure_type",
              "notes", "secondary_owners", "personal_representative"):
        v = full.get(k)
        if v:
            print(" ", k, "=>", str(v)[:250])
    ow = full.get("owner") or {}
    print("  owner mailing =>", json.dumps(ow.get("address"), default=str)[:250])
