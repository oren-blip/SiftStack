"""Harvest PRIVATE MONEY LENDERS out of Facebook groups.

Ty, 5DDF Day 5 [02:40:02]: search "private money real estate" -> Groups tab, join
them, then run the same Facebook scraping workflow. His caveat is the whole design
of this file: *"You're gonna get a lot of hard money lenders and companies reaching
out to you, but I have heard of people getting really good success finding
individuals."*  So an INDIVIDUAL lending their own money is the target, and a
loan shop is a separate tab - kept, not deleted, because the classifier is a
guess and Oren should see what it set aside.

Capture is fb_buyer_harvest.py's (search -> See-more -> comment threads); only the
classification is new. Three things make someone a candidate:
  lender_offer     - first person offering their own capital        (the person)
  lender_rollcall  - "any private lenders here? drop your info"     (commenters)
  capital_request  - an investor asking for money                   (commenters)

    python fb_lender_harvest.py --groups=<gid,gid> probe
    python fb_lender_harvest.py --groups=<gid,gid> harvest
    python fb_lender_harvest.py --groups=<gid,gid> threads --min-comments 4
    python fb_lender_harvest.py --groups=<gid,gid> build

Flags go BEFORE the subcommand. --groups is COMMA-separated here (the buyer
script's nargs="+" swallowed the subcommand and cost two silent no-op runs).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

import fb_buyer_harvest as fb

ROOT = Path(__file__).resolve().parent
OUTDIR = ROOT / "output" / "fb_lenders"
TODAY = datetime.now().strftime("%Y-%m-%d")

# Filled from output/fb_lenders/lender_groups_<date>.json at runtime; --groups wins.
GROUP_NAMES: dict[str, str] = {}

# Search terms, highest-yield first (if Facebook throttles mid-run the best files
# already exist). Half of these target the lender directly, half target the posts
# whose COMMENTS are full of lenders.
TERMS = [
    "private lender", "looking to lend", "funds to lend", "money to lend",
    "looking for a private lender", "need funding", "fund your deal",
    "passive investor", "self directed ira", "deed of trust", "first position",
    "gap funding", "jv partner", "capital to deploy", "looking for a deal to fund",
    "12% return",
]

# ------------------------------------------------------------------ classification
# Someone offering THEIR OWN money. First person, and specific about it.
LENDER_OFFER_RE = re.compile(
    r"((?:i|we)(?:'m| am|’m|'re| are|’re)?\s+(?:a\s+|an\s+)?(?:private|hard)\s*(?:money\s*)?lender"
    r"|private (?:money )?lender (?:here|available|looking|ready)"
    r"|(?:i|we)\s+(?:lend|fund|finance)\b|(?:i|we)\s+(?:can|will|do)\s+(?:lend|fund|finance)"
    # Needs an I/we subject: bare "looking to fund" is how a shop addresses the
    # READER ("Are you looking to fund your next deal?").
    r"|(?:i|we)(?:'m|’m| am|'re|’re| are)?\s+(?:currently |actively |still )?"
    r"(?:looking|want|wanting|ready|able|available|here)\s+to\s+(?:lend|fund|deploy|place)"
    # First-person only: "I have money to lend" is a lender, "looking for private
    # money to lend 1.25 million against my portfolio" is a BORROWER (Greg Hall, 9/9).
    r"|(?:i|we|my|our)\s+(?:have\s+|got\s+|with\s+)?(?:\$[\d,]+[km]?\s+(?:in\s+)?)?"
    r"(?:funds?|money|capital|cash)\s+(?:available\s+)?to\s+(?:lend|deploy|invest|place)"
    r"|(?:have|got)\s+(?:funds?|capital|money|cash)\s+(?:available|ready|sitting|to)"
    r"|looking for (?:a |good |solid |the next )?(?:deal|deals|borrower|borrowers|project|projects)\s+to\s+(?:fund|lend)"
    r"|(?:my|our)\s+own\s+(?:funds?|money|capital)|lend(?:ing)?\s+(?:my|our)\s+own"
    r"|self[- ]?directed\s+ira|\bsdira\b|(?:my|our)\s+(?:ira|401k|roth)"
    r"|passive(?:ly)?\s+invest|looking to invest passively|note investor|invest in notes"
    # "first position loans" is what a borrower ASKS for too - keep only the
    # phrasings that a lender alone would write.
    r"|first (?:lien|position)\s+(?:only|lender)|(?:i|we) lend (?:in|on) first"
    r"|secured by (?:a )?(?:deed|mortgage|note))",
    re.I,
)
# A shop, a broker, or a licensee - real money, but not Ty's "individual".
COMPANY_RE = re.compile(
    r"(\bnmls\b|\bdscr\b|apply (?:now|today|here|online)|pre[- ]?approv|loan (?:officer|programs?|options?|products?)"
    r"|account executive|branch manager|originat(?:or|ing)|\bbroker(?:age)?\b|\bmlo\b"
    r"|rates? (?:as low|start|from)\b|\bltv\b|\bltc\b|\barv\b\s*(?:up to|based)|min(?:imum)? (?:credit|fico)|\bfico\b"
    r"|terms?:|no[- ]doc\b|ground[- ]?up construction loans?|fix (?:and|&|n) flip loans?"
    r"|we(?:'ve| have)? funded|our (?:team|clients|borrowers|investors|company|fund)"
    r"|book a call|schedule a call|calendly|link in (?:bio|comments)|click the link|dm for (?:a )?(?:quote|terms|rate)"
    # No bare .com/.net - that matches every email address, and an email is the
    # single most valuable thing an INDIVIDUAL lender leaves in a comment.
    r"|https?://|www\."
    r"|\bllc\b|\binc\b|\bcorp\b|capital (?:group|partners|funding|llc)?\b|lending (?:group|llc|partners)?\b"
    r"|funding (?:group|llc|partners|solutions)|financial (?:group|services)|\bmortgage\b|\bbank\b)",
    re.I,
)
# Someone ASKING for money. Not the target, but their comment threads are where
# the individuals show up, and a borrower is still a JV contact.
CAPITAL_REQUEST_RE = re.compile(
    r"(looking for (?:a |an |any |some )?(?:private|hard)?\s*(?:money )?(?:lender|lenders|loan|funding|financing|capital|partner)"
    r"|need(?:ing)? (?:a |an |some )?(?:private|hard)?\s*(?:money )?(?:lender|loan|funding|financing|capital)"
    r"|(?:seeking|searching for|in need of|in search of) (?:a |an |some )?(?:private |hard )?"
    r"(?:money )?(?:funding|financing|capital|lender|loan|investor|partner)"
    r"|(?:anyone|who) (?:know|use|recommend|have|has)s? (?:a |any )?(?:good |reliable )?(?:private|hard)?\s*(?:money )?lender"
    r"|(?:need|looking for) (?:gap|bridge|transactional) fund"
    r"|need \$[\d,]+ ?(?:k|m)? ?(?:to|for)\b|looking for (?:a )?jv|joint venture partner)",
    re.I,
)
# "Drop your info if you lend" - a lender roll call.
ROLLCALL_RE = re.compile(
    r"((?:all|any|calling all) (?:private |hard money )?lenders"
    r"|lenders?,? (?:drop|comment|post|introduce|chime)"
    r"|(?:drop|comment|post) (?:your|you're|below) (?:info|name|terms|rates|criteria|contact)"
    r"|who (?:here )?(?:is|are) (?:lending|a lender|funding)|who(?:'s| is) lending"
    r"|introduce yourself|lender (?:roll ?call|thread|list|directory)"
    r"|looking to (?:build|grow) (?:my|our) (?:lender|funding) list)",
    re.I,
)
# Scam / MLM / credit-repair noise that floods lender groups.
JUNK_RE = re.compile(
    r"(credit repair|tradelines?|business credit|cpn\b|\bau tradeline|funding coach|shelf corp"
    r"|cash ?app|zelle only|western union|bitcoin|crypto|forex|binary option|telegram|whatsapp \+?\d"
    r"|guaranteed approval|no credit check needed|make \$\d+ (?:a|per) (?:day|week)"
    r"|dm me to (?:learn|start|earn)|financial freedom|passive income opportunity"
    # Advance-fee loan spam - the "do you live in <list of countries>" opener is
    # the tell, and these flood every lending group.
    r"|do you (?:live|reside) in .{0,60}(?:usa|canada|australia|new zealand|uk)"
    r"|loans? (?:offer|at) \d{1,2}(?:\.\d)?% ?(?:interest|rate|per annum)"
    r"|we (?:offer|give) loans? to (?:individuals|companies|anyone|people)"
    r"|corporate credit|personal loans?|debt consolidation|loan offer"
    r"|contact us (?:via|on|at) (?:whatsapp|telegram|email) ?\+?\d)",
    re.I,
)
# Does this post concern MONEY at all? Tested first, because COMPANY_RE's generic
# half (.com, LLC, "our team") otherwise swallows every wholesaler's deal post -
# 378 of 790 posts in the Pensacola/Charlotte corpus classified "company_ad"
# before this gate existed.
LENDING_CTX_RE = re.compile(
    r"(lend|loan|fund(?:s|ed|ing)?\b|financ|capital|private money|hard money|\bnote\b|mortgage"
    r"|interest rate|\bpoints\b|\bltv\b|borrow|\bira\b|401k|deed of trust|first (?:lien|position))",
    re.I,
)
# Company signals strong enough to settle it on their own - no individual writes these.
STRONG_COMPANY_RE = re.compile(
    r"(\bnmls\b|\bdscr\b|apply (?:now|today|here|online)|pre[- ]?approv|loan (?:officer|programs?|products?)"
    r"|account executive|branch manager|\bmlo\b|rates? (?:as low|start|from)\b|min(?:imum)? (?:credit|fico)|\bfico\b"
    r"|calendly|link in (?:bio|comments)|book a call|schedule a call)",
    # NOT bare https:// or www. - every wholesaler's deal post carries a photo link,
    # which alone was enough to file Oren's own listing as a loan company.
    re.I,
)
# How a lender ACTUALLY answers "I need $75k": not with lending vocabulary at all.
# Live sample from the 9/9 run - "We do!", "DM us!", "Right here", "Happy to help.
# Let's connect!", "Sent you a message", "How can I help you?". On a funding-request
# thread the CONTEXT is the signal and the wording is nearly empty, so requiring a
# lender phrase (or a phone number) here throws away almost every real lender.
RESPONDER_RE = re.compile(
    r"(\bwe do\b|\bi do\b|right here|happy to (?:help|assist)|glad to help|let'?s (?:connect|chat|talk)"
    r"|would love to (?:connect|help|chat)|(?:sent|send|left|shot) (?:you )?(?:a )?(?:dm|pm|message|msg|inbox)"
    r"|\bdm(?:'d|ed| me| us| sent)|\bpm(?:'d|ed| me| us| sent)|check your (?:inbox|dm|messages)"
    r"|inbox me|message me|reach out|(?:i|we) can (?:help|do (?:this|that|it))|may be able to help"
    r"|how can (?:i|we) help|what(?:'s| is) the (?:property|address|arv|deal|scenario)"
    r"|send (?:me|us) (?:the )?(?:details|info|deal|address|scenario)|tell me more|more (?:details|info)"
    r"|\binterested\b|call me|text me|here to help|let me know|happy to (?:take a )?look)",
    re.I,
)
# A CAPITAL RAISER advertising to lenders - the mirror image of our target, and it
# borrows every word a lender uses. Tell: it talks about the READER'S money.
# ("How well is your IRA working for YOU?", "Finance your retirement with real
# estate", "become a private lender") - three of the first twelve individuals on
# the 9/9 run were these. They want money, so they belong in the borrower tab.
CAPITAL_RAISER_RE = re.compile(
    r"((?:your|you're|you have|if you have|got)\s+(?:money|funds?|cash|capital|savings)"
    r"|your (?:ira|401k|roth|retirement|savings|nest egg|money) (?:working|sitting|earning|is)"
    r"|(?:how|is) (?:well )?(?:is )?your (?:ira|401k|retirement|money)"
    r"|finance your retirement|fund your retirement|exposure to real estate"
    r"|become a (?:private )?lender|want to be a (?:private )?lender|learn to (?:lend|be a lender)"
    r"|(?:earn|make|get) (?:up to )?\d{1,2}(?:\.\d)?%\s*(?:apy|annual|return|interest|on your)"
    r"|(?:we|i) pay \d{1,2}(?:\.\d)?%|returns? (?:to|for) (?:you|our|my) (?:investors?|lenders?)"
    r"|(?:partner|invest|lend) with (?:us|me)\b|our (?:investors|lenders) (?:earn|make|get)"
    r"|passive income (?:opportunity|stream) for you|secured by real estate.{0,30}your money)",
    re.I,
)
# A BORROWER piggybacking on someone else's funding request - looks like a reply,
# is actually another person asking for money ("I have a similar scenario, call me").
PIGGYBACK_RE = re.compile(
    r"(similar (?:scenario|situation|deal|need|request|boat)|same (?:situation|boat|here)\b"
    r"|^following\b|watching this|commenting for|\bme too\b|any luck (?:finding|getting|with)"
    r"|did you (?:find|get) (?:a|the|any)|(?:i'?m| i am|we'?re) (?:also )?looking for (?:a |an )?"
    r"(?:private |hard )?(?:money )?(?:lender|loan|funding|financing|capital)"
    r"|i need (?:a |an )?(?:private |hard )?(?:money )?(?:lender|loan|funding|financing|\$))",
    re.I,
)
# Somebody selling a house. Never a lender's post, whatever vocabulary it borrows.
DEAL_LISTING_RE = re.compile(
    r"(assign(?:able|ment fee)|under contract|asking\s*:?\s*\$|price\s*:?\s*\$|\barv\b\s*:?\s*\$"
    r"|\d+\s*(?:bed|bd|br)\b.{0,30}\d+\s*(?:bath|ba)\b|\bsq\s?ft\b|comps?\s+(?:at|around|in)"
    r"|(?:off[- ]market|wholesale|investor special|fixer)\s+(?:deal|property|opportunity|listing)"
    r"|\d{3,5}\s+[A-Z][a-z]+\s+(?:St|Ave|Rd|Dr|Ln|Blvd|Ct|Way|Pl)\b)",
    re.I,
)
# A business only counts as a LENDING business if it is offering money. Without
# this a wholesaler's deal post with a .com in it reads as a loan shop (161 of 790
# in the corpus, one of them Oren's own listing).
LENDS_SERVICE_RE = re.compile(
    r"(we (?:lend|fund|finance|offer)|lend(?:s|ing)? (?:on|to|in|nationwide|up to)"
    r"|loans? (?:up to|from|for|available|starting)|funding (?:available|up to|for|solutions)"
    r"|we can (?:fund|get you)|get (?:you )?funded|financing available|no money down"
    # NOT bare "hard money" / "private money" - every deal post says "cash or hard
    # money only", which is a wholesaler talking to buyers, not a lender.
    r"|(?:hard|private) money (?:lender|loans?|available|for)|bridge loans?|\bdscr\b|fix (?:and|&|n) flip loans?"
    r"|construction loans?|\bterms?:|close in \d+ days)",
    re.I,
)
# A name that is a business, not a person (people-vs-company gate, second half).
# Tested ANYWHERE in the name, not just the last word - "LGS Secured Financing",
# "Early Bird Private Money" and "AVL Homes" all reached the individual tab when
# this only anchored to the end.
BIZ_NAME_RE = re.compile(
    r"\b(llc|l\.l\.c|inc|corp|co\.|ltd|lp|llp|capital|fund(?:s|ing)?|lend(?:s|ing)?|lenders?|loans?"
    r"|financial|financing|finance|mortgage|bank|banc|group|partners?|ventures?|holdings?|equity"
    r"|realty|real estate|properties|property|homes|investments?|investors?|solutions|services"
    r"|associates|enterprises?|acquisitions?|advisors?|management|consulting|consultants?"
    r"|money|credit|trust|assets?|wealth|resources|network|team|agency)\b",
    re.I,
)


def _lender_kind(text: str) -> str:
    """Replaces fb._post_kind. Order matters: a shop's ad also says 'we lend'."""
    if JUNK_RE.search(text):
        return "junk"
    if not LENDING_CTX_RE.search(text):
        return "other"          # a deal post that happens to carry a .com is not a lender
    if DEAL_LISTING_RE.search(text) and not LENDER_OFFER_RE.search(text):
        return "other"          # a property for sale is nobody's lending ad
    if CAPITAL_RAISER_RE.search(text):
        return "capital_request"    # pitching the reader's IRA - they want money
    if ROLLCALL_RE.search(text):
        return "lender_rollcall"
    if STRONG_COMPANY_RE.search(text):
        return "company_ad"     # nobody lending their own IRA writes "NMLS #" or "apply now"
    offer = LENDER_OFFER_RE.search(text)
    if offer:
        # An individual who left a phone number beats a landing page; two company
        # tells in one post is a shop.
        return "company_ad" if len(COMPANY_RE.findall(text)) >= 2 else "lender_offer"
    if CAPITAL_REQUEST_RE.search(text):
        return "capital_request"
    if COMPANY_RE.search(text) and LENDS_SERVICE_RE.search(text):
        return "company_ad"
    return "other"


