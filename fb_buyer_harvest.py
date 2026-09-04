"""Harvest CASH BUYERS from Pensacola real-estate-investor Facebook groups.

Sister of fb_group_harvest.py (which mines a group for contractors). Same
persistent, human-logged-in Playwright profile (.fb_profile), same virtualised
search-results extraction, but aimed at buyer intent instead of trades, and with
a SECOND PASS that opens busy threads and captures the commenters - because on a
"cash buyers drop your info" or an off-market deal post, the people in the
comments ARE the buyers list.

    python fb_buyer_harvest.py probe                      # group name + are we a member?
    python fb_buyer_harvest.py harvest                    # in-group search, every term
    python fb_buyer_harvest.py threads --min-comments 3   # open busy threads, read comments
    python fb_buyer_harvest.py build                      # -> CSV + summary

Never launch this while another process holds .fb_profile (Chrome exit code 21).
Output: output/fb_buyers/<gid>/<term>.json, output/fb_buyers/<gid>/threads/*.json
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".fb_profile"
OUTDIR = ROOT / "output" / "fb_buyers"
TODAY = datetime.now().strftime("%Y-%m-%d")

GROUPS = {
    "630783891338311": "Pensacola REI - Real Estate Investors (5.0K, private)",
    "323092821516318": "Pensacola Real Estate Community (11.6K, public)",
}
# Not a default target - Oren's Charlotte buyer list (siftstack-fd) runs it with --groups.
CHARLOTTE_REI = "285310938318371"
GROUPS_ALL = {**GROUPS, CHARLOTTE_REI: "Charlotte Real Estate Investors"}

# Buyer-intent search terms. Ordered so the highest-yield phrasing runs first
# (if Facebook throttles search mid-run the best files already exist).
TERMS = [
    "cash buyer", "buyers list", "looking for deals", "send me deals",
    "looking to buy", "looking for properties", "fix and flip", "buy and hold",
    "flipper", "investor looking", "proof of funds", "we buy houses",
    "off market", "wholesale deal", "32503", "East Hill",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Someone saying they BUY (the person we want).
BUYER_RE = re.compile(
    r"(cash buyer|i(?:'m| am|’m) (?:a |an )?(?:cash |active |serious |local )?(?:buyer|investor|flipper)"
    r"|looking (?:for|to buy|to purchase|for deals|for properties|for off)"
    r"|send me (?:deals|your deals|what you|anything|info|the info|details|more)"
    r"|add me (?:to|on)|buyers? list|buy(?:ing)? (?:and|&|n) hold|fix (?:and|&|n) flip"
    r"|we buy|i buy|i purchase|actively buying|buying in|proof of funds|\bpof\b"
    r"|interested|dm(?:'d| me|ed| sent)?\b|pm(?:'d| me)?\b|more info|details please|price\?|what'?s the price"
    r"|i'?ll take|let'?s talk|call me|text me)",
    re.I,
)
# Someone SELLING (a wholesaler / competitor - their commenters are buyers).
DEAL_RE = re.compile(
    r"(\barv\b|assign|asking|off[- ]market|under contract|wholesale|wholesaling|\bemd\b"
    r"|earnest|walkthrough|showing|as[- ]is|cash only|investor special|needs (?:work|tlc|rehab)"
    r"|price:|\$\s?\d{2,3}k|\$\d{3},\d{3})",
    re.I,
)
# Lenders advertise in buyer vocabulary ("we fund fix and flips", "looking for
# investors") - 20 of 54 Charlotte "buyer" hits were hard-money shops.
LENDER_RE = re.compile(
    r"(\bdscr\b|bridge loan|100% financing|apply (?:today|now|online)|\bltv\b|\bpoints\b|hard[- ]money lender"
    r"|private (?:money )?lender|we (?:lend|fund|finance)|funding (?:available|for)|get funded|loan (?:program|options|approval)"
    r"|pre-?approv|interest[- ]only|no doc\b|rates? (?:start|as low)|\bapr\b|mortgage|loan officer|branch manager|originat(?:or|ing)|\bnmls\b)",
    re.I,
)
# Direction check (siftstack-fd: of 20 lender-classed Charlotte rows only 4 offered
# capital; 4 were investors SEEKING a loan - i.e. buyers about to buy).
SEEKING_LENDER_RE = re.compile(
    r"(looking for (?:a |an |any )?(?:good |reliable |local )?(?:hard[- ]money |private |money )?lender"
    r"|need (?:a |an )?(?:hard[- ]money |private )?(?:lender|loan|funding|financing)"
    r"|(?:anyone|who) (?:know|use|recommend|have)s? (?:a |any )?(?:good |reliable )?(?:hard[- ]money |private )?lender"
    r"|recommend(?:ations?)? (?:for |on )?(?:a )?(?:hard[- ]money |private )?lender|looking for funding"
    r"|who do you use for (?:hard money|lending|loans|financing)|lender recommendations?)",
    re.I,
)
# FIRST-PERSON buying statements - the only thing that makes a POST AUTHOR a buyer.
# ("interested" / "dm me" / "call me" are comment-level interest, not author evidence:
# every wholesaler's deal post ends with "call me for details".)
BUYER_STRONG_RE = re.compile(
    r"(?:(?:i(?:'m| am|\u2019m)|we(?:'re| are|\u2019re)|serious|local|active|end|out[- ]of[- ]state)\s+(?:a\s+|an\s+)?"
    r"(?:cash\s+|serious\s+|active\s+|local\s+|end\s+|real estate\s+)*(?:buyer|investor|flipper|landlord|rehabber)s?\b"
    r"|cash buyer (?:here|looking|seeking|in the)|as a cash buyer"
    r"|(?:add|put) me (?:to|on) (?:your|the) (?:cash )?(?:buyers?\s*)?list|add me to your list"
    r"|send me (?:your |any |all |the |more )?(?:deals|off[- ]market|properties|what you (?:have|got)|inventory|anything you)"
    r"|looking (?:to buy|to purchase|to acquire|to add|to pick up|for (?:my|our) (?:next|first)|for (?:more |off[- ]market |distressed |cash |wholesale |investment |rental |fixer|flip)?(?:deals|properties|off[- ]market|fixers?|flips?|rentals?|land|lots|multi[- ]?famil|duplex|sfh|houses|homes) (?:in|around|near|to buy))"
    r"|(?:i|we) (?:am|are|'m|'re)?\s?(?:actively |currently )?(?:buying|purchasing|acquiring)|actively buying|buying in \w+"
    r"|(?:my|our) (?:buy[- ]box|criteria|portfolio|next (?:flip|rental|project)|first (?:flip|rental))"
    r"|(?:have|with|got) (?:proof of funds|pof|cash (?:ready|in hand|on hand))|pof ready"
    r"|i (?:buy|purchase|flip|rehab|hold)\b|we (?:purchase|flip|rehab|acquire|hold)\b"
    r"|buy(?:ing)? (?:and|&|n) hold(?:ing)? (?:investor|in|properties|rentals)|fix (?:and|&|n) flip (?:investor|in|properties|houses|homes)"
    r"|need (?:more )?(?:deals|inventory|properties)|closing (?:in|with) cash|can close (?:in|fast|quick))",
    re.I,
)
# Interest shown IN A COMMENT under someone else's post.
BUYER_INTEREST_RE = re.compile(
    r"(interested|\bdm\b|\bpm\b|more info|info please|details|send (?:me|it|info|address|the)|still available|what'?s the (?:price|address|arv)"
    r"|price\?|address\?|\barv\b|rehab (?:preferred|budget)|max\b|budget|criteria|\bsfh\b|\d/\d\b|zip|call me|text me|my number|@[a-z0-9.-]+\.[a-z]{2,}"
    r"|i(?:'ll| will) take|let'?s talk|i need|send (?:them|deals|land|flips|rentals)|looking for|add me|i buy|we buy|i'?m (?:a )?(?:cash )?buyer)",
    re.I,
)
# Realtor / brokerage / wholesaler / event vocabulary - demotes an author who never says "I buy".
AGENT_RE = re.compile(
    r"(\brealtor\b|real estate agent|\bbroker(?:age)?\b|keller williams|\bkw\b|exp realty|re/?max|coldwell|century 21|berkshire"
    r"|just listed|new listing|\bmls\b|open house|listing (?:agent|appointment)|list(?:ing)? your (?:home|house)|title company|closing agent"
    r"|wholesal|assign(?:ment|ing|able)?|dispo\b|our buyers|my buyers|buyers list is|joint venture|\bjv\b|meetup|networking event|rsvp|tickets|eventbrite"
    r"|property manage|home inspector|insurance agent|contractor|looking to buy or sell|buy or sell|your (?:dream|next|forever) home"
    r"|beachside|let me help you|(?:buyer|seller)'?s agent|call me today|i can help you (?:buy|sell|find)|pressure wash|roofing|handyman|cleaning)",
    re.I,
)
# What they buy - pulled into its own column for the call sheet.
CRITERIA_RE = re.compile(
    r"([^\n.]*(?:\barv\b|price range|purchase (?:price|preferred)|below \$?\d|under \$?\d|max(?:imum)?\b|budget|rehab|\bsfh\b|single[- ]family|multi[- ]?family|duplex|\d\s?/\s?\d\b|\bbeds?\b|zip|3250\d|3256\d|3257\d|escambia|santa rosa|pensacola|milton|navarre|gulf breeze|cantonment|pace\b|land|lots?\b|mobile home|criteria|buy[- ]box)[^\n.]*)",
    re.I,
)
# A post that is clearly SELLING something (deal or listing) even if it also uses buyer words.
DEAL_STRONG_RE = re.compile(
    r"(off[- ]market (?:\S+ ){0,3}(?:deal|lot|property|house|duplex|opportunity|home|land)|deal alert|under contract|assign(?:ment|able)|asking[: ]|\barv[: ]|\barv\s?\$|wholesale deal|investor special"
    r"|calling (?:all )?(?:builders|investors|buyers|flippers)|(?:quietly )?selling (?:one of )?(?:my|our)|i(?:'m| am) selling|subto deal|subject[- ]to (?:deal|opportunity)"
    r"|for sale\b|price[: ]\$|\$\s?\d{2,3},?\d{3}\b.{0,40}\b(?:bed|bath|sq)|this (?:home|property|house) (?:sits|features|offers|combines|boasts|has)"
    r"|schedule (?:a |your )?(?:showing|tour)|for a showing|listed at|\bmls\b|showings? (?:start|begin|available)|won'?t last|hot deal|new listing)",
    re.I,
)
# A COMMENT written by a seller/wholesaler under a roll-call ("we'll send you deals", "I have a property").
SELLER_COMMENT_RE = re.compile(
    r"(we(?:'ll| will) (?:send|get) you|we have (?:deals|inventory|properties|a (?:deal|property))|our (?:website|buy[- ]box form|inventory|list of deals)"
    r"|fill out (?:your|our|the)|i have (?:a |an |some )?(?:deal|property|house|lot|duplex|off[- ]market)s?\b|i(?:'ve| have) got (?:a |some )?(?:deal|property|house)"
    r"|under contract|sending you (?:deals|info)|check (?:your )?(?:dm|inbox|messages)|i can (?:send|get) you (?:deals|properties)|i'?m a (?:realtor|agent|wholesaler)"
    r"|wholesal(?:e|er|ing)\b|we buy houses|dm(?:'d| sent|ed) you (?:a|the|some) (?:deal|property)"
    r"|for sale\b|buy now|send them over|i(?:'ll| will) send (?:them|it|you|over|some)|shot you a dm|i(?:'ve| have) got a few|email sent"
    r"|\bgot a (?:\w+ ){0,3}deal|are you buying|what are you buying|what'?s your (?:criteria|buy[- ]box)|wholesal\w*"
    r"|i have (?:a |an )?\d[- ]?plex|fourplex|triplex|quadplex|just built|i have (?:\w+ ){0,2}buyers)",
    re.I,
)
# Explicit "buyers, drop your info" requests - every commenter is a buyer.
ROLLCALL_RE = re.compile(
    r"(cash buyers?.{0,40}(?:drop|comment|below|list|reply|where)|who (?:are|is) (?:the )?(?:cash )?buy"
    r"|buyers?.{0,20}(?:drop|comment below|raise|roll ?call)|building (?:my|a|our) buyers"
    r"|looking for (?:\w+ ){0,2}(?:cash )?buyers|need (?:\w+ ){0,2}(?:cash )?buyers?|buyers? (?:wanted|needed)|any (?:cash )?buyers|cash buyers? (?:needed|wanted)"
    r"|what are you buying|what are you looking for|end buyers?|i'?ll reach out|drop (?:a comment|your|below)"
    r"|i have (?:\w+ ){0,2}buyers|(?:my|our) buyers (?:are|need|want)|need (?:more )?inventory|send me your deals"
    r"|(?:got|have) (?:a pipeline|deals|inventory|an influx))",
    re.I,
)


# ---------------------------------------------------------------- browser
def _ctx(p, headless: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        str(PROFILE), headless=headless, viewport={"width": 1400, "height": 1000},
        user_agent=UA, args=["--disable-blink-features=AutomationControlled"],
    )


def _logged_in(ctx) -> bool:
    try:
        return any(c.get("name") == "c_user" and c.get("value") for c in ctx.cookies())
    except Exception:
        return False


def _open(p, headless: bool):
    ctx = _ctx(p, headless)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    if not _logged_in(ctx):
        print("NOT LOGGED IN. Run first:  python fb_group_harvest.py login")
        ctx.close()
        sys.exit(2)
    return ctx, page


def _blocked(page) -> str:
    txt = page.evaluate("() => (document.body.innerText||'').slice(0, 3000)")
    for sig in ("temporarily blocked", "You can't use this feature", "restricted from",
                "Try again later", "This content isn't available"):
        if sig.lower() in txt.lower():
            return sig
    return ""


# ---------------------------------------------------------------- text utils
def _clean(text: str) -> str:
    """Strip Facebook's one-char-per-line timestamp ladder (U+034F padding)."""
    text = text.replace("\u034f", "").replace("\u200b", "").replace("\u200e", "")
    keep, run = [], 0
    for line in text.split("\n"):
        line = line.strip()
        if len(line) <= 1:
            run += 1
            continue
        if run >= 6:
            run = 0
        keep.append(line)
    return "\n".join(keep).strip()


