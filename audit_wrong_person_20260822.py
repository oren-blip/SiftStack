"""READ-ONLY audit: DP'd records where the CRM contact is a DIFFERENT person
than the one the court file names.

Prompted by Parker 26E001117-350 (2026-08-22). Gaston's case file put petitioner
Robin Lynn Parker at 116 Walking Horse Run, Stanley NC - the property. The CRM
had her at 17279 Phillips Hill Rd, Laurel, DE with six 302 phones and five DE
emails. Tracerfy AND the 8/20 Enformion sweep independently matched the same
wrong Robin Parker, so two "sources agreeing" proved nothing - common name, one
mistake, twice. Oren's rule: **the case file wins.**

The tell: the court file names a person AND gives their address, and the live
CRM address for that same person is in a different STATE. Out-of-state heirs are
normal and are NOT flagged on their own - the flag needs the court to disagree.

Court-file people come from the FTM pipeline CSVs:
  * "Beneficiaries"  - one per line, "Last, First - street, city, ST zip"
  * "Personal Representative" + the Mailing Address/City/State/Zip columns

Writes NOTHING. Every call is a GET.

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\audit_wrong_person_20260822.py

Output: output/wrong_person_audit_20260822.csv + console summary.
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
import os
import re
import sys
import time as _time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_dm_mailing_gap_20260822 import norm  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
SRC = REPO / "output" / "dm_mailing_gap_20260822.csv"
OUT = REPO / "output" / "wrong_person_audit_20260822.csv"
_LOG = open(REPO / "logs" / "audit_wrong_person_20260822.log", "a", encoding="utf-8")
_w = sys.stdout.write
sys.stdout.write = lambda t: (_w(t), _LOG.write(t), _LOG.flush())[0]

NC_AREA = {"252", "336", "704", "743", "828", "910", "919", "980", "984"}


def court_people() -> dict[str, list[dict]]:
    """Case No. -> [{first, last, street, state}] from the court's own party list."""
    out: dict[str, list[dict]] = {}
    for f in sorted(glob.glob(str(REPO / "output" / "nc_estates_ftm_*.csv")),
                    key=os.path.getmtime):
        try:
            fh = open(f, encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            r = csv.DictReader(fh)
            flds = r.fieldnames or []
            ck = next((c for c in flds if c.strip().lower().startswith("case no")), None)
            if not ck:
                continue
            for row in r:
                case = (row.get(ck) or "").strip()
                if not case:
                    continue
                people: list[dict] = []
                for line in (row.get("Beneficiaries") or "").splitlines():
                    # "Last, First - 6505 Quarterbridge Ln, Charlotte, NC 28262"
                    m = re.match(r"\s*([^,]+),\s*([^-]+?)\s*-\s*(.+)", line)
                    if not m:
                        continue
                    addr = m.group(3)
                    st = re.search(r"\b([A-Z]{2})\s+\d{5}", addr)
                    people.append({"first": m.group(2).strip(), "last": m.group(1).strip(),
                                   "street": addr.split(",")[0].strip(),
                                   "state": st.group(1) if st else "",
                                   "src": "Beneficiaries"})
                # NOTE: "Mailing Address" is OUR enrichment (people-search PR
                # lookup), NOT the court's party list - on Parker it held a
                # third wrong person (173 Garden Gate Ct, Middle Island NY). It
                # is collected for context and reported separately, never as
                # proof the CRM is wrong.
                pr = (row.get("Personal Representative") or "").strip()
                ms = (row.get("Mailing Address") or "").strip()
                if pr and ms and not pr.lower().startswith(("heirs", "estate")):
                    toks = pr.replace(",", " ").split()
                    if len(toks) >= 2:
                        people.append({"first": toks[0], "last": toks[-1], "street": ms,
                                       "state": (row.get("Mailing State") or "").strip().upper(),
                                       "src": "PR mailing"})
                if people:
                    out[case] = people      # latest file wins

    # Parties fetched straight from Odyssey by backfill_court_parties_20260822.py
    # for the DP'd cases whose Beneficiaries column was never filled. This is the
    # court's own answer, so it OVERRIDES anything derived from the CSVs.
    try:
        store = json.loads((REPO / "output" / "court_parties_dp_20260822.json")
                           .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {}
    for case, parties in store.items():
        people = []
        for p in parties:
            addrs = p.get("addresses") or []
            a = addrs[0] if addrs else {}
            street = (a.get("line1") or "").strip()
            if not street or not (p.get("last_name") or "").strip():
                continue
            people.append({"first": (p.get("first_name") or "").strip(),
                           "last": (p.get("last_name") or "").strip(),
                           "street": street,
                           "state": (a.get("state") or "").strip().upper(),
                           "src": "Odyssey Parties (" + (p.get("connection_type") or "?") + ")"})
        if people:
            out[case] = people
    return out


def get_prop(h: dict, uuid: str) -> dict:
    for attempt in range(3):
        try:
            r = requests.get(API + "/api/internal/property/" + uuid + "/",
                             headers=h, timeout=30)
        except requests.exceptions.RequestException:
            _time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            return {}
        d = r.json()
        return d.get("data") or d.get("result") or d
    return {}


def main() -> int:
    print("\n===== wrong-person audit at " + str(_dt.datetime.now()) + " =====")
    court = court_people()
    print("cases with court-named people + addresses: " + str(len(court)))
    targets = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig"))
               if r["UUID"].strip() and r["Case No."].strip()]
    print("DP'd records to check: " + str(len(targets)))

    tok = token()
    if not tok:
        print("login failed")
        return 1
    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": "Bearer " + tok,
         "content-type": "application/json"}

    rows = []
    for t in targets:
        case = t["Case No."]
        people = court.get(case) or []
        if not people:
            continue
        d = get_prop(h, t["UUID"])
        if not d:
            continue
        o = d.get("owner") or {}
        oa = o.get("address") or {}
        pa = d.get("address") or {}
        first = (o.get("first_name") or "").strip()
        last = (o.get("last_name") or "").strip()
        if not last or first.lower().startswith(("heirs", "estate")):
            continue

        # NEVER match the decedent. Courteau 26E001077-350 is why: the court
        # lists BOTH "Courteau, Robert Earl" (decedent, 536 Kiser Rd NC) and
        # "Courteau, Robert Clinton" (applicant/administrator, Hopewell VA).
        # First+last alone hit the decedent and cried wrong-person on a record
        # that was fine.
        living = [p for p in people
                  if "decedent" not in p["src"].lower()
                  and "deceased" not in p["src"].lower()]
        cands = [p for p in living
                 if p["last"].lower() == last.lower()
                 and p["first"].split()[0].lower() == (first.split() or [""])[0].lower()]
        if not cands:
            continue
        # prefer the party who actually signs - applicant/administrator/executor
        def rank(p: dict) -> int:
            s = p["src"].lower()
            for i, role in enumerate(("administrator", "executor", "applicant",
                                      "petitioner", "beneficiary")):
                if role in s:
                    return i
            return 9
        match = sorted(cands, key=rank)[0]

        crm_state = (oa.get("state") or "").strip().upper()
        court_state = (match["state"] or "").strip().upper()
        if not crm_state or not court_state:
            continue
        same_street = norm(oa.get("street") or "") == norm(match["street"])
        if same_street:
            continue
        # different STATE = likely a different human. Same state, different
        # street = usually a move, so it is listed but not called a wrong person.
        severity = "WRONG PERSON?" if crm_state != court_state else "moved?"

        phones = [("".join(c for c in str(p.get("number") or "") if c.isdigit()))[-10:]
                  for p in (o.get("phones") or [])]
        far = [p for p in phones if p[:3] and p[:3] not in NC_AREA]
        note = (str(len(far)) + " of " + str(len(phones)) + " phones out-of-state"
                if phones else "no phones")
        print("  " + severity.ljust(14) + case.ljust(16) + " " + (first + " " + last).ljust(24)
              + " CRM " + (oa.get("street", "") + ", " + crm_state).ljust(34)
              + " | COURT " + match["street"] + ", " + court_state
              + "  (" + note + ")")
        rows.append({"Case No.": case, "Flag": severity, "Owner": first + " " + last,
                     "Property": (pa.get("street") or "") + ", " + (pa.get("city") or ""),
                     "CRM Mailing": (oa.get("street") or "") + ", "
                                    + (oa.get("city") or "") + " " + crm_state,
                     "Court Says": match["street"] + ", " + court_state,
                     "Court Source": match["src"], "Phones": note, "UUID": t["UUID"]})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Case No.", "Flag", "Owner", "Property", "CRM Mailing",
                                           "Court Says", "Court Source", "Phones", "UUID"])
        w.writeheader()
        w.writerows(rows)
    print("\n==== SUMMARY ====")
    hard = [r for r in rows if r["Flag"] == "WRONG PERSON?" and r["Court Source"] != "PR mailing"]
    print("  checked " + str(sum(1 for t in targets if any(
        q["src"] != "PR mailing" for q in (court.get(t["Case No."]) or []))))
        + " of " + str(len(targets)) + " case-numbered DP'd records against a court address")
    print("  CRM in a DIFFERENT STATE than the court says (likely wrong person): " + str(len(hard)))
    print("  same state, different street (likely just moved): "
          + str(sum(1 for r in rows if r["Flag"] == "moved?")))
    print("wrote " + str(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
