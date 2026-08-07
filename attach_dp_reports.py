"""Attach deep-prospecting report PDFs to their DataSift property records.

WHY THIS IS UI-DRIVEN: DataSift exposes no file/attachment API -- every
candidate endpoint 404s (property/{uuid}/files|attachments|documents|media, and
the bare collections). Probed 2026-08-07. The capability exists only in the web
app, so this drives it the same way the uploader does.

Flow per report:
  1. Resolve Case No. -> property address from the week's FTM/datasift CSVs
     (the PDF filename carries the case number, not the address).
  2. Type the address into the records-page "Search for records..." box; the
     matching row links to /records/properties/{uuid}/details.
  3. Open the record, click the "Property Files" tab -- that is what renders the
     dropzone; before the click there is no input[type=file] on the page at all.
  4. set_input_files() the PDF onto input.dz-hidden-input, then confirm the
     filename appears in the Files list.

Usage:
    python attach_dp_reports.py --dry-run        # resolve + report, upload nothing
    python attach_dp_reports.py                  # attach every unattached report
    python attach_dp_reports.py --only 26E002916-590
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

sys.path.insert(0, "src")
from dotenv import load_dotenv

load_dotenv()

from playwright.async_api import async_playwright  # noqa: E402
from datasift_uploader import login  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("attach_dp")

REPORT_DIR = os.path.join("output", "reports")
RECORDS_URL = "https://app.reisift.io/records/properties"
CASE_RE = re.compile(r"(\d{2}E\d{6}-\d{3})")


def case_address_map() -> dict[str, dict]:
    """Case No. -> {street, city, zip} from the week CSVs, then manual_corrections.

    manual_corrections.csv wins. That is not cosmetic: Baker 26E002844-590 still
    reads "2417 Normancrest Ct" in the week CSV, but that parcel was proven to
    belong to a DIFFERENT Joseph Baker and is tagged "Wrong Parcel - Do Not Mail"
    in DataSift. Attaching the research pack there would file it on a stranger's
    record. The corrections file holds the verified address.
    """
    out: dict[str, dict] = {}
    files = sorted(glob.glob(os.path.join("output", "*_datasift.csv")),
                   key=os.path.getmtime)
    files += sorted(glob.glob(os.path.join("output", "*_merged.csv")),
                    key=os.path.getmtime)
    for f in files:  # later files win
        try:
            with open(f, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    case = (r.get("Case No.") or "").strip()
                    street = (r.get("Property Address") or "").strip()
                    if case and street:
                        out[case] = {"street": street,
                                     "city": (r.get("Property City") or "").strip(),
                                     "zip": (r.get("Property Zip") or "").strip()}
        except (OSError, csv.Error):
            continue

    _FIELD = {"Property Address": "street", "Property City": "city",
              "Property Zip": "zip"}
    try:
        with open("manual_corrections.csv", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                case = (r.get("Case No.") or "").strip()
                key = _FIELD.get((r.get("Field") or "").strip())
                val = (r.get("Value") or "").strip()
                if case and key and val and not case.startswith("#"):
                    out.setdefault(case, {"street": "", "city": "", "zip": ""})[key] = val
                    logger.debug("correction: %s %s=%s", case, key, val)
    except (OSError, csv.Error):
        pass
    return out


async def _find_record(page, address: str) -> str | None:
    """Search the records page for an address; return its uuid or None."""
    await page.goto(RECORDS_URL, wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(4000)
    box = page.locator('input[placeholder*="Search for records"]').first
    if not await box.count():
        logger.error("records search box not found")
        return None
    await box.click()
    await box.fill("")
    await box.fill(address)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(6000)
    href = await page.evaluate("""() => {
        const a = document.querySelector('a[href*="/records/properties/"]');
        return a ? a.getAttribute('href') : null;
    }""")
    if not href:
        return None
    m = re.search(r"/records/properties/([0-9a-f-]{36})", href)
    return m.group(1) if m else None


async def _attach(page, uuid: str, pdf_path: str) -> tuple[bool, str]:
    """Open the record's Property Files tab and drop the PDF in."""
    await page.goto(f"https://app.reisift.io/records/properties/{uuid}/details",
                    wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(5000)
    name = os.path.basename(pdf_path)

    tab = page.locator('a:has-text("Property Files"), [role=tab]:has-text("Property Files")').first
    if not await tab.count():
        return False, "no Property Files tab"
    try:
        await tab.scroll_into_view_if_needed(timeout=5000)
        await tab.click(timeout=10_000)
    except Exception:
        await page.evaluate("""() => {
            const a = [...document.querySelectorAll('a,[role=tab]')]
                .find(e => /property files/i.test(e.innerText||''));
            if (a) a.click();
        }""")
    await page.wait_for_timeout(4000)

    # already attached? don't pay the upload twice
    body = (await page.inner_text("body")) or ""
    if name in body:
        return True, "already attached"

    fi = page.locator("input[type=file]").first
    if not await fi.count():
        return False, "file input never rendered (tab may not have opened)"
    await fi.set_input_files(pdf_path)
    await page.wait_for_timeout(9000)
    body = (await page.inner_text("body")) or ""
    stem = os.path.splitext(name)[0][:28]
    if name in body or stem in body:
        return True, "attached"
    return False, "uploaded but filename not visible - verify by hand"


async def run(dry: bool, only: str | None, headless: bool) -> int:
    pdfs = sorted(glob.glob(os.path.join(REPORT_DIR, "*.pdf")))
    if only:
        pdfs = [p for p in pdfs if only in p]
    if not pdfs:
        logger.error("no report PDFs in %s (run src/deep_prospect_pdf.py first)", REPORT_DIR)
        return 1
    amap = case_address_map()
    jobs = []
    for p in pdfs:
        m = CASE_RE.search(os.path.basename(p))
        case = m.group(1) if m else ""
        addr = amap.get(case)
        jobs.append({"pdf": p, "case": case, "addr": addr})

    logger.info("%d report(s); %d resolved to an address", len(jobs),
                sum(1 for j in jobs if j["addr"]))
    for j in jobs:
        a = j["addr"]
        logger.info("  %-42s %s -> %s", os.path.basename(j["pdf"]), j["case"] or "NO CASE",
                    f"{a['street']}, {a['city']}" if a else "NO ADDRESS FOUND")
    if dry:
        logger.info("dry run - nothing uploaded")
        return 0

    ok = fail = 0
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=headless)
        page = await (await br.new_context()).new_page()
        if not await login(page, os.environ.get("DATASIFT_EMAIL", ""),
                           os.environ.get("DATASIFT_PASSWORD", "")):
            logger.error("DataSift login failed")
            await br.close()
            return 1
        for j in jobs:
            nm = os.path.basename(j["pdf"])
            if not j["addr"]:
                logger.warning("SKIP %s - no address for case %s", nm, j["case"])
                fail += 1
                continue
            addr = j["addr"]["street"]
            uuid = await _find_record(page, addr)
            if not uuid:
                logger.warning("SKIP %s - no DataSift record matched %r", nm, addr)
                fail += 1
                continue
            good, msg = await _attach(page, uuid, j["pdf"])
            if good:
                logger.info("OK   %s -> %s (%s)", nm, addr, msg)
                ok += 1
            else:
                logger.warning("FAIL %s -> %s (%s)", nm, addr, msg)
                fail += 1
        await br.close()
    logger.info("done: %d attached, %d skipped/failed", ok, fail)
    return 0 if fail == 0 else 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default=None, help="limit to one case number")
    ap.add_argument("--headed", action="store_true", help="watch the browser")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.dry_run, args.only, not args.headed)))


if __name__ == "__main__":
    main()
