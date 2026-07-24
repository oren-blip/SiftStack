"""Attach phone NUMBERS to existing DataSift records via
'Update Data -> Upload phone numbers by property address'.

The generic 'Add Data -> existing list' flow does NOT add phones to records that
already exist — it only fills new records. This dedicated Update flow does.
Mirrors upload_phone_tags but selects the phone-number-by-address option.

Pauses on Review (no commit) unless --finish is passed, so the mapping can be
eyeballed first. CSV = property address columns + Phone 1..9.
"""
import argparse, asyncio, os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv()
import logging
from playwright.async_api import async_playwright
from datasift_core import login, dismiss_popups as _dismiss_popups, screenshot as _screenshot
from datasift_uploader import _click_next_step

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("phone_num_upload")

RECORDS_URL = "https://app.reisift.io/records/properties"


async def _ensure_phone_numbers_yes(page, skiptrace_source="Tracerfy"):
    """Ensure 'Does data contain phone numbers? = Yes' + a skiptrace source in the
    'Update Data -> Upload phone numbers by property address' Setup step.

    Learned by dumping THIS step's DOM (2026-07-18):
      - The option multiselect STAYS OPEN after you pick an option and OVERLAYS
        the phone/skiptrace dropdowns below it — so clicks on them are
        intercepted (that was the mystery timeout). Close it first.
      - This flow DEFAULTS phones to "Yes" already; the only required action is
        filling the (blank) skiptrace source, else a blank skiptrace reverts
        phones -> No on advance.
    """
    ok = False
    try:
        # 1) Close the still-open option multiselect by clicking the modal heading.
        try:
            await page.locator('text="What are you looking to do?"').first.click(timeout=3000)
            await page.wait_for_timeout(500)
        except Exception:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)

        # 2) Phone dropdown = first SelectContainer after its label. Verify Yes.
        lbl = page.get_by_text("Does data contain phone numbers?", exact=False)
        phone_c = lbl.first.locator('xpath=following::*[contains(@class,"SelectContainer")][1]')
        cur = (await phone_c.locator('[data-testid="Select__SelectValue_Span"]')
               .first.text_content() or "").strip()
        if not cur.lower().startswith("yes"):
            await phone_c.locator('[class*="SelectValue"]').first.click()
            await page.wait_for_timeout(600)
            yes = phone_c.locator('[class*="SelectOptionContainer"][value="true"]')
            if await yes.count() > 0:
                try:
                    await yes.first.click(timeout=4000)
                except Exception:
                    await yes.first.click(force=True, timeout=4000)
                await page.wait_for_timeout(400)
            cur = (await phone_c.locator('[data-testid="Select__SelectValue_Span"]')
                   .first.text_content() or "").strip()
        ok = cur.lower().startswith("yes")
        logger.info("phones dropdown = %s", cur)

        # 3) Skiptrace = the SelectContainer right after the phone one -> Other -> source.
        skip_c = phone_c.locator('xpath=following::*[contains(@class,"SelectContainer")][1]')
        sh = await skip_c.element_handle()
        if sh:
            sv = await sh.query_selector('[class*="SelectValue"]')
            if sv:
                await sv.click()
                await page.wait_for_timeout(600)
            other = await sh.query_selector('[class*="SelectOptionContainer"][value="__OTHER__"]')
            if other:
                await other.click()
                await page.wait_for_timeout(500)
                spec = page.locator('input[placeholder="Type new value"]')
                if await spec.count() > 0:
                    await spec.first.fill(skiptrace_source)
                    await spec.first.press("Enter")
                    await page.wait_for_timeout(400)
                    logger.info("skiptrace source = Other / %s", skiptrace_source)
        if not ok:
            logger.warning("phones dropdown not confirmed Yes — check Review.")
    except Exception as e:
        logger.warning("phone=Yes/skiptrace setup failed: %s", e)
    return ok


