"""SmartSkip Group 1 push — verified phones onto the COURT-NAMED PR. No renames.

Oren runs this himself (the auto-mode classifier blocks Claude's DataSift writes):

    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_group1_20260825.py --dry-run
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_group1_20260825.py --limit 5
    d:\\SiftStack\\.venv\\Scripts\\python.exe d:\\SiftStack\\push_smartskip_group1_20260825.py

WHY THIS SCRIPT RENAMES NOTHING
-------------------------------
The 2026-08-24 SmartSkip run traced 82 "Heirs of" subjects. 49 of them already
had a court-named Personal Representative in a later weekly file — and
SmartSkip's top-ranked relative matched that PR only **9 times out of 49**.
Promoting the guess would have put the wrong name on 40 records: the same
failure as the 2026-08-22 rename incident (Parker 26E001117-350), five times
bigger. Oren's standing rule is that **the case file wins**.

So Group 1 does the one thing that is unambiguously safe and valuable: on the
29 estates where SmartSkip returned phone numbers **for the court's own PR**,
it appends those numbers to the existing record. Owner name, mailing address
and lists are never touched. Renames are Group 2, a separate script, and only
for estates where the court has named nobody.

GUARDS
------
  * the record's owner must be EITHER the court PR (already renamed) or the
    "Heirs <decedent-last>" placeholder — a record sitting on some third
    person is skipped loudly, never written to;
  * exactly one property must match the street, else skip;
  * phones already on the record are skipped (last-10-digit compare);
  * "Drop" tier (Trestle score < 21) is never pushed;
  * nothing is ever blanked — the owner is deep-copied and only appended to
    (pr_upgrade lesson, 2026-08-13);
  * every write is read back with GET /property/{uuid}/ and verified, because
    the DataSift SEARCH index is stale after writes;
  * re-runnable: records already carrying the run tag are skipped.

Input:  output/smartskip_group1_court_pr_phones.json
Log:    logs/push_smartskip_group1_20260825.log
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import sys
import time as _time
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from dp_push_20260819 import API, token  # noqa: E402

DRY = "--dry-run" in sys.argv
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

# Group 1B (2026-08-26) reuses this exact script via --src: the overnight
# eCourts catch-up named an executor on 22 more estates, and SmartSkip already
# holds phones for 14 of them. Same shape, same guards - a second copy of this
# code would only be a second place for the bugs we already fixed to come back.
_DEFAULT_SRC = REPO / "output" / "smartskip_group1_court_pr_phones.json"
SRC = _DEFAULT_SRC
for i, a in enumerate(sys.argv):
    if a == "--src" and i + 1 < len(sys.argv):
        SRC = Path(sys.argv[i + 1])
        if not SRC.is_absolute():
            SRC = REPO / SRC
LOG = REPO / "logs" / f"push_{SRC.stem}.log"

# The run tag is what makes this script rerun-safe, so a DIFFERENT push over the
# same records needs a DIFFERENT tag - otherwise the backup-heir pass would see
# the court-PR pass's tag and skip every record it already touched.
RUN_TAG = "SmartSkip 2026-08"
for i, a in enumerate(sys.argv):
    if a == "--tag" and i + 1 < len(sys.argv):
        RUN_TAG = sys.argv[i + 1]

# Trestle score < 21 is "Drop" — never worth a dial, never pushed.
PUSH_TIERS = {"Dial First", "Dial Second", "Dial Third", "Dial Fourth"}

# A record holds up to 30 phones (the UI shows N/30), but the API owner-PATCH
# saves only the FIRST 15 entries of the phones array, so 15 is the ceiling for
# THIS script's write path. Measured 2026-08-27 on 26E000919-170 (Punch): the
# record held 14 phones, the push sent 5 more, HTTP 200 - exactly ONE persisted,
# leaving 15; re-confirmed same day (15 + 4 sent = still 15). The server
# truncates silently and still answers 200, so nothing but a read-back catches
# it. Slots 16-30 need the UI or the phone-number upload wizard.
PHONE_CAP = 15


def headers(tok: str) -> dict:
    return {"authorization": f"Bearer {tok}", "content-type": "application/json",
            "accept": "application/json", "origin": "https://app.reisift.io",
            "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
            "x-reisift-ui-version": "2022.02.01.7"}


def digits(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())[-10:]


# Street-suffix and directional spellings DataSift and the county GIS disagree
# on. The 2026-08-25 dry run lost 5 of 29 estates to exact-string matching:
# "3206 Connecticut Av" never matched "3206 Connecticut Ave", and
# "9112 TREE HAVEN DR CHARLOTTE NC" carried the city and state inside the
# street field.
_SUFFIX = {
    "AV": "AVE", "AVEN": "AVE", "AVENUE": "AVE", "STREET": "ST", "ROAD": "RD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL",
    "BOULEVARD": "BLVD", "HIGHWAY": "HWY", "PARKWAY": "PKWY", "TERRACE": "TER",
    "TRAIL": "TRL", "POINT": "PT",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHWEST": "NW", "NORTHEAST": "NE", "SOUTHWEST": "SW", "SOUTHEAST": "SE",
}
_STATES = {"NC", "SC", "VA", "TN", "GA", "FL", "DE"}
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_CANON_SUFFIX = set(_SUFFIX.values()) | {
    "ST", "RD", "DR", "LN", "CT", "CIR", "PL", "BLVD", "HWY", "PKWY", "TER",
    "TRL", "PT", "AVE", "RUN", "WAY", "LOOP", "XING", "BND", "RDG",
}


def norm_street(raw: str) -> str:
    """Comparable form of a street: upper, unpunctuated, suffixes canonical,
    and any trailing city/state/ZIP dropped."""
    t = "".join(c if c.isalnum() or c.isspace() else " " for c in (raw or "").upper())
    toks = t.split()
    while toks and toks[-1].isdigit() and len(toks[-1]) in (5, 9):
        toks.pop()
    if toks and toks[-1] in _STATES:
        toks.pop()
        # Whatever sits between the street suffix and the state is the city.
        for i in range(len(toks) - 1, 0, -1):
            if _SUFFIX.get(toks[i], toks[i]) in _CANON_SUFFIX:
                toks = toks[:i + 1]
                break
    return " ".join(_SUFFIX.get(x, x) for x in toks)


def street_squash(raw: str) -> set[str]:
    """Space-collapsed comparison forms. DataSift holds '102 Pinetree Dr' where
    the county writes '102 Pine Tree Dr', and '115 Southpoint Dr' for
    '115 South Point Dr' (found 2026-08-26 - 3 of 7 "missing" records existed
    under exactly this kind of spelling). Word boundaries are the least stable
    part of an address; the letters are the most stable.

    Returns BOTH the canonicalised squash and a raw squash: canonicalising maps
    SOUTH->S, which is right for a leading directional but wrong inside a name
    ('SOUTHPOINT'), so neither form alone matches every real pair. Two streets
    match when their squash sets intersect."""
    canon = norm_street(raw).replace(" ", "")
    t = "".join(c if c.isalnum() or c.isspace() else " " for c in (raw or "").upper())
    toks = t.split()
    while toks and toks[-1].isdigit() and len(toks[-1]) in (5, 9):
        toks.pop()
    if toks and toks[-1] in _STATES:
        toks.pop()
        for i in range(len(toks) - 1, 0, -1):
            if _SUFFIX.get(toks[i], toks[i]) in _CANON_SUFFIX:
                toks = toks[:i + 1]
                break
    if toks:
        toks[-1] = _SUFFIX.get(toks[-1], toks[-1])   # suffix only, no directionals
    return {canon, "".join(toks)}


def street_core(raw: str) -> str:
    """House number + first street word - the part that almost never varies.
    Used only as a fallback, and only ever combined with the owner guard."""
    toks = norm_street(raw).split()
    return " ".join(toks[:2]) if len(toks) >= 2 else " ".join(toks)


def search_terms(raw: str) -> list[str]:
    """Progressively looser search strings for one street.

    The 2026-08-25 dry run skipped 5 estates on "0 returned" - the SEARCH came
    back empty, so no amount of match-tuning downstream could help. Two causes
    were mixed together: a street field carrying the city and state
    ("9112 TREE HAVEN DR CHARLOTTE NC"), and records that may simply not be in
    DataSift. Trying the raw string, then the street alone, then house number +
    street name tells those apart instead of guessing.
    """
    raw = (raw or "").strip()
    terms = [raw]

    toks = raw.replace(",", " ").split()
    # Trailing ZIP, then state, then the city that precedes it.
    while toks and toks[-1].isdigit() and len(toks[-1]) in (5, 9):
        toks.pop()
    if toks and toks[-1].upper() in _STATES:
        toks.pop()
        for i in range(len(toks) - 1, 0, -1):
            if _SUFFIX.get(toks[i].upper(), toks[i].upper()) in _CANON_SUFFIX:
                toks = toks[:i + 1]
                break
    street_only = " ".join(toks)
    if street_only and street_only != raw:
        terms.append(street_only)

    # House number + street name, no suffix - the loosest term still specific
    # enough to be worth searching.
    if len(toks) >= 2:
        terms.append(" ".join(toks[:2]))
        # Joined-word variant: their index holds "Pinetree" as one token, so
        # neither "Pine Tree Dr" nor "102 Pine" can ever hit it.
        if len(toks) >= 3:
            terms.append(toks[0] + " " + "".join(toks[1:-1]) + " " + toks[-1])
            terms.append(toks[0] + " " + "".join(toks[1:]))

    seen, out = set(), []
    for t in terms:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def decedent_last(name: str) -> str:
    """'Parker, Geraldine' -> 'parker'; 'Robert Lee Yow, Jr' -> 'yow'."""
    n = (name or "").strip()
    if "," in n:
        head = n.split(",")[0].strip()
        if len(head.split()) == 1:
            return head.lower()
        n = head
    toks = [t for t in n.replace(",", " ").split()
            if t.lower().rstrip(".") not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return toks[-1].lower() if toks else ""


def find_record(h: dict, e: dict, out) -> dict | None:
    """One record at this street whose owner is the court PR or the Heirs
    placeholder. Anything else is somebody we did not research - skip it.

    Tries each search term IN TURN until one yields a usable match - stopping
    at the first term that merely returns *something* is how Roberson was
    missed twice (2026-08-26): "Dockery" returned 5 other Dockerys and the
    loop never went on to try the decedent's surname, which is the term their
    index actually resolves that record under.
    """
    street = e["property"]
    want_pr = e["pr_last"].strip().lower()
    want_dec = decedent_last(e["decedent"])
    want_norm, want_core = norm_street(street), street_core(street)
    want_squash = street_squash(street)

    def owner_ok(rec):
        ow = rec.get("owner") or {}
        first = (ow.get("first_name") or "").strip().lower()
        # Strip suffix tokens from the record's surname before comparing:
        # DataSift holds 'Maurice Jan Foster Ii' with surname 'Foster Ii'
        # (the suffix-in-surname import flaw), which made the guard reject
        # the court PR's own record (found 2026-08-26).
        last = " ".join(t for t in (ow.get("last_name") or "").strip().lower().split()
                        if t.rstrip(".") not in _NAME_SUFFIXES)
        return last == want_pr or (first == "heirs" and last == want_dec)

    def try_term(term):
        # DataSift drops the connection partway through a long search loop
        # (WinError 10054). Unretried, that aborts the whole run and the
        # estates after it never get looked at - which is how the 2026-08-26
        # group 3 dry run died on its first pass. Back off and retry; only a
        # persistent failure is allowed to skip the estate.
        r = None
        for attempt in range(4):
            try:
                r = requests.post(f"{API}/api/internal/property/",
                                  headers={**h, "x-http-method-override": "GET"},
                                  json={"query": {"must": {"search": term}}},
                                  timeout=30)
                break
            except requests.exceptions.RequestException as exc:
                if attempt == 3:
                    out(f"  search {term!r} -> connection failed 4x ({exc}) - SKIP")
                    return None, []
                _time.sleep(2 * (attempt + 1))
        if r.status_code != 200:
            out(f"  search {term!r} -> HTTP {r.status_code}")
            return None, []
        results = r.json().get("results", [])
        exact = [x for x in results
                 if norm_street((x.get("address") or {}).get("street")) == want_norm
                 or (street_squash((x.get("address") or {}).get("street")) & want_squash)]
        loose = ([] if exact else
                 [x for x in results
                  if street_core((x.get("address") or {}).get("street")) == want_core])
        pool = exact or loose
        hits = [x for x in pool if owner_ok(x)]
        if len(hits) == 1:
            if term != street:
                out(f"  matched via term {term!r}: "
                    f"{(hits[0].get('address') or {}).get('street')!r}")
            return hits[0], results
        return None, results

    # Surname terms last: safe because the street match + owner guard still
    # have to pass, but only useful when the address terms fail.
    terms = search_terms(street) + [e["pr_last"], decedent_last(e["decedent"])]
    seen, any_results = set(), False
    for term in terms:
        t = (term or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        hit, results = try_term(t)
        if hit:
            return hit
        if results:
            any_results = True
    out(f"  {street!r}: no usable match on any of {sorted(seen)}"
        + ("" if any_results else " - record is not in DataSift")
        + " - SKIP")
    return None


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
        f"{len(entries)} estate(s), PHONES ONLY, no renames")
    h = headers(token())
    ok = skipped = phones_added = 0

    for e in entries:
        out(f"\n=== {e['case_no']} {e['county']} | {e['decedent']} "
            f"| court PR: {e['court_pr']}")
        rec = find_record(h, e, out)
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
        # Deep copy and append only. Nothing existing is overwritten or blanked.
        new_owner = copy.deepcopy(owner)
        existing = {digits(p.get("number")) for p in (owner.get("phones") or [])}
        batch_seen: set[str] = set()

        added = []
        for ph in e["phones"]:
            tier = ph.get("tier")
            if tier not in PUSH_TIERS:
                continue
            num = ph["phone"]
            if digits(num) in existing:
                out(f"  {num} already on record - skip")
                continue
            # ALSO dedupe within this batch. Group 1 carried one person's
            # numbers per estate so this could not arise; a backup-heir push
            # carries a whole family, and relatives share household lines -
            # the 2026-08-26 dry run queued 8653858328 twice on one record and
            # 7046899117 twice on another. Writing a number twice bloats the
            # record toward the phone cap and reads as sloppy to a caller.
            if digits(num) in batch_seen:
                out(f"  {num} already queued for this record - skip (duplicate)")
                continue
            batch_seen.add(digits(num))
            ltype = ("MOBILE" if "mobile" in str(ph.get("line_type") or "").lower()
                     else "LANDLINE")
            # The API PATCH persists only the first PHONE_CAP entries (see the
            # PHONE_CAP note up top). A cluster push can carry 10+ numbers onto
            # a record that already holds some, so stop before the cap rather
            # than let the CRM silently truncate and leave us believing a
            # number landed.
            if len(new_owner.get("phones") or []) >= PHONE_CAP:
                out(f"  phone cap {PHONE_CAP} reached on this record - "
                    f"{num} and any after it NOT added")
                break
            # Honest provenance: whose number this is and where it came from.
            # Backup-heir pushes set a per-phone label, because on those the
            # number belongs to a relative, NOT to the owner of record - a
            # caller must be able to see that before dialling.
            label = ph.get("label") or f"Court PR {e['court_pr']}"
            new_owner.setdefault("phones", []).append({
                "number": num, "type": ltype,
                "tags": [tier, label, "SmartSkip"],
            })
            added.append(num)

        if not added:
            out("  nothing new to add - skip")
            ok += 1
            continue

        out(f"  owner stays {owner.get('first_name')} {owner.get('last_name')} "
            f"(NO rename); +{len(added)} phone(s): {added}")
        if DRY:
            ok += 1
            phones_added += len(added)   # "would add" in a dry run
            continue

        r = requests.patch(f"{API}/api/internal/property/{uuid}/", headers=h,
                           json={"owner": new_owner}, timeout=30)
        out(f"  PATCH owner -> HTTP {r.status_code}")
        if r.status_code != 200:
            out(f"    {r.text[:200]} - SKIPPING tag")
            skipped += 1
            continue
        r = requests.post(f"{API}/api/internal/property/{uuid}/add-tags/",
                          headers=h, json={"tags": [RUN_TAG]}, timeout=30)
        out(f"  add-tags [{RUN_TAG}] -> HTTP {r.status_code}")

        # Verify against the RECORD, never the search index (it goes stale).
        r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
        if r.status_code != 200:
            out("  verify GET failed - treat as UNCONFIRMED")
            skipped += 1
            continue
        d2 = r.json()
        ow2 = d2.get("owner") or {}
        live = {digits(p.get("number")) for p in (ow2.get("phones") or [])}
        missing = [n for n in added if digits(n) not in live]
        tags2 = [t.get("title") if isinstance(t, dict) else str(t)
                 for t in (d2.get("tags") or [])]
        # The owner must be untouched — this script must never rename.
        same_owner = ((ow2.get("last_name") or "").strip().lower()
                      == (owner.get("last_name") or "").strip().lower())
        out(f"  verify: phones_missing={missing} tagged={RUN_TAG in tags2} "
            f"owner_unchanged={same_owner}")
        if not missing and same_owner:
            ok += 1
            phones_added += len(added)
        else:
            skipped += 1

    verb = "WOULD be added (DRY RUN - nothing written)" if DRY else "actually added"
    out(f"\n{ok} ok, {skipped} skipped, of {len(entries)} estate(s); "
        f"{phones_added} phone(s) {verb}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
