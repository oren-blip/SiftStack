"""Harvest contractor/vendor leads from a private Facebook group.

Phase 1 of the vendor-directory-builder skill. The group is login-walled, so this
drives a real browser with a persistent profile: you log in ONCE, the session is
reused for every later run.

    # one time: opens a browser, you log into Facebook, it saves the session
    python fb_group_harvest.py login

    # then, unattended: runs in-group search for every trade term
    python fb_group_harvest.py harvest
    python fb_group_harvest.py harvest --terms plumber electrician
    python fb_group_harvest.py harvest --headless        # after login works

Per the sourcing playbook: use the group's SEARCH url once per trade term rather
than scrolling the feed, harvest self-promoters (contact is in the post text) and
recommendation threads (the gold is in the comments), and record comment counts so
the richest threads can be opened later.

Output: output/fb_harvest/<term>.json  (resumable - existing terms are skipped)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".fb_profile"
OUTDIR = ROOT / "output" / "fb_harvest"
GROUP = "CharlotteRealEstateInvestors"

# Flip-crew taxonomy from references/use-case-taxonomies.md. Core trades first,
# then the specialty trades that are usually thin in a general investor group,
# then the niche/underground layer.
TERMS = [
    # core (~90% of a flip)
    "general contractor", "contractor", "handyman", "plumber", "plumbing",
    "electrician", "electrical", "hvac", "roofer", "roofing",
    "foundation", "waterproofing", "flooring", "painter", "painting",
    "drywall", "carpenter", "cabinets", "deck",
    # specialty
    "septic", "termite", "countertops", "dumpster", "junk removal",
    "cleanout", "landscaping", "tree removal", "pest control",
    # niche / underground
    "excavation", "grading", "water line", "survey",
    # recommendation-phrasing sweeps (catch threads the trade terms miss)
    "recommendation contractor", "who do you use", "looking for a contractor",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def _ctx(p, headless: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        str(PROFILE),
        headless=headless,
        viewport={"width": 1400, "height": 1000},
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
    )


def _logged_in(ctx, page=None) -> bool:
    """`c_user` is Facebook's session cookie: present only when logged in.

    Checking the cookie beats sniffing the DOM, which races the SPA render and
    changes whenever Facebook reshuffles its aria-labels.
    """
    try:
        for c in ctx.cookies():
            if c.get("name") == "c_user" and c.get("value"):
                return True
    except Exception:
        pass
    return False


def cmd_login(args) -> int:
    with sync_playwright() as p:
        ctx = _ctx(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        if _logged_in(ctx):
            print("Already logged in - session is saved. Run: python fb_group_harvest.py harvest")
            ctx.close()
            return 0
        print("\n" + "=" * 68)
        print("  A browser window is open. Log into Facebook in it.")
        print("  Finish any 2FA. You do NOT need to open the group.")
        print("  This window is yours - nothing is typed for you.")
        print("  Waiting up to 10 minutes, checking every 15s...")
        print("=" * 68 + "\n")
        deadline = time.time() + 600
        while time.time() < deadline:
            page.wait_for_timeout(15000)
            try:
                if _logged_in(ctx):
                    print("Logged in. Session saved to .fb_profile")
                    print("Now run: python fb_group_harvest.py harvest")
                    ctx.close()
                    return 0
            except Exception:
                pass
            print("  ...still waiting for login")
        print("Timed out waiting for login.")
        ctx.close()
        return 1


def _clean(text: str) -> str:
    """Strip Facebook's anti-scrape timestamp obfuscation.

    Post dates are rendered one character per line, each padded with an invisible
    COMBINING GRAPHEME JOINER (U+034F), so the card text carries a 60-line ladder of
    single letters that buries the actual post body. Drop the joiners, then drop the
    resulting one-character lines.
    """
    text = text.replace("͏", "").replace("​", "").replace("‎", "")
    keep, run = [], 0
    for line in text.split("\n"):
        line = line.strip()
        if len(line) <= 1:
            run += 1
            continue
        if run >= 6:          # a scrambled date ladder just ended; drop it entirely
            run = 0
        keep.append(line)
    return "\n".join(keep).strip()


# Facebook truncates a long post at "See more" and the hidden tail is NOT in the DOM
# text - which is where a lot of the phone numbers live ("Fence Staining 704.775.2785...
# See more"). Expand inline before extracting. Clicking the span expands in place; it
# does not navigate, so this is safe to fire on every card each round.
EXPAND_JS = """() => {
    let n = 0;
    for (const el of document.querySelectorAll('[role="button"], span, div')) {
        const t = (el.textContent || '').trim();
        if (t === 'See more' || t === '… See more' || t === '...See more') {
            try { el.click(); n++; } catch (e) {}
        }
    }
    return n;
}"""


EXTRACT_JS = """() => {
        const out = [];
        const seen = new Set();
        // The group SEARCH page renders results as [role="feed"] > div, while the
        // group FEED uses [role="article"]. Probed 2026-09-03: search returned
        // article=0 / feedKids=18, so keying on article alone harvested nothing.
        const nodes = [
            ...document.querySelectorAll('[role="feed"] > div'),
            ...document.querySelectorAll('[role="article"]'),
        ];
        for (const art of nodes) {
            // Drop the "Facebook" skeleton lines and other chrome-only rows.
            const txt = (art.innerText || '')
                .split('\\n')
                .filter(l => l.trim() && !['Facebook', 'Online status indicator',
                                           'Active', 'Shared post'].includes(l.trim()))
                .join('\\n')
                .trim();
            if (txt.length < 60) continue;
            const key = txt.slice(0, 160);
            if (seen.has(key)) continue;
            seen.add(key);
            let permalink = '';
            const hrefs = [];
            for (const a of art.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (h.includes('/groups/') && hrefs.length < 6) hrefs.push(h);
                if (!permalink && (h.includes('/posts/') || h.includes('permalink') ||
                    h.includes('multi_permalinks'))) permalink = h;
            }
            const lines = txt.split('\\n').map(s => s.trim()).filter(Boolean);
            // Engagement renders as bare digits in the card footer ("Shared post/6/27"),
            // NOT as "12 comments" - that regex matched nothing on every card.
            const trailing = [];
            for (let i = lines.length - 1; i >= 0 && trailing.length < 4; i--) {
                const l = lines[i];
                if (/^[0-9][0-9,]*$/.test(l)) trailing.unshift(parseInt(l.replace(/,/g,''), 10));
                else if (l !== 'Shared post' && !/^Comment as/.test(l)) break;
            }
            // Guarded: an unanchored "<number> comments" match reads a Charlotte ZIP
            // followed by a Comment line as 28,269 comments. Cap at something a group
            // thread can plausibly reach, else fall through to the footer digits.
            let m = txt.match(/([0-9,]+)\\s+comments?/i);
            if (m && parseInt(m[1].replace(/,/g, ''), 10) > 2000) m = null;
            out.push({
                text: txt.slice(0, 4000),
                permalink,
                hrefs,
                // explicit "N comments" wins; otherwise the largest footer number is
                // the best available proxy for a busy thread
                // Footer order is reactions-then-comments ("181 / 28"), so the LAST
                // number is the comment count. Taking the max overstated it 6x.
                comments: m ? parseInt(m[1].replace(/,/g, ''), 10)
                            : (trailing.length ? trailing[trailing.length - 1] : 0),
                engagement: trailing,
                author: lines[0] || '',
                subline: (lines[1] && lines[1].length < 80) ? lines[1] : '',
            });
        }
        return out;
    }"""


# --- comment-thread pass -------------------------------------------------------
# Method validated by siftstack-11 on 2026-09-03. There is no permalink anywhere in a
# search card's HTML, but the comment-count control is a role=button labelled "Leave a
# comment"; clicking it opens the post in a dialog AND puts the real permalink in the
# address bar. Hovering the timestamp does NOT work - that was the first guess and it
# grows no link.
CLICK_COMMENTS_JS = """(snippet) => {
    // The snippet has had punctuation stripped (quotes and commas break Facebook's
    // phrase search), so the card text must be normalised the same way before
    // comparing - matching raw innerText against a stripped snippet silently missed
    // every post whose opening line contained a comma.
    const norm = s => (s || '').replace(/[^\\w\\s]/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
    const want = norm(snippet);
    const cards = document.querySelectorAll('[role="feed"] > div, [role="article"]');
    const tried = [];
    for (const art of cards) {
        if (!norm(art.innerText).includes(want)) continue;
        for (const b of art.querySelectorAll('[role="button"]')) {
            const lab = (b.getAttribute('aria-label') || '');
            if (lab.startsWith('Leave a comment')) { b.click(); return {ok: true}; }
            if (lab && tried.length < 10) tried.push(lab.slice(0, 40));
        }
        return {ok: false, matched: true, labels: tried};
    }
    return {ok: false, matched: false, cards: cards.length};
}"""

# Expanders are plain buttons. The pattern is deliberately wide: siftstack-11 measured
# only 52% of claimed comments captured on Pensacola, with the WORST losses on the
# busiest threads (145 claimed -> 19 captured) and three threads returning zero, and
# traced it to expander controls that were never clicked. Anything unmatched is
# reported back as `leftovers` so the misses are diagnosable instead of invisible.
EXPAND_COMMENTS_JS = """() => {
    let n = 0;
    const leftovers = [];
    const HIT = /^(view|see|show)\\s+(all\\s+)?(\\d[\\d,]*\\s+)?(more\\s+)?(comments?|repl(y|ies)|hidden\\s+(comments?|replies)|previous\\s+comments?)/i;
    const MAYBE = /(comment|repl(y|ies))/i;
    for (const b of document.querySelectorAll('[role="button"], div[tabindex="0"], span[role="button"]')) {
        const t = (b.textContent || '').trim();
        if (!t || t.length > 60) continue;
        if (HIT.test(t.replace(/\\s+/g, ' '))) {
            try { b.click(); n++; } catch (e) {}
        } else if (MAYBE.test(t) && !/^(Comment as|Like|Share|Reply)$/i.test(t)) {
            if (leftovers.length < 12 && !leftovers.includes(t)) leftovers.push(t);
        }
    }
    return {clicked: n, leftovers: leftovers};
}"""

# Comments are role=article, labelled "Comment by <name>" / "Reply by <name> to <name>".
READ_COMMENTS_JS = """() => {
    const out = [];
    for (const c of document.querySelectorAll('[role="article"]')) {
        const lab = c.getAttribute('aria-label') || '';
        if (!/^(Comment|Reply) by /.test(lab)) continue;
        // Collect EVERY (link text, uid) pair and let Python pick the one whose text
        // matches the author from the aria-label. Taking the first /user/ link was
        // wrong: in a reply, Facebook renders the replied-to person's mention link
        // first, so the captured uid belonged to the person being replied to. That
        // produced fake aliasing - "Tony Reed" appeared to own five accounts - and it
        // fails in both directions, either inventing independence or destroying it.
        let author = '';
        const links = [];
        for (const a of c.querySelectorAll('a[href*="/user/"], a[href*="/groups/"]')) {
            const t = (a.textContent || '').trim();
            const h = a.getAttribute('href') || '';
            const m = h.match(/\\/user\\/(\\d+)\\//);
            if (m) links.push({text: t, uid: m[1], profile: h.split('?')[0]});
            if (t && t.length < 60 && !author) { author = t; }
        }
        out.push({
            label: lab.slice(0, 120),
            author: author,
            links: links.slice(0, 8),
            text: (c.innerText || '').trim().slice(0, 2000),
        });
    }
    return out;
}"""


def _harvest_thread(page, post: dict) -> dict | None:
    """Open one post's comments and read every commenter."""
    # The stored text OPENS with the poster's name and often a business-page subline,
    # so the naive first-eight-words phrase was "Michael Cox I need a contractor that"
    # - a quoted search for that matches nothing, which is why every re-find failed.
    # Search on the first substantial line of the BODY instead.
    lines = [l for l in _clean(post["text"]).split("\n") if l.strip()]
    author = (post.get("author") or "").strip()
    body = [l for l in lines if l.strip() != author and l.strip() != post.get("subline", "")]
    phrase = next((l for l in body if len(l) > 40), body[0] if body else "")
    # Quotes and punctuation break the phrase search; keep plain words only.
    words = " ".join(re.sub(r"[^\w\s]", " ", phrase).split()[:8])
    if len(words) < 15:
        return None
    # Try the quoted phrase first, then unquoted, then a shorter stem: Facebook's
    # phrase search is fuzzy and a long quoted string often returns nothing at all.
    short = " ".join(words.split()[:5])
    hit = None
    for query in (f"%22{words.replace(' ', '%20')}%22",
                  words.replace(" ", "%20"),
                  short.replace(" ", "%20")):
        page.goto(f"https://www.facebook.com/groups/{GROUP}/search/?q={query}",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        page.evaluate(EXPAND_JS)
        page.wait_for_timeout(800)
        hit = page.evaluate(CLICK_COMMENTS_JS, short)
        if hit.get("ok"):
            break
    if not hit or not hit.get("ok"):
        print(f"      no-open: {hit}")
        return None
    page.wait_for_timeout(4000)
    permalink = page.url

    # The comment list is virtualised exactly like the feed, so accumulate per scroll.
    seen: dict[str, dict] = {}
    box = page.viewport_size or {"width": 1400, "height": 1000}
    page.mouse.move(box["width"] // 2, box["height"] // 2)   # scroll the DIALOG, not the page
    leftovers: set[str] = set()
    quiet = 0
    # 30 rounds, not 12. The measured failure mode is stopping while expanders remain,
    # and it hurts the busiest threads worst - which are the only ones worth opening.
    for _ in range(30):
        try:
            res = page.evaluate(EXPAND_COMMENTS_JS)
            clicked = res.get("clicked", 0)
            leftovers.update(res.get("leftovers", []))
            page.wait_for_timeout(1500 if clicked else 700)
            before = len(seen)
            for c in page.evaluate(READ_COMMENTS_JS):
                c["text"] = _clean(c["text"])
                seen.setdefault(c["text"][:120], c)
        except Exception:
            break
        # Only stop once nothing expands AND nothing new is being read, several rounds
        # running - a single quiet round is usually just the next batch still loading.
        quiet = quiet + 1 if (clicked == 0 and len(seen) == before) else 0
        if quiet >= 4:
            break
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(random.uniform(1400, 2000))

    phone_re = re.compile(r"(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})\b")
    comments = list(seen.values())
    for c in comments:
        c["phones"] = sorted({"-".join(g) for g in phone_re.findall(c["text"])})
        # The aria-label is the reliable author source, but a reply reads
        # "Reply by A to B's comment" - keeping the tail would credit the referral to
        # the person being replied to rather than the person making it.
        name = re.sub(r"^(Comment|Reply) by ", "", c.get("label", ""))
        name = name.split(" to ")[0].strip()
        # The label ends with a relative timestamp ("Kristina Solara 3 years ago"),
        # which would otherwise become part of the referrer's name.
        # Covers "3y", "3 years ago" AND the wordy "a year ago" - without the a/an
        # branch, "CharLit Paintings a year ago" survives as a separate name and the
        # same account reads as two independent vouches for its own number.
        name = re.sub(r"\s+(\d+|an?)\s*(y|m|d|w|h|yr|mo|sec|min)s?\b.*$", "", name, flags=re.I)
        name = re.sub(r"\s+(\d+|an?)\s+(year|month|week|day|hour|minute|second)s?\s+ago.*$",
                      "", name, flags=re.I).strip()
        if name:
            c["author"] = name
        # A top-level comment and a reply are different evidence. Two comments naming
        # the same vendor are two vouches; a vendor replying under a second account is
        # one self-promo. Without this, cross-validation counts the self-promo twice.
        lab = c.get("label", "")
        c["is_reply"] = lab.startswith("Reply by")
        m = re.search(r" to (.+?)(?:'s comment|’s comment|$)", lab)
        c["reply_to"] = m.group(1).strip() if (c["is_reply"] and m) else ""
        # Bind the uid to the AUTHOR's own link, matched on the label-derived name.
        # If no link matches, leave it EMPTY - an absent uid is honest, a guessed one
        # silently corrupts every identity conclusion built on top of it.
        c["uid"] = c["profile"] = ""
        want = (c.get("author") or "").strip().lower()
        for ln in c.get("links", []):
            if want and (ln.get("text", "").strip().lower() == want):
                c["uid"], c["profile"] = ln.get("uid", ""), ln.get("profile", "")
                break
        c.pop("links", None)
    return {
        "post_author": post.get("author", ""),
        "post_text": post["text"][:1500],
        "permalink": permalink,
        "claimed_comments": post.get("comments", 0),
        "captured": len(comments),
        "with_phone": sum(1 for c in comments if c["phones"]),
        # Button labels that mention comments/replies but matched no expander pattern.
        # A thread that captures well below its claimed count should be diagnosed here
        # first - it names the control that was never clicked.
        "unclicked_labels": sorted(leftovers),
        "comments": comments,
    }


def cmd_refresh(args) -> int:
    """Re-open specific thread files in place, to add fields they predate.

    Named files are rewritten under their EXISTING names rather than a fresh hash,
    because downstream work refers to them by name; a rename would orphan those
    references. Used to backfill `uid`, which only the newer harvests capture and
    which is the only reliable defence against one person using two display names.
    """
    out_dir = OUTDIR / "threads"
    wanted = []
    for name in args.files:
        f = out_dir / (name if name.endswith(".json") else name + ".json")
        if not f.is_file():
            print(f"  missing: {f.name}")
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        wanted.append((f, d))
    print(f"refreshing {len(wanted)} thread file(s) in place\n")

    ok = miss = 0
    with sync_playwright() as pw:
        ctx = _ctx(pw, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        if not _logged_in(ctx):
            print("NOT LOGGED IN. Run: python fb_group_harvest.py login")
            ctx.close()
            return 2
        for i, (f, d) in enumerate(wanted, 1):
            post = {"text": d.get("post_text", ""), "author": d.get("post_author", ""),
                    "comments": d.get("claimed_comments", 0), "subline": ""}
            try:
                res = _harvest_thread(page, post)
            except Exception as exc:
                print(f"[{i}/{len(wanted)}] ERROR {f.name}: {type(exc).__name__}: {exc}")
                miss += 1
                continue
            if not res:
                print(f"[{i}/{len(wanted)}] could not re-open {f.name} (kept existing)")
                miss += 1
                continue
            with_uid = sum(1 for c in res["comments"] if c.get("uid"))
            f.write_text(json.dumps(res, indent=1), encoding="utf-8")
            print(f"[{i}/{len(wanted)}] {f.name:<34} {res['captured']:>3} comments, "
                  f"{with_uid} with uid")
            ok += 1
        ctx.close()
    print(f"\nrefreshed {ok}, failed {miss}")
    return 0


def cmd_threads(args) -> int:
    """Open the busiest recommendation threads and read their comments."""
    out_dir = OUTDIR / "threads"
    out_dir.mkdir(parents=True, exist_ok=True)

    best: list[tuple[int, str, dict]] = []
    for f in sorted(SRC_GLOB()):
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in data.get("posts", []):
            # Files harvested before the ZIP guard can carry a bogus count (a Charlotte
            # 28269 read as 28,269 comments). Fall back to the footer digits, which are
            # stored raw, rather than re-harvesting every term to fix a sort key.
            n = p.get("comments", 0)
            if n > 2000:
                eng = [e for e in (p.get("engagement") or []) if e <= 2000]
                n = eng[-1] if eng else 0
                p = {**p, "comments": n}
            if n >= args.min_comments:
                best.append((n, f.stem, p))

    # Raw comment count picks the loudest thread, not the useful one - the top three
    # by count were community drama ("a guy living in his car in front of my rental"),
    # which yielded 460 captured comments and zero vendor names. What we actually want
    # is a REFERRAL REQUEST about a trade: "anyone know a good plumber?". Rank those
    # first, and only fall back to raw count once they run out.
    ASK = re.compile(r"\b(looking for|anyone (know|have|use|recommend)|recommend|"
                     r"who (do you|does everyone|can|should)|need a|suggestions|"
                     r"referral|any good)\b", re.I)
    TRADE = re.compile(r"\b(contractor|handyman|plumb|electric|hvac|roof|foundation|"
                       r"crawl|flooring|floor|paint|drywall|carpent|cabinet|deck|septic|"
                       r"termite|countertop|dumpster|junk|landscap|tree|pest|excavat|"
                       r"grading|survey|concrete|gutter|fence|mason)", re.I)

    # Broad requests beat single-trade ones. Measured over 49 threads: the
    # who_do_you_use_* threads added 5, 6 and 9 new business names against a much
    # lower median, while single-trade asks in already-saturated categories
    # (survey, pest control, a second "looking for a contractor") added ZERO.
    # Breadth = how many distinct trades the post touches, plus an explicit bonus
    # for roll-call phrasing.
    BROAD = re.compile(r"\b(who do you use|who does everyone|go[- ]to (guy|person|list)|"
                       r"list of|your (team|crew|people)|recommendations? for|"
                       r"any(one)? (good|reliable)|building (a|my) (team|list)|"
                       r"subcontractors?|trades?people|vendors?)\b", re.I)

    def breadth(text: str) -> int:
        trades = {m.group(0).lower() for m in TRADE.finditer(text)}
        return len(trades) + (3 if BROAD.search(text) else 0)

    def rank(item):
        n, _stem, p = item
        t = p["text"]
        referral = bool(ASK.search(t)) and bool(TRADE.search(t))
        return (0 if referral else 1, -breadth(t), -n)

    best.sort(key=rank)
    referral_n = sum(1 for it in best if rank(it)[0] == 0)
    print(f"{referral_n} of {len(best)} candidate threads look like trade referral "
          f"requests; those are opened first")
    seen_text = set()
    picked = []
    for n, stem, p in best:
        k = p["text"][:120]
        if k in seen_text:
            continue
        seen_text.add(k)
        picked.append((n, stem, p))
        if len(picked) >= args.limit:
            break

    print(f"{len(picked)} threads to open (>= {args.min_comments} comments)\n")
    with sync_playwright() as pw:
        ctx = _ctx(pw, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        if not _logged_in(ctx):
            print("NOT LOGGED IN. Run: python fb_group_harvest.py login")
            ctx.close()
            return 2
        # Skip by POST CONTENT, not by filename. Filenames were position-based, so any
        # change to the ranking shifted every index and would have re-harvested threads
        # already on disk under new names - duplicating work and double-counting vouches
        # downstream. The name now carries a stable hash of the post.
        done_texts = set()
        for f in out_dir.glob("*.json"):
            try:
                done_texts.add(json.loads(f.read_text(encoding="utf-8"))
                               .get("post_text", "")[:120])
            except Exception:
                pass

        ok = miss = 0
        for i, (n, stem, p) in enumerate(picked, 1):
            key = hashlib.sha1(p["text"][:160].encode("utf-8")).hexdigest()[:8]
            dest = out_dir / f"{stem}_{key}.json"
            if (dest.exists() or p["text"][:120] in done_texts) and not args.force:
                print(f"[{i}/{len(picked)}] skip (already harvested)")
                continue
            try:
                res = _harvest_thread(page, p)
            except Exception as exc:
                print(f"[{i}/{len(picked)}] ERROR {stem}: {type(exc).__name__}: {exc}")
                miss += 1
                continue
            if not res:
                print(f"[{i}/{len(picked)}] could not re-find/open ({n} comments) {stem}")
                miss += 1
                continue
            dest.write_text(json.dumps(res, indent=1), encoding="utf-8")
            print(f"[{i}/{len(picked)}] {stem:<26} claimed {n:>3} -> captured "
                  f"{res['captured']:>3} comments, {res['with_phone']} with a phone")
            ok += 1
        ctx.close()
    print(f"\nopened {ok}, failed {miss}. Files in {out_dir}")
    return 0


def SRC_GLOB():
    return [f for f in OUTDIR.glob("*.json")]


def _harvest_term(page, term: str) -> dict:
    url = f"https://www.facebook.com/groups/{GROUP}/search/?q={term.replace(' ', '%20')}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)

    # Facebook renders a skeleton first: every result card is the literal word
    # "Facebook" repeated until it hydrates. Scrolling alone is not enough - wait
    # until cards carry real text, or the harvest captures placeholders.
    def _hydrated() -> int:
        return page.evaluate(
            """() => {
                let n = 0;
                for (const d of document.querySelectorAll('[role="feed"] > div')) {
                    const t = (d.innerText || '').replace(/Facebook/g, '').trim();
                    if (t.length > 120) n++;
                }
                return n;
            }"""
        )

    # The results feed is VIRTUALISED: Facebook drops cards from the DOM once they
    # scroll out of view, so reading the DOM once at the end returns only the last
    # visible handful (three different posts on three consecutive runs). Extract
    # after every scroll and accumulate instead.
    MIN_SCROLLS, MAX_SCROLLS = 12, 30
    collected: dict[str, dict] = {}
    stale_rounds = 0
    for i in range(MAX_SCROLLS):
        try:
            if page.evaluate(EXPAND_JS):
                page.wait_for_timeout(900)   # let the expanded text paint
        except Exception:
            pass
        for post in page.evaluate(EXTRACT_JS):
            key = post["text"][:160]
            if key not in collected:
                collected[key] = post
        before = len(collected)
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(random.uniform(2200, 3200))
        stale_rounds = stale_rounds + 1 if len(collected) == before else 0
        if i + 1 >= MIN_SCROLLS and stale_rounds >= 5:
            break
    for post in page.evaluate(EXTRACT_JS):
        collected.setdefault(post["text"][:160], post)
    posts = list(collected.values())


    # Capture the three groups so the number can be normalised: matching the whole
    # span kept stray punctuation ("(704-281-2867") that would break a dial list.
    phone_re = re.compile(r"(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})\b")
    for post in posts:
        post["text"] = _clean(post["text"])
        post["author"] = _clean(post["author"])
        post["phones"] = sorted({"-".join(g) for g in phone_re.findall(post["text"])})
        post["term"] = term
    posts.sort(key=lambda x: -x["comments"])
    return {
        "term": term,
        "url": url,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "post_count": len(posts),
        "posts": posts,
    }


def cmd_harvest(args) -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    terms = args.terms or TERMS
    with sync_playwright() as p:
        ctx = _ctx(p, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # Navigate before reading cookies: Chromium populates the cookie jar for a
        # domain lazily, so a cold ctx.cookies() looks empty even with a live session.
        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
        except Exception as exc:
            print(f"could not reach facebook.com: {exc}")
        if not _logged_in(ctx):
            print("NOT LOGGED IN. Run first:  python fb_group_harvest.py login")
            print(f"  (cookies seen: {sorted({c['name'] for c in ctx.cookies()})[:12]})")
            ctx.close()
            return 2

        done = failed = 0
        for i, term in enumerate(terms, 1):
            dest = OUTDIR / (re.sub(r"[^a-z0-9]+", "_", term.lower()) + ".json")
            if dest.exists() and not args.force:
                print(f"[{i}/{len(terms)}] skip (have it)  {term}")
                continue
            try:
                data = _harvest_term(page, term)
                dest.write_text(json.dumps(data, indent=1), encoding="utf-8")
                rich = sum(1 for x in data["posts"] if x["comments"] >= 3)
                print(f"[{i}/{len(terms)}] {term:<26} {data['post_count']:>3} posts, "
                      f"{rich} with 3+ comments -> {dest.name}")
                done += 1
            except Exception as exc:
                print(f"[{i}/{len(terms)}] FAILED {term}: {type(exc).__name__}: {exc}")
                failed += 1
            page.wait_for_timeout(random.uniform(2500, 4500))
        ctx.close()
    print(f"\nHarvested {done} term(s), {failed} failed. Files in {OUTDIR}")
    return 1 if failed and not done else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    h = sub.add_parser("harvest")
    h.add_argument("--terms", nargs="+", help="only these search terms")
    h.add_argument("--headless", action="store_true")
    h.add_argument("--force", action="store_true", help="re-harvest terms already saved")
    t = sub.add_parser("threads", help="open the busiest threads and read their comments")
    t.add_argument("--min-comments", type=int, default=10)
    t.add_argument("--limit", type=int, default=40)
    t.add_argument("--headless", action="store_true")
    t.add_argument("--force", action="store_true")
    r = sub.add_parser("refresh", help="re-open named thread files in place")
    r.add_argument("files", nargs="+", metavar="FILE")
    r.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    if args.cmd == "login":
        return cmd_login(args)
    if args.cmd == "refresh":
        return cmd_refresh(args)
    return cmd_threads(args) if args.cmd == "threads" else cmd_harvest(args)


if __name__ == "__main__":
    sys.exit(main())
