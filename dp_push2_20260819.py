"""DP push #2, 2026-08-19 PM — Oren runs this himself (classifier blocks
Claude's DataSift writes):

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push2_20260819.py            # real
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\dp_push2_20260819.py --dry-run  # preview

Pushes the afternoon batch (Scearce / Keener / Courteau — the three
"Verify: No PR Address" records). Findings in output/reports/DP_Week33_*,
ledger rows in dp_log.csv. Reuses the verified engine from
dp_push_20260819.py (owner round-trip PATCH, add/remove-tags endpoints,
re-GET verify); output tees into logs/dp_push_20260819.log.

- Scearce 26E000825-790: widow CO-TRUSTEE Cheryl P Scearce at the property
  (trust may sell without probate). ** occupied-spouse — flagged for hold **
- Keener 26E000942-170: son Jeffrey S Lawson NEXT DOOR (7030 Martin Mill);
  the record's old Dial First was the decedent's dead mobile -> retagged Drop.
- Courteau 26E001077-350: sons Robert Clinton (VA, DM) + Everette (GA, DM2).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"d:\SiftStack")))
from dp_push_20260819 import API, DRY, do_tags, push_one, tag_titles, token  # noqa: E402
import requests  # noqa: E402

PUSHES2 = [
    {"label": "Scearce 26E000825-790 @ 220 Neel Rd",
     "uuid": "8840b9e3-6b43-4cf5-b1f9-18b9f8bad1e0",
     "owner_frag": "scearce",
     "rename": ("Cheryl P", "Scearce"),
     "mail": None,  # she lives at the property; mailing already correct
     "phones": [("7047986425", ["Dial First", "Widow co-trustee Cheryl Scearce"])],
     "rm": ["Verify: No PR Address"],
     # real hold approved 8/19 PM — hold_occupied_20260819.py applies
     # "Hold - Occupied"; no interim review tag needed here
     "add": ["DP Complete"]},
    {"label": "Keener 26E000942-170 @ 7050 Martin Mill Rd",
     "uuid": "62fbc070-1349-4be0-a695-e8f34f8eba1e",
     "owner_frag": "keener",
     "rename": ("Jeffrey", "Lawson"),
     "mail": {"street": "7030 Martin Mill Rd", "city": "Hickory",
              "state": "NC", "postal_code": "28602"},
     "phones": [("8282440250", ["Dial First", "Son Jeffrey S Lawson"]),
                ("8283227030", ["Dial First", "Jeffrey home line"])],
     "tag_existing_phone": ("8283021731", ["Drop", "decedent's disconnected mobile"]),
     "rm": ["Verify: No PR Address"], "add": ["DP Complete"]},
    {"label": "Courteau 26E001077-350 @ 536 Kiser Rd",
     "uuid": "a46fda3a-2884-4b61-a909-351d4d7b2db2",
     "owner_frag": "courteau",
     "rename": ("Robert Clinton", "Courteau"),
     "mail": {"street": "2207 Circlestone Ct", "city": "South Chesterfield",
              "state": "VA", "postal_code": "23834"},
     "phones": [("8046472756", ["Dial First", "Son Robert Clinton Courteau"]),
                ("3365492756", ["Dial Third", "Son Everette Courteau (GA)"]),
                ("8046517860", ["Dial Third", "Robert Clinton alt"]),
                ("7709749132", ["Dial Fourth", "Everette home"])],
     "rm": ["Verify: No PR Address"], "add": ["DP Complete"]},
]


def main() -> int:
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/",
         "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
         "authorization": f"Bearer {tok}", "content-type": "application/json"}
    print(f"\n--- push #2 (Scearce/Keener/Courteau) dry_run={DRY} ---")
    done = sum(1 for spec in PUSHES2 if push_one(h, spec))
    print(f"\n{done}/{len(PUSHES2)} records pushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
