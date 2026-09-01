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
import time
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


def _street_of(rec: dict) -> str:
    return (rec.get("address") or {}).get("street") or ""


def _street_compatible(a: str, b: str) -> bool:
    """True when two street strings can be the same address written differently.

    The surname + house-number fallback used to accept ANY single record at the
    right house number, which is how "235 N East End Ave" matched a record
    reading "235 E End Ave" — right property as it turned out, but the same
    rule would just as happily have matched "235 Oak St" and renamed a stranger.

    Compatible means one side's folded tokens are a subset of the other's:
    DataSift drops directionals and abbreviates, so the stored street is a
    shortening of the county's, never a different road.
    """
    ta = set(_fold(a or "", _SHORT).lower().split())
    tb = set(_fold(b or "", _SHORT).lower().split())
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


def surname(name: str) -> str:
    """'Hutchinson, Faye' and 'Bradley Hutchinson' both -> 'Hutchinson'."""
    name = (name or "").strip()
    if not name:
        return ""
    if "," in name:                      # audit CSV writes the decedent LAST, FIRST
        return name.split(",")[0].strip()
    parts = [p for p in name.split()
             if p.lower().rstrip(".") not in ("jr", "sr", "ii", "iii", "iv")]
    return parts[-1] if parts else ""


def match_one(rows: list[dict], street: str) -> dict | None:
    """Exact-ish street match only. Ambiguity is reported, never guessed."""
    want = _norm(street)
    hits = [r for r in rows if _norm(_street_of(r)) == want]
    return hits[0] if len(hits) == 1 else None


def find_record(h: dict, street: str, decedent: str = "",
                pr: str = "") -> tuple[dict | None, str]:
    """Locate the record, and say why when it can't. Returns (record, how).

    Street search alone is not enough. The API matches the whole search string
    against stored text, and GIS and DataSift disagree on spelling *and* case
    ("994 22nd St Pl NE" returns 0 against a record reading "994 22Nd Street
    Pl Ne"), so audit_rename_gap_20260822 falls back to a surname search
    narrowed by house number. Same fallback here — the estate's decedent and PR
    are the two names the record is most likely filed under.

    `how` distinguishes the two failures that used to look identical in the
    log: a property that was never uploaded (nothing to suppress, not a bug)
    from one with several candidate hits (needs a human).
    """
    if not street:
        return None, "NO ADDRESS in audit row"
    want, num = _norm(street), (street.split() or [""])[0].lower()

    tried: list[str] = []
    for form in (street, _fold(street, _SHORT), _fold(street, _LONG)):
        if form in tried:
            continue
        tried.append(form)
        rows = _search(h, form)
        if not rows:
            continue
        rec = match_one(rows, street)
        if rec:
            return rec, f"street {form!r}"
        return None, f"AMBIGUOUS ({len(rows)} hits on {form!r}, none an exact street match)"

    for label, person in (("decedent", decedent), ("PR", pr)):
        ln = surname(person)
        if not ln:
            continue
        rows = _search(h, ln)
        if not rows:
            continue
        near = [r for r in rows if _street_of(r).lower().startswith(num + " ")] if num else rows
        exact = [r for r in near if _norm(_street_of(r)) == want]
        if len(exact) == 1:
            return exact[0], f"{label} surname {ln!r} + house number"
        if len(near) == 1 and _street_compatible(street, _street_of(near[0])):
            return near[0], (f"{label} surname {ln!r} + house number "
                             f"(record street reads {_street_of(near[0])!r})")
        if len(near) == 1:
            return None, (f"AMBIGUOUS (one {label}-surname record at house number "
                          f"{num}, but its street reads {_street_of(near[0])!r} "
                          f"against {street!r})")
        if near:
            return None, (f"AMBIGUOUS ({len(near)} records at house number {num} "
                          f"under {label} surname {ln!r})")

    return None, "NOT IN CRM (no street or surname hit — never uploaded?)"


def add_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    """Add tags by TITLE. The route is /add-tags/ (not /tag/) and the payload
    carries titles, not uuids — same shape dp_push_20260819.py uses.
    """
    r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/", headers=h,
                      json={"tags": titles}, timeout=30)
    return r.status_code in (200, 201, 202, 204)


def read_tags(h: dict, uuid: str) -> set[str] | None:
    """Titles currently on the record, or None if the read itself failed."""
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    if r.status_code != 200:
        return None
    d = r.json()
    d = d.get("data") or d
    return {(t.get("title") if isinstance(t, dict) else str(t)) or ""
            for t in (d.get("tags") or [])}


# The write is durable before the read reflects it. On 2026-08-23 all three
# suppressions logged FAILED and all three were verified tagged minutes later —
# a single immediate re-read is a coin flip, not a check. Retry before believing
# a failure; never verify via search, whose index is staler still.
VERIFY_TRIES = 4
VERIFY_WAIT = 3  # seconds between reads


def verify_tags(h: dict, uuid: str, titles: list[str]) -> bool:
    """Re-read the property until the titles land, or the retries run out."""
    for attempt in range(VERIFY_TRIES):
        have = read_tags(h, uuid)
        if have is not None and all(w in have for w in titles):
            return True
        if attempt < VERIFY_TRIES - 1:
            time.sleep(VERIFY_WAIT)
    return False


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
        if (r.get("uuid") or "").strip():
            # CRM-sourced row (sold_audit --crm-legacy): the parcel came FROM
            # this record, so there is nothing to search for.
            rec, how = {"uuid": r["uuid"].strip()}, "CRM uuid"
        else:
            rec, how = find_record(h, street, r.get("decedent", ""), r.get("pr", ""))
        case = r.get("case") or "NO CASE#"
        if rec is None:
            print(f"  {how[:26]:26s} {case} | {street[:38]}")
            results.append({**r, "result": how, "uuid": ""})
            continue
        uuid = rec.get("uuid")
        if not args.apply:
            extra = f" + Sold {month}" if month_tag else ""
            print(f"  would tag                  {case} | {street[:38]:38s} | Sold{extra}")
            results.append({**r, "result": "DRY RUN", "uuid": uuid, "how": how})
            continue
        # Already-tagged records re-verify clean and cost one read — leave the
        # write in anyway so a partially-tagged record (Sold, no month) heals.
        ok = add_tags(h, uuid, want) and verify_tags(h, uuid, want)
        state = "TAGGED (verified)" if ok else "FAILED"
        print(f"  {state:26s} {case} | {street[:38]}")
        results.append({**r, "result": state, "uuid": uuid, "how": how})

    if args.apply and results:
        new = not LOG.exists()
        with LOG.open("a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "run_date", "case", "county", "decedent", "address", "sale_date",
                "sale_price", "owner", "class", "result", "uuid", "how"],
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