def _phones(text: str) -> list[str]:
    """NANP-plausible only: area code and exchange start 2-9 (kills '$100,001 2095' artefacts)."""
    out = set()
    for a, b, c in PHONE_RE.findall(text):
        if a[0] in "01" or b[0] in "01" or a in {"555", "800", "888", "877", "866", "855", "844", "833"}:
            continue
        out.add(f"{a}-{b}-{c}")
    return sorted(out)


AUTHOR_TIME_RE = re.compile(r"\s+(?:a|an|\d+)\s+(?:second|minute|hour|day|week|month|year|yr|mo|wk|hr|min)s?\s*(?:ago)?\s*$", re.I)


def _clean_author(name: str, kind: str = "") -> str:
    name = (name or "").strip()
    if kind.lower() == "reply":
        name = re.sub(r"\s+to\s+.*$", "", name)
    name = re.sub(r"['\u2019]s? (?:comment|reply)$", "", name)
    for _ in range(2):
        name = AUTHOR_TIME_RE.sub("", name)
    name = re.sub(r"\s+Shared post.*$", "", name)
    return name.strip(" '\u2019\u00b7-")


def _emails(text: str) -> list[str]:
    return sorted({e.lower() for e in EMAIL_RE.findall(text)})


def _post_kind(text: str) -> str:
    if SEEKING_LENDER_RE.search(text) and not re.search(
            r"we (?:lend|fund|finance)|apply (?:today|now)|\bnmls\b|without using your own money|get you funded|(?:get|secure) (?:funded|funding) (?:for|fast|today)"
            r"|funding for (?:your|investors|real estate)|no money down|100% financing|we (?:can )?help you (?:get|secure)", text, re.I):
        return "buyer_post"          # an investor hunting for a loan is about to buy
    if LENDER_RE.search(text) and not re.search(
            r"cash buyer|i(?:'m| am) (?:a )?(?:cash )?buyer|we buy|i buy|our (?:own )?portfolio|we (?:also )?(?:flip|rehab|purchase|acquire) "
            r"|i (?:flip|rehab)|fix (?:&|and) flips? (?:per|a|each) year", text, re.I):
        return "lender"
    if ROLLCALL_RE.search(text):
        return "buyer_rollcall"
    if DEAL_RE.search(text) and (DEAL_STRONG_RE.search(text) or not BUYER_STRONG_RE.search(text)):
        return "deal_post"
    if BUYER_STRONG_RE.search(text):
        return "buyer_post"
    return "other"