async def run(csv_path: Path, finish: bool, review_wait_min: float):
    email = os.environ["DATASIFT_EMAIL"]; pw = os.environ["DATASIFT_PASSWORD"]
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context(viewport={"width":1280,"height":800})
        page = await ctx.new_page()
        try:
            if not await login(page, email, pw):
                logger.error("login failed"); return
            await page.goto(RECORDS_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            await _dismiss_popups(page)

            await page.locator('text="Upload File"').first.click(); await page.wait_for_timeout(2500)
            await _dismiss_popups(page)
            await page.locator('text="Update Data"').first.click(); await page.wait_for_timeout(2000)
            logger.info("Selected 'Update Data'")

            dd = page.locator('text="Select one or more options"')
            if await dd.count()==0:
                dd = page.locator('text="Select one option"')
            if await dd.count()>0:
                await dd.first.click(); await page.wait_for_timeout(1500)

            opts = await page.evaluate("""() => [...document.querySelectorAll('*')]
                .filter(e=>e.childElementCount===0 && /upload phone numbers/i.test(e.textContent||''))
                .map(e=>e.textContent.trim())""")
            logger.info("phone-number options: %s", opts)

            # Prefer 'by property address'
            target=None
            for t in ["Upload phone numbers by property address",
                      "Upload phone numbers by mailing address"]:
                loc=page.locator(f'text="{t}"')
                if await loc.count()>0:
                    target=loc.first; logger.info("selecting: %s", t); break
            if target is None:
                logger.error("no 'Upload phone numbers by ...' option found");
                await _screenshot(page,"pnum_no_option"); return
            await target.click(force=True); await page.wait_for_timeout(2000)
            await _ensure_phone_numbers_yes(page)
            await _screenshot(page, "pnum_after_option")

            # This flow may need extra setup before the file step. Advance up to
            # 3 times, screenshotting, until a file input appears.
            fi=page.locator('input[type="file"]')
            for step in range(4):
                if await fi.count()>0:
                    break
                await _screenshot(page, f"pnum_step{step}")
                stepinfo = await page.evaluate("""() => {
                    const labels=[...document.querySelectorAll('[class*="InputLabel"],h1,h2,h3,label')]
                        .map(e=>e.textContent.trim()).filter(t=>t&&t.length<80);
                    return labels.slice(0,15);
                }""")
                logger.info("step %d labels: %s", step, stepinfo)
                if not await _click_next_step(page, timeout=8000):
                    logger.warning("Next Step not clickable at step %d", step)
                    break
                await page.wait_for_timeout(2000)
            if await fi.count()==0:
                await _screenshot(page, "pnum_no_file_input")
                logger.error("file input never appeared"); return
            await fi.first.set_input_files(str(csv_path.resolve())); await page.wait_for_timeout(3000)
            logger.info("uploaded file: %s", csv_path.name)

            # advance to Review
            for _ in range(4):
                await _dismiss_popups(page)
                if await page.locator('text="Review your upload", button:has-text("Finish Upload")').count()>0:
                    break
                if not await _click_next_step(page, timeout=12000): break
                await page.wait_for_timeout(2000)
            await page.wait_for_timeout(1500)
            await _screenshot(page, "pnum_review")
            logger.info("Reached Review — screenshot saved (pnum_review.png)")

            if finish:
                fb=page.locator('button:has-text("Finish Upload"), button:has-text("Finish")')
                if await fb.count()>0:
                    await fb.first.click(); logger.info("clicked Finish Upload")
                    try:
                        await page.locator('text="Review your upload"').first.wait_for(state="hidden", timeout=60000)
                        logger.info("committed (wizard closed)")
                    except Exception:
                        logger.warning("wizard did not close in 60s")
                else:
                    logger.warning("Finish button not found")
            else:
                logger.info("PAUSED on Review (no commit). Holding %g min for inspection.", review_wait_min)
                for _ in range(int(review_wait_min*6)):
                    await page.wait_for_timeout(10000)
        finally:
            await b.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--finish", action="store_true")
    ap.add_argument("--review-wait", type=float, default=4.0)
    a=ap.parse_args()
    asyncio.run(run(Path(a.csv), a.finish, a.review_wait))

if __name__=="__main__":
    main()
