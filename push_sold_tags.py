"""Nightly sold suppression, free — county GIS is the sale feed, not SiftMap.

Why this exists (2026-08-23): Ty's Day-2 "recently sold auto-add" is a SiftMap
Pro feature ($297/mo; the toggle renders disabled on this account). The point
of it — sold properties drop out of marketing every day without a monthly
sweep — is reproducible for $0, and more accurately: on 2026-08-01 the
parcel-level GIS audit caught 13 transferred probate properties that DataSift's
SiftMap merge caught ZERO of.

Flow:
    sold_audit.py  -> output/sold_audit_<date>.csv  (parcel-level GIS truth)
    this script    -> reads that CSV, tags the real sales "Sold" in DataSift

Because the 12 NSM presets now carry must_not.any_tags = [Sold] (see
add_sold_exclusion_20260823.py), the tag alone removes the record from every
call and mail lane. No sequence has to fire — bulk tag adds do NOT fire
sequences on this account, which is exactly why the preset rule went in first.

Classification drives the action (sold_audit.classify):
    MARKET SALE / INVESTOR PURCHASE -> tag Sold + Sold YYYY-MM  (suppress)
    HEIR TRANSFER                   -> NOT suppressed. Estate settled, title
                                       cleared, new owner is family: Oren's
                                       standing rule is these are HOT re-target
                                       leads. Reported for the Inherited lane.
    UNCLEAR TRANSFER                -> reported only, never tagged. $0-ish
                                       stranger transfers need Oren's eyes
                                       (cf. Rice -> Almendarez, still open).

    python push_sold_tags.py                  # dry run, writes nothing
    python push_sold_tags.py --apply          # tag the real sales
    python push_sold_tags.py --csv <path>     # use a specific audit CSV

Every tag write is verified by re-reading the property (the DataSift search
index is stale after writes — never trust the write response or a search).
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
SUPPRESS = ("MARKET SALE", "INVESTOR PURCHASE")
REPORT_ONLY = ("HEIR TRANSFER", "UNCLEAR TRANSFER")
LOG = REPO / "output" / "sold_tag_push_log.csv"


def headers() -> dict:
    return {"accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
            "user-agent": "Mozilla/5.0", "authorization": f"Bearer {token()}",
            "content-type": "application/json"}


def latest_audit_csv() -> Path | None:
    hits = sorted(glob.glob(str(REPO / "output" / "sold_audit_*.csv")))
    return Path(hits[-1]) if hits else None


def tag_map(h: dict) -> dict[str, str]:
    """title(lower) -> uuid for every tag on the account."""
    r = requests.get(f"{API}/api/internal/tag/", headers=h,
                     params={"limit": 500}, timeout=60)
    r.raise_for_status()
    rows = r.json().get("results") or r.json().get("data") or []
    return {(t.get("title") or "").strip().lower(): t.get("uuid") for t in rows}


# County GIS and DataSift disagree on street spelling: GIS writes "305 South D
# Ave", DataSift stores "305 S D Ave", and the API's search is a whole-string
# match — "305 South D Ave" returns 0 hits while "305 S D Ave" returns the
# record. So every lookup is tried in both the abbreviated and spelled-out form,
# and comparison folds both to the short form.
_SHORT = {
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    "street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "lane": "ln",
    "court": "ct", "circle": "cir", "place": "pl", "trail": "trl",
    "boulevard": "blvd", "parkway": "pkwy", "highway": "hwy", "terrace": "ter",
}
_LONG = {v: k for k, v in _SHORT.items()}


def _fold(street: str, table: dict) -> str:
    return " ".join(table.get(t.lower(), t) for t in (street or "").split())


def _norm(s: str) -> str:
    """Canonical form for comparison: abbreviations folded short, punctuation out."""
    return re.sub(r"[^a-z0-9]", "", _fold(s or "", _SHORT).lower())


def _search(h: dict, text: str) -> list[dict]:
    """One search. The term MUST sit at query.must.search — a top-level "search"
    key is silently ignored and the API hands back the first page of the whole
    account instead (200 bogus "hits"). limit=200; the default page hides matches.
    """
    r = requests.post(f"{API}/api/internal/property/",
                      headers={**h, "x-http-method-override": "GET"},
                      json={"limit": 200, "query": {"must": {"search": text}}},
                      timeout=60)
    if r.status_code != 200:
        return []
    d = r.json()
    return d.get("results") or d.get("data") or []


def find_record(h: dict, street: str) -> list[dict]:
    """Search the street in both spelling conventions; first form that hits wins."""
    if not street:
        return []
    tried = []
    for form in (street, _fold(street, _SHORT), _fold(street, _LONG)):
        if form in tried:
            continue
        tried.append(form)
        rows = _search(h, form)
        if rows:
            return rows
    return []


def match_one(rows: list[dict], street: str) -> dict | None:
    """Exact-ish street match only. Ambiguity is reported, never guessed."""
    want = _norm(street)
    hits = [r for r in rows if _norm((r.get("address") or {}).get("street")) == want]
    return hits[0] if len(hits) == 1 else None


def add_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    """Add tags by TITLE. The route is /add-tags/ (not /tag/) and the payload
    carries titles, not uuids — same shape dp_push_20260819.py uses.
    """
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/", headers=h,
                      json={"tags": titles}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def verify_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    """Re-read the property and confirm the titles landed. Never trust the write
    response, and never verify via search — the search index is stale after writes.
    """
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        return False
    d = r.json()
    d = d.get("data") or d
    have = {(t.get("title") if isinstance(t, dict) else str(t)) or ""
            for t in (d.get("tags") or [])}
    return all(w in have for w in titles)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the tags (default: dry run)")
    ap.add_argument("--csv", help="audit CSV to read (default: newest sold_audit_*.csv)")
    args = ap.parse_args()

    path = Path(args.csv) if args.csv else latest_audit_csv()
    if not path or not path.exists():
        print("No sold_audit_*.csv found — run: python sold_audit.py --since YYYY-MM-DD")
        return 1
    print(f"reading {path.name}")

    rows = [r for r in csv.DictReader(path.open(encoding="utf-8-sig")) if r.get("flag")]
    if not rows:
        print("No flagged sales in that audit — nothing to suppress.")
        return 0

    # sold_audit puts 'class' only in its console output, so re-derive it here.
    from sold_audit import classify
    for r in rows:
        r["class"] = classify(r)

    h = headers()
    tags = tag_map(h)
    sold_uuid = tags.get("sold")
    if not sold_uuid:
        print('No "Sold" tag on the account — aborting rather than creating one.')
        return 1

    todo = [r for r in rows if r["class"] in SUPPRESS]
    hold = [r for r in rows if r["class"] in REPORT_ONLY]

    print(f"\n{len(rows)} flagged sales: {len(todo)} to suppress, "
          f"{len(hold)} report-only\n")
    for r in hold:
        print(f"  KEEP MARKETING  {r.get('case') or 'NO CASE#'} | {r['class']:17s} | "
              f"{(r.get('address') or '')[:38]:38s} | {r.get('sale_date')}")
    if hold:
        print()

    results = []
    for r in todo:
        street = r.get("address") or ""
        month = (r.get("sale_date") or "")[:7]
        # Only reuse a month tag that already exists — don't spawn new ones.
        month_tag = f"Sold {month}" if tags.get(f"sold {month}") else None
        want = ["Sold"] + ([month_tag] if month_tag else [])
        found = find_record(h, street)
        rec = match_one(found, street)
        case = r.get("case") or "NO CASE#"
        if rec is None:
            state = f"NO MATCH ({len(found)} search hits)"
            print(f"  {state:26s} {case} | {street[:38]}")
            results.append({**r, "result": state, "uuid": ""})
            continue
        uuid = rec.get("uuid")
        if not args.apply:
            extra = f" + Sold {month}" if month_tag else ""
            print(f"  would tag                  {case} | {street[:38]:38s} | Sold{extra}")
            results.append({**r, "result": "DRY RUN", "uuid": uuid})
            continue
        ok = add_tags(h, uuid, want) and verify_tags(h, uuid, want)
        state = "TAGGED (verified)" if ok else "FAILED"
        print(f"  {state:26s} {case} | {street[:38]}")
        results.append({**r, "result": state, "uuid": uuid})

    if args.apply and results:
        new = not LOG.exists()
        with LOG.open("a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "run_date", "case", "county", "decedent", "address", "sale_date",
                "sale_price", "owner", "class", "result", "uuid"],
                extrasaction="ignore")
            if new:
                w.writeheader()
            for r in results:
                w.writerow({**r, "run_date": date.today().isoformat()})
        print(f"\nappended {len(results)} rows -> {LOG}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
