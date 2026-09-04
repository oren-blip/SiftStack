"""The 5 Charlotte buyers held back from the 2026-09-04 upload because their
mailing address collides with an existing DataSift record.

Two of them turned out to be entities that ALREADY have a record under a
different contact person, so they are ENRICHED in place (no duplicate):
  Northway Homes  -> existing owner Lee Lewis   ; add Katrina Parks + email
  J2 Land Invest. -> existing owner John Sears  ; add John Lambert (COO)

The other three have no record and are written to a CSV for the upload wizard.
Every write is verified by re-reading the record.

    python add_held_buyers_20260904.py            # dry run
    python add_held_buyers_20260904.py --apply
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dstok import token

API = "https://apiv2.reisift.io"
TAGS = ["Charlotte Metro Buyer", "cash buyers"]
FB_TAG = "Charlotte REI FB Group"

# uuid -> what to add. Verified by hand from the live records on 2026-09-04.
ENRICH = {
    "c58b98a8-104f-48e1-b162-08bb42de0205": {
        "label": "NORTHWAY HOMES LLC (existing owner Lee Lewis)",
        "add_desc": (" | Buyer Prospector 9/2026: 84 purchases in the last 6 months across "
                     "Gaston, Iredell, Mecklenburg, Rowan. Second contact: Katrina Parks, "
                     "katrina@northwayhomes.com (company email domain). Posts deals in the "
                     "Charlotte REI Facebook group."),
        "tags": TAGS + [FB_TAG],
    },
    "67420fbb-90ca-4f7b-9c5c-9df7f01c3a08": {
        "label": "J2 LAND INVESTMENTS LLC (existing owner John Sears)",
        "add_desc": (" | Buyer Prospector 9/2026: 106 purchases in the last 6 months across "
                     "Cabarrus, Catawba, Gaston, Mecklenburg, Union. Second contact: John "
                     "Lambert, Chief Operating Officer (named on a York County SC deed "
                     "acknowledgment), 704-453-2700 x151. Buy-and-hold."),
        "tags": TAGS,
    },
}

# no record anywhere -> upload wizard
NEW = [
    {"Property Street Address": "2308 Kannapolis Hwy", "Property City": "Concord",
     "Property State": "NC", "Property ZIP Code": "28027",
     "Owner First Name": "Joshua B", "Owner Last Name": "Swart", "Tags": "cash buyers",
     "Notes": ("CASH BUYER (Buyer Prospector 9/2026): 125 purchases in the last 6 months in "
               "Cabarrus, Gaston, Iredell, Rowan, Union. Flipper, 167 tracked acquisitions, "
               "avg $105,353, latest Aug 2026. Entity: STRAIGHT PATH REAL ESTATE SOLUTIONS LLC. "
               "Contact: Joshua B Swart (Registered Agent / President). Posts as a buyer in the "
               "Charlotte REI Facebook group. NOTE: this office address is shared with Spres "
               "Fund 3 LLC (Gary Quigg), a separate DataSift record.")},
    {"Property Street Address": "1800 Camden Rd Ste 107", "Property City": "Charlotte",
     "Property State": "NC", "Property ZIP Code": "28203",
     "Owner First Name": "Todd", "Owner Last Name": "Brockmann", "Tags": "cash buyers",
     "Notes": ("CASH BUYER (Buyer Prospector 9/2026): 16 purchases in the last 6 months in "
               "Catawba, Mecklenburg. Flipper, 27 tracked acquisitions, latest May 2026. "
               "Entity: WICKENDEN PARTNERS LLC. Contact: Todd Brockmann (Registered Agent). "
               "NOTE: shared office with Northway Homes (Ste 107-240) - separate records.")},
    {"Property Street Address": "2339 Odell School Rd Ste A", "Property City": "Concord",
     "Property State": "NC", "Property ZIP Code": "28027",
     "Owner First Name": "Jon", "Owner Last Name": "Devine", "Tags": "cash buyers",
     "Notes": ("CASH BUYER (Buyer Prospector 9/2026): 10 purchases in the last 6 months in "
               "Cabarrus. Buy-and-hold, 32 tracked acquisitions, latest Jul 2026. Entity: "
               "JOURNEY INVESTMENT GROUP LLC. Contact: Jon Devine (Registered Agent). "
               "NOTE: this address is shared with J2 Land Investments (John Sears).")},
]

# owners that must NOT change - checked before and after the wizard run
GUARD = {
    "993859c3-1601-403f-a5a0-a9f3f4bad433": ("Gary", "Quigg"),      # 2308 Kannapolis Hwy
    "67420fbb-90ca-4f7b-9c5c-9df7f01c3a08": ("John", "Sears"),      # 2339 Odell Ste A
    "c58b98a8-104f-48e1-b162-08bb42de0205": ("Lee", "Lewis"),       # 1800 Camden Ste 107-240
    "5787d69c-0f31-4003-b9ac-a201913a89c6": ("Matthew", "Gallo"),   # 1800 Camden Rd
}


def get(h, uuid):
    d = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30).json()
    return d.get("data") or d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    h = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    print("=== guard snapshot (owners that must survive) ===")
    for u, (f, l) in GUARD.items():
        d = get(h, u); o = d.get("owner") or {}
        got = (o.get("first_name"), o.get("last_name"))
        print(f"  {got[0]} {got[1]:<12} {(d.get('address') or {}).get('street')}"
              f"   {'OK' if got == (f, l) else '!! CHANGED, expected ' + f + ' ' + l}")

    print("\n=== enrich existing records ===")
    for u, spec in ENRICH.items():
        d = get(h, u)
        have = [t if isinstance(t, str) else t.get("title") for t in (d.get("tags") or [])]
        need = [t for t in spec["tags"] if t not in have]
        desc = str(d.get("description") or "")
        add_desc = spec["add_desc"] if "Buyer Prospector 9/2026" not in desc else ""
        print(f"  {spec['label']}")
        print(f"    tags to add: {need or 'none'}")
        print(f"    description: {'append' if add_desc else 'already noted'}")
        if not a.apply:
            continue
        if need:
            requests.post(f"{API}/api/internal/property/{u}/add-tags/", headers=h,
                          json={"tags": need}, timeout=30)
        if add_desc:
            requests.patch(f"{API}/api/internal/property/{u}/", headers=h,
                           json={"description": (desc + add_desc)[:4000]}, timeout=30)
        chk = get(h, u)
        ct = [t if isinstance(t, str) else t.get("title") for t in (chk.get("tags") or [])]
        ok_t = all(t in ct for t in spec["tags"])
        ok_d = "Buyer Prospector 9/2026" in str(chk.get("description") or "")
        o = chk.get("owner") or {}
        print(f"    verify: tags={ok_t} description={ok_d} owner still "
              f"{o.get('first_name')} {o.get('last_name')}")

    out = Path("output/charlotte_buyers_HELD_2026-09-04.csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(NEW[0].keys())); w.writeheader(); w.writerows(NEW)
    print(f"\n=== {len(NEW)} new records -> {out} ===")
    for r in NEW:
        print(f"  {r['Owner First Name']} {r['Owner Last Name']:<12} {r['Property Street Address']}")
    if not a.apply:
        print("\n(dry run - re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