# Threads worth the ~13s it costs to re-find and open one.
THREAD_RANK = {"lender_rollcall": 0, "capital_request": 1, "lender_offer": 2,
               "company_ad": 3, "other": 4, "junk": 5}


def _thread_targets(args):
    targets = []
    for gid in args.groups:
        for post in fb._load_posts(gid).values():
            if post["comments"] < args.min_comments:
                continue
            if post["kind"] in {"junk"}:
                continue
            if post["kind"] in {"other", "company_ad"} and not args.all_kinds:
                continue
            targets.append((gid, post))
    targets.sort(key=lambda t: (THREAD_RANK[t[1]["kind"]], -t[1]["comments"]))
    if args.limit:
        targets = targets[: args.limit]
    return targets


# ------------------------------------------------------------------ commands
def cmd_harvest(args) -> int:
    terms = args.terms or TERMS
    with sync_playwright() as p:
        ctx, page = fb._open(p, args.headless)
        done = failed = 0
        for gid in args.groups:
            gdir = OUTDIR / gid
            gdir.mkdir(parents=True, exist_ok=True)
            for i, term in enumerate(terms, 1):
                dest = gdir / (re.sub(r"[^a-z0-9]+", "_", term.lower()) + ".json")
                if dest.exists() and not args.force:
                    print(f"[{gid} {i}/{len(terms)}] skip (have it)  {term}")
                    continue
                try:
                    data = fb._harvest_term(page, gid, term)
                    dest.write_text(json.dumps(data, indent=1), encoding="utf-8")
                    kinds: dict[str, int] = {}
                    for x in data["posts"]:
                        k = _lender_kind(x["text"])
                        kinds[k] = kinds.get(k, 0) + 1
                    print(f"[{gid} {i}/{len(terms)}] {term:<28} {data['post_count']:>3} posts  "
                          f"{kinds} -> {dest.name}", flush=True)
                    done += 1
                except Exception as exc:
                    print(f"[{gid} {i}/{len(terms)}] FAILED {term}: {type(exc).__name__}: {exc}", flush=True)
                    failed += 1
                    if "Facebook says" in str(exc):
                        print("  Facebook is throttling - stopping this run.")
                        ctx.close()
                        return 3
                page.wait_for_timeout(random.uniform(2500, 4500))
        ctx.close()
    print(f"\nHarvested {done} term-file(s), {failed} failed. Files in {OUTDIR}")
    return 1 if failed and not done else 0


