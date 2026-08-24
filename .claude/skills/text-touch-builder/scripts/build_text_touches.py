#!/usr/bin/env python3
"""Build four personalized text touches per record from a DataSift CSV export.

Self-contained (Python 3.8+, standard library only). Reads the CSV you exported
from your filter preset, generates Text Touch 1-4 for every record following the
message recipe (see references/message-recipe.md), and writes an import-ready
CSV you upload back into DataSift with the four columns mapped to your
Text Touch custom fields.

Variant selection is seeded by the record's address + owner, so:
- neighboring records get DIFFERENT message sequences (cold-email style rotation)
- re-running on a grown export regenerates IDENTICAL text for existing records

Usage:
  python build_text_touches.py exported_records.csv
  python build_text_touches.py export.csv --out touches.csv --sender Maria
  python build_text_touches.py export.csv --col-street "Street" --col-first "First Name"

Sign-off resolution: the "Assigned To" column when present (first name only),
else --sender. Records with neither are skipped and reported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

MAX_CHARS = 320  # 2 SMS segments; pools aim well under 160

ENTITY_RX = re.compile(
    r"\b(llc|l\.l\.c|inc|corp|trust|trustee|estate|properties|property|holdings|"
    r"investments|ventures|partners|lp|llp|company|bank|assoc|church|city of|county|"
    r"heir|heirs|unknown|occupant|et al)\b",
    re.I,
)

# GIS exports shout; these tokens should stay shouting when we quiet the rest down
KEEP_UPPER = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "US", "SR", "II", "III", "IV",
              "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "IA", "ID",
              "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS",
              "MT", "NC", "ND", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA",
              "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY"}
ORDINAL_RX = re.compile(r"^(\d+)(ST|ND|RD|TH)$", re.I)
COMPASS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}

# {first} owner first name, {addr} street line, {city} city, {sender} caller name.
# Rewrite these in YOUR voice; keep the structure (see references/message-recipe.md).
TOUCH1 = [
    "Hi {first}! I hope your week is going great. My name is {sender}, I was looking at {addr} and was wondering if it's yours? Thanks so much!",
    "Hi {first}, I pray all is well your way! I'm {sender}, and I know this is random, but does {addr} happen to be yours? Do I have the right person?",
    "Hey {first}, I hope you are doing great! I'm not even sure I have the right number, but is {addr} yours? Thank you! {sender}",
    "Hi there! I hope things are going well for you. This is {sender}, hoping to speak with {first} about {addr}. Do I have the right number?",
    "Hi {first}! My name is {sender}. I've been looking at {addr} in {city} and was wondering, does it belong to you by any chance? Have a great day!",
]
TOUCH1_NONAME = [
    "Hi! I hope your week is going great. My name is {sender}, I'm trying to reach the owner of {addr}. Did I get the right number? Thanks so much!",
    "Hi there! This is {sender}. I know this is random, but I'm hoping to reach whoever handles {addr} in {city}. Do I have the right contact?",
]
TOUCH2 = [
    "Hi {first}, I reached out the other day and wasn't sure my text went through. Is {addr} your place? {sender} here.",
    "Hey, sorry to bother you! Did you get my message about {addr}? Just want to make sure I have the right contact. I'm {sender}.",
    "Hi {first}! {sender} again. Sometimes my texts don't go through, so I wanted to try once more. Is {addr} yours?",
    "Hey {first}, just floating my last text back up in case it got buried. Is {addr} your property? Thanks! {sender}",
]
TOUCH2_NONAME = [
    "Hi, {sender} here again. I texted the other day about {addr} and wasn't sure it went through. Is this the right contact for that property?",
    "Hey, sorry to double text! Did my message about {addr} come through? Just making sure I have the right contact. I'm {sender}.",
]
TOUCH3 = [
    "Hi {first}, {sender} again about {addr}. If it's yours, have you ever thought about selling it? No pressure at all, just curious!",
    "Hey {first}! I hope I'm not being a bother. I'm interested in {addr} and would love to ask you a couple quick questions. Would a short call work?",
    "Hi {first}, this is {sender}. I work with homeowners in {city} and I'd love to chat about {addr} for a minute or two. Would you be open to that?",
    "Hey {first}, me again! If you've ever considered an offer on {addr}, I'd love to be the one you talk to first. Can I give you a quick call?",
]
TOUCH3_NONAME = [
    "Hi, {sender} again. If {addr} is one of yours, would you be open to a quick conversation about it? Happy to work around your schedule!",
    "Hey there, this is {sender}. I'm interested in {addr} in {city}. If you handle that property, would a short call sometime work for you?",
]
TOUCH4 = [
    "Hi {first}, I've sent a few texts about {addr} and haven't heard back. Did you decide to keep it instead? Either way, wishing you the best! {sender}",
    "Hey {first}, last one from me, I promise! If selling {addr} is ever on your mind, I'd love to be your first call. Take care! {sender}",
    "Hi {first}, I'll stop bugging you after this! Just wanted to leave my number in case {addr} ever becomes something you'd like to talk about. {sender}",
    "Hey {first}, {sender} here one more time. If I have the wrong number, I'm so sorry! If not, I'd still love to connect about {addr} whenever works for you.",
]
TOUCH4_NONAME = [
    "Hi, {sender} here one last time about {addr}. If there's a better contact for that property, I'd be grateful for a point in the right direction. Thanks!",
    "Hey there, last text from me! If {addr} is ever something you'd consider selling, I'd love to be your first call. All the best! {sender}",
]
POOLS = [(TOUCH1, TOUCH1_NONAME), (TOUCH2, TOUCH2_NONAME),
         (TOUCH3, TOUCH3_NONAME), (TOUCH4, TOUCH4_NONAME)]

# ---------------------------------------------------------------------------
# VACANT / ABSENTEE / FREE-AND-CLEAR pools  (niche: "vacant")
#
# Different job from the default pools. These owners are ABSENTEE, so the
# credible reason you are contacting them is that YOU are near the property and
# they are not. That drive-by hook is the whole opener.
#
# HARD RULE, from the challenge: insinuate, never name the distress. Nothing in
# here may reference the property being vacant, empty, abandoned, neglected,
# run-down, behind on taxes, or owned free and clear. Say what you SAW from the
# street, never what you know from the data.
# ---------------------------------------------------------------------------
VAC_TOUCH1 = [
    "Hi {first}! My name is {sender}. I was over in {city} this week and went past {addr} - is that one yours by any chance? Thanks!",
    "Hi {first}, hope your week is going well. I'm {sender}. I came across {addr} while I was out in {city} and wondered if it belongs to you?",
    "Hey {first}! {sender} here. I know this is out of the blue - I was on your street in {city} and noticed {addr}. Do I have the right owner?",
    "Hi {first}, this is {sender}. I pick up a few places around {city} each year and {addr} caught my eye. Is that yours? Hope I have the right number!",
    "Hi {first}! I'm {sender}, local to the {city} area. I was looking at {addr} and wanted to check I had the right person before I said more. Thanks!",
]
VAC_TOUCH1_NONAME = [
    "Hi! My name is {sender}. I was out in {city} this week and went past {addr} - I'm trying to reach whoever owns it. Did I get the right number?",
    "Hi there, {sender} here. I came across {addr} in {city} and I'm hoping to reach the owner. Do I have the right contact? Thanks!",
]
VAC_TOUCH2 = [
    "Hi {first}, {sender} here - I texted about {addr} the other day and wasn't sure it landed. Is that property yours?",
    "Hey, sorry to double up! Did my note about {addr} come through? Just want to be sure I have the right owner. {sender}",
    "Hi {first}! {sender} again. My texts don't always go through, so trying once more - is {addr} in {city} yours?",
    "Hey {first}, floating my last message back up in case it got buried. Is {addr} your property? Thanks! {sender}",
]
VAC_TOUCH2_NONAME = [
    "Hi, {sender} again. I messaged the other day about {addr} and wasn't sure it went through - is this the right contact for it?",
    "Hey, sorry to text twice! Did my message about {addr} in {city} reach you? Just checking I have the right person. {sender}",
]
VAC_TOUCH3 = [
    "Hi {first}, {sender} again about {addr}. If it is yours, would you ever consider an offer on it? No pressure - just wanted to ask you directly.",
    "Hey {first}! I'm genuinely interested in {addr}. Would you be open to a quick call? I can work around whatever time suits you.",
    "Hi {first}, this is {sender}. I'd take {addr} as-is and handle everything on my end. Worth a two-minute conversation?",
    "Hey {first}, me again - if you'd ever part with {addr}, I'd love to be the first person you talk to. Can I give you a quick call?",
]
VAC_TOUCH3_NONAME = [
    "Hi, {sender} again. If {addr} is one of yours, would you be open to an offer on it? Happy to work around your schedule.",
    "Hey there, {sender} here. I'm interested in {addr} in {city} - if you look after that one, would a short call work?",
]
VAC_TOUCH4 = [
    "Hi {first}, I've sent a few notes about {addr} with no luck. Maybe you're holding onto it - totally fair! Wishing you well. {sender}",
    "Hey {first}, last one from me. If {addr} ever becomes something you'd sell, I'd love to be your first call. Take care! {sender}",
    "Hi {first}, I'll leave you alone after this! Just leaving my number in case {addr} ever comes up down the road. {sender}",
    "Hey {first}, {sender} one more time. If I have the wrong number I'm sorry! If not, I'd still love to talk about {addr} whenever suits you.",
]
VAC_TOUCH4_NONAME = [
    "Hi, {sender} here one last time about {addr}. If someone else looks after that property, a point in the right direction would be a big help. Thanks!",
    "Hey there, last text from me! If {addr} is ever something you'd consider selling, I'd love to be your first call. All the best! {sender}",
]
VACANT_POOLS = [(VAC_TOUCH1, VAC_TOUCH1_NONAME), (VAC_TOUCH2, VAC_TOUCH2_NONAME),
                (VAC_TOUCH3, VAC_TOUCH3_NONAME), (VAC_TOUCH4, VAC_TOUCH4_NONAME)]

# niche name -> pool set. text_touch_api_backfill picks per record.
POOLS_BY_NICHE = {"default": POOLS, "vacant": VACANT_POOLS}

# words that would name the distress - guarded by test_vacant_pools()
_BANNED_RX = re.compile(
    r"\b(vacant|empty|abandon\w*|unoccupied|neglect\w*|run.?down|distress\w*|"
    r"delinquen\w*|foreclos\w*|free and clear|equity|probate|deceased|estate|"
    r"eyesore|boarded|condemn\w*)\b", re.I)


def test_vacant_pools() -> None:
    """Fail loudly if the vacant copy ever names the distress or runs long."""
    for i, (pool, noname) in enumerate(VACANT_POOLS, 1):
        for msg in list(pool) + list(noname):
            bad = _BANNED_RX.search(msg)
            assert not bad, f"touch {i} names the distress ({bad.group(0)!r}): {msg}"
            rendered = msg.format(first="Jonathan", addr="1234 Old Charlotte Rd Sw",
                                  city="Concord", sender="Oren")
            assert len(rendered) <= MAX_CHARS, f"touch {i} too long ({len(rendered)}): {msg}"


# common DataSift export header spellings, first match wins (case-insensitive)
COLUMN_GUESSES = {
    "street": ["property street address", "property street", "street address",
               "property address", "site address", "situs address", "street", "address"],
    "city": ["property city", "city"],
    "state": ["property state", "state"],
    "zip": ["property zip", "property zip code", "zip", "zip code", "postal code"],
    "first": ["owner first name", "first name", "owner 1 first name"],
    "last": ["owner last name", "last name", "owner 1 last name"],
    "owner": ["owner name", "owner full name", "owner"],
    "assigned": ["assigned to", "assignee", "assigned"],
}


def detect(headers: list[str], key: str, override: str) -> str:
    if override:
        for h in headers:
            if h.strip().lower() == override.strip().lower():
                return h
        sys.exit(f"FATAL: column {override!r} not found in the CSV. Headers: {headers}")
    lower = {h.strip().lower(): h for h in headers}
    for guess in COLUMN_GUESSES[key]:
        if guess in lower:
            return lower[guess]
    return ""


def clean_first(raw: str) -> str:
    """Usable first name: drop leading initials ('C Eugene' -> 'Eugene'),
    keep only the first real token; '' when nothing usable ('E A')."""
    for tok in (raw or "").replace(".", " ").split():
        if len(tok) >= 2 and tok.replace("'", "").replace("-", "").isalpha():
            return tok.title()
    return ""


def tidy_place(raw: str) -> str:
    """Quiet a SHOUTED city/street down to something that reads handwritten,
    and repair the ordinals/compass points that upstream title-casing mangles
    ('36Th Ave Dr Ne' -> '36th Ave Dr NE')."""
    s = " ".join((raw or "").split())
    shouted = s.isupper()
    out = []
    for tok in s.split():
        m = ORDINAL_RX.match(tok)
        if m:  # 36TH / 36Th -> 36th
            out.append(m.group(1) + m.group(2).lower())
        elif tok.upper() in COMPASS:  # Ne / ne -> NE
            out.append(tok.upper())
        elif not shouted:  # mixed case: only the two repairs above
            out.append(tok)
        elif tok in KEEP_UPPER:
            out.append(tok)
        elif tok.startswith("MC") and len(tok) > 2:
            out.append("Mc" + tok[2:].title())
        else:
            out.append(tok.title())
    return " ".join(out)


def tidy_addr(raw: str) -> str:
    """Message-safe address. Vacant parcels carry a '0 <street>' bookkeeping
    prefix (or no house number at all), which reads as a typo to the owner --
    phrase those as 'the lot on <street>' instead."""
    s = tidy_place(raw)
    stripped = re.sub(r"^0+\s+", "", s)
    if stripped != s or not re.match(r"^\d", s):
        return "the lot on " + stripped
    return s


def render(seed_text: str, first: str, addr: str, city: str, sender: str,
           no_name: bool, pools: list | None = None) -> list[str]:
    """Render the 4 touches. `pools` defaults to the general-purpose set;
    pass VACANT_POOLS (or POOLS_BY_NICHE['vacant']) for the vacant stack."""
    s = int(hashlib.md5(seed_text.encode()).hexdigest(), 16)
    out = []
    for i, (pool, noname_pool) in enumerate(pools or POOLS):
        p = noname_pool if (no_name or not first) else pool
        msg = p[(s // (7 ** i)) % len(p)].format(
            first=first, addr=addr, city=city, sender=sender)
        out.append(re.sub(r"\s+", " ", msg).strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv_in", help="CSV exported from your DataSift filter preset")
    ap.add_argument("--out", default="text_touches_import.csv")
    ap.add_argument("--sender", default="", help="fallback signer when no Assigned To column/value")
    ap.add_argument("--show", type=int, default=3, help="sample records to print")
    for k in ("street", "city", "first", "last", "owner", "assigned"):
        ap.add_argument(f"--col-{k}", default="", help=f"exact header of the {k} column")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv_in, encoding="utf-8-sig")))
    if not rows:
        sys.exit("FATAL: no rows in the input CSV")
    headers = list(rows[0].keys())

    col = {k: detect(headers, k, getattr(a, f"col_{k}", ""))
           for k in COLUMN_GUESSES}
    if not col["street"]:
        sys.exit(f"FATAL: could not find a street address column. Headers: {headers}\n"
                 "Pass it explicitly with --col-street \"Your Header\"")
    print("column mapping:", {k: v for k, v in col.items() if v})

    out_rows, skipped = [], []
    for r in rows:
        street = (r.get(col["street"]) or "").strip()
        if not street:
            skipped.append(("(blank street)", "no street address"))
            continue
        city = (r.get(col["city"]) or "").strip() if col["city"] else ""
        raw_first = (r.get(col["first"]) or "") if col["first"] else ""
        if not raw_first and col["owner"]:
            raw_first = (r.get(col["owner"]) or "").split(" ")[0]
        owner_full = " ".join(x.strip() for x in [
            r.get(col["first"], "") if col["first"] else "",
            r.get(col["last"], "") if col["last"] else ""] if x.strip()) \
            or (r.get(col["owner"], "") if col["owner"] else "")
        no_name = bool(ENTITY_RX.search(owner_full or raw_first))
        first = "" if no_name else clean_first(raw_first)

        sender = ""
        if col["assigned"]:
            sender = clean_first(r.get(col["assigned"]) or "")
        if not sender:
            sender = a.sender.strip().title()
        if not sender:
            skipped.append((street, "no Assigned To value and no --sender"))
            continue

        touches = render(f"{street}|{owner_full}".lower(), first, tidy_addr(street),
                         tidy_place(city) or "the area", sender, no_name)
        if any(len(t) > MAX_CHARS for t in touches):
            skipped.append((street, f"a touch exceeded {MAX_CHARS} chars"))
            continue
        out = {col["street"]: street}
        for k in ("city", "state", "zip"):
            if col[k]:
                out[col[k]] = (r.get(col[k]) or "").strip()
        for i, t in enumerate(touches, 1):
            out[f"Text Touch {i}"] = t
        out["_sender"] = sender
        out_rows.append(out)

    if not out_rows:
        sys.exit("FATAL: nothing renderable. Check the column mapping.")

    fields = [c for c in (col["street"], col["city"], col["state"], col["zip"]) if c]
    fields += [f"Text Touch {i}" for i in range(1, 5)]
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    senders: dict[str, int] = {}
    for r in out_rows:
        senders[r["_sender"]] = senders.get(r["_sender"], 0) + 1
    two_seg = sum(1 for r in out_rows for i in range(1, 5)
                  if len(r[f"Text Touch {i}"]) > 160)
    print(f"\nrendered {len(out_rows)} records -> {a.out}")
    print(f"skipped {len(skipped)}", f"e.g. {skipped[:5]}" if skipped else "")
    if two_seg:
        print(f"note: {two_seg} of {len(out_rows) * 4} messages run past 160 chars "
              "(2 SMS segments -- delivers fine, just costs double)")
    print(f"signer distribution: {senders}")
    print("\nsamples:")
    for r in out_rows[: a.show]:
        print(f"\n  {r[col['street']]}  (signer: {r['_sender']})")
        for i in range(1, 5):
            t = r[f"Text Touch {i}"]
            print(f"    T{i} ({len(t)}c): {t}")
    print("\nNext: upload this CSV via Add Data into the SAME list (upserts by address),"
          "\nand drag Text Touch 1-4 onto your custom fields in the mapping step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
