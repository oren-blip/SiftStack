"""One-off probe of a group PERMALINK page: what are the exact expander / sort labels,
and how many comments can we surface by clicking them? (41-comment roll-call thread.)"""
import json
import sys

from playwright.sync_api import sync_playwright

import fb_buyer_harvest as f

URL = "https://www.facebook.com/groups/630783891338311/permalink/1611234126626611/"

BUTTONS_JS = """() => {
    const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').trim();
    const seen = {};
    for (const b of document.querySelectorAll('[role="button"], [role="menuitem"]')) {
        const t = norm(b.innerText).slice(0, 40); const a = (b.getAttribute('aria-label')||'').slice(0, 40);
        const k = t + ' | ' + a; if (!t && !a) continue; seen[k] = (seen[k]||0) + 1;
    }
    return {buttons: seen,
            comments: document.querySelectorAll('[role="article"][aria-label^="Comment by"]').length,
            replies: document.querySelectorAll('[role="article"][aria-label^="Reply by"]').length,
            labels: [...document.querySelectorAll('[role="article"][aria-label]')].map(e => e.getAttribute('aria-label').slice(0, 70)).slice(0, 6)};
}"""

CLICK_TEXT_JS = """(pattern) => {
    const re = new RegExp(pattern, 'i');
    const norm = s => (s||'').replace(/[\\u034f\\u200b\\u200e]/g,'').replace(/\\s+/g,' ').trim();
    let n = 0;
    for (const b of document.querySelectorAll('[role="button"]')) {
        if (re.test(norm(b.innerText)) || re.test(b.getAttribute('aria-label')||'')) { try { b.click(); n++; } catch (e) {} }
    }
    return n;
}"""


def main():
    with sync_playwright() as p:
        ctx, page = f._open(p, False)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        st = page.evaluate(BUTTONS_JS)
        print("initial:", st["comments"], "comments,", st["replies"], "replies")
        print("labels:", st["labels"])
        print("buttons:", json.dumps({k: v for k, v in st["buttons"].items() if any(w in k.lower() for w in ("comment", "repl", "more", "relevant", "newest", "all", "view", "see"))}, indent=1))
        page.screenshot(path=str(f.OUTDIR / "permalink_probe_0.png"))

        # 1. sort control
        n = page.evaluate(CLICK_TEXT_JS, "most relevant|^top comments|^newest")
        page.wait_for_timeout(1500)
        menu = page.evaluate("""() => [...document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')].map(m => (m.innerText||'').trim().slice(0, 40))""")
        print("sort clicks:", n, "menu items:", menu)
        if menu:
            k = page.evaluate("""() => { for (const m of document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')) { if (/all comments/i.test(m.innerText||'')) { m.click(); return 'all'; } } return 'none'; }""")
            print("picked:", k)
            page.wait_for_timeout(3000)
        page.screenshot(path=str(f.OUTDIR / "permalink_probe_1.png"))

        # 2. expansion loop with scrolling
        for i in range(20):
            n = page.evaluate(CLICK_TEXT_JS, "^(view|see) (\\d+ )?more (comments?|replies)|^\\d+ (more )?repl(y|ies)|^view all \\d+|^view \\d+ (previous |more )?(comments|replies)|^see more$|previous comments|^view more")
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(2000)
            st = page.evaluate(BUTTONS_JS)
            print(f"round {i}: clicked {n} -> {st['comments']} comments, {st['replies']} replies")
            if n == 0 and i >= 2:
                break
        print("remaining expander-ish buttons:", json.dumps({k: v for k, v in st["buttons"].items() if any(w in k.lower() for w in ("comment", "repl", "more", "view"))}, indent=1))
        page.screenshot(path=str(f.OUTDIR / "permalink_probe_2.png"))
        data = f._harvest_thread_here(page, "630783891338311", URL)
        print("harvested:", data["comment_count"], "comments;", sum(1 for c in data["comments"] if c["buyer_signal"]), "buyer-signal;", sum(1 for c in data["comments"] if c["phones"] or c["emails"]), "with contact")
        for c in data["comments"][:40]:
            print(f"  - {c['kind']} {c['author'][:34]!r}: {c['text'][:70]!r} {c['phones']} {c['emails']}")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