def cmd_threads(args) -> int:
    targets = _thread_targets(args)
    print(f"{len(targets)} thread(s) to open (min {args.min_comments} comments)")
    with sync_playwright() as p:
        ctx, page = fb._open(p, args.headless)
        done = failed = 0
        for i, (gid, post) in enumerate(targets, 1):
            dest = fb._thread_dest(gid, post)
            if dest.exists() and not args.force:
                print(f"[{i}/{len(targets)}] skip (have it) {dest.name}")
                continue
            t0 = time.time()
            try:
                pl, how = fb._locate_thread(page, gid, post)
                if not pl:
                    print(f"[{i}/{len(targets)}] NOT FOUND {post['kind']} {post['author'][:30]} [{how}]", flush=True)
                    failed += 1
                    continue
                if pl != "DIALOG" and not re.search(r"/posts/\d+|/permalink/\d+|multi_permalinks=\d+", page.url):
                    page.goto(pl, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(6000)
                data = fb._harvest_thread_here(page, gid, "" if pl == "DIALOG" else pl)
                data["search_kind"] = post["kind"]
                data["search_comments"] = post["comments"]
                data["search_author"] = post["author"]
                data["search_text"] = post["text"][:600]
                data["located_via"] = how
                dest.write_text(json.dumps(data, indent=1), encoding="utf-8")
                lend = sum(1 for c in data["comments"] if LENDER_OFFER_RE.search(c["text"]))
                print(f"[{i}/{len(targets)}] {post['kind']:<16} expected {post['comments']:>3}  got {data['comment_count']:>3} "
                      f"({lend} lender-signal) all={data['sorted_all_comments']} {time.time()-t0:.0f}s -> {dest.name}", flush=True)
                done += 1
            except Exception as exc:
                print(f"[{i}/{len(targets)}] FAILED {post['author'][:30]}: {type(exc).__name__}: {exc}", flush=True)
                failed += 1
                if "Facebook says" in str(exc):
                    ctx.close()
                    return 3
            page.wait_for_timeout(random.uniform(2500, 4500))
        ctx.close()
    print(f"\nOpened {done} thread(s), {failed} failed/not found.")
    return 0


# ------------------------------------------------------------------ build
def _is_person(name: str, texts: list[str]) -> bool:
    if BIZ_NAME_RE.search(name.strip()):
        return False
    return len(name.split()) >= 2


def _evidence(texts: list[str], pattern: re.Pattern, limit: int = 3) -> list[str]:
    out = []
    for t in texts:
        for m in pattern.finditer(t or ""):
            s, e = max(0, m.start() - 60), min(len(t), m.end() + 90)
            frag = re.sub(r"\s+", " ", t[s:e]).strip()
            if frag and frag not in out:
                out.append(frag)
            if len(out) >= limit:
                return out
    return out


def cmd_build(args) -> int:
    people: dict[str, dict] = {}

    def rec_for(gid, name, profile):
        name = fb._clean_author(name)
        if not name or len(name) < 3 or name.lower() in {
                "facebook", "anonymous member", "anonymous participant", "group member"}:
            return None
        rec = people.setdefault(fb._norm_name(name), {
            "Name": name, "Profile": "", "Groups": set(),
            "n_offer": 0, "n_offer_comment": 0, "n_rollcall_answer": 0, "n_request": 0,
            "n_responder": 0,
            "n_company": 0, "n_junk": 0,
            "Phones": set(), "Emails": set(), "Texts": [], "Permalinks": [],
        })
        if profile and not rec["Profile"]:
            rec["Profile"] = fb._abs(profile)
        rec["Groups"].add(GROUP_NAMES.get(gid, gid))
        return rec

    def add_text(rec, text, permalink, front=False):
        rec["Phones"].update(fb._phones(text))
        rec["Emails"].update(fb._emails(text))
        if front:
            rec["Texts"].insert(0, text)
        else:
            rec["Texts"].append(text)
        pl = fb._abs(permalink) if permalink else ""
        if pl and pl not in rec["Permalinks"] and len(rec["Permalinks"]) < 3:
            rec["Permalinks"].append(pl)

    n_posts = n_threads = n_comments = 0
    for gid in args.groups:
        for post in fb._load_posts(gid).values():
            n_posts += 1
            rec = rec_for(gid, post["author"], post.get("authorHref", ""))
            if rec is None:
                continue
            body = "\n".join(post["text"].split("\n")[1:]) or post["text"]
            k = post["kind"]
            if k == "lender_offer":
                rec["n_offer"] += 1
            elif k == "company_ad":
                rec["n_company"] += 1
            elif k == "capital_request":
                rec["n_request"] += 1
            elif k == "junk":
                rec["n_junk"] += 1
            add_text(rec, body, post.get("permalink", ""), front=(k == "lender_offer"))

        tdir = OUTDIR / gid / "threads"
        for f in (tdir.glob("*.json") if tdir.exists() else []):
            th = json.loads(f.read_text(encoding="utf-8"))
            n_threads += 1
            author_n = fb._norm_name(th.get("search_author") or "")
            ctx_kind = th.get("search_kind") or "other"
            for c in th["comments"]:
                if fb._norm_name(c["author"]) == author_n or not c["author"]:
                    continue
                rec = rec_for(gid, c["author"], c.get("profile", ""))
                if rec is None:
                    continue
                text = c["text"]
                n_comments += 1
                if JUNK_RE.search(text):
                    rec["n_junk"] += 1
                    continue
                offer = bool(LENDER_OFFER_RE.search(text)) and not CAPITAL_RAISER_RE.search(text)
                # A company tell only counts when the comment is about lending -
                # otherwise a signature line makes every commenter a loan shop.
                company = bool(STRONG_COMPANY_RE.search(text)) or bool(
                    COMPANY_RE.search(text) and LENDS_SERVICE_RE.search(text))
                has_contact = bool(fb._phones(text) or fb._emails(text))
                if offer and not company:
                    rec["n_offer_comment"] += 1
                elif company:
                    rec["n_company"] += 1
                elif CAPITAL_REQUEST_RE.search(text) or PIGGYBACK_RE.search(text):
                    rec["n_request"] += 1       # a borrower under someone else's ask
                elif ctx_kind in ("capital_request", "lender_rollcall") and (
                        has_contact or RESPONDER_RE.search(text) or len(text) > 40):
                    # Answered a funding request without saying anything lender-shaped.
                    rec["n_responder"] += 1
                else:
                    continue
                add_text(rec, text, th.get("permalink", ""), front=offer)

    rows = []
    for rec in people.values():
        lends = rec["n_offer"] + rec["n_offer_comment"] + rec["n_rollcall_answer"]
        person = _is_person(rec["Name"], rec["Texts"])
        answers = rec["n_responder"]
        if rec["n_junk"] and not lends and not answers:
            cls, score, tab = "JUNK / MLM", 0, "junk"
        elif lends and rec["n_company"] == 0 and person:
            cls, score, tab = "PRIVATE LENDER (individual)", 70 + 10 * min(lends, 3), "individual"
        elif lends and (rec["n_company"] or not person):
            cls, score, tab = "LENDING COMPANY / BROKER", 40 + 5 * min(lends, 3), "company"
        elif answers and rec["n_company"] == 0 and person:
            # Said "happy to help" under someone's funding request and nothing more.
            # Weaker than a stated offer, but on these threads it IS the lender.
            cls, score, tab = "LIKELY LENDER (answered a funding request)", 48 + 6 * min(answers, 4), "individual"
        elif answers:
            cls, score, tab = "LENDING COMPANY / BROKER (answered a request)", 34 + 3 * min(answers, 4), "company"
        elif rec["n_company"]:
            cls, score, tab = "LENDING COMPANY / BROKER", 30, "company"
        elif rec["n_request"]:
            cls, score, tab = "BORROWER (wants money)", 15, "borrower"
        else:
            continue
        if rec["Phones"]:
            score += 12
        if rec["Emails"]:
            score += 8
        if rec["Profile"]:
            score += 2
        rows.append({
            "Score": score,
            "Class": cls,
            "Tab": tab,
            "Name": rec["Name"],
            "Phones": ", ".join(sorted(rec["Phones"])),
            "Emails": ", ".join(sorted(rec["Emails"])),
            "Lender posts": rec["n_offer"],
            "Lender comments": rec["n_offer_comment"] + rec["n_rollcall_answer"],
            "Answered a request": rec["n_responder"],
            "Company hits": rec["n_company"],
            "Groups": ", ".join(sorted(rec["Groups"])),
            "Evidence": " || ".join(_evidence(rec["Texts"], LENDER_OFFER_RE)
                                    or [re.sub(r"\s+", " ", t)[:200] for t in rec["Texts"][:2]]),
            "Profile": rec["Profile"],
            "Post": rec["Permalinks"][0] if rec["Permalinks"] else "",
        })
    rows.sort(key=lambda r: (-r["Score"], r["Name"]))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    dest = ROOT / "output" / f"fb_private_lenders_{TODAY}.csv"
    cols = [c for c in rows[0].keys() if c != "Tab"] if rows else []
    with dest.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["Tab"] + cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by_tab: dict[str, int] = {}
    for r in rows:
        by_tab[r["Tab"]] = by_tab.get(r["Tab"], 0) + 1
    print(f"\n{n_posts} posts, {n_threads} threads, {n_comments} comments -> {len(rows)} people")
    for tab in ("individual", "company", "borrower", "junk"):
        print(f"  {tab:<12} {by_tab.get(tab, 0)}")
    print(f"  with phone: {sum(1 for r in rows if r['Phones'])}   "
          f"with email: {sum(1 for r in rows if r['Emails'])}")
    print(f"\n-> {dest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    # Comma-separated on purpose: the buyer script uses nargs="+", which silently
    # swallows the subcommand ("--groups a b harvest" -> a group called "harvest").
    ap.add_argument("--groups", required=True, type=lambda v: [x for x in v.split(",") if x],
                    help="comma-separated group ids or slugs")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--force", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    h = sub.add_parser("harvest")
    h.add_argument("--terms", nargs="+")
    t = sub.add_parser("threads")
    t.add_argument("--min-comments", type=int, default=3)
    t.add_argument("--limit", type=int, default=0)
    t.add_argument("--all-kinds", action="store_true")
    sub.add_parser("build")
    args = ap.parse_args()

    # Point the shared machinery at the lender corpus and the lender classifier.
    fb.OUTDIR = OUTDIR
    fb._post_kind = _lender_kind

    survey = sorted(OUTDIR.glob("lender_groups_*.json"))
    if survey:
        try:
            data = json.loads(survey[-1].read_text(encoding="utf-8"))
            GROUP_NAMES.update({k: (v.get("name") or k)[:60] for k, v in data.items()})
        except Exception:
            pass

    if args.cmd == "probe":
        args_ns = argparse.Namespace(groups=args.groups, headless=args.headless)
        return fb.cmd_probe(args_ns)
    if args.cmd == "harvest":
        return cmd_harvest(args)
    if args.cmd == "threads":
        return cmd_threads(args)
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