# ---------------------------------------------------------------- pass 1: search
EXTRACT_JS = """() => {
        const out = [];
        const seen = new Set();
        const nodes = [
            ...document.querySelectorAll('[role="feed"] > div'),
            ...document.querySelectorAll('[role="article"]'),
        ];
        for (const art of nodes) {
            const txt = (art.innerText || '')
                .split('\\n')
                .filter(l => l.trim() && !['Facebook', 'Online status indicator',
                                           'Active', 'Shared post'].includes(l.trim()))
                .join('\\n')
                .trim();
            if (txt.length < 40) continue;
            const key = txt.slice(0, 160);
            if (seen.has(key)) continue;
            seen.add(key);
            let permalink = '';
            let authorHref = '';
            for (const a of art.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (!permalink && (h.includes('/posts/') || h.includes('permalink') ||
                    h.includes('multi_permalinks'))) permalink = h;
                if (!authorHref && /\\/groups\\/\\d+\\/user\\/\\d+/.test(h)) authorHref = h;
            }
            const lines = txt.split('\\n').map(s => s.trim()).filter(Boolean);
            const trailing = [];
            for (let i = lines.length - 1; i >= 0 && trailing.length < 4; i--) {
                const l = lines[i];
                if (/^[0-9][0-9,]*$/.test(l)) trailing.unshift(parseInt(l.replace(/,/g,''), 10));
                else if (l !== 'Shared post' && !/^Comment as/.test(l)) break;
            }
            const m = txt.match(/([0-9,]+)\\s+comments?/i);
            out.push({
                text: txt.slice(0, 4000),
                permalink, authorHref,
                comments: m ? parseInt(m[1].replace(/,/g, ''), 10)
                            : (trailing.length ? trailing[trailing.length - 1] : 0),
                engagement: trailing,
                author: lines[0] || '',
            });
        }
        return out;
    }"""



# Facebook truncates long posts at "See more" and the hidden tail is NOT in the DOM
# (found by siftstack-21/a7 on the Charlotte run: 24 businesses whose phone sat
# below the fold). Expanding is inline, no navigation, safe to fire every round.
SEE_MORE_JS = """() => {
        let n = 0;
        for (const el of document.querySelectorAll('[role="button"], span, div')) {
            const t = (el.textContent || '').trim();
            if (t === 'See more' || t === '\u2026 See more' || t === '...See more' || t === '... See more') {
                try { el.click(); n++; } catch (e) {}
            }
        }
        return n;
    }"""

def _harvest_term(page, gid: str, term: str) -> dict:
    url = f"https://www.facebook.com/groups/{gid}/search/?q={term.replace(' ', '%20')}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    if (b := _blocked(page)):
        raise RuntimeError(f"Facebook says: {b}")

    MIN_SCROLLS, MAX_SCROLLS = 10, 28
    collected: dict[str, dict] = {}
    stale = 0
    for i in range(MAX_SCROLLS):
        if page.evaluate(SEE_MORE_JS):
            page.wait_for_timeout(900)
        for post in page.evaluate(EXTRACT_JS):
            # expanded text wins over a truncated capture of the same card
            key = post["text"][:160]
            if key not in collected or len(post["text"]) > len(collected[key]["text"]):
                collected[key] = post
        before = len(collected)
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(random.uniform(2200, 3200))
        stale = stale + 1 if len(collected) == before else 0
        if i + 1 >= MIN_SCROLLS and stale >= 5:
            break
    if page.evaluate(SEE_MORE_JS):
        page.wait_for_timeout(900)
    for post in page.evaluate(EXTRACT_JS):
        key = post["text"][:160]
        if key not in collected or len(post["text"]) > len(collected[key]["text"]):
            collected[key] = post

    posts = []
    for post in collected.values():
        post["text"] = _clean(post["text"])
        post["author"] = _clean(post["author"])
        post["phones"] = _phones(post["text"])
        post["emails"] = _emails(post["text"])
        post["kind"] = _post_kind(post["text"])
        post["term"] = term
        post["group"] = gid
        posts.append(post)
    posts.sort(key=lambda x: -x["comments"])
    return {"group": gid, "term": term, "url": url,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "post_count": len(posts), "posts": posts}


