"""Turn the raw per-term harvest into one deduped lead table.

Facebook's in-group search is loose - a "plumber" query returns roofing and HVAC
posts too - so the same post lands in many term files. Dedupe across ALL files
before counting anything, and classify the trade from the post TEXT, never from
which search surfaced it.

    python fb_harvest_normalize.py

Writes output/fb_harvest_leads.csv (contactable leads: a phone or an email)
and prints the counts worth knowing before verification starts.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "output" / "fb_harvest"
OUT = ROOT / "output" / "fb_harvest_leads.csv"

# Trade -> the words that actually appear in a post about it. Order matters:
# first match wins, so put the specific ones before the generic ones.
TRADES = [
    ("Septic", r"\bseptic|drain ?field|leach ?field"),
    ("Termite / WDO", r"\btermite|wdo\b|wood[- ]destroying"),
    ("Excavation / water line", r"\bexcavat|grading|water ?line|trench|bore\b|underground utilit"),
    ("Survey", r"\bsurvey(or|ing)?\b|\bplat\b"),
    ("Foundation / waterproofing", r"\bfoundation|crawl ?space|waterproof|encapsulat|pier|footing"),
    ("Roofing", r"\broof"),
    ("HVAC", r"\bhvac\b|\bac unit|air ?condition|furnace|heat ?pump|mini ?split"),
    ("Plumbing", r"\bplumb|water heater|repipe|sewer line"),
    ("Electrical", r"\belectric|\bpanel\b|rewire|breaker"),
    ("Countertops / cabinets", r"\bcountertop|granite|quartz|\bcabinet"),
    ("Flooring", r"\bfloor|\blvp\b|hardwood|carpet|tile\b"),
    ("Drywall / paint", r"\bdrywall|sheetrock|\bpaint"),
    ("Carpentry / deck", r"\bcarpent|\bdeck\b|framing|trim work"),
    ("Dumpster / cleanout", r"\bdumpster|junk removal|clean ?out|haul ?away"),
    ("Landscaping / tree", r"\blandscap|\btree\b|stump|lawn"),
    ("Pest control", r"\bpest control|exterminat|\bmice\b|roach"),
    ("Handyman", r"\bhandy ?man"),
    ("General contractor", r"\bgeneral contractor|\bgc\b|\bcontractor"),
]

# Non-trades that advertise in trade vocabulary and pollute the directory. Match on
# what the POSTER does, not on the words appearing: "ATTENTION Contractors, Property
# Managers and Realtors" is a junk-removal ad AIMED at realtors, not a realtor, so
# these patterns are first-person/self-describing on purpose. Flagged, never deleted -
# the verification pass makes the call.
NON_TRADE = [
    ("lender", r"featured lender|hard money|dscr|bridge loan|100% financing|"
               r"\bltv\b|private money|financial group|we (fund|lend)|apply today"),
    ("wholesaler", r"price discount!|dm me for (more )?details|comps, pictures|"
                   r"build-ready parcel|prime land opportunity|under contract|assignment fee"),
    ("agent/insurance", r"i'?m a (commercial )?(insurance broker|realtor|agent)|"
                        r"commercial real estate policy|listing agent"),
]

PHONE = re.compile(r"(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Someone ASKING for a referral is a thread to open, not a provider to call.
ASKING = re.compile(
    r"\b(looking for|anyone (know|have|use)|recommend(ation)?s?\?|"
    r"who (do you|does everyone|can|should)|need a|any(one)? good|suggestions)\b", re.I)

# ...but an AD opens with the same words as a rhetorical hook: "Looking for an
# electrician? Give us a call." Treating that as a request buried JP Construction &
# Design - the one group-sourced vendor with an active NCLBGC licence able to hold a
# $40k+ job - under "do not call". First-person offering language settles it, and it
# must be checked BEFORE the asking test.
RECRUITING = re.compile(
    r"\b(add to our team|to add to our|join (our|the) team|now hiring|we'?re hiring|"
    r"are hiring|looking for (a )?(sub|subs|guys|crew|help|installer|carpenter|"
    r"painter|laborer)s? to|subs? wanted|hiring )\b", re.I)

OFFERING = re.compile(
    r"\b(give (us|me) a call|call us|we (offer|have|do|install|specialize|are here)|"
    r"here to help|our (team|company|crew)|free (estimate|quote)|licen[cs]ed and insured|"
    r"we'?re (available|taking)|open availability|dm me for a (quote|price)|"
    r"i run a|we just|book (us|now))\b", re.I)


def trade_of(text: str) -> str:
    low = text.lower()
    for label, pattern in TRADES:
        if re.search(pattern, low):
            return label
    return "Unclassified"


def main() -> int:
    files = sorted(SRC.glob("*.json"))
    if not files:
        print("No harvest files in", SRC)
        return 1

    posts: dict[str, dict] = {}
    terms_for: dict[str, set] = defaultdict(set)
    raw = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in data.get("posts", []):
            raw += 1
            key = p["text"][:160]
            terms_for[key].add(p.get("term", f.stem))
            if key not in posts or len(p["text"]) > len(posts[key]["text"]):
                posts[key] = p

    rows = []
    for key, p in posts.items():
        text = p["text"]
        phones = sorted({"-".join(m) for m in PHONE.findall(text)})
        emails = sorted(set(EMAIL.findall(text)))
        # Recruitment reads as offering ("our team", "our company") but is neither a
        # vendor to call nor a job to bid: it is a GC staffing up. Says they have
        # volume, says nothing about whether they would take Oren's work - and
        # Lakeland & Co, sourced this way, turned out to hold a REVOKED NCLBGC licence.
        hiring = bool(RECRUITING.search(text))
        offering = bool(OFFERING.search(text)) and not hiring
        asking = bool(ASKING.search(text)) and not offering and not hiring
        rows.append({
            "trade": trade_of(text),
            "posted_by": p.get("author", "")[:60],
            "phones": "; ".join(phones),
            "emails": "; ".join(emails),
            # A "looking for a painter" post often carries the POSTER's own number.
            # Calling it is calling a homeowner who is hiring, not a provider - so the
            # asking test must win even when contact details are present. The value of
            # those posts is their comment thread, not the contact on the post.
            "kind": "RECRUITING - GC staffing up, not a vendor" if hiring else
                    "REQUEST - do not call, value is in comments" if asking else
                    ("PROVIDER lead" if phones or emails else "discussion"),
            "flag": "; ".join(l for l, pat in NON_TRADE if re.search(pat, text, re.I)),
            "comments": p.get("comments", 0),
            "found_via": "; ".join(sorted(terms_for[key])),
            "text": " ".join(text.split())[:600],
        })

    contactable = [r for r in rows if r["phones"] or r["emails"]]
    contactable.sort(key=lambda r: (r["trade"], -r["comments"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(contactable)

    providers = [r for r in contactable if r["kind"] == "PROVIDER lead"]
    clean = [r for r in providers if not r["flag"]]
    # One provider often posts the same ad repeatedly; text-dedupe keeps them all, so
    # count distinct phone numbers to get the real size of the bench.
    distinct = {p for r in clean for p in r["phones"].split("; ") if p}

    print(f"raw post rows across {len(files)} term files : {raw}")
    print(f"unique posts after dedupe                 : {len(posts)}"
          f"   ({raw - len(posts)} were cross-term duplicates)")
    print(f"unique posts carrying a phone or email    : {len(contactable)}")
    print(f"  of those, PROVIDER leads                : {len(providers)}")
    print(f"  flagged possible non-trade              : {len(providers) - len(clean)}")
    print(f"  DISTINCT provider phone numbers         : {len(distinct)}  <- real bench size")
    print(f"high-discussion threads (>=10 comments)   : "
          f"{sum(1 for r in rows if r['comments'] >= 10)}")
    print(f"\nwrote {OUT}\n")
    print("contactable leads by trade:")
    for trade, n in Counter(r["trade"] for r in contactable).most_common():
        print(f"  {trade:<28} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
