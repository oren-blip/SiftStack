"""Clear the Status back to default on the 6 sweep records the API refused.

apiv2 PATCH /property/{uuid}/ rejects every clear attempt for `status`
(null -> "may not be null", ""/Default/none -> "not a valid status choice"),
so this drives the record page's Status dropdown in the UI instead.

SAFETY: this script clicks ONLY the Status select in the record header. It
never focuses or types into any free-text input — the record page "message"
box is the live SMS composer (see feedback_never_automate_datasift_free_text).

    python clear_status_20260826.py --probe   # one record, dump dropdown options, no click
    python clear_status_20260826.py --apply   # clear all 6, verify via API refetch
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(r"d:\SiftStack")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
import requests  # noqa: E402
from audit_rename_gap_20260822 import token  # noqa: E402

API = "https://apiv2.reisift.io"
PROBE = "--probe" in sys.argv
APPLY = "--apply" in sys.argv

# Case No. -> uuid, from the live sweep results: the status-400 rows.
# RENAMED rows ONLY — already-named records (Curtis Williams 26E000974-350,
# Dale Brawley) KEEP their status by Oren's 8/26 "split by renamed" decision.
TARGETS = {}
for r in csv.DictReader(open(REPO / "output" / "court_mailing_sweep_20260826.csv",
                             encoding="utf-8-sig")):
    if ((r.get("Renamed") or "") == "yes"
            and "VOID" in (r.get("Result") or "")
            and "status='" in (r.get("Note") or "")):
        TARGETS[r["Case No."]] = r["UUID"]


def api_status(h: dict, uuid: str):
    r = requests.get(f"{API}/api/internal/property/{uuid}/", headers=h, timeout=30)
    d = r.json() if r.status_code == 200 else {}
    d = d.get("data") or d.get("result") or d
    return d.get("status")


async def main(tok: str) -> int:
    from playwright.async_api import async_playwright
    from datasift_uploader import login

    h = {"accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "x-reisift-ui-version": "2022.02.01.7",
         "user-agent": "Mozilla/5.0", "authorization": f"Bearer {tok}",
         "content-type": "application/json"}

    print(f"targets ({len(TARGETS)}):")
    for c, u in TARGETS.items():
        print(f"  {c}  {u}  status={api_status(h, u)!r}")
    if not (PROBE or APPLY):
        print("\npass --probe or --apply")
        return 0

    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await (await b.new_context()).new_page()
        ok = await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                         os.environ.get("DATASIFT_PASSWORD", ""))
        if not ok:
            print("login failed")
            return 1

        items = list(TARGETS.items())[:1] if PROBE else list(TARGETS.items())
        done = 0
        for case, uuid in items:
            print(f"\n=== {case}  {uuid}")
            await page.goto(f"https://app.reisift.io/records/properties/{uuid}/",
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(3500)
            # kill known pointer-event blockers
            await page.evaluate(
                """() => ['#npsIframeContainer', '#beamerPushModal']
                       .forEach(s => document.querySelector(s)?.remove())""")

            # debug: what select-ish controls does the header actually have?
            candidates = await page.evaluate(
                """() => [...document.querySelectorAll('div,button,span')]
                    .filter(e => (e.className || '').toString().match(/Select|Dropdown|Status/i))
                    .filter(e => { const r = e.getBoundingClientRect();
                                   return r.x > 450 && r.y < 400 && r.width > 40; })
                    .slice(0, 25)
                    .map(e => ({cls: e.className.toString().slice(0, 60),
                                txt: (e.textContent || '').trim().slice(0, 30)}))""")
            for c in candidates:
                print(f"    cand: {c['txt']!r:32}  {c['cls']}")

            # the Status styled-select in the record header (x > 450 avoids
            # the sidebar; y < 400 keeps us in the header, away from the
            # message board / SMS composer further down)
            statuses = ['Status', 'follow_up', 'not_interested', 'No Contact New Lead',
                        'Cold Lead', 'Warm Lead', 'Hot Lead', 'Dead Lead', 'Exhausted',
                        'new_lead', 'Ghosting Lead', 'sold', 'listed', 'dnc']
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
                }""", statuses)
            print(f"  status select opened (was {opened!r})")
            if opened is None:
                print("  STATUS SELECT NOT FOUND - skip")
                continue
            await page.wait_for_timeout(800)

            options = await page.evaluate(
                """() => [...document.querySelectorAll('[class*="SelectOption"]')]
                        .map(e => (e.textContent || '').trim())
                        .filter(t => t && t.length < 40)""")
            print(f"  options: {options}")
            if PROBE:
                break

            # pick the blank / "Status" / Default-looking option
            target = next((o for o in options
                           if o.lower() in ("status", "default", "none", "no status",
                                            "- none -", "clear")), None)
            if target is None and "" in options:
                target = ""
            if target is None:
                print("  NO clear/default option in dropdown - cannot clear via UI")
                continue
            picked = await page.evaluate(
                """(want) => {
                    const els = [...document.querySelectorAll('[class*="SelectOption"]')];
                    const el = els.find(e => (e.textContent || '').trim() === want);
                    if (el) { el.click(); return true; }
                    return false;
                }""", target)
            print(f"  picked {target!r}: {picked}")
            await page.wait_for_timeout(2000)

            now = api_status(h, uuid)
            print(f"  VERIFY via API: status={now!r} -> "
                  f"{'OK' if not now else 'STILL SET'}")
            done += not now
        await b.close()
    if APPLY:
        print(f"\ncleared {done}/{len(items)}")
    return 0


if __name__ == "__main__":
    _tok = token()  # sync context — token() runs its own asyncio loop
    sys.exit(asyncio.run(main(_tok)))
