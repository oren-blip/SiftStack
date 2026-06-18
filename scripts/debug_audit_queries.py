"""Verify lookup_by_address + address_fallback_from_beneficiaries on Young Carl Sr."""
import sys
sys.path.insert(0, "src")
sys.path.insert(0, ".")
from nc_gis_lookup import lookup_by_address
from fix_addresses_and_prep import address_fallback_from_beneficiaries

# Test 1: Direct address lookup
print("=== lookup_by_address('2511 MARY AVE', 'Gaston') ===")
hits = lookup_by_address("2511 MARY AVE", "Gaston")
print(f"Hits: {len(hits)}")
for h in hits[:3]:
    print(f"  CURR_NAME1={h.get('CURR_NAME1')!r}  PIN={h.get('PIN')!r}  PHYSSTRADD={h.get('PHYSSTRADD')!r}")

# Test 2: Polish step on a synthetic Young Carl row with the actual beneficiaries
synthetic = {
    "Case No.": "26E000789-350",
    "County": "Gaston",
    "Deceased Owner": "Young, Carl Sr.",
    "First Name": "Kristal",
    "Last Name": "Young",
    "Mailing Address": "513 Tallwood CT",
    "Parcel ID": "",  # BLANK — triggers the fallback
    "Property Address": "",
    "Beneficiaries": (
        "Davis, Tadarian 2511 Mary Avenue Gastonia, NC 28052 "
        "Davis, Taloria 2511 Mary Ave Gastonia NC 28052 "
        "Leland, Ramya 505 Waterview Dr NW Concord, NC 28025 "
        "Young, Carl Jr. 707 Seigle Ave Apt 321 Charlotte, NC 28208 "
        "Young, Qunita 2106 Lyon St Gastonia, NC 28052"
    ),
    "Notes": "",
}
print()
print("=== address_fallback_from_beneficiaries on synthetic Young Carl row ===")
n = address_fallback_from_beneficiaries([synthetic])
print(f"Recovered: {n}")
print(f"After step:")
print(f"  Parcel ID:        {synthetic['Parcel ID']!r}")
print(f"  Property Address: {synthetic['Property Address']!r}")
print(f"  Property use:     {synthetic.get('Property use', '')!r}")
print(f"  Notes:            {synthetic['Notes']!r}")
