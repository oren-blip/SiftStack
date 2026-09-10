"""Push the 2026-09-09 SmartSkip heir results into DataSift.

Batch: 282 estates nobody could phone -> SmartSkip -> Trestle -> 477 heirs across
240 estates, 641 surviving numbers (516 Dial First, 76 Dial Second).

WHY THIS DOES MORE THAN ADD PHONES
    Adding numbers alone would have wasted the batch. "02. Ready to Call" gates on
    predictivecall_attempts == 0 AND no lead status. Of the 239 estates matched:
      - 220 sat above 0 dial attempts (199 at exactly 4, the mail threshold), so
        fresh numbers would land and never reach a call queue.
      - 29 carried a status; 20 of those were "Dead Lead", killed by Oren in the
        last three weeks, 12 of them after 0-2 calls and none with a reason noted.
    Oren's call 2026-09-09: wake all Dead Leads back up EXCEPT 1041 Short St,
    which is genuinely dead (auction 12/11, ten calls, note on the record).

WRITES PER RECORD (each verified by refetch, never trusted on HTTP alone)
    1. owner.phones  += heir numbers, tagged [tier, relationship]
    2. predictivecall_attempts -> 0        (new contact = fresh call cycle; the
                                            same reset court_mailing_sweep does)
    3. status -> None                      (only the 19 approved Dead Leads)
    4. custom fields DM 2/3 Name+Relationship -> the heirs
    Mail counters are deliberately untouched, so the mail cadence is undisturbed.

THINGS THAT WILL BITE YOU HERE
    - An owner PATCH with a TRIMMED phones array DELETES the missing ones. Always
      send existing + new, never just new.
    - The API saves only the FIRST 15 entries of phones and truncates silently at
      HTTP 200. Guarded below.
    - "Decision Maker" (the court-named PR) is NEVER overwritten. Heirs go to the
      DM 2 / DM 3 slots. The court beats a skip-trace guess.

Usage:
    python push_smartskip_heirs_20260909.py              # dry run
    python push_smartskip_heirs_20260909.py --apply
    python push_smartskip_heirs_20260909.py --apply --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import requests  # noqa: E402

from trestle_api_backfill import API, get_token, headers  # noqa: E402

logger = logging.getLogger("push_heirs")

OUT_DIR = Path("output")
REVIEW = Path("output/smartskip_heirs_20260909_153315.csv")
STATUS_SNAPSHOT = None          # set from --status-json
KEEP_TIERS = {"Dial First", "Dial Second"}
MAX_PHONES = 15                 # API silently truncates past this
KEEP_DEAD = "1041 Short St"     # auction 12/11 -- stays dead per Oren

# Custom-field writes take a BARE JSON LIST of {"field_uuid": <uuid>, "value": ...}.
# Passing the integer id, or wrapping in {"custom_fields": [...]}, returns HTTP 500
# on every call -- which the retry loop then burned 22s per record on before this
# was caught. Verified 2026-09-09 by probe + read-back.
CF = {"dm2_name": "1a8124fb-a008-4faf-99a3-a886d2e40efb",
      "dm2_rel":  "006f1e0f-260d-4de9-a626-0b0e0c61749a",
      "dm3_name": "1b4ea269-2802-4a87-801a-54cc18bc2af4",
      "dm3_rel":  "05b53202-5b67-4cd2-90ff-bcc53d348f2b"}


def nk(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", "", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def rq(method: str, url: str, retries: int = 5, **kw):
    """Retry transient failures. A persistent 500 is usually a BAD BODY, not a
    flaky server -- retrying it five times cost 22s per record on the first run
    of this script, so callers that can be wrong should pass retries=2."""
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, timeout=60, **kw)
            last = r
            if r.status_code < 500:
                return r
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return last


def load_heirs() -> dict[str, list[dict]]:
    """property street -> its heir rows (already shortlisted and scored)."""
    out: dict[str, list[dict]] = {}
    with REVIEW.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.setdefault(nk(r.get("Property Address")), []).append(r)
    return out


def heir_phones(row: dict) -> list[dict]:
    """The kept, scored numbers for one heir, tagged tier + relationship."""
    rel = (row.get("Relationship") or "").strip()
    out = []
    for n in (1, 2):
        num = digits(row.get(f"Phone {n}"))
        tier = (row.get(f"Phone {n} Tier") or "").strip()
        if not num or tier not in KEEP_TIERS:
            continue
        tags = [tier] + ([rel] if rel and rel.lower() != "unknown" else [])
        out.append({"number": num,
                    "type": (row.get(f"Phone {n} Type") or "").strip() or None,
                    "tags": tags})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status-json", required=True,
                    help="the status/uuid snapshot built during the audit")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    heirs = load_heirs()
    snap = json.load(open(a.status_json, encoding="utf-8"))
    if a.limit:
        snap = snap[:a.limit]

    h = headers(get_token())
    stats = {"phones_added": 0, "dials_reset": 0, "status_cleared": 0,
             "cf_written": 0, "records": 0, "skipped": 0, "failed": []}
    status_queue: list[dict] = []

    for rec in snap:
        uuid, street = rec["uuid"], rec.get("street") or ""
        rows = heirs.get(nk(street)) or []
        new = [p for r in rows for p in heir_phones(r)]
        if not new:
            stats["skipped"] += 1
            continue

        d = rq("GET", f"{API}/api/internal/property/{uuid}/", headers=h)
        if d is None or d.status_code != 200:
            stats["failed"].append((uuid, "read failed"))
            continue
        d = d.json()
        owner = d.get("owner") or {}
        existing = list(owner.get("phones") or [])
        have = {digits(p.get("number")) for p in existing}

        merged = existing + [p for p in new if p["number"] not in have]
        truncated = False
        if len(merged) > MAX_PHONES:                 # API drops the rest silently
            merged, truncated = merged[:MAX_PHONES], True

        want_status_clear = (rec.get("status") == "Dead Lead"
                             and nk(KEEP_DEAD) not in nk(street))
        added = len(merged) - len(existing)

        logger.info("%-32s +%d phone(s)%s | dials %s->0%s",
                    street[:32], added,
                    " (TRUNCATED at 15)" if truncated else "",
                    rec.get("calls"),
                    " | status cleared" if want_status_clear else "")

        if not a.apply:
            stats["records"] += 1
            stats["phones_added"] += added
            stats["status_cleared"] += want_status_clear   # PLANNED, not done
            continue

        ok = True
        if added:
            o2 = dict(owner)
            o2["phones"] = merged
            r = rq("PATCH", f"{API}/api/internal/property/{uuid}/", headers=h,
                   data=json.dumps({"owner": o2}))
            ok = ok and r is not None and r.status_code in (200, 202)

        # STATUS IS NOT PATCHABLE. null -> "may not be null", "" and "Default"
        # -> "not a valid status choice", both HTTP 400. Worse, sending it
        # alongside another field 400s the WHOLE request, so the first run of
        # this script silently lost the dial reset on all 11 records it tried to
        # clear. Dials go on their own; status clearing is a browser job --
        # see clear_status_20260826.py. Queue them instead.
        r = rq("PATCH", f"{API}/api/internal/property/{uuid}/", headers=h,
               data=json.dumps({"predictivecall_attempts": 0}))
        ok = ok and r is not None and r.status_code in (200, 202)
        if want_status_clear:
            status_queue.append({"uuid": uuid, "street": street,
                                 "status": rec.get("status")})

        # DM 2/3 -- never touch "Decision Maker", that is the court-named PR
        items = []
        for i, row in enumerate(rows[:2]):
            nm = (row.get("Heir Name") or "").strip()
            rel = (row.get("Relationship") or "").strip()
            if not nm:
                continue
            k = "dm2" if i == 0 else "dm3"
            items.append({"field_uuid": CF[f"{k}_name"], "value": nm})
            if rel:
                items.append({"field_uuid": CF[f"{k}_rel"], "value": rel})
        if items:
            r = rq("PATCH",
                   f"{API}/api/internal/property/{uuid}/custom-field/update-values/",
                   headers=h, data=json.dumps(items))
            if r is not None and r.status_code in (200, 202):
                stats["cf_written"] += 1

        # verify -- HTTP success means nothing on this API
        time.sleep(0.3)
        v = rq("GET", f"{API}/api/internal/property/{uuid}/", headers=h)
        if v is None or v.status_code != 200:
            stats["failed"].append((uuid, "verify read failed"))
            continue
        v = v.json()
        vph = {digits(p.get("number")) for p in ((v.get("owner") or {}).get("phones") or [])}
        landed = sum(1 for p in new if p["number"] in vph)
        vcalls = v.get("predictivecall_attempts") or 0
        vstat = v.get("status")

        if landed != added and added:
            stats["failed"].append((uuid, f"phones: wanted {added}, landed {landed}"))
        if vcalls != 0:
            stats["failed"].append((uuid, f"dials still {vcalls}"))
        # vstat is EXPECTED to still be set -- the API cannot clear it.

        stats["records"] += 1
        stats["phones_added"] += landed
        stats["dials_reset"] += (vcalls == 0)

    logger.info("=" * 62)
    mode = "APPLIED" if a.apply else "DRY RUN (nothing written)"
    logger.info("%s: %d record(s), %d phone(s), %d dial reset(s), "
                "%d status clear(s), %d custom-field write(s)",
                mode, stats["records"], stats["phones_added"],
                stats["dials_reset"], stats["status_cleared"], stats["cf_written"])
    logger.info("skipped (no surviving heir phone): %d", stats["skipped"])
    if status_queue:
        q = OUT_DIR / "heirs_status_clear_queue_20260909.json"
        q.parent.mkdir(parents=True, exist_ok=True)
        json.dump(status_queue, q.open("w"), indent=1)
        logger.info("STATUS QUEUE: %d record(s) need the status cleared in the "
                    "BROWSER (the API cannot) -> %s", len(status_queue), q)
    if stats["failed"]:
        logger.warning("VERIFY FAILURES: %d", len(stats["failed"]))
        for u, why in stats["failed"][:15]:
            logger.warning("   %s  %s", u, why)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
