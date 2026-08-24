"""Russell 26E001013-350 — fix the mangled owner name and add the 2nd co-executor.

Oren approved on 2026-08-23, after push_court_mailings_20260823.py repointed this
record's mailing from 325 Gaither Rd (which is beneficiary Wanda McCormick's
address) to Gilbert's own 2713 Rawhide Dr.

Two defects were left on it:

1. The owner reads **"Gilbert Jr"** — the name parser took the court's
   "Gilbert Winfred Russell, Jr" and split it first="Gilbert" / last="Jr", so
   the surname Russell is gone and every letter and text touch on this record
   addresses a man named "Gilbert Jr". (The 'Personal Representative' custom
   field has the full correct name, which is how we know the parse, not the
   source, is at fault.)
2. It is a **two-signer estate**. The Estates Action Cover Sheet filed 7/28/26
   names co-executors Gilbert Winfred Russell Jr AND Darrell Dean Russell —
   both must sign to sell — but Darrell was nowhere on the record.

What this does:
  * owner "Gilbert Jr" -> "Gilbert Russell"
  * appends Darrell's cover-sheet phone 704-460-1962, tagged "Court Verified"
    + "co-executor Darrell Dean Russell" (no dial tier — it has never been
    Trestle-scored; the post-upload sweep tiers untiered numbers)
  * fills the blank DM / DM 2 / DM 3 custom fields from the cover sheet
    (FILL-IF-BLANK only — a live value is never clobbered, per
    project_pr_upgrade_silent_save_failure)
  * adds the account's existing "Multi-Signer (2)" tag so a caller sees at a
    glance that one signature is not enough

NOT done: Gilbert's own cover-sheet phone 704-685-0631 is still missing from the
record. Court-sourced phones are a queue Oren wants to approve himself
(project_estate_cover_sheet_phones), so it is reported, not pushed.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\fix_russell_multisigner_20260823.py            # DRY RUN
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\fix_russell_multisigner_20260823.py --apply    # live
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
APPLY = "--apply" in sys.argv
UUID = "3d861922-e90f-4b49-b311-3dfb22fff1a6"
CASE = "26E001013-350"

RENAME = ("Gilbert", "Russell")
DARRELL_PHONE = "7044601962"
PHONE_TAGS = ["Court Verified", "co-executor Darrell Dean Russell"]
ADD_TAG = "Multi-Signer (2)"
CUSTOM_IF_BLANK = {
    "decision maker": "Gilbert Winfred Russell Jr",
    "dm relationship": "co-executor (beneficiary)",
    "dm 2 name": "Darrell Dean Russell",
    "dm 2 relationship": "co-executor (beneficiary)",
    "dm 3 name": "Wanda Marie Russell McCormick",
    "dm 3 relationship": "beneficiary",
}


def digits(s) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def get_prop(h: dict, uuid: str) -> dict:
    r = requests.get(API + "/api/internal/property/" + uuid + "/", headers=h, timeout=30)
    if r.status_code != 200:
        print("  GET -> HTTP " + str(r.status_code))
        return {}
    d = r.json()
    return d.get("data") or d.get("result") or d


def cf_definitions(h: dict) -> dict[str, str]:
    r = requests.get(API + "/api/internal/custom-fields/?entity_type=property"
                     "&offset=0&limit=1000", headers=h, timeout=30)
    if r.status_code != 200:
        return {}
    return {(f.get("label") or "").strip().lower(): f["uuid"]
            for f in (r.json().get("results") or []) if f.get("uuid")}


def cf_values(h: dict, uuid: str) -> dict[str, dict]:
    r = requests.get(API + "/api/internal/property/" + uuid
                     + "/custom-field/?offset=0&limit=1000", headers=h, timeout=30)
    if r.status_code != 200:
        return {}
    out = {}
    for e in (r.json().get("results") or []):
        lab = ((e.get("custom_field") or {}).get("label") or "").strip().lower()
        if lab:
            out[lab] = e
    return out


def main() -> int:
    print("===== Russell " + CASE + " fix "
          + ("LIVE" if APPLY else "DRY RUN") + " =====")
    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    d = get_prop(h, UUID)
    if not d:
        return 1
    owner = d.get("owner") or {}
    pa = d.get("address") or {}
    first = (owner.get("first_name") or "").strip()
    last = (owner.get("last_name") or "").strip()
    print("  property   : " + str(pa.get("street")) + ", " + str(pa.get("city")))
    print("  live owner : " + repr(first + " " + last))

    # identity guard — right property, and the owner still reads the mangled name
    if not (pa.get("street") or "").lower().startswith("1700 gaither"):
        print("  property is not 1700 Gaither Rd — ABORT")
        return 1
    if first.lower() != "gilbert" or last.lower() not in ("jr", "russell"):
        print("  owner is not the expected 'Gilbert Jr'/'Gilbert Russell' — ABORT")
        return 1

    new_owner = copy.deepcopy(owner)
    if (first, last) != RENAME:
        print("  rename " + repr(first + " " + last) + " -> " + repr(" ".join(RENAME)))
        new_owner["first_name"], new_owner["last_name"] = RENAME
    else:
        print("  name already correct — no rename")

    have = {digits(p.get("number"))[-10:] for p in (new_owner.get("phones") or [])}
    if DARRELL_PHONE in have:
        print("  Darrell's phone already on the record — no append")
    else:
        print("  + phone " + DARRELL_PHONE + " tags " + str(PHONE_TAGS))
        new_owner.setdefault("phones", []).append(
            {"number": DARRELL_PHONE, "type": "UNKNOWN", "tags": PHONE_TAGS})

    defs = cf_definitions(h)
    rows = cf_values(h, UUID)
    items = []
    for lab, val in CUSTOM_IF_BLANK.items():
        cur = (rows.get(lab, {}).get("value") or "").strip()
        if cur:
            print("  custom " + repr(lab) + " already " + repr(cur) + " — left as-is")
            continue
        fu = defs.get(lab) or ((rows.get(lab) or {}).get("custom_field") or {}).get("uuid")
        if not fu:
            print("  !! no field definition for " + repr(lab) + " — unwritten")
            continue
        print("  custom " + repr(lab) + " (blank) -> " + repr(val))
        items.append({"field_uuid": fu, "value": val})

    live_tags = [t.get("title") if isinstance(t, dict) else str(t)
                 for t in (d.get("tags") or [])]
    need_tag = ADD_TAG not in live_tags
    print("  tag " + repr(ADD_TAG) + (" -> will add" if need_tag else " already present"))

    if not APPLY:
        print("\nDRY RUN — nothing written.")
        return 0

    r = requests.patch(API + "/api/internal/property/" + UUID + "/", headers=h,
                       data=json.dumps({"owner": new_owner}), timeout=30)
    print("  PATCH owner -> " + str(r.status_code) + " " + r.text[:90])
    if r.status_code not in (200, 202):
        return 1
    if items:
        r = requests.patch(API + "/api/internal/property/" + UUID
                           + "/custom-field/update-values/", headers=h,
                           data=json.dumps(items), timeout=30)
        print("  PATCH custom-fields (" + str(len(items)) + ") -> "
              + str(r.status_code) + " " + r.text[:90])
    if need_tag:
        r = requests.post(API + "/api/internal/property/" + UUID + "/add-tags/",
                          headers=h, json={"tags": [ADD_TAG]}, timeout=30)
        print("  add-tags -> " + str(r.status_code))

    v = get_prop(h, UUID)
    vo = v.get("owner") or {}
    vname = ((vo.get("first_name") or "") + " " + (vo.get("last_name") or "")).strip()
    vph = {digits(p.get("number"))[-10:] for p in (vo.get("phones") or [])}
    vtags = [t.get("title") if isinstance(t, dict) else str(t)
             for t in (v.get("tags") or [])]
    vcf = cf_values(h, UUID)
    missing_cf = [lab for lab in CUSTOM_IF_BLANK
                  if not (vcf.get(lab, {}).get("value") or "").strip()]
    print("  VERIFY: owner=" + repr(vname)
          + "  darrell_phone=" + str(DARRELL_PHONE in vph)
          + "  multi_signer_tag=" + str(ADD_TAG in vtags)
          + "  blank DM fields left=" + str(missing_cf or "none"))
    ok = (vname == " ".join(RENAME) and DARRELL_PHONE in vph and ADD_TAG in vtags)
    print("\n" + ("DONE" if ok else "SOMETHING DID NOT STICK"))
    print("NOTE: Gilbert's own cover-sheet phone 704-685-0631 is still not on "
          "this record — court-phone pushes await Oren's go-ahead.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