# ---------------------------------------------------------------- pass 2: threads
COMMENTS_JS = """() => {
        const out = [];
        for (const el of document.querySelectorAll('[role="article"][aria-label]')) {
            const label = el.getAttribute('aria-label') || '';
            const m = label.match(/^(Comment|Reply) by (.+?)(?:\\s+\\d+\\s*(?:second|minute|hour|day|week|month|year|[smhdwy]).*)?$/i);
            if (!m) continue;
            let profile = '';
            for (const a of el.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (/\\/groups\\/\\d+\\/user\\/\\d+/.test(h) || /profile\\.php\\?id=\\d+/.test(h)) { profile = h; break; }
            }
            let body = '';
            const dirs = el.querySelectorAll('div[dir="auto"]');
            if (dirs.length) body = [...dirs].map(d => d.innerText || '').join('\\n');
            if (!body) body = el.innerText || '';
            out.push({kind: m[1], author: m[2].trim(), profile, text: body.slice(0, 1500)});
        }
        return out;
    }"""

EXPAND_JS = """() => {
        let n = 0;
        for (const b of document.querySelectorAll('div[role="button"], span[role="button"]')) {
            const t = (b.innerText || '').trim();
            if (/^(View|See) (\\d+ )?more (comments?|repl(y|ies))|^\\d+ (more )?repl(y|ies)$|^View (all )?\\d+ (previous |more )?(comments?|repl(y|ies))|^View hidden repl|^View previous comments|^See more$|^View more/i.test(t)) {
                try { b.click(); n++; } catch (e) {}
            }
        }
        return n;
    }"""

POST_JS = """() => {
        const el = document.querySelector('[data-ad-comet-preview="message"], [data-ad-preview="message"]');
        if (el) return el.innerText || '';
        for (const a of document.querySelectorAll('[role="article"]')) {
            if (!(a.getAttribute('aria-label') || '').match(/^(Comment|Reply) by/)) return (a.innerText || '').slice(0, 3000);
        }
        return '';
    }"""


def _abs(href: str) -> str:
    if href.startswith("http"):
        return href
    return "https://www.facebook.com" + href


def _post_id(permalink: str) -> str:
    m = re.search(r"/posts/(\d+)|permalink/(\d+)|multi_permalinks=(\d+)", permalink)
    return next((g for g in (m.groups() if m else ()) if g), "") or re.sub(r"\W+", "_", permalink)[-40:]


def _switch_to_all_comments(page) -> bool:
    """Facebook defaults to 'Most relevant', which hides most comments."""
    try:
        btn = page.locator('div[role="button"]:has-text("Most relevant"), span:has-text("Most relevant")').first
        if btn.count() == 0:
            return False
        btn.click(timeout=3000)
        page.wait_for_timeout(1200)
        item = page.locator('div[role="menuitem"]:has-text("All comments")').first
        if item.count():
            item.click(timeout=3000)
            page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


def _harvest_thread(page, gid: str, permalink: str) -> dict:
    url = _abs(permalink)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)
    if (b := _blocked(page)):
        raise RuntimeError(f"Facebook says: {b}")
    sorted_all = _switch_to_all_comments(page)
    try:
        page.mouse.move(700, 600)
    except Exception:
        pass
    post_text = _clean(page.evaluate(POST_JS))
    # Facebook VIRTUALISES the comment list too: after scrolling, the top comments leave
    # the DOM (20 present -> 14 read at the end on the probe). Accumulate every round.
    raw_by_key: dict[tuple, dict] = {}

    def _grab():
        for c in page.evaluate(COMMENTS_JS):
            raw_by_key.setdefault((c["author"], c["text"][:120]), c)

    _grab()
    quiet = 0
    for _ in range(40):
        n = page.evaluate(EXPAND_JS)
        page.wait_for_timeout(random.uniform(1200, 2000))
        _grab()
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(700)
        _grab()
        quiet = quiet + 1 if n == 0 else 0
        if quiet >= 3:
            break
    raw = list(raw_by_key.values())
    seen, comments = set(), []
    for c in raw:
        c["text"] = _clean(c["text"])
        key = (c["author"], c["text"][:120])
        if key in seen:
            continue
        seen.add(key)
        c["phones"] = _phones(c["text"])
        c["emails"] = _emails(c["text"])
        c["buyer_signal"] = bool(BUYER_RE.search(c["text"]))
        comments.append(c)
    return {"group": gid, "permalink": url, "post_id": _post_id(permalink),
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "sorted_all_comments": sorted_all, "post_text": post_text,
            "post_kind": _post_kind(post_text), "comment_count": len(comments),
            "comments": comments}



# ---------------------------------------------------------------- thread locator
# Search cards carry NO post href in the DOM (0 of 1,665 on the Charlotte harvest):
# Facebook materialises the timestamp link on hover. So to open a thread we
# re-find its card (phrase search first, the original term search as fallback),
# hover the timestamp anchor, read the href it grew - or click it and take the URL.
DATE_RE_JS = "/(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december| ago$|^\\d+\\s?[smhdwy]$)/i"

FIND_CARD_JS = """(needle) => {
        const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
        const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
        for (const c of cards) {
            if (!norm(c.innerText).includes(needle)) continue;
            c.scrollIntoView({block: 'center'});
            const isDate = a => DATE_RE.test(a.getAttribute('aria-label') || '');
            const ts = [...c.querySelectorAll('a[aria-label]')].filter(isDate);
            const anchors = ts.length ? ts : [...c.querySelectorAll('a')];
            for (const a of anchors) {
                for (const ev of ['pointerover', 'mouseover', 'mouseenter']) {
                    try { a.dispatchEvent(new MouseEvent(ev, {bubbles: true, cancelable: true})); } catch (e) {}
                }
            }
            return {found: true, tsCount: ts.length, anchors: anchors.length};
        }
        return {found: false, tsCount: 0, anchors: 0};
    }""".replace("DATE_RE", DATE_RE_JS)

