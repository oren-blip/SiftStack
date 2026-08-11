"""One-off: fix the Smith 26E002810-590 DataSift record (Week 31).

The matcher attached the WRONG Donald Smith's house (1308 Eagles Landing Dr,
owner DONALD SMITH | DENISE RICHARDS-SMITH) and the first upload (7/29) even
promoted the stranger's wife Denise as owner/contact. The decedent Donald
Corben Smith's real parcel is 3611 Daisyfield Dr Charlotte 28104 (PID
02770115, DONALD C SMITH | LINDA F SMITH, $331,300) — it sat in the row's
own Notes as the +1 sibling. Court PR: Sandy Smith, court phone 7043616316
already pushed onto the record.

Modes:
    python fix_smith_record.py --probe    # find record, dump page structure, no changes
    python fix_smith_record.py            # apply the fix (edit form + verify by reload)
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "src")
from dotenv import load_dotenv

load_dotenv()

from playwright.async_api import async_playwright  # noqa: E402
import config  # noqa: E402,F401
from datasift_core import login, get_credentials  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fix_smith")

RECORDS_URL = "https://app.reisift.io/records/properties"
OLD_ADDR = "1308 EAGLES LANDING"
SURNAME = "Sandy Smith"


async def _search(page, term: str) -> list[dict]:
    await page.goto(RECORDS_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    box = page.locator('input[placeholder*="Search for records"]').first
    if not await box.count():
        log.error("records search box not found")
        return []
    await box.fill(term)
    await page.wait_for_timeout(3500)
    return await page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a[href*="/records/properties/"]').forEach(a => {
            const m = a.href.match(/properties\\/([0-9a-f-]{20,})/);
            if (m) out.push({uuid: m[1], text: (a.innerText || '').replace(/\\s+/g,' ').trim().slice(0,160)});
        });
        return out;
    }""")


async def find_record(page) -> str | None:
    for term in (OLD_ADDR, SURNAME):
        rows = await _search(page, term)
        log.info("search %r -> %d rows", term, len(rows))
        for r in rows:
            log.info("  %s | %s", r["uuid"][:12], r["text"])
        hit = [r for r in rows if "EAGLES LANDING" in r["text"].upper()
               or "SANDY" in r["text"].upper()]
        if len(hit) == 1:
            return hit[0]["uuid"]
        if hit:
            log.warning("multiple candidate rows — taking the Eagles Landing one")
            for r in hit:
                if "EAGLES LANDING" in r["text"].upper():
                    return r["uuid"]
            return hit[0]["uuid"]
    return None


