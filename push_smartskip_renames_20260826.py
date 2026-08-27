"""SmartSkip Group 2 - RENAME the 12 estates that survived the court re-check.

Oren runs this himself (the auto-mode classifier blocks Claude's DataSift writes):

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_renames_20260826.py --dry-run
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_renames_20260826.py --limit 3
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_renames_20260826.py

WHY ONLY 12 OF 29
-----------------
The overnight eCourts catch-up (2026-08-25 -> 26) named an executor on 22 of the
33 no-PR estates. Compared against SmartSkip's ranked heir, **the court named
someone else 17 times and agreed only 4 times** - an 81% miss rate, and several
of the misses were the same surname with a different first name (TED vs JEFFREY
Lawson, EVERETTE vs ROBERT Courteau, EDWARD vs SHIRLEY Baker). Those 17 are
excluded here; their phones went onto the COURT's person instead, via
push_smartskip_group1_20260825.py --src ...group1b....

What is left is the only defensible set:
  * 4 where the court named exactly who SmartSkip ranked first  -> court-confirmed
  * 8 where the court still names nobody, so the ranked heir is the best
    answer available -> smartskip-heir

MARKETING RULES (Oren, 2026-08-25)
----------------------------------
  * Heir living in the property: **calling is fine, direct mail is not.** Those
    records get "Hold Mail - Heir Occupies" and their mailing address is left
    pointing at the property (never redirected to themselves).
  * An heir with no dialable number may end up at "Needs first mail" - but only
    after other methods are exhausted. This script does NOT set that status; it
    tags "No Phone - Review" and leaves the decision to Oren.

GUARDS
------
  * a record is renamed ONLY if its owner is still the "Heirs <decedent-last>"
    placeholder. A record already sitting on a real person is left alone - that
    person came from somewhere, and overwriting them is how the 2026-08-22
    wrong-person incident happened;
  * mailing is written to owner["address"] - owner["mailing_address"] is a key
    the API accepts and silently ignores (0 of 16 saved, found 2026-08-22);
  * mailing is only redirected when the heir lives ELSEWHERE and the address
    parses completely; never blanked, never partial (pr_upgrade lesson);
  * every write is read back with GET /property/{uuid}/ - the search index is
    stale after writes - and the rename, mailing and tags are each verified;
  * re-runnable: records already carrying the run tag are skipped.

Input:  output/smartskip_group2_renames.json
Log:    logs/push_smartskip_renames_20260826.log
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402
# Reuse the address matching proven on the 2026-08-25 phone push rather than
# re-deriving it: it already handles Av/Ave, a street carrying its own city and
# state, and the widening search cascade.
from push_smartskip_group1_20260825 import (  # noqa: E402
    decedent_last, digits, headers, norm_street, search_terms, street_core,
    street_squash,
)

DRY = "--dry-run" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

SRC = REPO / "output" / "smartskip_group2_renames.json"
LOG = REPO / "logs" / "push_smartskip_renames_20260826.log"

RUN_TAG = "SmartSkip Rename 2026-08"
TAG_OCCUPIED = "Hold Mail - Heir Occupies"
TAG_NO_PHONE = "No Phone - Review"
PUSH_TIERS = {"Dial First", "Dial Second", "Dial Third", "Dial Fourth"}


def find_heirs_record(h: dict, e: dict, out) -> dict | None:
    """The ONE record at this street still owned by 'Heirs <decedent-last>'.

    Deliberately stricter than the phone push: that one could also accept a
    record already renamed to the court PR, because appending a phone to the
    right person is harmless. A RENAME must never land on a record that already
    names somebody.
    """
    street = e["property"]
    want_dec = decedent_last(e["decedent"])
    # Surname fallback - see push_smartskip_group1_20260825.find_record.
    results = []
    for term in search_terms(street) + [want_dec]:
        r = requests.post(f"{API}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"query": {"must": {"search": term}}}, timeout=30)
        if r.status_code != 200:
            out(f"  search {term!r} -> HTTP {r.status_code}")
            continue
        results = r.json().get("results", [])
        if results:
            if term != street:
                out(f"  search widened: {street!r} -> {term!r} ({len(results)})")
            break
    if not results:
        out(f"  {street!r}: search returned NOTHING - not in DataSift - SKIP")
        return None

    want_norm, want_core = norm_street(street), street_core(street)
    want_squash = street_squash(street)
    at_street = [x for x in results
                 if norm_street((x.get("address") or {}).get("street")) == want_norm
                 or (street_squash((x.get("address") or {}).get("street")) & want_squash)]
    if not at_street:
        at_street = [x for x in results
                     if street_core((x.get("address") or {}).get("street")) == want_core]

    hits, others = [], []
    for x in at_street:
        ow = x.get("owner") or {}
        first = (ow.get("first_name") or "").strip().lower()
        last = (ow.get("last_name") or "").strip().lower()
        if first == "heirs" and last == want_dec:
            hits.append(x)
        else:
            others.append(f"{ow.get('first_name')} {ow.get('last_name')}")
    if len(hits) != 1:
        out(f"  {street!r}: {len(hits)} 'Heirs {want_dec}' record(s) of "
            f"{len(at_street)} at this street"
            + (f"; already named: {others}" if others else "")
            + " - SKIP (never overwrite a real person)")
        return None
    return hits[0]


def main() -> int:
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    if LIMIT:
        entries = entries[:LIMIT]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = LOG.open("a", encoding="utf-8")

    def out(text: str) -> None:
        print(text)
        log.write(text + "\n")
        log.flush()

    out(f"\n===== run at {_dt.datetime.now()} dry_run={DRY} - "
        f"{len(entries)} rename(s)")
    h = headers(token())
    ok = skipped = renamed = 0

    for e in entries:
        out(f"\n=== {e['case_no']} {e['county']} | Heirs of {e['decedent']} "
            f"-> {e['new_full']} ({e['relationship']}, {e['source']})")
        rec = find_heirs_record(h, e, out)
        if not rec:
            skipped += 1
            continue
        uuid = rec.get("uuid")
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            out(f"  GET {uuid} -> {r.status_code} - SKIP")
            skipped += 1
            continue
        d = r.json()
        tags_now = [t.get("title") if isinstance(t, dict) else str(t)
                    for t in (d.get("tags") or [])]
        if RUN_TAG in tags_now:
            out("  already carries the run tag - skip (rerun-safe)")
            ok += 1
            continue

        owner = d.get("owner") or {}
        new_owner = copy.deepcopy(owner)
        new_owner["first_name"] = e["new_first"]
        new_owner["last_name"] = e["new_last"]

        # Mailing: only redirect an heir who lives ELSEWHERE, and only when the
        # whole address is present. An occupying heir keeps the property address
        # (Oren: call them, do not mail them).
        mail_note = "mailing unchanged"
        if e["at_property"]:
            mail_note = "mailing unchanged (heir occupies - mail is held)"
        else:
            parts = (e["heir_mailing"], e["heir_city"], e["heir_state"], e["heir_zip"])
            if all((p or "").strip() for p in parts):
                ma = new_owner.get("address") or {}
                ma.update({"street": e["heir_mailing"], "city": e["heir_city"],
                           "state": e["heir_state"], "postal_code": e["heir_zip"]})
                new_owner["address"] = ma
                mail_note = (f"mailing -> {e['heir_mailing']}, {e['heir_city']} "
                             f"{e['heir_state']} {e['heir_zip']}")
            else:
                mail_note = "mailing unchanged (heir address incomplete)"

        existing = {digits(p.get("number")) for p in (owner.get("phones") or [])}
        added = []
        for ph in e["phones"]:
            if ph.get("tier") not in PUSH_TIERS:
                continue
            if digits(ph["phone"]) in existing:
                continue
            new_owner.setdefault("phones", []).append({
                "number": ph["phone"], "type": "MOBILE",
                "tags": [ph["tier"], f"{e['relationship']} {e['new_full']}", "SmartSkip"],
            })
            added.append(ph["phone"])

        add_tags = [RUN_TAG]
        if e["at_property"]:
            add_tags.append(TAG_OCCUPIED)
        if not e["phones"]:
            add_tags.append(TAG_NO_PHONE)

        out(f"  rename 'Heirs {decedent_last(e['decedent'])}' -> "
            f"{e['new_first']} {e['new_last']}; {mail_note}; "
            f"+{len(added)} phone(s); tags {add_tags}")
        if DRY:
            ok += 1
            renamed += 1
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"owner": new_owner}, timeout=30)
        out(f"  PATCH owner -> HTTP {r.status_code}")
        if r.status_code != 200:
            out(f"    {r.text[:200]} - SKIPPING tags")
            skipped += 1
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": add_tags}, timeout=30)
        out(f"  add-tags {add_tags} -> HTTP {r.status_code}")

        # Verify off the RECORD - the search index lies after a write.
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            out("  verify GET failed - treat as UNCONFIRMED")
            skipped += 1
            continue
        d2 = r.json()
        ow2 = d2.get("owner") or {}
        name_ok = ((ow2.get("last_name") or "").strip().lower()
                   == e["new_last"].strip().lower()
                   and (ow2.get("first_name") or "").strip().lower()
                   == e["new_first"].strip().lower())
        live = {digits(p.get("number")) for p in (ow2.get("phones") or [])}
        missing = [n for n in added if digits(n) not in live]
        tags2 = [t.get("title") if isinstance(t, dict) else str(t)
                 for t in (d2.get("tags") or [])]
        mail_ok = True
        if mail_note.startswith("mailing -> "):
            mail_ok = ((ow2.get("address") or {}).get("street") or "").strip().lower() \
                == e["heir_mailing"].strip().lower()
        tags_ok = all(t in tags2 for t in add_tags)
        out(f"  verify: renamed={name_ok} mailing_saved={mail_ok} "
            f"phones_missing={missing} tags={tags_ok}")
        if name_ok and mail_ok and not missing and tags_ok:
            ok += 1
            renamed += 1
        else:
            skipped += 1

    verb = "WOULD be renamed (DRY RUN - nothing written)" if DRY else "renamed"
    out(f"\n{ok} ok, {skipped} skipped, of {len(entries)}; {renamed} record(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