READ_CARD_LINK_JS = """(needle) => {
        const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
        const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
        for (const c of cards) {
            if (!norm(c.innerText).includes(needle)) continue;
            for (const a of c.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (/\\/posts\\/\\d+|\\/permalink\\/\\d+|multi_permalinks=\\d+|story_fbid=\\d+/.test(h)) return {href: h, via: 'href'};
            }
            const html = c.outerHTML;
            const m = html.match(/\\/posts\\/(\\d+)/) || html.match(/multi_permalinks=(\\d+)/)
                   || html.match(/story_fbid=(\\d+)/) || html.match(/"post_id":"(\\d+)"/);
            if (m) return {href: '/posts/' + m[1] + '/', via: 'html'};
            return {href: '', via: 'none'};
        }
        return {href: '', via: 'nocard'};
    }"""

CLICK_COUNT_JS = """(needle) => {
        const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
        const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
        for (const c of cards) {
            if (!norm(c.innerText).includes(needle)) continue;
            c.scrollIntoView({block: 'center'});
            // The comment COUNT is a role=button labelled "Leave a comment" whose text is the
            // bare digits ("41"). Clicking it opens the post at /groups/<gid>/permalink/<id>/.
            const btns = [...c.querySelectorAll('[role="button"]')];
            const cnt = btns.filter(b => (b.getAttribute('aria-label')||'') === 'Leave a comment' && /^\\d[\\d,]*$/.test(norm(b.innerText)));
            if (cnt.length) { cnt[cnt.length - 1].click(); return 'count:' + norm(cnt[cnt.length - 1].innerText); }
            const digits = btns.filter(b => /^\\d[\\d,]*$/.test(norm(b.innerText)) && !/like|react/i.test(b.getAttribute('aria-label')||''));
            if (digits.length) { digits[digits.length - 1].click(); return 'digits:' + norm(digits[digits.length - 1].innerText); }
            return 'no-count-button';
        }
        return 'nocard';
    }"""

CLICK_TS_JS = """(needle) => {
        const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
        const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
        for (const c of cards) {
            if (!norm(c.innerText).includes(needle)) continue;
            const isDate = a => DATE_RE.test(a.getAttribute('aria-label') || '');
            const ts = [...c.querySelectorAll('a[aria-label]')].filter(isDate);
            if (ts.length) { ts[0].click(); return 'timestamp'; }
            const links = [...c.querySelectorAll('a[role="link"]')].filter(a => !/\\/user\\//.test(a.getAttribute('href')||''));
            if (links.length > 1) { links[1].click(); return 'link2'; }
            return 'none';
        }
        return 'nocard';
    }""".replace("DATE_RE", DATE_RE_JS)

DIALOG_LINK_JS = """() => {
        const d = document.querySelector('[role="dialog"]');
        if (!d) return '';
        for (const a of d.querySelectorAll('a[href]')) {
            const h = a.getAttribute('href') || '';
            if (/\\/posts\\/\\d+|\\/permalink\\/\\d+/.test(h)) return h;
        }
        return 'dialog-no-link';
    }"""


def _needle(post: dict) -> str:
    """A ~50-char slice of the post BODY (skip the author line) for card matching."""
    lines = [l for l in post["text"].split("\n") if l.strip()]
    body = " ".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")
    body = re.sub(r"[\u034f\u200b\u200e]", "", body)
    body = re.sub(r"\s+", " ", body).strip().lower()
    body = body.split(" see more")[0]
    return body[:50]


def _phrase(post: dict) -> str:
    lines = [l for l in post["text"].split("\n") if l.strip()]
    body = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
    body = re.split(r"\bSee more\b", body)[0]
    words = re.findall(r"[A-Za-z0-9$']+", body)[:8]
    return " ".join(words)


def _locate_thread(page, gid: str, post: dict) -> tuple[str, str]:
    """Return (permalink_url | 'DIALOG', how). Empty permalink = could not locate."""
    needle = _needle(post)
    if len(needle) < 12:
        return "", "needle-too-short"
    searches = [f'"{_phrase(post)}"'] + [t for t in post.get("terms", [post.get("term", "")]) if t]
    tried = set()
    for q in searches:
        if not q or q in tried:
            continue
        tried.add(q)
        url = f"https://www.facebook.com/groups/{gid}/search/?q={q.replace(' ', '%20')}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        if (b := _blocked(page)):
            raise RuntimeError(f"Facebook says: {b}")
        max_scroll = 4 if q.startswith('"') else 26
        for _ in range(max_scroll):
            r = page.evaluate(FIND_CARD_JS, needle)
            if r["found"]:
                page.wait_for_timeout(600)
                how = page.evaluate(CLICK_COUNT_JS, needle)
                page.wait_for_timeout(4500)
                if re.search(r"/posts/\d+|/permalink/\d+", page.url):
                    return page.url.split("?")[0], f"{how} q={q[:30]}"
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                link = page.evaluate(READ_CARD_LINK_JS, needle)
                if link["href"]:
                    return _abs(link["href"]), f"{link['via']} ts={r['tsCount']} q={q[:30]}"
                how = page.evaluate(CLICK_TS_JS, needle)
                page.wait_for_timeout(4500)
                cur = page.url
                if re.search(r"/posts/\d+|/permalink/\d+|multi_permalinks=\d+", cur):
                    return cur, f"click:{how} ts={r['tsCount']} q={q[:30]}"
                dlg = page.evaluate(DIALOG_LINK_JS)
                if dlg and dlg != "dialog-no-link":
                    return _abs(dlg), f"dialog ts={r['tsCount']} q={q[:30]}"
                if dlg == "dialog-no-link":
                    return "DIALOG", f"dialog-open click:{how} q={q[:30]}"
                break  # card found but nothing opened - try the next query
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(random.uniform(1800, 2600))
    return "", "not-found"


def _harvest_thread_here(page, gid: str, permalink: str) -> dict:
    """Comments from whatever post is open now (page or dialog)."""
    sorted_all = _switch_to_all_comments(page)
    for _ in range(14):
        n = page.evaluate(EXPAND_JS)
        page.wait_for_timeout(random.uniform(1500, 2500))
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(600)
        if n == 0:
            break
    post_text = _clean(page.evaluate(POST_JS))
    raw = page.evaluate(COMMENTS_JS)
    seen, comments = set(), []
    for c in raw:
        c["text"] = _clean(c["text"])
        c["author"] = _clean_author(c["author"], c["kind"])
        key = (c["author"], c["text"][:120])
        if key in seen:
            continue
        seen.add(key)
        c["phones"] = _phones(c["text"])
        c["emails"] = _emails(c["text"])
        seeking = bool(SEEKING_LENDER_RE.search(c["text"]))
        c["lender_signal"] = bool(LENDER_RE.search(c["text"])) and not seeking
        c["buyer_signal"] = (bool(BUYER_INTEREST_RE.search(c["text"])) or bool(BUYER_STRONG_RE.search(c["text"])) or seeking) and not c["lender_signal"]
        comments.append(c)
    return {"group": gid, "permalink": permalink, "post_id": _post_id(permalink) if permalink else "",
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "sorted_all_comments": sorted_all, "post_text": post_text,
            "post_kind": _post_kind(post_text), "comment_count": len(comments),
            "comments": comments}

