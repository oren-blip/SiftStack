"""Review the estates whose property was DEEDED TO A HEIR, not sold.

Writes NOTHING to DataSift. Every call is a GET or a search.

Why these matter: sold_audit classifies a transfer as HEIR TRANSFER when the new
deed holder shares a surname with the decedent or the PR. Those rows are excluded
from Sold suppression and correctly keep marketing — but nothing has ever looked
at WHO the deed names. That name is the strongest signer evidence the pipeline
can get, stronger than the court PR and far stronger than an Enformion relative
guess (see [[project_court_pr_beats_dp_guess]]): the court appoints a
representative, but the register of deeds records who actually holds title today.
Whoever is on that deed is who signs.

Three things the deed string gives us that the CRM does not:

  1. A NAME for a record still reading "Heirs of <Decedent>".
  2. A CORRECTION when the deed names someone other than the CRM's owner.
  3. A MULTI-SIGNER flag — "ETAL", "+" and "/" in a GIS owner string all mean
     more than one person is on title, so a single signature cannot convey.

Trusts are called out separately: a revocable trust holding the property usually
means it was in the trust BEFORE death and the GIS "sale" is a title cleanup, so
the trustee signs and there may be no probate sale at all.

    python heir_transfer_review_20260823.py            # review, writes a CSV
    python heir_transfer_review_20260823.py --csv X     # a specific transfers CSV
"""
from __future__ import annotations
import argparse
import csv
import glob
import re
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402
from push_sold_tags import find_record, surname  # noqa: E402

API = "https://apiv2.reisift.io"

# A GIS owner string carrying any of these has more than one person on title.
_MULTI = ("ETAL", " ET AL", "+", "/", "&")
_TRUST = ("TRUST", "TRUSTEE")
_SUFFIX = {"JR", "SR", "II", "III", "IV", "ETAL", "ET", "AL"}

# Mecklenburg's polaris3g publishes FIRST MIDDLE LAST ("CHERITH D FOSTER").
# Every ArcGIS county publishes LAST FIRST MIDDLE ("SUTTLE EMILY SCARBOROUGH").
# Getting this backwards silently swaps first and last name on every push.
_FIRST_LAST_COUNTIES = {"mecklenburg"}


def headers() -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/",
            "x-reisift-ui-version": "2022.02.01.7", "user-agent": "Mozilla/5.0",
            "authorization": f"Bearer {token()}", "content-type": "application/json"}


def deed_parties(owner: str) -> list[str]:
    """Split a GIS owner string into the individual parties on title."""
    parts = re.split(r"\s*/\s*|\s*\+\s*|\s+&\s+", owner or "")
    return [p.strip() for p in parts if p.strip()]


def parse_name(party: str, county: str) -> tuple[str, str]:
    """(first, last) from one GIS party string, honouring the county's order.

    Returns ("", "") for anything that isn't a person — trusts, LLCs, and the
    "HEIRS OF" placeholder some counties write onto the deed itself.
    """
    p = re.sub(r"\s+", " ", (party or "").strip().upper())
    if not p or any(m in p for m in _TRUST) or "HEIRS OF" in p:
        return "", ""
    toks = [t for t in p.split() if t.strip(".") not in _SUFFIX and len(t) > 1]
    if len(toks) < 2:
        return "", ""
    if county.lower() in _FIRST_LAST_COUNTIES:
        first, last = toks[0], toks[-1]
    else:
        last, first = toks[0], toks[1]
    return first.title(), last.title()


def full_record(h: dict, uuid: str) -> dict | None:
    """Search results carry a THIN record — `tags` comes back empty on every hit
    even when the record is tagged. Only GET /property/{uuid}/ has the real list,
    so anything tag-dependent must refetch rather than read the search payload.
    """
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    return d.get("data") or d


def crm_owner(rec: dict) -> str:
    o = rec.get("owner") or {}
    return f"{(o.get('first_name') or '').strip()} {(o.get('last_name') or '').strip()}".strip()


def is_placeholder(name: str) -> bool:
    """The un-renamed 'Heirs of ...' / 'Estate of ...' owner."""
    return (name or "").strip().lower().startswith(("heir", "estate"))


def tags_of(rec: dict) -> list[str]:
    return [t.get("title") if isinstance(t, dict) else str(t)
            for t in (rec.get("tags") or [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="transfers CSV (default: newest heir_transfers_*.csv)")
    args = ap.parse_args()

    path = Path(args.csv) if args.csv else Path(
        sorted(glob.glob(str(REPO / "output" / "heir_transfers_*.csv")))[-1])
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    print(f"reading {path.name}: {len(rows)} heir transfers\n")

    h = headers()
    out = []
    for r in rows:
        county = r.get("county", "")
        street = r.get("address") or ""
        case = r.get("case") or "NO CASE#"
        deed = r.get("owner") or ""
        pr = r.get("pr") or ""

        parties = deed_parties(deed)
        people = [parse_name(p, county) for p in parties]
        people = [p for p in people if p[0]]
        multi = len(parties) > 1 or any(m in deed.upper() for m in _MULTI)
        trust = any(t in deed.upper() for t in _TRUST)

        rec, how = find_record(h, street, r.get("decedent", ""), pr)
        if rec:
            rec = full_record(h, rec.get("uuid", "")) or rec
        live = crm_owner(rec) if rec else ""
        deed_name = f"{people[0][0]} {people[0][1]}" if people else ""

        # What is actually worth doing to this record, in priority order.
        if rec is None:
            action = "NOT IN CRM"
        elif trust and not people:
            action = "TRUST HOLDS TITLE - trustee signs"
        elif is_placeholder(live) and deed_name:
            action = "NAME THE HEIRS ROW"
        elif not deed_name:
            action = "REVIEW - could not read a person off the deed"
        elif surname(live).lower() != people[0][1].lower():
            action = "DEED NAMES SOMEONE ELSE"
        elif live.lower() != deed_name.lower():
            action = "same family, name differs in detail"
        else:
            action = "CONFIRMS CRM owner"

        flags = []
        if multi:
            flags.append(f"MULTI-SIGNER ({len(parties)} on title)"
                         if len(parties) > 1 else "MULTI-SIGNER (ETAL)")
        if trust:
            flags.append("TRUST")
        tg = tags_of(rec) if rec else []
        if any("dp complete" in (t or "").lower() for t in tg):
            flags.append("DP Complete")

        print(f"  {case:20s} {county:12s} {action}")
        print(f"      deed : {deed}")
        print(f"      crm  : {live!r}   court PR: {pr!r}")
        if flags:
            print(f"      flags: {', '.join(flags)}")

        out.append({
            "case": case, "county": county, "week": r.get("week", ""),
            "decedent": r.get("decedent", ""), "address": street,
            "action": action,
            "crm_owner": live, "court_pr": pr,
            "deed_owner_raw": deed, "deed_signer": deed_name,
            "all_signers": " | ".join(f"{f} {l}" for f, l in people),
            "multi_signer": "yes" if multi else "",
            "trust": "yes" if trust else "",
            "sale_date": r.get("sale_date", ""),
            "uuid": (rec or {}).get("uuid", ""), "found_via": how,
            "tags": "|".join(t or "" for t in tg),
        })

    dest = REPO / "output" / "heir_transfer_review_20260823.csv"
    with dest.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    print("\n" + "=" * 62)
    from collections import Counter
    for action, n in Counter(o["action"] for o in out).most_common():
        print(f"  {n:3d}  {action}")
    print(f"  {sum(1 for o in out if o['multi_signer']):3d}  carry a multi-signer deed")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
