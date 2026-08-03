"""PR-upgrade step: fix "Heirs of" DataSift records once the real executor lands.

A case uploaded on day one often ships as "Heirs of <decedent>" because the
court feed lags the portal by 1-2 days. When the executor arrives, the
workbook gets the real name — but the upload ledger (correctly) blocks
re-uploading the case, so the DataSift record would keep "Heirs" as its
contact forever, and DataSift's skip trace ran against a non-person (which is
why heirs-of records sit phoneless).

This step closes the loop nightly:
  1. Export the week's records from DataSift; find owners named "Heirs ...".
  2. Match each to the workbook by property address; where the workbook now
     has a REAL court PR, open the record's owner page and edit the contact
     (first/last + mailing) through the UI form — the Update Data wizard has
     no owner-name option, and the record edit form is the supported path.
  3. Click "Skip Trace Owner" on the updated record so DataSift searches for
     the real person (pay-per-record, ~$0.15 — only for upgraded records).

Run AFTER the polish; text touches for upgraded records regenerate on the
next weekly touch run (or run text_touch_step.py --week N by hand).

Usage:
    python pr_upgrade_step.py --week 31
    python pr_upgrade_step.py --week 31 --dry-run     # detect only
    python pr_upgrade_step.py --week 31 --no-trace    # update names, skip trace
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import config  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
from datasift_core import login, screenshot, dismiss_popups  # noqa: E402
from datasift_uploader import export_phone_enrichment  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pr_upgrade")


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _latest_week_csv(week: int) -> Path | None:
    cands = sorted(glob.glob(f"output/nc_estates_ftm_*_week{week}_dm_enriched.csv"))
    return Path(cands[-1]) if cands else None


def find_upgrades(export_csv: Path, week: int) -> list[dict]:
    """Export rows whose owner is 'Heirs ...' matched to workbook rows that
    now carry a real court PR."""
    wb_csv = _latest_week_csv(week)
    if not wb_csv:
        logger.error("No week %d dm_enriched CSV found", week)
        return [], []
    with wb_csv.open(newline="", encoding="utf-8-sig") as f:
        by_addr = {_norm(r.get("Property Address")): r for r in csv.DictReader(f)}
    out = []
    mismatches = []
    with export_csv.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            first = (r.get("First Name") or "").strip()
            wb = by_addr.get(_norm(r.get("Property address")))
            if not wb:
                continue
            pr = (wb.get("Personal Representative") or "").strip()
            if not pr or pr.lower().startswith("heirs of"):
                continue
            ds_name = f"{first} {(r.get('Last Name') or '').strip()}".strip()
            if not first.lower().startswith("heirs"):
                # Existing REAL name that differs from the workbook PR — could
                # be a stale bulk-list contact (Wanda McCormick / Jenna
                # Kachmarik class) OR an edit Oren made in DataSift. Never
                # auto-overwrite; report for his call (--fix-case applies it).
                # Same person, different middle-name form (Donna B Katz vs
                # Donna Katz) is NOT a mismatch: compare token sets, one side
                # a subset of the other = same person.
                ds_toks = {t for t in re.findall(r"[A-Z]+", ds_name.upper()) if len(t) > 1}
                pr_toks = {t for t in re.findall(r"[A-Z]+", pr.upper()) if len(t) > 1}
                same_person = ds_toks and pr_toks and (
                    ds_toks <= pr_toks or pr_toks <= ds_toks)
                wb_pr_norm = _norm(pr)
                if wb_pr_norm and not same_person and _norm(ds_name) != wb_pr_norm:
                    mismatches.append({"case": wb.get("Case No.", ""),
                                       "address": (r.get("Property address") or "").strip(),
                                       "ds": ds_name, "wb": pr})
                continue
            out.append({
                "case": wb.get("Case No.", ""),
                "address": (r.get("Property address") or "").strip(),
                "old": f"{first} {(r.get('Last Name') or '').strip()}".strip(),
                "first": (wb.get("First Name") or "").strip(),
                "last": (wb.get("Last Name") or "").strip(),
                "pr": pr,
                "mail_street": (wb.get("Mailing Address") or "").strip(),
                "mail_city": (wb.get("Mailing City") or "").strip(),
                "mail_state": (wb.get("Mailing State") or "NC").strip() or "NC",
                "mail_zip": (wb.get("Mailing Zip") or "").strip(),
            })
    return out, mismatches


async def _open_owner_page(page, address: str) -> bool:
    await page.goto("https://app.reisift.io/records/properties",
                    wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await dismiss_popups(page)
    search = page.locator('input[placeholder*="Search for records"]')
    if await search.count() == 0:
        return False
    await search.first.fill(address)
    await page.wait_for_timeout(2500)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(4000)
    link = page.locator('[class*="TableRow"] a')
    if await link.count() > 0:
        await link.first.click()
    else:
        # UI drift (2026-08-02): result rows are no longer <a> links. Click
        # the row container → property details page → follow the owner link.
        row = page.locator('[class*="TableRowContainer"]')
        if await row.count() == 0:
            return False
        await row.first.click()
        await page.wait_for_timeout(4000)
        owner = page.locator('a[href*="/records/owners/"]')
        if await owner.count() == 0:
            return False
        await owner.first.click()
    await page.wait_for_timeout(5000)
    return "/records/owners/" in page.url


async def _edit_owner(page, up: dict) -> bool:
    """On an owner page: pencil -> set first/last + mailing -> Save."""
    # 1500 chars, not 400: the nav bar + usage banner push the owner name
    # deep into body text (varies per page — 400 skipped 5 of 7 real upgrades).
    heading = await page.evaluate("() => document.body.innerText.slice(0, 1500)")
    if "Heirs" not in heading and up["old"] not in heading:
        logger.warning("  %s: owner page shows neither 'Heirs' nor %r — "
                       "skipping for safety", up["case"], up["old"])
        return False
    btns = await page.evaluate("""() =>
        [...document.querySelectorAll('button')].map(b => {
            const r = b.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    txt: (b.textContent || '').trim(), svg: b.querySelector('svg') ? 1 : 0};
        }).filter(b => b.y > 90 && b.y < 140 && b.svg && !b.txt && b.x > 700 && b.x < 900)""")
    if not btns:
        logger.warning("  %s: edit pencil not found", up["case"])
        return False
    await page.mouse.click(btns[0]["x"] + 15, btns[0]["y"] + 15)
    await page.wait_for_timeout(2500)
    fields = {"first_name": up["first"], "last_name": up["last"]}
    if up["mail_street"]:
        fields.update({"address.street": up["mail_street"],
                       "address.city": up["mail_city"],
                       "address.state": up["mail_state"],
                       "address.postal_code": up["mail_zip"]})
    for name, val in fields.items():
        inp = page.locator(f'input[name="{name}"]')
        if await inp.count() == 0:
            logger.warning("  %s: form input %r missing", up["case"], name)
            return False
        await inp.first.click()
        await inp.first.fill(val)
    # The DOM carries several zero-size hidden type=submit buttons ("Buy
    # Credits" sidebar clones) that match a naive selector's .first and
    # time out on click. Click the visible button whose text starts with
    # "Save" (the form's real button is "Save Changes").
    clicked = await page.evaluate("""() => {
        const b = [...document.querySelectorAll('button')].find(b => {
            const r = b.getBoundingClientRect();
            return (b.textContent || '').trim().startsWith('Save') && r.width > 0;
        });
        if (b) { b.click(); return true; }
        return false;
    }""")
    if not clicked:
        logger.warning("  %s: visible Save button not found", up["case"])
        return False
    await page.wait_for_timeout(4000)

    # VERIFY THE WRITE. Clicking Save is not proof it saved: Isenhour
    # 26E002823-590 was reported "contact updated to Emily Mcbryde" on three
    # separate runs (2026-08-02 x2, 2026-08-03) while DataSift still held
    # "Heirs Isenhour" — the export had no Mcbryde anywhere. A false success
    # is worse than a failure here: it hides the problem AND re-fires a paid
    # Skip Trace Owner on a record that never changed. Re-read the page and
    # require the new surname to be present.
    await page.reload(wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    body = await page.evaluate("() => document.body.innerText.slice(0, 3000)")
    want_last = (up.get("last") or "").strip()
    want_first = (up.get("first") or "").strip()
    if want_last and want_last.lower() not in body.lower():
        logger.error("  %s: SAVE DID NOT STICK — page still lacks %r after reload "
                     "(was %r). Not counting as upgraded; skipping skip trace.",
                     up["case"], f"{want_first} {want_last}".strip(), up["old"])
        return False
    return True


async def _trace_owner(page, up: dict) -> bool:
    btn = page.locator('button:has-text("Skip Trace Owner")')
    if await btn.count() == 0:
        return False
    await btn.first.click()
    await page.wait_for_timeout(2500)
    # confirm dialog (terms/agree/confirm variants)
    for sel in ('button:has-text("Skip Trace")', 'button:has-text("Confirm")',
                'button:has-text("Agree")', 'button:has-text("Yes")'):
        c = page.locator(sel)
        if await c.count() > 0:
            try:
                await c.last.click(timeout=3000)
                await page.wait_for_timeout(2000)
                break
            except Exception:  # noqa: BLE001
                continue
    await screenshot(page, f"pr_upgrade_trace_{up['case'].replace('-', '_')}")
    return True


async def run(week: int, *, dry_run: bool, trace: bool, headless: bool,
              fix_cases: set[str] | None = None) -> int:
    fix_cases = fix_cases or set()
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return 2
    tag = f"NC Estates Week {week} {datetime.now().year}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, password):
                logger.error("login failed")
                return 1
            res = await export_phone_enrichment(page, filter_tag=tag)
            if not res.get("success") or not res.get("download_path"):
                logger.error("export failed: %s", res.get("message"))
                return 1
            ups, mismatches = find_upgrades(Path(res["download_path"]), week)
            if fix_cases:
                ups += [{"case": m["case"], "address": m["address"],
                         "old": m["ds"], "pr": m["wb"],
                         "first": m["wb"].split()[0],
                         "last": m["wb"].split()[-1],
                         "mail_street": "", "mail_city": "",
                         "mail_state": "NC", "mail_zip": ""}
                        for m in mismatches if m["case"] in fix_cases]
                mismatches = [m for m in mismatches if m["case"] not in fix_cases]
            for m in mismatches:
                logger.warning("MISMATCH (not auto-fixed) %s: DataSift has %r, "
                               "workbook PR is %r — approve with --fix-case %s",
                               m["case"], m["ds"], m["wb"], m["case"])
            if not ups:
                logger.info("No PR upgrades pending — every uploaded record "
                            "already matches the workbook contact.")
                return 0
            logger.info("%d PR upgrade(s) pending:", len(ups))
            for u in ups:
                logger.info("  %s  %s -> %s  (%s)", u["case"], u["old"], u["pr"],
                            u["address"])
            if dry_run:
                return 0
            done = 0
            for u in ups:
                try:
                    if not await _open_owner_page(page, u["address"]):
                        logger.warning("  %s: record not found by address %r",
                                       u["case"], u["address"])
                        continue
                    if not await _edit_owner(page, u):
                        continue
                except Exception as e:  # noqa: BLE001 — one bad record must not kill the run
                    logger.warning("  %s: upgrade failed (%s)", u["case"], e)
                    continue
                logger.info("  %s: contact updated to %s", u["case"], u["pr"])
                if trace:
                    if await _trace_owner(page, u):
                        logger.info("  %s: Skip Trace Owner fired", u["case"])
                    else:
                        logger.warning("  %s: Skip Trace Owner button not found",
                                       u["case"])
                done += 1
            logger.info("PR upgrades applied: %d/%d. Re-run text_touch_step "
                        "--week %d to refresh greetings.", done, len(ups), week)
            return 0 if done == len(ups) else 1
        finally:
            await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-trace", action="store_true")
    ap.add_argument("--fix-case", action="append", default=[],
                    help="Case No. whose DataSift-vs-workbook name MISMATCH is "
                         "approved to overwrite (repeatable)")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(args.week, dry_run=args.dry_run,
                           trace=not args.no_trace, headless=args.headless,
                           fix_cases=set(args.fix_case)))


if __name__ == "__main__":
    raise SystemExit(main())