# ---------------------------------------------------------------- commands
def cmd_probe(args) -> int:
    with sync_playwright() as p:
        ctx, page = _open(p, args.headless)
        for gid in args.groups:
            page.goto(f"https://www.facebook.com/groups/{gid}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            info = page.evaluate("""() => {
                const t = document.title;
                const body = (document.body.innerText || '');
                const btns = [...document.querySelectorAll('[role="button"], a[role="link"]')]
                    .map(b => (b.innerText||'').trim()).filter(x => /^(Join group|Joined|Invite|Visit|Cancel request|\\+ Invite)/i.test(x));
                const m = body.match(/([0-9.,]+[KM]?)\\s+members/i);
                const priv = /Private group/i.test(body) ? 'Private' : (/Public group/i.test(body) ? 'Public' : '?');
                return {title: t, buttons: [...new Set(btns)].slice(0, 8), members: m ? m[1] : '?', privacy: priv, url: location.href};
            }""")
            shot = OUTDIR / f"probe_{gid}.png"
            OUTDIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot))
            print(f"\n{gid}: {json.dumps(info, indent=1)}\n  screenshot: {shot}")
            (OUTDIR / f"probe_{gid}.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
            page.wait_for_timeout(2500)
        ctx.close()
    return 0


def cmd_harvest(args) -> int:
    terms = args.terms or TERMS
    with sync_playwright() as p:
        ctx, page = _open(p, args.headless)
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
                    data = _harvest_term(page, gid, term)
                    dest.write_text(json.dumps(data, indent=1), encoding="utf-8")
                    kinds = defaultdict(int)
                    for x in data["posts"]:
                        kinds[x["kind"]] += 1
                    print(f"[{gid} {i}/{len(terms)}] {term:<26} {data['post_count']:>3} posts  "
                          f"{dict(kinds)} -> {dest.name}", flush=True)
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


def _load_posts(gid: str) -> dict[str, dict]:
    """Unique posts across every term file, keyed by permalink (fallback text key)."""
    posts: dict[str, dict] = {}
    for f in (OUTDIR / gid).glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for post in data.get("posts", []):
            post["kind"] = _post_kind(post["text"])
            post["phones"] = _phones(post["text"])
            post["emails"] = _emails(post["text"])
            cnt = post.get("comments")
            post["comments"] = int(cnt) if isinstance(cnt, (int, float)) and cnt == cnt else 0
            key = post.get("permalink") or post["text"][:160]
            cur = posts.get(key)
            if cur is None:
                post = dict(post)
                post["terms"] = [post["term"]]
                posts[key] = post
            else:
                cur["terms"].append(post["term"])
                cur["comments"] = max(cur["comments"], post["comments"])
                if len(post["text"]) > len(cur["text"]):      # expanded beats truncated
                    cur["text"], cur["phones"], cur["emails"], cur["kind"] = post["text"], post["phones"], post["emails"], post["kind"]
    return posts


def _thread_targets(args):
    targets = []
    for gid in args.groups:
        for post in _load_posts(gid).values():
            if post["comments"] < args.min_comments:
                continue
            if post["kind"] == "other" and not args.all_kinds:
                continue
            targets.append((gid, post))
    targets = [t for t in targets if t[1]["kind"] != "lender"]
    rank = {"buyer_rollcall": 0, "deal_post": 1, "buyer_post": 2, "other": 3}
    targets.sort(key=lambda t: (rank[t[1]["kind"]], -t[1]["comments"]))
    if args.limit:
        targets = targets[: args.limit]
    return targets


def _thread_dest(gid: str, post: dict) -> Path:
    tdir = OUTDIR / gid / "threads"
    tdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", (post["author"] + " " + _needle(post))[:60].lower()).strip("_")
    return tdir / (slug + ".json")


def cmd_probe_links(args) -> int:
    targets = _thread_targets(args)[: args.limit or 3]
    with sync_playwright() as p:
        ctx, page = _open(p, args.headless)
        for gid, post in targets:
            t0 = time.time()
            try:
                pl, how = _locate_thread(page, gid, post)
            except Exception as exc:
                pl, how = "", f"ERR {type(exc).__name__}: {exc}"
            print(f"{post['kind']:<14} {post['comments']:>3}c  {post['author'][:28]:<28} -> {pl[:90] or '(none)'}  [{how}] {time.time()-t0:.0f}s")
            print(f"     needle={_needle(post)!r}  phrase={_phrase(post)!r}  url_now={page.url[:100]}")
            shot = OUTDIR / f"probe_links_{_post_id(pl) if pl and pl != 'DIALOG' else 'none'}.png"
            page.screenshot(path=str(shot))
            if pl:
                data = _harvest_thread_here(page, gid, "" if pl == "DIALOG" else pl)
                print(f"     comments captured: {data['comment_count']} (all-sort={data['sorted_all_comments']})")
                for c in data["comments"][:6]:
                    print(f"       - {c['kind']} {c['author'][:30]!r}: {c['text'][:90]!r} {c['phones']}")
        ctx.close()
    return 0


def cmd_threads(args) -> int:
    targets = _thread_targets(args)
    print(f"{len(targets)} thread(s) to open (min {args.min_comments} comments)")
    with sync_playwright() as p:
        ctx, page = _open(p, args.headless)
        done = failed = 0
        for i, (gid, post) in enumerate(targets, 1):
            dest = _thread_dest(gid, post)
            if dest.exists() and not args.force:
                print(f"[{i}/{len(targets)}] skip (have it) {dest.name}")
                continue
            t0 = time.time()
            try:
                pl, how = _locate_thread(page, gid, post)
                if not pl:
                    print(f"[{i}/{len(targets)}] NOT FOUND {post['kind']} {post['author'][:30]} [{how}]", flush=True)
                    failed += 1
                    continue
                if pl != "DIALOG" and not re.search(r"/posts/\d+|/permalink/\d+|multi_permalinks=\d+", page.url):
                    page.goto(pl, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(6000)
                data = _harvest_thread_here(page, gid, "" if pl == "DIALOG" else pl)
                data["search_kind"] = post["kind"]
                data["search_comments"] = post["comments"]
                data["search_author"] = post["author"]
                data["search_text"] = post["text"][:600]
                data["located_via"] = how
                dest.write_text(json.dumps(data, indent=1), encoding="utf-8")
                buyers = sum(1 for c in data["comments"] if c["buyer_signal"])
                print(f"[{i}/{len(targets)}] {post['kind']:<14} expected {post['comments']:>3}  got {data['comment_count']:>3} "
                      f"({buyers} buyer-signal) all={data['sorted_all_comments']} {time.time()-t0:.0f}s -> {dest.name}", flush=True)
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


# ---------------------------------------------------------------- build
NICKNAMES = {
    "mike": "michael", "bob": "robert", "rob": "robert", "bobby": "robert", "bill": "william", "will": "william", "billy": "william",
    "jim": "james", "jimmy": "james", "chris": "christopher", "dave": "david", "tom": "thomas", "tommy": "thomas", "tony": "anthony",
    "andy": "andrew", "drew": "andrew", "joe": "joseph", "joey": "joseph", "dan": "daniel", "danny": "daniel", "matt": "matthew",
    "nick": "nicholas", "ben": "benjamin", "sam": "samuel", "steve": "steven", "jon": "jonathan", "alex": "alexander", "rich": "richard",
    "rick": "richard", "dick": "richard", "ed": "edward", "eddie": "edward", "greg": "gregory", "jeff": "jeffrey", "ken": "kenneth",
    "kenny": "kenneth", "larry": "lawrence", "pat": "patrick", "tim": "timothy", "ron": "ronald", "don": "donald", "jerry": "gerald",
    "liz": "elizabeth", "beth": "elizabeth", "kate": "katherine", "katie": "katherine", "jen": "jennifer", "jenny": "jennifer",
    "sandy": "sandra", "becky": "rebecca", "debbie": "deborah", "sue": "susan", "peggy": "margaret", "maggie": "margaret",
    "charlie": "charles", "chuck": "charles", "frank": "francis", "hank": "henry", "jack": "john", "johnny": "john", "ray": "raymond",
    "russ": "russell", "stan": "stanley", "ted": "theodore", "vince": "vincent", "walt": "walter", "zach": "zachary", "josh": "joshua",
}


def _norm_name(n: str) -> str:
    n = re.sub(r"\(.*?\)", " ", n or "")
    n = re.sub(r"[^a-z ]+", " ", n.lower())
    toks = [t for t in n.split() if t not in {"llc", "inc", "the", "of", "jr", "sr", "ii", "iii"}]
    if toks:
        toks[0] = NICKNAMES.get(toks[0], toks[0])
    return " ".join(toks)


def _baseline() -> dict[str, str]:
    """Names already on Oren's Pensacola buyer sheets -> which sheet."""
    base: dict[str, str] = {}
    files = [
        (ROOT / "output" / "pensacola_3823_dispo_buyers_CALL_SHEET_v3_2026-08-26.csv", ["Buyer Name", "Contact", "Company"], "IB call sheet 8/26"),
        (ROOT / "output" / "pensacola_new_buyers_call_sheet_2026-09-03.csv", ["Buyer", "Person"], "new-buyer sheet 9/3"),
    ]
    for path, cols, label in files:
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                for c in cols:
                    v = _norm_name(row.get(c) or "")
                    if len(v) > 3:
                        base.setdefault(v, label)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(ROOT / "output" / "Escambia_FL_Buyer_Analysis.xlsx", read_only=True)
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            hdr = [str(h or "") for h in next(rows, [])]
            idx = [i for i, h in enumerate(hdr) if re.search(r"name|buyer|entity|decision|principal|owner", h, re.I)]
            for r in rows:
                for i in idx:
                    v = _norm_name(str(r[i]) if i < len(r) and r[i] else "")
                    if len(v) > 3:
                        base.setdefault(v, f"Escambia workbook/{ws.title}")
    except Exception:
        pass
    return base


def _match_base(name: str, base: dict[str, str]) -> str:
    n = _norm_name(name)
    if not n:
        return ""
    if n in base:
        return base[n]
    toks = n.split()
    if len(toks) >= 2:
        fl = f"{toks[0]} {toks[-1]}"
        for k, v in base.items():
            kt = k.split()
            if len(kt) >= 2 and f"{kt[0]} {kt[-1]}" == fl:
                return v
    return ""


def _criteria(texts) -> str:
    found = []
    for t in texts:
        for m in CRITERIA_RE.findall(t or ""):
            m = re.sub(r"\s+", " ", m).strip(" -\u2022*")
            if 8 <= len(m) <= 160 and m not in found:
                found.append(m)
    return " | ".join(found[:4])


def cmd_build(args) -> int:
    base = _baseline()
    people: dict[tuple[str, str], dict] = {}

    def rec_for(gid, name, profile):
        name = _clean_author(name)
        if not name or len(name) < 3 or name.lower() in {"facebook", "anonymous member", "anonymous participant", "group member"}:
            return None
        key = (_norm_name(name), "")
        rec = people.setdefault(key, {
            "Name": name, "Profile": "", "Groups": set(),
            "n_buyer_post": 0, "n_deal": 0, "n_rollcall": 0, "n_lender": 0, "n_other": 0,
            "n_rollcall_answer": 0, "n_deal_response": 0, "n_signal_comment": 0, "n_lender_comment": 0, "n_seller_comment": 0,
            "agent_hits": 0, "Phones": set(), "Emails": set(), "Texts": [], "Evidence": [], "Permalinks": [],
        })
        if profile and not rec["Profile"]:
            rec["Profile"] = _abs(profile)
        rec["Groups"].add(GROUPS_ALL.get(gid, gid).split(" (")[0])
        return rec

    def add_text(rec, text, permalink, phones, emails, front=False):
        rec["Phones"].update(phones)
        rec["Emails"].update(emails)
        rec["Texts"].append(text)
        ev = re.sub(r"\s+", " ", text).strip()[:240]
        if ev and ev not in rec["Evidence"]:
            rec["Evidence"].insert(0, ev) if front else rec["Evidence"].append(ev)
        pl = _abs(permalink) if permalink else ""
        if pl and pl not in rec["Permalinks"] and len(rec["Permalinks"]) < 3:
            rec["Permalinks"].append(pl)
        if AGENT_RE.search(text):
            rec["agent_hits"] += 1

    n_posts = n_threads = 0
    for gid in args.groups:
        for post in _load_posts(gid).values():
            n_posts += 1
            rec = rec_for(gid, post["author"], post.get("authorHref", ""))
            if rec is None:
                continue
            body = "\n".join(post["text"].split("\n")[1:]) or post["text"]
            k = post["kind"]
            rec["n_buyer_post" if k == "buyer_post" else "n_deal" if k == "deal_post" else "n_rollcall" if k == "buyer_rollcall"
                else "n_lender" if k == "lender" else "n_other"] += 1
            add_text(rec, body, post.get("permalink", ""), post["phones"], post["emails"], front=(k == "buyer_post"))
        tdir = OUTDIR / gid / "threads"
        for f in (tdir.glob("*.json") if tdir.exists() else []):
            th = json.loads(f.read_text(encoding="utf-8"))
            n_threads += 1
            author_n = _norm_name(th.get("search_author") or "")
            ctx_kind = th.get("search_kind") or th.get("post_kind") or "other"
            for c in th["comments"]:
                c["phones"] = _phones(c["text"])
                c["emails"] = _emails(c["text"])
                if _norm_name(c["author"]) == author_n or not c["author"]:
                    continue
                rec = rec_for(gid, c["author"], c.get("profile", ""))
                if rec is None:
                    continue
                if c.get("lender_signal"):
                    rec["n_lender_comment"] += 1
                    add_text(rec, c["text"], th["permalink"], c["phones"], c["emails"])
                    continue
                if SELLER_COMMENT_RE.search(c["text"]) and not BUYER_STRONG_RE.search(c["text"]):
                    rec["n_seller_comment"] += 1
                    add_text(rec, c["text"], th["permalink"], c["phones"], c["emails"])
                    continue
                has_contact = bool(c["phones"] or c["emails"])
                if BUYER_STRONG_RE.search(c["text"]):
                    rec["n_buyer_post"] += 1          # "we are an end buyer, actively buying" in a comment
                    if ctx_kind == "buyer_rollcall":
                        rec["n_rollcall_answer"] += 1
                elif ctx_kind == "buyer_rollcall" and (c["buyer_signal"] or has_contact):
                    rec["n_rollcall_answer"] += 1
                elif ctx_kind == "deal_post" and (c["buyer_signal"] or has_contact):
                    rec["n_deal_response"] += 1
                elif c["buyer_signal"]:
                    rec["n_signal_comment"] += 1
                else:
                    continue
                add_text(rec, c["text"], th["permalink"], c["phones"], c["emails"], front=True)

    rows = []
    for rec in people.values():
        strong = rec["n_buyer_post"] + rec["n_rollcall_answer"]
        sells = rec["n_deal"] + rec["n_rollcall"] + rec["n_seller_comment"]
        agent = rec["agent_hits"] >= 2 or (rec["agent_hits"] >= 1 and rec["n_rollcall_answer"] == 0 and rec["n_buyer_post"] <= 1)
        if rec["n_lender"] and strong == 0:
            cls, score = "LENDER (not a buyer)", 0
        elif sells and rec["n_buyer_post"] == 0 and rec["n_rollcall_answer"] == 0:
            cls, score = "WHOLESALER / AGENT (posts deals - co-wholesale or competitor)", 10 + min(sells, 5)
        elif strong and sells:
            cls, score = "BUYER who also wholesales", 40 + 10 * min(strong, 3)
        elif rec["n_rollcall_answer"]:
            cls, score = "CASH BUYER", 70 + 10 * min(rec["n_rollcall_answer"], 3)
        elif rec["n_buyer_post"] and not agent:
            cls, score = "CASH BUYER", 60 + 5 * min(rec["n_buyer_post"], 3)
        elif rec["n_buyer_post"] and agent:
            cls, score = "AGENT / SERVICE claiming to buy", 30
        elif rec["n_deal_response"]:
            cls, score = "DEAL RESPONDER (asked about a deal)", 45 + 5 * min(rec["n_deal_response"], 3)
        elif rec["n_signal_comment"]:
            cls, score = "POSSIBLE BUYER (weak comment signal)", 25
        elif rec["n_lender_comment"]:
            cls, score = "LENDER (not a buyer)", 0
        elif rec["n_seller_comment"]:
            cls, score = "WHOLESALER / AGENT (posts deals - co-wholesale or competitor)", 5
        else:
            continue
        flags = []
        if rec["agent_hits"]:
            flags.append("agent/wholesaler vocabulary")
        if rec["n_seller_comment"]:
            flags.append("seller talk in comments")
        if any(re.search(r"realtor|realty|kw\.com|exp", e) for e in rec["Emails"]):
            flags.append("realtor email")
        crit = _criteria(rec["Texts"][:6])
        score += 10 if rec["Phones"] else 0
        score += 8 if rec["Emails"] else 0
        score += 8 if crit else 0
        roles = []
        for k, lab in (("n_buyer_post", "buyer post"), ("n_rollcall_answer", "answered roll-call"), ("n_deal_response", "responded to deal"),
                       ("n_signal_comment", "buyer-signal comment"), ("n_deal", "posts deals"), ("n_rollcall", "asked for buyers"),
                       ("n_lender", "lender post"), ("n_lender_comment", "lender comment"), ("n_seller_comment", "seller-talk comment")):
            if rec[k]:
                roles.append(f"{lab} x{rec[k]}")
        rows.append({
            "Class": cls, "Score": score, "Name": rec["Name"], "Group": " + ".join(sorted(rec["Groups"])),
            "Phones": " | ".join(sorted(rec["Phones"])), "Emails": " | ".join(sorted(rec["Emails"])),
            "Criteria": crit, "Flags": "; ".join(flags), "Roles": "; ".join(roles), "Already On Sheet": _match_base(rec["Name"], base),
            "Evidence": " || ".join(rec["Evidence"][:3]), "Profile": rec["Profile"],
            "Permalinks": " | ".join(rec["Permalinks"]),
        })
    order = ["CASH BUYER", "BUYER who also wholesales", "DEAL RESPONDER (asked about a deal)", "POSSIBLE BUYER (weak comment signal)",
             "AGENT / SERVICE claiming to buy", "WHOLESALER / AGENT (posts deals - co-wholesale or competitor)", "LENDER (not a buyer)"]
    rows.sort(key=lambda r: (order.index(r["Class"]), -r["Score"], r["Name"]))
    label = "charlotte" if set(args.groups) == {CHARLOTTE_REI} else "pensacola"
    out = ROOT / "output" / f"{label}_fb_cash_buyers_{TODAY}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["Name"])
        w.writeheader()
        w.writerows(rows)
    by = defaultdict(int)
    for r in rows:
        by[r["Class"]] += 1
    print(f"posts={n_posts} threads={n_threads} people={len(rows)} -> {out}")
    for k in order:
        if by[k]:
            print(f"  {by[k]:>4}  {k}")
    buyers = [r for r in rows if r["Class"] in order[:3]]
    print(f"  {len(buyers):>4}  buyers total; {sum(1 for r in buyers if r['Phones'])} with phone, {sum(1 for r in buyers if r['Emails'])} with email, "
          f"{sum(1 for r in buyers if r['Already On Sheet'])} already on a sheet")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groups", nargs="+", default=list(GROUPS), help="numeric group ids")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--force", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    h = sub.add_parser("harvest")
    h.add_argument("--terms", nargs="+")
    for name in ("threads", "probe-links"):
        t = sub.add_parser(name)
        t.add_argument("--min-comments", type=int, default=3)
        t.add_argument("--limit", type=int, default=0)
        t.add_argument("--all-kinds", action="store_true", help="also open busy 'other' posts")
    sub.add_parser("build")
    args = ap.parse_args()
    return {"probe": cmd_probe, "harvest": cmd_harvest, "threads": cmd_threads,
            "probe-links": cmd_probe_links, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
