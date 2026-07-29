"""Upload a net-new DataSift CSV into an existing list, with auto-finish fallback.

Reusable driver for the "upload the cases the scraper caught that aren't in my
manual workbook" task. Runs the upload wizard against an EXISTING list and stops
on the Review screen. From there:

  * If a human clicks "Finish Upload" within --review-wait minutes, the script
    detects the Review screen closing and exits — the human stayed in control.
  * If nobody clicks within that window, the script clicks "Finish Upload"
    itself (unless --no-auto-finish), so the upload still commits when Oren is
    away. The NC probate CSVs auto-map every column by name (no APN to hand-map),
    so the manual eyeball is optional — the fallback is safe.

Detection uses the wizard's own canonical signal: the "Review your upload"
heading disappearing == Finish was clicked and the wizard closed.

After the upload commits, it fires DataSift's OWN skip trace on just this week's
rows (scoped by the per-week tag "NC Estates Week N YYYY", so it never re-traces
the whole PROBATE list and burns the monthly limit). The uploaded Tracerfy/court
phones stay; DataSift's numbers get ADDED alongside. Needs --week to scope the
tag; disable with --no-skip-trace.

Usage:
    python upload_netnew_datasift.py --csv output/week29_NETNEW_datasift_upload.csv \
        --list PROBATE --week 29
    python upload_netnew_datasift.py --csv <file> --list PROBATE --week 30 \
        --no-skip-trace           # upload only, don't trigger DataSift skip trace
    python upload_netnew_datasift.py --csv <file> --list PROBATE --week 30 \
        --review-wait 5            # wait 5 min for a manual Finish, else auto-finish
    python upload_netnew_datasift.py --csv <file> --no-auto-finish   # never auto-click
    python upload_netnew_datasift.py --csv <file> --review-wait 0     # finish immediately
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright, TimeoutError as PwTimeout
from datasift_uploader import login, upload_csv, skip_trace_records

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("netnew_upload")

REVIEW_HEADING = 'text="Review your upload"'
FINISH_SELECTOR = ('button:has-text("Finish Upload"), '
                   'button:has-text("Finish"), '
                   'button:has-text("Submit")')


async def _wait_for_wizard_close(page, timeout_ms: int = 60000) -> bool:
    """True once the Review heading is hidden (wizard closed = upload committed)."""
    try:
        await page.locator(REVIEW_HEADING).first.wait_for(state="hidden", timeout=timeout_ms)
        return True
    except PwTimeout:
        return False


async def _skip_trace_week(page, list_name: str, week: int, year: int,
                           settle_s: int) -> None:
    """Fire DataSift's own skip trace on JUST this week's rows, after the upload
    finishes importing. Scoped by the per-week tag ("NC Estates Week N YYYY") so
    it never re-traces the whole PROBATE list (protects the monthly limit). The
    uploaded Tracerfy/court phones stay — DataSift's numbers get ADDED alongside.
    """
    tag = f"NC Estates Week {week} {year}"
    logger.info("Upload committed. Waiting %ds for DataSift to import the rows "
                "before skip trace (so the tag filter finds them)...", settle_s)
    await page.wait_for_timeout(settle_s * 1000)
    logger.info("Skip tracing this week's rows only (tag=%r)...", tag)
    res = await skip_trace_records(page, list_name, filter_tag=tag)
    if res.get("success"):
        logger.info("DataSift skip trace started: %s", res.get("message"))
    else:
        logger.error("DataSift skip trace did NOT start: %s — run it by hand: "
                     "Records -> filter tag %r -> Select all -> Send To -> Skip Trace.",
                     res.get("message"), tag)


async def run(csv_path: Path, list_name: str, week: int | None, year: int,
              review_wait_min: float, auto_finish: bool, headless: bool,
              skip_trace: bool = True, skiptrace_settle_s: int = 90) -> None:
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    if not email or not password:
        logger.error("DATASIFT_EMAIL / DATASIFT_PASSWORD not set")
        return
    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = await context.new_page()
        try:
            logger.info("Logging in to DataSift...")
            if not await login(page, email, password):
                logger.error("Login failed")
                return

            logger.info("Uploading %s into existing list '%s' (stopping at Review)...",
                        csv_path.name, list_name)
            result = await upload_csv(page, csv_path, mode="add",
                                      list_name=list_name, existing_list=True,
                                      finish=False)
            if not result.get("success"):
                logger.error("Wizard did not reach Review: %s", result.get("message"))
                return

            # Anchor: confirm we're actually on the Review screen.
            try:
                await page.locator(REVIEW_HEADING).first.wait_for(state="visible", timeout=15000)
            except PwTimeout:
                logger.warning("Couldn't confirm the Review heading — proceeding anyway.")

            # ── Hold for a manual Finish, then auto-finish as fallback ──
            polls = int(review_wait_min * 6)   # poll every 10s
            committed = False
            if review_wait_min > 0:
                logger.info("Review screen is up. Click 'Finish Upload' within %g min "
                            "to stay in control; otherwise it auto-finishes.", review_wait_min)
                for i in range(polls):
                    await page.wait_for_timeout(10000)
                    try:
                        visible = await page.locator(REVIEW_HEADING).first.is_visible()
                    except Exception:
                        visible = False
                    if not visible:
                        committed = True
                        logger.info("Review screen closed — you clicked Finish. Upload committed.")
                        break
                    if (i + 1) % 6 == 0:
                        logger.info("...waiting for manual Finish (%d min elapsed)", (i + 1) // 6)

            if not committed:
                if not auto_finish:
                    logger.info("No manual Finish within the window and auto-finish is OFF — "
                                "closing WITHOUT committing. Nothing was uploaded.")
                    return
                # Fallback: click Finish ourselves.
                logger.info("No manual Finish within %g min — auto-clicking 'Finish Upload'.",
                            review_wait_min)
                finish_btn = page.locator(FINISH_SELECTOR)
                if await finish_btn.count() > 0:
                    await finish_btn.first.click()
                    logger.info("Auto-clicked 'Finish Upload'.")
                    if await _wait_for_wizard_close(page):
                        committed = True
                        logger.info("Upload committed (wizard closed) — processing in background.")
                    else:
                        logger.warning("Wizard did not close within 60s — verify on the Activity page.")
                else:
                    logger.error("Finish button not found — nothing committed. Check the browser.")

            # ── Record committed cases in the upload ledger so tomorrow's
            # NETNEW excludes them (the CSV has no Case No. column — the
            # sidecar manifest written next to it carries the case numbers) ──
            if committed:
                try:
                    import json as _json
                    from nc_datasift_export import record_uploaded_cases
                    sidecar = csv_path.with_suffix(".cases.json")
                    if sidecar.exists():
                        cases = _json.loads(sidecar.read_text(encoding="utf-8")).get("cases", [])
                        total = record_uploaded_cases(cases)
                        logger.info("Upload ledger: recorded %d case(s), ledger now %d total.",
                                    len(cases), total)
                    else:
                        logger.warning("No .cases.json sidecar next to %s — ledger not updated; "
                                       "tomorrow's NETNEW may re-include these rows.", csv_path.name)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Upload ledger update failed (%s) — tomorrow's NETNEW "
                                   "may re-include these rows.", e)

            # ── Fire DataSift's own skip trace on just this week's rows ──
            if committed and skip_trace:
                if week is None:
                    logger.warning("Skip trace requested but --week not set — can't scope the "
                                   "per-week tag, so SKIPPING it to avoid tracing the whole list. "
                                   "Pass --week N (or --no-skip-trace to silence this).")
                else:
                    await _skip_trace_week(page, list_name, week, year, skiptrace_settle_s)
        finally:
            await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="DataSift-native upload CSV")
    ap.add_argument("--list", dest="list_name", default="PROBATE",
                    help="Existing DataSift list to add into (default: PROBATE)")
    ap.add_argument("--week", type=int, default=None,
                    help="ISO week — scopes the post-upload skip trace to this week's "
                         "tag ('NC Estates Week N YYYY'). Without it, skip trace is skipped.")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--review-wait", type=float, default=5.0,
                    help="Minutes to wait for a manual Finish before auto-finishing "
                         "(default 5; 0 = finish immediately)")
    ap.add_argument("--no-auto-finish", action="store_true",
                    help="Never auto-click Finish; close uncommitted if no human acts")
    ap.add_argument("--no-skip-trace", action="store_true",
                    help="Don't fire DataSift's own skip trace after commit "
                         "(default: skip-trace this week's rows, scoped by the week tag)")
    ap.add_argument("--skiptrace-settle", type=int, default=90,
                    help="Seconds to wait after commit for DataSift to import the rows "
                         "before skip trace, so the tag filter finds them (default 90)")
    ap.add_argument("--headless", action="store_true", help="Run browser headless")
    args = ap.parse_args()

    asyncio.run(run(Path(args.csv), args.list_name, args.week, args.year,
                    args.review_wait, not args.no_auto_finish, args.headless,
                    skip_trace=not args.no_skip_trace,
                    skiptrace_settle_s=args.skiptrace_settle))


if __name__ == "__main__":
    main()
