"""One-off resume for the 2026-08-14 W33 net-new upload (15 rows).

The upload + phones push committed at 11:31 but the skip trace couldn't
start: the batch tag wasn't searchable yet (DataSift indexes new tags in
background, ~30 min on a fresh upload) and the built-in retries only cover
~8 min. This script picks the flow back up at skip trace:

  wait -> skip trace (tag 'Skip Trace 2026-08-14 093711 W33', fresh browser
  per attempt) -> 10 min settle -> Trestle tier step -> text touches
  (both scoped to batch tag 'NC Upload 2026-08-14').

Safe to re-run: skip trace is scoped to the 12 traceable rows of this one
upload (3 'Heirs of' rows carry 'Needs DP' instead and are excluded).
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from datasift_uploader import login, skip_trace_records

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("resume_skiptrace")

LIST_NAME = "PROBATE"
TRACE_TAG = "Skip Trace 2026-08-14 093711 W33"
BATCH_TAG = "NC Upload 2026-08-14"
WEEK = 33
INITIAL_WAIT_S = 900       # tag committed 11:31; give indexing its full ~30 min
BETWEEN_ROUNDS_S = 300
ROUNDS = 4                 # fresh browser each round (stale-panel failures seen)
TIER_SETTLE_S = 600


async def try_skip_trace() -> bool:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = await context.new_page()
        try:
            if not await login(page, email, password):
                logger.error("Login failed")
                return False
            res = await skip_trace_records(page, LIST_NAME, filter_tag=TRACE_TAG)
            if res.get("success"):
                logger.info("Skip trace started: %s", res.get("message"))
                return True
            logger.warning("Skip trace not started: %s", res.get("message"))
            return False
        finally:
            await browser.close()


async def main() -> int:
    logger.info("Waiting %d min before first attempt (tag indexing lag)...",
                INITIAL_WAIT_S // 60)
    await asyncio.sleep(INITIAL_WAIT_S)

    traced = False
    for i in range(ROUNDS):
        if i:
            logger.info("Retrying in %d min (round %d/%d, fresh browser)...",
                        BETWEEN_ROUNDS_S // 60, i + 1, ROUNDS)
            await asyncio.sleep(BETWEEN_ROUNDS_S)
        traced = await try_skip_trace()
        if traced:
            break
    if not traced:
        logger.error("Skip trace never started after %d rounds — run it by hand: "
                     "Records -> filter tag %r -> Select all -> Send To -> "
                     "Skip Trace, then: python trestle_tier_step.py --week %d",
                     ROUNDS, TRACE_TAG, WEEK)
        return 1

    logger.info("Waiting %d min for the skip trace to finish, then tier step "
                "(tag=%r)...", TIER_SETTLE_S // 60, BATCH_TAG)
    await asyncio.sleep(TIER_SETTLE_S)

    from trestle_tier_step import run as tier_run
    rc = await tier_run(BATCH_TAG, dry_run=False, headless=False)
    if rc != 0:
        logger.error("Tier step exited %d — run by hand: "
                     "python trestle_tier_step.py --week %d", rc, WEEK)
        return rc
    logger.info("Tier step complete — dial-priority tags are live.")

    from text_touch_step import run as touch_run
    trc = await touch_run(BATCH_TAG, sender="Oren", export_csv=None,
                          list_name=LIST_NAME, dry_run=False, headless=False)
    if trc == 0:
        logger.info("Text touches written.")
    else:
        logger.error("Text-touch step exited %d — run by hand: "
                     "python text_touch_step.py --week %d", trc, WEEK)
    return trc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
