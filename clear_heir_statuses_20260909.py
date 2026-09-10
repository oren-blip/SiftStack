"""Clear the Dead Lead status on the 2026-09-09 SmartSkip heir records.

WHY A BROWSER AND NOT THE API
    apiv2 PATCH /property/{uuid}/ refuses every clear for `status`:
    null -> "may not be null", "" / "Default" / "none" -> "not a valid status
    choice". Both HTTP 400. Worse, sending status alongside another field 400s
    the WHOLE request, so the first push run silently lost the dial reset on all
    11 records it tried to clear at the same time. Dials are patched separately
    now; status is a UI job. Same approach as clear_status_20260826.py.

WHY THESE RECORDS
    They came back from SmartSkip with a Dial First mobile for a child or
    sibling. Oren's call 2026-09-09 was to wake them back up, since 12 of the 20
    were killed after 0-2 calls with no reason noted -- i.e. abandoned for want
    of a phone number, which is exactly what just changed. 1041 Short St is NOT
    in the queue: real reason, auction 12/11, ten calls.

SAFETY
    Clicks ONLY the Status select in the record header (x > 450 keeps out of the
    sidebar, y < 400 keeps out of the message board). It never focuses or types
    into any free-text input -- the record page "message" box is the live SMS
    composer and must never be automated.

Usage:
    python clear_heir_statuses_20260909.py            # list targets, no browser
    python clear_heir_statuses_20260909.py --probe    # one record, dump options
    python clear_heir_statuses_20260909.py --apply    # clear all, verify by API
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
QUEUE = Path(os.environ.get("STATUS_QUEUE") or (REPO / "output" / "heirs_status_clear_queue_20260909.json"))
PROBE = "--probe" in sys.argv
APPLY = "--apply" in sys.argv

STATUS_LABELS = ['Status', 'follow_up', 'not_interested', 'No Contact New Lead',
                 'Cold Lead', 'Warm Lead', 'Hot Lead', 'Dead Lead', 'Exhausted',
                 'new_lead', 'Ghosting Lead', 'sold', 'listed', 'dnc']


def api_status(h: dict, uuid: str):
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=45)
    d = r.json() if r.status_code == 200 else {}
    s = d.get("status")
    return (s.get("title") if isinstance(s, dict) else s)


async def main(tok: str) -> int:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    targets = json.load(QUEUE.open(encoding="utf-8"))
    print(f"queue: {len(targets)} record(s)")
    for t in targets:
        print(f"  {t['street'][:34]:<34} {t['uuid']}  status={api_status(h, t['uuid'])!r}")
    if not (PROBE or APPLY):
        print("\npass --probe or --apply")
        return 0

    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await (await b.new_context()).new_page()
        if not await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                           os.environ.get("DATASIFT_PASSWORD", "")):
            print("login failed")
            return 1

        items = targets[:1] if PROBE else targets
        done, stuck = 0, []
        for t in items:
            uuid, street = t["uuid"], t["street"]
            print(f"\n=== {street}  {uuid}")
            await page.goto(f"https://app.reisift.io/records/properties/{uuid}/",
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(3500)
            await page.evaluate(
                """() => ['#npsIframeContainer', '#beamerPushModal']
                       .forEach(s => document.querySelector(s)?.remove())""")

            # The header Select renders late on a cold page. A flat 3.5s wait
            # missed it on 7 of 15 records; poll for it instead of guessing.
            for _ in range(12):
                present = await page.evaluate(
                    """(statuses) => [...document.querySelectorAll('div,button')]
                        .filter(e => (e.className || '').toString().match(/Select|Dropdown/i))
                        .filter(e => { const r = e.getBoundingClientRect();
                                       return r.x > 450 && r.y < 400; })
                        .some(e => statuses.includes((e.textContent || '').trim()))""",
                    STATUS_LABELS)
                if present:
                    break
                await page.wait_for_timeout(1000)

            opened = await page.evaluate(
                """(statuses) => {
                    const els = [...document.querySelectorAll('div,button')]
                        .filter(e => (e.className || '').toString().match(/Select|Dropdown/i))
                        .filter(e => { const r = e.getBoundingClientRect();
                                       return r.x > 450 && r.y < 400; });
                    for (const s of els) {
                        const t = (s.textContent || '').trim();
                        if (statuses.includes(t)) {
                            s.scrollIntoView({behavior: 'instant', block: 'center'});
                            s.click();
                            return t;
                        }
                    }
                    return null;
                }""", STATUS_LABELS)
            print(f"  opened status select (was {opened!r})")
            if opened is None:
                stuck.append((street, "status select not found"))
                continue
            await page.wait_for_timeout(800)

            options = await page.evaluate(
                """() => [...document.querySelectorAll('[class*="SelectOption"]')]
                        .map(e => (e.textContent || '').trim())
                        .filter(t => t && t.length < 40)""")
            print(f"  options: {options}")
            if PROBE:
                break

            target = next((o for o in options
                           if o.lower() in ("status", "default", "none", "no status",
                                            "- none -", "clear")), None)
            if target is None and "" in options:
                target = ""
            if target is None:
                stuck.append((street, f"no clear option; saw {options}"))
                continue
            picked = await page.evaluate(
                """(want) => {
                    const els = [...document.querySelectorAll('[class*="SelectOption"]')];
                    const el = els.find(e => (e.textContent || '').trim() === want);
                    if (el) { el.click(); return true; }
                    return false;
                }""", target)
            await page.wait_for_timeout(2000)

            now = api_status(h, uuid)          # verify by API, never by the UI
            print(f"  picked {target!r} ({picked}) -> status now {now!r}")
            if now:
                stuck.append((street, f"still {now}"))
            done += not now
        await b.close()

    print(f"\ncleared and verified {done}/{len(items)}")
    if stuck:
        print(f"NOT cleared: {len(stuck)}")
        for s, why in stuck:
            print(f"   {s}  --  {why}")
    return 0


if __name__ == "__main__":
    _tok = token()
    sys.exit(asyncio.run(main(_tok)))