async def probe(page, uuid: str) -> None:
    await page.goto(f"{RECORDS_URL}/{uuid}/details", wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    await page.screenshot(path="output/screenshots/smith_record_details.png", full_page=True)
    info = await page.evaluate("""() => {
        const btns = [];
        document.querySelectorAll('button, [role="button"], a').forEach(b => {
            const t = (b.innerText || b.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim();
            if (t && t.length < 40) btns.push(t);
        });
        const body = (document.body.innerText || '').replace(/\\s+/g,' ');
        return {buttons: [...new Set(btns)].slice(0, 80), body: body.slice(0, 2500)};
    }""")
    log.info("BUTTONS: %s", info["buttons"])
    log.info("BODY: %s", info["body"])
    # Deep probe: edit affordances near the property-address header
    edit_info = await page.evaluate("""() => {
        const out = {near_addr: [], icon_buttons: [], addr_html: ''};
        const walker = document.evaluate(
            "//*[contains(text(), 'Eagles Landing')]", document, null,
            XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        for (let i = 0; i < walker.snapshotLength; i++) {
            const el = walker.snapshotItem(i);
            let box = el.closest('div');
            for (let up = 0; up < 3 && box; up++) box = box.parentElement;
            if (box && !out.addr_html) out.addr_html = box.outerHTML.slice(0, 3000);
        }
        document.querySelectorAll('button, [role="button"], svg, [class*="edit" i], [class*="Edit"]').forEach(b => {
            const aria = b.getAttribute && (b.getAttribute('aria-label') || '');
            const cls = (typeof b.className === 'string' ? b.className : (b.className && b.className.baseVal) || '');
            const txt = (b.innerText || '').trim();
            if (/edit|pencil/i.test(aria + ' ' + cls) || (!txt && b.tagName === 'BUTTON')) {
                const r = b.getBoundingClientRect();
                out.icon_buttons.push({tag: b.tagName, aria, cls: cls.slice(0, 80),
                                       x: Math.round(r.x), y: Math.round(r.y)});
            }
        });
        return out;
    }""")
    log.info("ADDR HTML: %s", edit_info["addr_html"][:3000])
    for b in edit_info["icon_buttons"][:40]:
        log.info("ICON BTN: %s", b)
    # Probe the Additional Info tab for editable property fields
    tab = page.locator('text="Additional Info"').first
    if await tab.count():
        await tab.click()
        await page.wait_for_timeout(3000)
        await page.screenshot(path="output/screenshots/smith_additional_info.png", full_page=True)
        inputs = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('input, textarea, select').forEach(i => {
                const r = i.getBoundingClientRect();
                if (r.width < 5) return;
                out.push({name: i.name || '', placeholder: i.placeholder || '',
                          value: (i.value || '').slice(0, 60), type: i.type || i.tagName,
                          y: Math.round(r.y)});
            });
            const body = (document.body.innerText || '').replace(/\\s+/g, ' ');
            const idx = body.indexOf('Additional Info');
            return {inputs: out.slice(0, 60), body: body.slice(Math.max(0, idx), idx + 1800)};
        }""")
        log.info("ADDL-INFO BODY: %s", inputs["body"])
        for i in inputs["inputs"]:
            log.info("INPUT: %s", i)


async def main() -> int:
    do_probe = "--probe" in sys.argv
    email, password = get_credentials()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                log.error("login failed")
                return 1
            uuid = await find_record(page)
            if not uuid:
                log.error("record not found")
                return 1
            log.info("record uuid: %s", uuid)
            if do_probe:
                await probe(page, uuid)
                return 0
            # ── apply: mark old Eagles Landing record Dead Lead + note ──
            await page.goto(f"{RECORDS_URL}/{uuid}/details", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            note = ("WRONG PROPERTY - matcher error. This is a different living Donald "
                    "Smith's house (deed: DONALD SMITH | DENISE RICHARDS-SMITH). The "
                    "decedent Donald Corben Smith's real parcel is 3611 Daisyfield Dr "
                    "Charlotte 28269 (new record created 8/10/26). Phone (704) 607-6553 "
                    "and the Levanduski emails here belong to Vicky Levanduski - wrong "
                    "person, do not dial. Case 26E002810-590.")
            box = page.locator('textarea[name="message"]')
            if await box.count():
                await box.first.fill(note)
                await page.wait_for_timeout(500)
                sent = await page.evaluate("""() => {
                    const ta = document.querySelector('textarea[name="message"]');
                    if (!ta) return 'no-textarea';
                    let el = ta.parentElement;
                    for (let up = 0; up < 4 && el; up++, el = el.parentElement) {
                        const btn = el.querySelector('button[type="submit"], button');
                        if (btn) { btn.click(); return 'clicked: ' + (btn.innerText || btn.type); }
                    }
                    return 'no-button';
                }""")
                log.info("message-board note: %s", sent)
                await page.wait_for_timeout(2500)
            else:
                log.warning("message board textarea not found — note skipped")
            # Status -> Dead Lead (chip list is rendered inline on the record page)
            chip = page.locator('text="Dead Lead"').first
            if await chip.count():
                await chip.click()
                await page.wait_for_timeout(3000)
                log.info("clicked Dead Lead status chip")
            else:
                log.warning("Dead Lead chip not found")
            # ── verify by reload ──
            await page.goto(f"{RECORDS_URL}/{uuid}/details", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            state = await page.evaluate("""() => {
                const body = (document.body.innerText || '').replace(/\\s+/g, ' ');
                return {noted: /WRONG PROPERTY - matcher error/.test(body)};
            }""")
            log.info("verify old record note: %s", state)
            await page.screenshot(path="output/screenshots/smith_old_record_after.png", full_page=True)
            # Status verify via the records-search row (its status column shows
            # the ACTUAL status; the record page renders every status name so
            # a body-text check there proves nothing).
            rows = await _search(page, "Sandy Smith")
            for r in rows:
                log.info("  status-check row: %s | %s", r["uuid"][:12], r["text"])
            # ── verify the NEW Daisyfield record exists ──
            rows = await _search(page, "3611 Daisyfield")
            log.info("Daisyfield search -> %d rows", len(rows))
            for r in rows:
                log.info("  %s | %s", r["uuid"][:12], r["text"])
            return 0
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
