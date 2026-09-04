"""One-off DOM probe: how do we open the comments of a search-result card?

Hovering the timestamp grew no href (probe-links 23:41). So dump the card's anchors
and buttons, then try the two in-card controls that should open comments: the
comment-count digits and the "Comment" button. Report what appears in the DOM.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

import fb_buyer_harvest as f

OUT = f.OUTDIR
DUMP_JS = """(needle) => {
    const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
    const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
    for (const c of cards) {
        if (!norm(c.innerText).includes(needle)) continue;
        c.scrollIntoView({block: 'center'});
        const anchors = [...c.querySelectorAll('a')].map(a => ({
            href: (a.getAttribute('href')||'').slice(0, 90), aria: (a.getAttribute('aria-label')||'').slice(0, 50),
            role: a.getAttribute('role')||'', text: norm(a.innerText).slice(0, 30)}));
        const buttons = [...c.querySelectorAll('[role="button"]')].map(b => ({
            text: norm(b.innerText).slice(0, 40), aria: (b.getAttribute('aria-label')||'').slice(0, 50)}));
        const labels = [...c.querySelectorAll('[aria-label]')].map(e => e.tagName + ':' + (e.getAttribute('aria-label')||'').slice(0, 50));
        return {anchors, buttons, labels: labels.slice(0, 60), abbr: c.querySelectorAll('abbr').length,
                html_ids: (c.outerHTML.match(/\\d{15,17}/g) || []).slice(0, 12)};
    }
    return null;
}"""

CLICK_JS = """([needle, mode]) => {
    const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').toLowerCase();
    const cards = [...document.querySelectorAll('[role="feed"] > div'), ...document.querySelectorAll('[role="article"]')];
    for (const c of cards) {
        if (!norm(c.innerText).includes(needle)) continue;
        const btns = [...c.querySelectorAll('[role="button"]')];
        if (mode === 'count') {
            const digits = btns.filter(b => /^\\d[\\d,]*$/.test(norm(b.innerText)) || /comments?$/.test(norm(b.innerText)));
            if (!digits.length) return 'no-count-button';
            digits[digits.length - 1].click(); return 'clicked:' + norm(digits[digits.length - 1].innerText);
        }
        if (mode === 'comment') {
            const b = btns.find(x => norm(x.innerText) === 'comment' || (x.getAttribute('aria-label')||'') === 'Leave a comment');
            if (!b) return 'no-comment-button';
            b.click(); return 'clicked:comment';
        }
        if (mode === 'aria-comments') {
            const el = [...c.querySelectorAll('[aria-label]')].find(x => /comment/i.test(x.getAttribute('aria-label')||'') && !/^Leave a comment$/.test(x.getAttribute('aria-label')||''));
            if (!el) return 'no-aria';
            el.click(); return 'clicked-aria:' + el.getAttribute('aria-label');
        }
    }
    return 'nocard';
}"""

STATE_JS = """() => ({
    url: location.href.slice(0, 120),
    dialog: !!document.querySelector('[role="dialog"]'),
    dialogLabel: (document.querySelector('[role="dialog"]')||{getAttribute:()=>''}).getAttribute('aria-label') || '',
    commentArticles: document.querySelectorAll('[role="article"][aria-label^="Comment by"], [role="article"][aria-label^="Reply by"]').length,
    anyCommentLabel: [...document.querySelectorAll('[aria-label]')].filter(e => /^Comment by/i.test(e.getAttribute('aria-label'))).length,
    postLinks: [...document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]')].map(a => a.getAttribute('href').slice(0, 80)).slice(0, 4),
    sortBtn: [...document.querySelectorAll('[role="button"]')].filter(b => /most relevant|all comments|newest/i.test(b.innerText||'')).map(b => (b.innerText||'').trim().slice(0, 30)).slice(0, 3),
})"""


def main():
    gid = "630783891338311"
    posts = [p for p in f._load_posts(gid).values() if p["kind"] == "buyer_rollcall" and p["comments"] >= 5]
    posts.sort(key=lambda p: -p["comments"])
    post = posts[0]
    needle = f._needle(post)
    print("target:", post["author"], post["comments"], "comments | needle:", needle)
    with sync_playwright() as p:
        ctx, page = f._open(p, False)
        q = f'"{f._phrase(post)}"'
        page.goto(f"https://www.facebook.com/groups/{gid}/search/?q={q.replace(' ', '%20')}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        for _ in range(4):
            dump = page.evaluate(DUMP_JS, needle)
            if dump:
                break
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(2000)
        if not dump:
            print("card not found")
            ctx.close()
            return 1
        print(json.dumps(dump, indent=1)[:6000])
        page.screenshot(path=str(OUT / "dom_probe_card.png"))
        for mode in ("count", "comment", "aria-comments"):
            r = page.evaluate(CLICK_JS, [needle, mode])
            page.wait_for_timeout(4000)
            st = page.evaluate(STATE_JS)
            print(f"\n[{mode}] {r} -> {json.dumps(st)}")
            page.screenshot(path=str(OUT / f"dom_probe_{mode}.png"))
            if st["commentArticles"] or st["anyCommentLabel"]:
                # try expanding + reading with the harvester's own routines
                data = f._harvest_thread_here(page, gid, "")
                print(f"   harvested {data['comment_count']} comments, all-sort={data['sorted_all_comments']}")
                for c in data["comments"][:8]:
                    print(f"     - {c['kind']} {c['author'][:28]!r}: {c['text'][:80]!r} {c['phones']} {c['profile'][:50]}")
                break
            if st["dialog"]:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1500)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
