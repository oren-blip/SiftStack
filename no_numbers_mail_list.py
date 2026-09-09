"""Build the "no numbers anywhere" direct-mail list.

Tyler Austin, 5DDF Day 3 (2026-07-15): records that came back EMPTY from skip
tracing in multiple places are not a dead end, they are the highest-ROI direct
mail list he runs.

    "Out of those 100 properties, skip tracing it in DataSift, in Smart Skip and
     in Direct Skip, 10 of them had no results across all 3 locations. This is
     another really, really valuable list, and it's the list that is giving me
     the highest direct mail ROI."

    "I sent 137 [...] we got 3 contracts from the 137 records, and I think it
     was something like 70 or 90 grand [...] I try to do it every 6 months."

Ty's reasoning for why the empties are worth more, not less (Day 3 2026-08-19):

    "if no numbers are coming back for them on the DataSift side, that means a
     lot of other people have skip-traced these individual records and also not
     reached them."

Until now nothing in this repo consumed that set. This script is what consumes it.

CORRECTION 2026-09-09, read this before repeating the original claim
    The first version of this file said the qualifying records reached no mail
    preset and were going unmailed. That was WRONG. It came from replaying
    preset queries through the API search, which does not reproduce what a
    saved filter does in the app. Oren checked in the UI and had just sent 200+
    pieces from "07. Mail Monthly"; reading the 43 records one at a time
    confirms 40 of 43 were mailed in August 2026, 1 in March, and only 2 never.

    So mail was never the gap. The gap is the PHONE side: these people cannot
    be called and nothing re-traces them. The tag exists to make that set
    findable for re-tracing. Never quote a preset-replay count as fact -- ask
    for a UI count, or reason per record from fields a GET actually returns.

WHY IT READS THE CRM AND NOT THE WORKBOOK
    The weekly CSVs are a snapshot from the night a week was polished; phones
    land in DataSift afterwards and the CSV never learns. A batch selected from
    the workbook measured 72% waste on 2026-09-09. Phone truth lives in the CRM.

WHAT IT WILL NOT DO
    It never sends mail and never writes to DataSift unless you pass --apply,
    which only adds a marker tag. Mailing an occupied heir is a standing NO
    (call yes, mail no), so occupancy is filtered here, not left to the preset.

Usage:
    python no_numbers_mail_list.py                 # audit + CSV, no writes
    python no_numbers_mail_list.py --min-attempts 3
    python no_numbers_mail_list.py --apply         # also tag in DataSift
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import requests  # noqa: E402

from trestle_api_backfill import (  # noqa: E402
    API,
    _search,
    get_token,
    headers,
    tag_uuid_map,
)

logger = logging.getLogger("no_numbers_mail")

OUT_DIR = Path("output")
MARKER_TAG = "No Numbers Anywhere"

# Tags that mean "do not put this in a mail campaign", for reasons already
# settled elsewhere in the system. Kept as names, resolved to uuids at runtime.
SUPPRESS_TAGS = {
    "Sold",                 # sold sweep already tagged it
    "Do Not Mail",
    "Do Not Market",
    "Not Buy Box",
    "Dead Area",
    "Hold - Occupied",      # occupied: callable, never mailable
    "cash buyers",          # a buyer record, not a seller lead
    "Entity - Dead",        # defunct LLC, nobody opens the envelope
    "Low Equity",
    "Negative Equity",
}

# Lead statuses that are not a cold-mail target.
SUPPRESS_STATUS = {
    "sold", "buyer", "dnc", "listed", "not_interested", "dead lead",
    "under contract", "contract",
}


def rq(method: str, url: str, **kw):
    """The internal API resets connections under concurrency. Retry politely."""
    for i in range(5):
        try:
            r = requests.request(method, url, timeout=60, **kw)
            if r.status_code < 500:
                return r
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def _status_text(status) -> str:
    if isinstance(status, dict):
        return (status.get("title") or status.get("name") or "").strip().lower()
    return str(status or "").strip().lower()


def fetch_candidates(h: dict) -> list[dict]:
    """Every courthouse record the CRM says holds zero phone numbers."""
    tm = None
    for _ in range(5):
        try:
            tm = tag_uuid_map(h)
            break
        except requests.RequestException:
            time.sleep(3)
    if not tm:
        raise SystemExit("could not read the tag list")
    ch = tm.get("Courthouse Data")
    if not ch:
        raise SystemExit("'Courthouse Data' tag not found")
    slim = _search(h, {"must": {"phone": 0, "any_tags": [ch]}})
    logger.info("zero-phone courthouse records: %d", len(slim))

    def one(rec):
        r = rq("GET", f"{API}/api/internal/property/{rec['uuid']}/", headers=h)
        if r is None or r.status_code != 200:
            return None
        return r.json()

    with ThreadPoolExecutor(max_workers=4) as ex:
        full = [d for d in ex.map(one, slim) if d]
    logger.info("fetched in full: %d", len(full))
    return full


def classify(d: dict, min_attempts: int) -> tuple[bool, str]:
    """Keep/drop one record, with the reason. Reason is the audit trail."""
    owner = d.get("owner") or {}
    tags = {t.strip() for t in (d.get("tags") or [])}

    hit = tags & SUPPRESS_TAGS
    if hit:
        return False, f"suppressed tag: {sorted(hit)[0]}"
    if _status_text(d.get("status")) in SUPPRESS_STATUS:
        return False, f"status: {_status_text(d.get('status'))}"
    if d.get("do_not_mail_ever") or owner.get("do_not_mail_ever"):
        return False, "do_not_mail_ever"
    if owner.get("dnc") or owner.get("opt_out"):
        return False, "owner dnc/opt-out"

    attempts = owner.get("skiptrace_attempts") or 0
    if attempts < min_attempts:
        return False, f"only {attempts} skip trace attempt(s)"

    if (owner.get("phones") or []):
        return False, "actually has a phone"

    mail = ((owner.get("address") or {}).get("street") or "").strip()
    prop = ((d.get("address") or {}).get("street") or "").strip()
    if not mail:
        return False, "no mailing address to send to"
    # Occupied: standing rule is call yes, mail no.
    if mail.lower() == prop.lower():
        return False, "owner occupies the property (mail hold)"

    if not ((owner.get("first_name") or "").strip()
            or (owner.get("last_name") or "").strip()):
        return False, "no addressable name"

    return True, f"traced {attempts}x, still no numbers"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-attempts", type=int, default=2,
                    help="skip-trace attempts required before a miss counts as "
                         "'nobody can reach them' (default 2, Tyler's bar is 2-3)")
    ap.add_argument("--apply", action="store_true",
                    help=f"also add the {MARKER_TAG!r} tag in DataSift")
    ap.add_argument("--out")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    h = headers(get_token())
    full = fetch_candidates(h)

    keep, drop_reasons = [], {}
    for d in full:
        ok, why = classify(d, args.min_attempts)
        if ok:
            keep.append((d, why))
        else:
            drop_reasons[why] = drop_reasons.get(why, 0) + 1

    logger.info("--- dropped ---")
    for why, n in sorted(drop_reasons.items(), key=lambda kv: -kv[1]):
        logger.info("  %4d  %s", n, why)
    logger.info("MAILABLE: %d record(s)", len(keep))

    out = Path(args.out) if args.out else OUT_DIR / f"no_numbers_mail_{date.today():%Y%m%d}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["uuid", "First Name", "Last Name", "Mailing Address", "Mailing City",
            "Mailing State", "Mailing Zip", "Property Address", "Property City",
            "Property State", "Property Zip", "County", "Structure Type",
            "Estimated Value", "Skip Trace Attempts", "Times Mailed", "Why"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d, why in keep:
            o = d.get("owner") or {}
            oa, pa = (o.get("address") or {}), (d.get("address") or {})
            w.writerow({
                "uuid": d.get("uuid"),
                "First Name": o.get("first_name") or "",
                "Last Name": o.get("last_name") or "",
                "Mailing Address": oa.get("street") or "",
                "Mailing City": oa.get("city") or "",
                "Mailing State": oa.get("state") or "",
                "Mailing Zip": oa.get("postal_code") or "",
                "Property Address": pa.get("street") or "",
                "Property City": pa.get("city") or "",
                "Property State": pa.get("state") or "",
                "Property Zip": pa.get("postal_code") or "",
                "County": pa.get("county") or "",
                "Structure Type": d.get("structure_type") or "",
                "Estimated Value": d.get("estimate_value") or "",
                "Skip Trace Attempts": o.get("skiptrace_attempts") or 0,
                "Times Mailed": d.get("directmail_attempts") or 0,
                "Why": why,
            })
    logger.info("wrote %s", out)

    if not args.apply:
        logger.info("AUDIT ONLY - nothing written to DataSift. "
                    "Re-run with --apply to add the %r tag.", MARKER_TAG)
        return 0

    # add-tags takes tag TITLES, not uuids. Passing a uuid returns HTTP 200 and
    # saves NOTHING -- a silent no-op that only a read-back catches. Verified
    # 2026-09-09 when 43/43 "succeeded" and 0/5 actually carried the tag.
    tagged, failed = 0, []
    for d, _ in keep:
        u = d["uuid"]
        r = rq("POST", f"{API}/api/internal/property/{u}/add-tags/",
               headers=h, json={"tags": [MARKER_TAG]})
        if r is None or r.status_code >= 300:
            failed.append(u)
            continue
        chk = rq("GET", f"{API}/api/internal/property/{u}/", headers=h)
        titles = []
        if chk is not None and chk.status_code == 200:
            titles = [t if isinstance(t, str) else (t or {}).get("title")
                      for t in (chk.json().get("tags") or [])]
        if MARKER_TAG in titles:
            tagged += 1
        else:
            failed.append(u)          # HTTP said fine, the record disagrees
    logger.info("tagged and VERIFIED %d of %d record(s) with %r",
                tagged, len(keep), MARKER_TAG)
    if failed:
        logger.warning("%d record(s) did NOT take the tag: %s",
                       len(failed), ", ".join(failed[:5]))
    logger.info("NOTE: the tag is a marker only. No mail preset gates on it yet - "
                "add it to a mail preset deliberately, and check the occupied "
                "exclusion is still in place first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
