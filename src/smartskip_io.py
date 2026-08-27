"""SmartSkip CSV round-trip — bulk relative-cluster skip trace for deep prospecting.

SmartSkip has NO API and says so deliberately (their own "API vs manual" post
argues API integrations "require custom development for every piece of software
in your stack"). Everything is CSV in, CSV out. So this module is two halves
with a human in the middle:

    1. export  — turn deep-prospecting target rows into SmartSkip's bulk
                 upload CSV. You upload that file at smartskip.io.
    2. ingest  — read the "campaign format" file you download back, rebuild
                 each subject's relative cluster, gate it down to the people
                 who actually have to sign, Trestle-score their phones, and
                 keep only Dial First / Dial Second.

That gate is not decoration. Ty's 2026-08-19 demo pulled **41 associated
individuals from one $0.15 hit** on decedent "Tomas" and the flow whittled it
to **the 3 people who matter** — DataSift caps phones per record (~30), so
writing a raw 41-person cluster back would blow the record up. Shortlist
first, always.

Subject = the DECEASED OWNER anchored to the PROPERTY address, not the PR.
Straight from the transcript: *"the input name is the person who is the owner
on title, so we're always putting that in, and we're putting in the property
address that's linked."* Skip tracing the PR gets you the PR's own numbers,
which we usually already have; skip tracing the decedent is what returns the
family cluster.

Cost: $0.15 per uploaded row (SmartSkip Basic is free; Premium $50/mo is what
officially lists relatives + associates + caller ID). Trestle adds ~$0.015 per
NEW phone — already-scored numbers come free from output/.trestle_score_cache.json.

This module never uploads anything to DataSift and never calls SmartSkip over
the network. It reads and writes files. Deliberate: the upload/download step is
yours, and the review artifact it produces is meant to be eyeballed first.

Usage:
    python src/smartskip_io.py export output/FTM_wk34_datasift.csv
    python src/smartskip_io.py export <csv> --filter heirs --dry-run
    python src/smartskip_io.py ingest output/smartskip_download.csv --no-trestle
    python src/smartskip_io.py ingest <csv> --keep-tiers "Dial First,Dial Second"
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("smartskip")

COST_PER_ROW = 0.15               # SmartSkip bulk, per row uploaded
TRESTLE_PER_PHONE = 0.015         # mirrors phone_validator.COST_PER_PHONE
_TRESTLE_CACHE = Path("output") / ".trestle_score_cache.json"
_OUT_DIR = Path("output")

# Columns SmartSkip's bulk template expects. Their template is the authority —
# if a future upload is rejected, fix this list (and only this list) to match
# the headers on the sample file they hand you. Order is preserved on write.
UPLOAD_COLUMNS = [
    "First Name",
    "Last Name",
    "Mailing Address",
    "Mailing City",
    "Mailing State",
    "Mailing Zip",
    "Property Address",
    "Property City",
    "Property State",
    "Property Zip",
]

# Our rejoin handle. Emitted as an extra column AND written to a sidecar key
# file, because a vendor template is free to strip columns it doesn't know.
KEY_COLUMN = "SiftKey"

_NAME_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v"}

# Particles that belong to the surname they precede: "Van Dyke", "De La Cruz",
# "St. John", "Mc Donald". Without these the surname-is-the-last-token rule
# would upload "Cruz" for a De La Cruz and match the wrong family.
_NAME_PARTICLES = {"van", "von", "de", "del", "dela", "della", "di", "da",
                   "du", "la", "le", "les", "st", "saint", "san", "santa",
                   "mac", "mc", "o", "ter", "ten", "vander", "van der"}

# Signing priority. Lower rank = closer to the estate = more likely a required
# signer. Anything unmatched lands in _REL_OTHER, which the shortlist keeps
# only after real relatives are exhausted — SmartSkip clusters are padded with
# neighbours and associates, and mailing a neighbour is worse than mailing
# nobody.
# Confirmed against a live 1,178-row export (2026-08-24). SmartSkip splits this
# across TWO columns:
#   "Relationship"  = the ROLE — Subject / Relative / Associate
#   "Possible Type" = the actual TIE — Spouse, Child, Parent, Sibling, In-law,
#                     Other Relative, Unknown, Neighbor, Past neighbor, Friend,
#                     Tenant, Coworker, Landlord
# The tie is what we rank on; the role is what we filter on.
REL_PRIORITY: list[tuple[int, tuple[str, ...]]] = [
    (0, ("spouse", "wife", "husband", "widow", "widower")),
    (1, ("child", "son", "daughter", "stepson", "stepdaughter")),
    (2, ("grandson", "granddaughter", "grandchild")),
    (3, ("sibling", "brother", "sister")),
    (4, ("parent", "father", "mother")),
    (5, ("niece", "nephew")),
    (6, ("in-law", "in law")),
    (7, ("cousin", "aunt", "uncle")),
    (8, ("other relative",)),
]
_REL_OTHER = 9

# Roles that are never a contact. "Subject" is the dead owner themselves — they
# come back in their own cluster and mailing them is the exact failure this
# whole pipeline exists to fix. Every "Associate" tie observed in the live
# export was a non-signer (Past neighbor 186, Neighbor 85, Unknown 23,
# Friend 19, Tenant 19, Coworker 10, Landlord 5), so the role is dropped whole.
ROLE_EXCLUDE = ("subject", "associate")

# Belt and braces: if a tie ever shows up under the Relative role that clearly
# isn't family, drop it on the tie as well.
REL_EXCLUDE = ("neighbor", "neighbour", "roommate", "coworker", "co-worker",
               "landlord", "tenant", "friend")


# ── Names ─────────────────────────────────────────────────────────────────

def split_name(full: str) -> tuple[str, str]:
    """'Gilbert Winfred Russell, Jr' -> ('Gilbert', 'Russell').

    The Last field must come out comma-free AND suffix-free. DataSift's
    importer splits on the comma and keeps the trailing token, so a surname of
    'Russell, Jr' lands in the CRM as owner "Gilbert Jr" with the real surname
    gone (Russell 26E001013-350, found 2026-08-23). Same lesson as
    fix_addresses_and_prep._split_app_pr_name — kept local so this module stays
    dependency-light.

    Handles 'LAST, FIRST MIDDLE' too, which is how county GIS and Odyssey
    hand us owner names.
    """
    raw = (full or "").strip()
    if not raw:
        return ("", "")
    # 'SMITH, JOHN A' — comma before a single leading chunk means LAST, FIRST.
    if "," in raw:
        head, _, tail = raw.partition(",")
        tail_tokens = [t for t in tail.split()
                       if t.lower().rstrip(".") not in _NAME_SUFFIX_TOKENS]
        head_tokens = head.split()
        if tail_tokens and len(head_tokens) == 1:
            return (tail_tokens[0].strip(), head_tokens[0].strip())
    parts = raw.replace(",", " ").split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    first = parts[0]
    rest = parts[1:]
    # Strip trailing suffixes: 'Jr' is never anyone's surname.
    while len(rest) > 1 and rest[-1].lower().rstrip(".") in _NAME_SUFFIX_TOKENS:
        rest.pop()
    if len(rest) == 1 and rest[0].lower().rstrip(".") in _NAME_SUFFIX_TOKENS:
        return (first.strip(), "")
    # Surname is the LAST token, not everything after the first — a skip-trace
    # vendor matches on the real surname, so "Betty Louise Walker" must upload
    # as Walker, not "Louise Walker". (This is where we diverge from
    # fix_addresses_and_prep._split_app_pr_name, which keeps multi-token middles
    # because DataSift's PR column wants the fuller name.) Particles ride along.
    surname = [rest[-1]]
    idx = len(rest) - 2
    while idx >= 0 and rest[idx].lower().rstrip(".") in _NAME_PARTICLES:
        surname.insert(0, rest[idx])
        idx -= 1
    return (first.strip(), " ".join(surname).strip())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def make_key(first: str, last: str, zip_code: str) -> str:
    """Rejoin handle: surname + first initial + 5-digit ZIP. Survives a vendor
    reformatting the name (SmartSkip echoes the input name back, but casing and
    middle initials are not guaranteed to round-trip)."""
    z = re.sub(r"\D", "", zip_code or "")[:5]
    return f"{_norm(last)}-{_norm(first)[:1]}-{z}"


# ── Row selection ─────────────────────────────────────────────────────────

def _has_phone(row: dict) -> bool:
    for k, v in row.items():
        if not k:
            continue
        kl = k.lower()
        if "phone" in kl and "tier" not in kl and (v or "").strip():
            return True
    return False


def is_heirs_row(row: dict) -> bool:
    """The 'Heirs of <Decedent>' fallback — no real person to contact.
    Mirrors nc_datasift_export.is_heirs_placeholder."""
    if (row.get("First Name") or "").strip().lower() == "heirs":
        return True
    return (row.get("Personal Representative") or "").strip().lower().startswith("heirs of")


FILTERS = {
    # The flagship DP entry point: owner is dead and we never named a signer.
    "heirs": lambda r: is_heirs_row(r),
    # Ty's second entry point — "if no numbers are coming back for them on the
    # DataSift side, that means a lot of other people have skip-traced these
    # individual records and also not reached them."
    "no-phone": lambda r: not _has_phone(r),
    "all": lambda r: True,
}


def cases_with_a_real_pr(rows: list[dict]) -> set[str]:
    """Case numbers where ANY row names a real Personal Representative.

    A case can be "Heirs of" in week 29 and have a court-named PR by week 31 —
    the Parties API lags the filing. Scanning many weekly files without
    collapsing per case therefore resurrects estates the court has since
    resolved.
    """
    out: set[str] = set()
    for r in rows:
        cn = (r.get("Case No.") or "").strip()
        pr = (r.get("Personal Representative") or "").strip()
        if cn and pr and not pr.lower().startswith("heirs of"):
            out.add(cn)
    return out


def select_rows(rows: list[dict], which: str) -> list[dict]:
    pred = FILTERS[which]
    # THE COURT WINS. On the 2026-08-24 run this filter was missing and 49 of
    # 82 exported subjects already had a court-named PR in a later week —
    # SmartSkip's top pick matched that PR only 9 times, so promoting its guess
    # would have named the wrong person on 40 records. Same failure as the
    # 2026-08-22 rename incident. Never trace an estate the court has answered.
    resolved = cases_with_a_real_pr(rows) if which == "heirs" else set()
    out = []
    for r in rows:
        if not pred(r):
            continue
        if (r.get("Case No.") or "").strip() in resolved:
            continue
        # A subject with no name at all cannot be traced at any price.
        if not ((r.get("Deceased Owner") or "").strip()
                or (r.get("Personal Representative") or "").strip()):
            continue
        out.append(r)
    return out


# ── Export ────────────────────────────────────────────────────────────────

def build_upload_row(row: dict, subject: str = "deceased") -> dict | None:
    """One FTM row -> one SmartSkip upload row, or None if untraceable.

    subject="deceased" anchors the deceased owner to the PROPERTY address
    (the cluster-returning shape). subject="pr" traces the court-named PR at
    their OWN mailing address — narrower, use only when you specifically want
    that person's numbers.
    """
    if subject == "pr":
        if is_heirs_row(row):
            return None  # "Heirs of X" is not a person
        name = (row.get("Personal Representative") or "").strip()
        addr = (row.get("Mailing Address") or "").strip()
        city = (row.get("Mailing City") or "").strip()
        state = (row.get("Mailing State") or "NC").strip()
        zp = (row.get("Mailing Zip") or "").strip()
    else:
        name = (row.get("Deceased Owner") or "").strip()
        addr = (row.get("Property Address") or "").strip()
        city = (row.get("Property City") or "").strip()
        state = (row.get("Property State") or "NC").strip()
        zp = (row.get("Property Zip") or "").strip()

    first, last = split_name(name)
    if not last or not (addr and zp):
        return None  # no surname or no address anchor -> guaranteed miss

    return {
        "First Name": first,
        "Last Name": last,
        "Mailing Address": addr,
        "Mailing City": city,
        "Mailing State": state,
        "Mailing Zip": zp,
        "Property Address": (row.get("Property Address") or "").strip(),
        "Property City": (row.get("Property City") or "").strip(),
        "Property State": (row.get("Property State") or "NC").strip(),
        "Property Zip": (row.get("Property Zip") or "").strip(),
        KEY_COLUMN: make_key(first, last, zp),
    }


def build_upload_csv(rows: list[dict], out_path: Path,
                     subject: str = "deceased") -> tuple[int, int, Path]:
    """Write the SmartSkip bulk upload file + a sidecar key map.

    Returns (written, skipped, keymap_path). Deduped on the rejoin key — the
    same decedent appearing on two parcels is one $0.15 hit, not two.
    """
    seen: set[str] = set()
    payload: list[dict] = []
    keymap: list[dict] = []
    skipped = 0
    for r in rows:
        up = build_upload_row(r, subject)
        if up is None:
            skipped += 1
            continue
        key = up[KEY_COLUMN]
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        payload.append(up)
        keymap.append({
            KEY_COLUMN: key,
            "County": (r.get("County") or "").strip(),
            "Case No.": (r.get("Case No.") or "").strip(),
            "Parcel ID": (r.get("Parcel ID") or "").strip(),
            "Deceased Owner": (r.get("Deceased Owner") or "").strip(),
            "Property Address": (r.get("Property Address") or "").strip(),
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = UPLOAD_COLUMNS + [KEY_COLUMN]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(payload)

    keymap_cols = [KEY_COLUMN, "County", "Case No.", "Parcel ID",
                   "Deceased Owner", "Property Address"]
    keymap_path = out_path.with_name(out_path.stem + "_keymap.csv")
    with keymap_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keymap_cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(keymap)
    return len(payload), skipped, keymap_path


# ── Ingest ────────────────────────────────────────────────────────────────

@dataclass
class Person:
    name: str = ""
    relationship: str = ""
    age: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    role: str = ""            # SmartSkip "Relationship": Subject/Relative/Associate
    deceased: bool = False    # SmartSkip "Deceased" == "true"
    rank: int = _REL_OTHER
    scored: list[dict] = field(default_factory=list)   # filled by score_people


@dataclass
class Cluster:
    key: str = ""
    subject_name: str = ""
    subject_address: str = ""
    people: list[Person] = field(default_factory=list)


def _hdr_find(headers: list[str], *needles: str) -> str | None:
    """First header containing ALL needles (case/space-insensitive)."""
    for h in headers:
        if not h:
            continue
        n = _norm(h)
        if all(_norm(x) in n for x in needles):
            return h
    return None


def _hdr_all(headers: list[str], *needles: str) -> list[str]:
    return [h for h in headers
            if h and all(_norm(x) in _norm(h) for x in needles)]


def _phones_from(row: dict, headers: list[str]) -> list[str]:
    """Every phone-ish column, deduped on digits, CONNECTED numbers first.

    SmartSkip ships each number as a trio: "Phone N number", "Phone N type",
    "Phone N connected". Only ~10% carry the connected flag (334 of 3,472 in
    the live export), and a connected number is the single best predictor of
    reaching someone — so it leads, before Trestle has scored anything.
    """
    found: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for h in headers:
        if not h:
            continue
        n = _norm(h)
        if "phone" not in n and "mobile" not in n and "landline" not in n:
            continue
        # The sibling metadata columns are not numbers.
        if ("type" in n or "score" in n or "dnc" in n or "count" in n
                or "connected" in n):
            continue
        digits = re.sub(r"\D", "", (row.get(h) or ""))
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10 or digits in seen:
            continue
        seen.add(digits)
        # "Phone 3 number" -> "Phone 3 connected"
        conn_h = next((c for c in headers
                       if c and _norm(c) == n.replace("number", "") + "connected"), None)
        found.append((digits, bool((row.get(conn_h) or "").strip()) if conn_h else False))
    found.sort(key=lambda t: 0 if t[1] else 1)   # stable: connected first
    return [d for d, _ in found]


def _emails_from(row: dict, headers: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for h in headers:
        if not h or "email" not in _norm(h):
            continue
        v = (row.get(h) or "").strip()
        if "@" in v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def rank_relationship(rel: str) -> int:
    r = (rel or "").lower()
    for rank, keys in REL_PRIORITY:
        if any(k in r for k in keys):
            return rank
    return _REL_OTHER


def is_excluded(rel: str) -> bool:
    return any(k in (rel or "").lower() for k in REL_EXCLUDE)


def parse_export(path: Path) -> list[Cluster]:
    """Read a SmartSkip campaign-format download into clusters.

    Sniffs the layout because the exact template is the vendor's to change:

      LONG  — one row per associated person, with a Relationship column and an
              input/subject name column tying rows back to the searched person.
              This is the shape Ty's demo shows.
      WIDE  — one row per subject, associates in numbered groups
              ("Relative 1 Name", "Relative 1 Phone 1", ...).

    Anything it can't classify raises with the headers it saw, rather than
    silently returning an empty result.
    """
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h for h in (reader.fieldnames or []) if h]
        rows = list(reader)
    if not rows:
        return []

    # The TIE ("Possible Type": Child / Sibling / In-law ...) is what we rank on.
    # The ROLE ("Relationship": Subject / Relative / Associate) is what we filter
    # on. Older/other layouts put the tie in the relationship column, so fall
    # back to it when there is no separate type column.
    role_col = _hdr_find(headers, "relationship")
    tie_col = (_hdr_find(headers, "possible", "type") or _hdr_find(headers, "relative", "type")
               or role_col or _hdr_find(headers, "relation"))
    if tie_col == role_col:
        role_col = None          # one column can't be both
    rel_col = tie_col
    wide_groups = _hdr_all(headers, "relative", "name") + _hdr_all(headers, "associate", "name")

    # WIDE wins when there are numbered groups, because a wide file ALSO has
    # per-group relationship columns ("Relative 1 Relationship") and a plain
    # relationship check would misread it as long — collapsing every group into
    # one person holding everybody's phones.
    if len(wide_groups) >= 2:
        return _parse_wide(rows, headers, wide_groups)
    if rel_col:
        return _parse_long(rows, headers, rel_col, role_col)
    if wide_groups:
        return _parse_wide(rows, headers, wide_groups)
    raise ValueError(
        "Cannot classify this SmartSkip export — no relationship column and no "
        "'Relative N Name' groups.\nHeaders seen: " + ", ".join(headers) +
        "\nIf this is the right file, add its layout to parse_export().")


def _subject_of(row: dict, headers: list[str]) -> tuple[str, str, str]:
    """(key, subject_name, subject_address) for a row, using our SiftKey when
    it survived the round trip and falling back to the echoed input name."""
    key = (row.get(KEY_COLUMN) or "").strip()
    name_col = (_hdr_find(headers, "input", "name") or _hdr_find(headers, "search", "name")
                or _hdr_find(headers, "subject", "name") or _hdr_find(headers, "owner", "name"))
    first_col = _hdr_find(headers, "input", "first") or _hdr_find(headers, "search", "first")
    last_col = _hdr_find(headers, "input", "last") or _hdr_find(headers, "search", "last")
    if name_col:
        subject = (row.get(name_col) or "").strip()
    elif first_col or last_col:
        subject = " ".join(p for p in (
            (row.get(first_col) or "").strip() if first_col else "",
            (row.get(last_col) or "").strip() if last_col else "") if p)
    else:
        subject = ""
    addr_col = (_hdr_find(headers, "input", "address") or _hdr_find(headers, "search", "address")
                or _hdr_find(headers, "property", "address"))
    zip_col = (_hdr_find(headers, "input", "zip") or _hdr_find(headers, "property", "zip")
               or _hdr_find(headers, "mailing", "zip"))
    addr = (row.get(addr_col) or "").strip() if addr_col else ""
    if not key:
        f, l = split_name(subject)
        key = make_key(f, l, (row.get(zip_col) or "") if zip_col else "")
    return key, subject, addr


def _person_name(row: dict, headers: list[str]) -> str:
    """The found person's name. In the live export there is no single full-name
    column — the person is in plain "First Name" / "Last Name", while
    "Input Name" holds the SUBJECT we searched for. Mixing those up would put
    the dead owner's name on every heir, so Input/Search columns are excluded
    explicitly rather than by luck of header order."""
    def usable(*needles):
        h = _hdr_find(headers, *needles)
        if h and ("input" in _norm(h) or "search" in _norm(h) or "subject" in _norm(h)):
            return None
        return h

    full = usable("full", "name") or usable("relative", "name") or usable("associate", "name")
    if full and (row.get(full) or "").strip():
        return (row.get(full) or "").strip()
    fc, lc = usable("first", "name"), usable("last", "name")
    parts = [(row.get(c) or "").strip() for c in (fc, lc) if c]
    name = " ".join(p for p in parts if p)
    if name:
        return name
    generic = usable("name")
    return (row.get(generic) or "").strip() if generic else ""


def _is_true(v: str) -> bool:
    return (v or "").strip().lower() in ("true", "yes", "1", "y")


def _person_from_row(row: dict, headers: list[str], rel: str,
                     role_col: str | None = None) -> Person:
    # Prefer the plain mailing address over a pre-joined "... Full" variant,
    # which duplicates the city/state/zip we already carry in their own columns.
    addr_col = next((h for h in headers
                     if h and _norm(h) == "mailingaddress"), None)         or _hdr_find(headers, "mailing", "address") or _hdr_find(headers, "address")
    age_col = _hdr_find(headers, "age")
    city_col = _hdr_find(headers, "city")
    state_col = _hdr_find(headers, "state")
    zip_col = _hdr_find(headers, "zip")
    dec_col = _hdr_find(headers, "deceased")
    return Person(
        name=_person_name(row, headers),
        relationship=rel,
        role=(row.get(role_col) or "").strip() if role_col else "",
        deceased=_is_true(row.get(dec_col) or "") if dec_col else False,
        age=(row.get(age_col) or "").strip() if age_col else "",
        address=(row.get(addr_col) or "").strip() if addr_col else "",
        city=(row.get(city_col) or "").strip() if city_col else "",
        state=(row.get(state_col) or "").strip() if state_col else "",
        zip=(row.get(zip_col) or "").strip() if zip_col else "",
        phones=_phones_from(row, headers),
        emails=_emails_from(row, headers),
        rank=rank_relationship(rel),
    )


def _parse_long(rows: list[dict], headers: list[str], rel_col: str,
                role_col: str | None = None) -> list[Cluster]:
    clusters: dict[str, Cluster] = {}
    for row in rows:
        key, subject, addr = _subject_of(row, headers)
        if not key:
            continue
        c = clusters.setdefault(key, Cluster(key=key, subject_name=subject,
                                             subject_address=addr))
        if not c.subject_name and subject:
            c.subject_name = subject
        if not c.subject_address and addr:
            c.subject_address = addr
        rel = (row.get(rel_col) or "").strip()
        p = _person_from_row(row, headers, rel, role_col)
        if p.name or p.phones:
            c.people.append(p)
    return list(clusters.values())


def _parse_wide(rows: list[dict], headers: list[str],
                name_cols: list[str]) -> list[Cluster]:
    """One row per subject; associates in numbered groups. The group prefix is
    everything before 'name' ('Relative 1 Name' -> 'Relative 1 Phone N')."""
    clusters = []
    for row in rows:
        key, subject, addr = _subject_of(row, headers)
        c = Cluster(key=key, subject_name=subject, subject_address=addr)
        for ncol in name_cols:
            nm = (row.get(ncol) or "").strip()
            if not nm:
                continue
            prefix = _norm(ncol).replace("name", "")
            grp = [h for h in headers if _norm(h).startswith(prefix)] if prefix else []
            rel_col = _hdr_find(grp, "relationship") or _hdr_find(grp, "relation")
            rel = (row.get(rel_col) or "").strip() if rel_col else ""
            sub = {h: row.get(h) for h in grp}
            age_col = _hdr_find(grp, "age")
            addr_col = _hdr_find(grp, "address")
            city_col = _hdr_find(grp, "city")
            state_col = _hdr_find(grp, "state")
            zip_col = _hdr_find(grp, "zip")
            c.people.append(Person(
                name=nm, relationship=rel,
                age=(row.get(age_col) or "").strip() if age_col else "",
                address=(row.get(addr_col) or "").strip() if addr_col else "",
                city=(row.get(city_col) or "").strip() if city_col else "",
                state=(row.get(state_col) or "").strip() if state_col else "",
                zip=(row.get(zip_col) or "").strip() if zip_col else "",
                phones=_phones_from(sub, grp),
                emails=_emails_from(sub, grp),
                rank=rank_relationship(rel),
            ))
        if c.people:
            clusters.append(c)
    return clusters


# ── Shortlist (41 -> 3) ───────────────────────────────────────────────────

def shortlist(cluster: Cluster, max_people: int = 5) -> list[Person]:
    """Rank a cluster down to the people who plausibly have to sign.

    Rules, in order:
      * drop the Subject row — that IS the deceased owner, returned inside their
        own cluster; mailing them is the exact failure this pipeline exists to fix;
      * drop anyone SmartSkip flags Deceased;
      * drop the whole Associate role (neighbours, past neighbours, friends,
        tenants, coworkers, landlords) — they never sign, and mailing them is
        worse than mailing nobody;
      * drop anyone with no name;
      * prefer closer relationships (spouse > child > grandchild > sibling ...);
      * within a rank, prefer people who actually have a phone, then a mailing
        address — an heir we can't reach is not a lead;
      * keep at most max_people.

    Unlabelled people (rank _REL_OTHER) survive only if ranked relatives don't
    fill the quota. SmartSkip returns relationship guesses, not court findings,
    so this is a marketing shortlist — the deed chain still decides who signs.
    """
    live = [p for p in cluster.people
            if p.name
            and not p.deceased                       # never call or mail the dead
            and (p.role or "").strip().lower() not in ROLE_EXCLUDE
            and not is_excluded(p.relationship)]
    live.sort(key=lambda p: (p.rank, 0 if p.phones else 1,
                             0 if p.address else 1, p.name.lower()))
    return live[:max_people]


# ── Trestle scoring ───────────────────────────────────────────────────────

def _load_trestle_cache() -> dict:
    try:
        return json.loads(_TRESTLE_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt cache is just empty
        return {}


def _save_trestle_cache(cache: dict) -> None:
    try:
        _TRESTLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TRESTLE_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("could not persist Trestle cache: %s", e)


def count_new_phones(people: list[Person]) -> int:
    """Phones not already in the Trestle cache — the only ones that cost money."""
    cache = _load_trestle_cache()
    return len({ph for p in people for ph in p.phones if ph not in cache})


def score_people(people: list[Person], api_key: str | None = None,
                 keep_tiers: tuple[str, ...] = ("Dial First", "Dial Second"),
                 max_spend: float = 5.00) -> tuple[int, int, float]:
    """Trestle-score every phone on `people` and keep only `keep_tiers`.

    Cached numbers are free and always used. Only uncached numbers are billed,
    and billing stops at max_spend — same discipline as the Enformion cap.
    Writes results onto each Person.scored and prunes Person.phones down to the
    kept tiers, so a 41-person cluster cannot push 100 unscored numbers into a
    record that caps around 30.

    A number we could not score is KEPT, not dropped — an unscored phone is
    unknown, not bad, and silently discarding it would lose real contacts.

    Returns (scored, dropped, spent).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import phone_validator  # noqa: E402 — local module, path set above

    api_key = api_key or os.environ.get("TRESTLE_API_KEY", "")
    cache = _load_trestle_cache()
    spent = 0.0
    scored = dropped = 0
    dirty = False
    capped = False

    for p in people:
        kept: list[str] = []
        for digits in p.phones:
            rec = cache.get(digits)
            if rec is None:
                if not api_key:
                    kept.append(digits)      # unscorable, don't silently drop
                    continue
                if spent + TRESTLE_PER_PHONE > max_spend:
                    if not capped:
                        logger.warning("Trestle spend cap $%.2f reached - "
                                       "remaining numbers left unscored",
                                       max_spend)
                        capped = True
                    kept.append(digits)
                    continue
                try:
                    rec = phone_validator.call_trestle(digits, api_key)
                except Exception as e:  # noqa: BLE001 — one bad number is not fatal
                    logger.warning("Trestle failed on %s: %s", digits, e)
                    kept.append(digits)
                    continue
                spent += TRESTLE_PER_PHONE
                if rec and not rec.get("assigned_tag"):
                    try:
                        rec["assigned_tag"] = phone_validator.assign_tier(
                            int(rec.get("activity_score") or 0),
                            phone_validator.DEFAULT_TIERS)
                    except Exception:  # noqa: BLE001
                        rec["assigned_tag"] = ""
                if rec:
                    cache[digits] = rec
                    dirty = True
            tag = (rec or {}).get("assigned_tag") or ""
            p.scored.append({"phone": digits, "tier": tag,
                             "score": (rec or {}).get("activity_score"),
                             "line_type": (rec or {}).get("line_type")})
            scored += 1
            if tag in keep_tiers:
                kept.append(digits)
            else:
                dropped += 1
        p.phones = kept

    if dirty:
        _save_trestle_cache(cache)
    return scored, dropped, spent


# ── Review artifact ───────────────────────────────────────────────────────

REVIEW_COLUMNS = ["SiftKey", "County", "Case No.", "Deceased Owner",
                  "Property Address", "Heir Name", "Relationship", "Age",
                  "At Property", "Heir Mailing Address", "Heir City",
                  "Heir State", "Heir Zip",
                  "Phone 1", "Phone 1 Tier", "Phone 2", "Phone 2 Tier",
                  "Email", "Source"]


def _addr_key(a: str) -> str:
    return "".join(ch for ch in (a or "").lower() if ch.isalnum())


def write_review_csv(clusters: list[Cluster], keymap: dict[str, dict],
                     out_path: Path, max_people: int = 5) -> int:
    """One row per shortlisted heir, joined back to County / Case No.

    This is a REVIEW file, not an upload. Nothing here reaches DataSift until
    you say so — the standing rule is that uploads are always asked for first.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for c in clusters:
            meta = keymap.get(c.key, {})
            prop_key = _addr_key(meta.get("Property Address") or c.subject_address)
            for p in shortlist(c, max_people):
                tiers = {s["phone"]: s.get("tier") or "" for s in p.scored}
                ph = p.phones[:2] + ["", ""]
                w.writerow({
                    "SiftKey": c.key,
                    "County": meta.get("County", ""),
                    "Case No.": meta.get("Case No.", ""),
                    "Deceased Owner": meta.get("Deceased Owner") or c.subject_name,
                    "Property Address": meta.get("Property Address") or c.subject_address,
                    "Heir Name": p.name,
                    "Relationship": p.relationship,
                    "Age": p.age,
                    # An heir whose own mailing address IS the subject property
                    # is living in it. That drives the occupied-hold rule, and
                    # it is also the tell for an unlabelled surviving spouse
                    # (SmartSkip typed a 95-year-old at the property "Unknown").
                    "At Property": ("YES" if prop_key and _addr_key(p.address) == prop_key
                                    else ""),
                    "Heir Mailing Address": p.address,
                    "Heir City": p.city,
                    "Heir State": p.state,
                    "Heir Zip": p.zip,
                    "Phone 1": ph[0], "Phone 1 Tier": tiers.get(ph[0], ""),
                    "Phone 2": ph[1], "Phone 2 Tier": tiers.get(ph[1], ""),
                    "Email": p.emails[0] if p.emails else "",
                    "Source": "smartskip",
                })
                n += 1
    return n


def load_keymap(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {(r.get(KEY_COLUMN) or "").strip(): r for r in csv.DictReader(f)}


# ── CLI ───────────────────────────────────────────────────────────────────

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def cmd_export(args) -> int:
    # Multiple inputs are the normal case for a backlog sweep: the same estate
    # appears in every weekly file until it's archived, and dedup on the rejoin
    # key means we pay $0.15 for that decedent ONCE, not once per week.
    paths = [Path(p) for p in args.input]
    rows: list[dict] = []
    for src in paths:
        with src.open(newline="", encoding="utf-8-sig") as f:
            rows.extend(csv.DictReader(f))
    targets = select_rows(rows, args.filter)
    label = paths[0].name if len(paths) == 1 else f"{len(paths)} file(s)"
    logger.info("%s: %d row(s), %d match filter %r",
                label, len(rows), len(targets), args.filter)

    if args.dry_run:
        # Count what would actually be uploaded, post-dedup, without writing.
        seen: set[str] = set()
        ok = skip = 0
        for r in targets:
            up = build_upload_row(r, args.subject)
            if up is None or up[KEY_COLUMN] in seen:
                skip += 1
                continue
            seen.add(up[KEY_COLUMN])
            ok += 1
        logger.info("DRY RUN: would upload %d unique subject(s), skip %d "
                    "(no surname / no address anchor / duplicate)", ok, skip)
        logger.info("DRY RUN: SmartSkip cost ~$%.2f at $%.2f/row - ZERO spent",
                    ok * COST_PER_ROW, COST_PER_ROW)
        return 0

    out = Path(args.out) if args.out else _OUT_DIR / f"smartskip_upload_{_stamp()}.csv"
    written, skipped, keymap = build_upload_csv(targets, out, args.subject)
    logger.info("wrote %s - %d subject(s), %d skipped", out, written, skipped)
    logger.info("keymap: %s (keep it - ingest rejoins County/Case No. from it)",
                keymap)
    logger.info("estimated SmartSkip cost: $%.2f at $%.2f/row",
                written * COST_PER_ROW, COST_PER_ROW)
    logger.info("NEXT: upload %s at smartskip.io, download the campaign-format "
                "result, then run: python src/smartskip_io.py ingest <download> "
                "--keymap %s", out.name, keymap.name)
    return 0


def cmd_ingest(args) -> int:
    src = Path(args.input)
    clusters = parse_export(src)
    people_total = sum(len(c.people) for c in clusters)
    logger.info("%s: %d cluster(s), %d associated person(s) returned",
                src.name, len(clusters), people_total)
    if not clusters:
        logger.warning("nothing parsed - check the export format")
        return 1

    short = [p for c in clusters for p in shortlist(c, args.max_people)]
    logger.info("shortlist: %d -> %d person(s) after signer gating "
                "(neighbours/associates dropped, closest relatives first)",
                people_total, len(short))

    if args.no_trestle:
        logger.info("--no-trestle: phones left unscored, all kept")
    else:
        new = count_new_phones(short)
        logger.info("phones: %d new (billable at $%.3f = $%.2f), rest cached free",
                    new, TRESTLE_PER_PHONE, new * TRESTLE_PER_PHONE)
        if args.dry_run:
            logger.info("DRY RUN: no Trestle calls, no files written")
            return 0
        keep = tuple(t.strip() for t in args.keep_tiers.split(",") if t.strip())
        scored, dropped, spent = score_people(short, keep_tiers=keep,
                                              max_spend=args.max_spend)
        logger.info("Trestle: scored %d phone(s), dropped %d below %s, "
                    "spent $%.2f", scored, dropped, "/".join(keep), spent)

    if args.dry_run:
        logger.info("DRY RUN: no files written")
        return 0

    keymap_path = (Path(args.keymap) if args.keymap
                   else src.with_name(src.stem + "_keymap.csv"))
    keymap = load_keymap(keymap_path)
    if not keymap:
        logger.warning("no keymap at %s - review file will have blank "
                       "County/Case No.", keymap_path)
    out = Path(args.out) if args.out else _OUT_DIR / f"smartskip_heirs_{_stamp()}.csv"
    n = write_review_csv(clusters, keymap, out, args.max_people)
    logger.info("wrote %s - %d heir row(s) for review", out, n)
    logger.info("REVIEW THIS FILE before anything is pushed. Nothing was "
                "uploaded to DataSift.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SmartSkip CSV round-trip for deep prospecting.")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="build the SmartSkip bulk upload CSV")
    e.add_argument("input", nargs="+",
                   help="FTM / datasift CSV(s) to pull targets from; multiple "
                        "files are merged and deduped on the rejoin key")
    e.add_argument("--filter", choices=sorted(FILTERS), default="heirs")
    e.add_argument("--subject", choices=("deceased", "pr"), default="deceased",
                   help="who to trace (default: the deceased owner at the "
                        "property address - the cluster-returning shape)")
    e.add_argument("--out")
    e.add_argument("--dry-run", action="store_true",
                   help="count + cost only, writes nothing")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("ingest", help="parse a SmartSkip campaign-format download")
    i.add_argument("input", help="the CSV downloaded from SmartSkip")
    i.add_argument("--keymap", help="sidecar written by export (default: "
                                    "<input>_keymap.csv)")
    i.add_argument("--max-people", type=int, default=5,
                   help="cap per subject after gating (default 5)")
    i.add_argument("--keep-tiers", default="Dial First,Dial Second",
                   help="Trestle tiers to keep (default: the top two)")
    i.add_argument("--max-spend", type=float, default=5.00,
                   help="hard Trestle ceiling for this run (default $5)")
    i.add_argument("--no-trestle", action="store_true",
                   help="skip scoring entirely; keep every phone")
    i.add_argument("--out")
    i.add_argument("--dry-run", action="store_true")
    i.set_defaults(func=cmd_ingest)

    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
