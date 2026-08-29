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
import re
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


def _trace_scope_from_csv(csv_path: Path) -> tuple[str | None, int, int]:
    """Read the per-upload trace-scope tag back out of the CSV's Tags column.

    The export stamps "Skip Trace <run stamp> [WN]" on every row whose contact
    is a real person, and "Needs DP" (with NO trace tag) on "Heirs of"
    placeholder rows. Returns (trace_tag, rows_with_tag, needs_dp_rows);
    trace_tag is None for pre-2026-08-12 CSVs, which fall back to the batch tag.
    """
    import csv as _csv
    try:
        from nc_datasift_export import NEEDS_DP_TAG, TRACE_TAG_PREFIX
    except ImportError:
        NEEDS_DP_TAG, TRACE_TAG_PREFIX = "Needs DP", "Skip Trace "
    trace_tag, n_traceable, n_needs_dp = None, 0, 0
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                tags = [t.strip() for t in (row.get("Tags") or "").split(",")]
                row_trace = next((t for t in tags if t.startswith(TRACE_TAG_PREFIX)), None)
                if row_trace:
                    trace_tag = trace_tag or row_trace
                    n_traceable += 1
                if NEEDS_DP_TAG in tags:
                    n_needs_dp += 1
    except OSError as e:
        logger.warning("Could not re-read %s for trace scoping (%s) — falling "
                       "back to the batch tag.", csv_path.name, e)
    return trace_tag, n_traceable, n_needs_dp


_ADDR_COLS = ["Property Street Address", "Property City",
              "Property State", "Property ZIP Code"]

# Single-user account — tasks go to Oren.
_OREN_USER_UUID = "f8f08dd8-e17c-4e69-a033-5f9f7446bf02"


async def _create_needs_dp_tasks(page, csv_path: Path) -> None:
    """POST a 'Needs DP' task onto each uploaded placeholder row's record.

    Rows tagged "Needs DP" (contact is "Heirs of <Decedent>") skip the paid
    trace, so their defined next step is deep-prospecting research. The task
    makes that queue visible in the task presets (the preset alternative hit
    the account's "Filter presets limit reached!" cap, 2026-08-14). Routes
    from app.reisift.io main.min.js: POST /api/internal/task/ with
    assigned_to_property; record found via the search API by exact street.
    Non-fatal throughout — a missed task is logged, never blocks the upload.
    """
    import csv as _csv
    from datetime import datetime, timedelta, timezone

    import requests as _rq
    try:
        from nc_datasift_export import NEEDS_DP_TAG
    except ImportError:
        NEEDS_DP_TAG = "Needs DP"
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            rows = [r for r in _csv.DictReader(f)
                    if NEEDS_DP_TAG in {t.strip() for t in
                                        (r.get("Tags") or "").split(",")}]
    except OSError as e:
        logger.warning("Needs DP tasks: could not re-read %s (%s)", csv_path.name, e)
        return
    if not rows:
        return
    try:
        token = await page.evaluate("() => localStorage.getItem('rs_token')")
    except Exception as e:  # noqa: BLE001
        logger.warning("Needs DP tasks: no API token from page (%s) — skipped.", e)
        return
    h = {"authorization": f"Bearer {token}", "content-type": "application/json",
         "accept": "application/json", "origin": "https://app.reisift.io",
         "referer": "https://app.reisift.io/", "user-agent": "Mozilla/5.0",
         "x-reisift-ui-version": "2022.02.01.7"}
    api = "https://apiv2.reisift.io"
    # End-of-day Eastern, 3 days out (observed task convention: T03:59:59.999Z
    # is the previous day's midnight Eastern).
    due = (datetime.now(timezone.utc) + timedelta(days=4)).strftime(
        "%Y-%m-%dT03:59:59.999000Z")
    made = missed = 0
    for r in rows:
        street = (r.get("Property Street Address") or "").strip()
        try:
            sr = _rq.post(f"{api}/api/internal/property/",
                          headers={**h, "x-http-method-override": "GET"},
                          json={"query": {"must": {"search": street}}}, timeout=30)
            hits = [rec for rec in (sr.json().get("results") or [])
                    if ((rec.get("address") or {}).get("street") or "")
                    .strip().lower() == street.lower()] if sr.status_code == 200 else []
            if len(hits) != 1:
                logger.warning("Needs DP task: %r -> %d record match(es) — "
                               "create the task by hand.", street, len(hits))
                missed += 1
                continue
            tr = _rq.post(f"{api}/api/internal/task/", headers=h, timeout=30,
                          json={"title": "Needs DP — deep prospecting queued",
                                "all_day": True, "due_date": due,
                                "event_type": "task",
                                "assigned_to_user": _OREN_USER_UUID,
                                "assigned_to_property": hits[0].get("uuid")})
            if tr.status_code in (200, 201):
                made += 1
            else:
                logger.warning("Needs DP task POST for %r -> HTTP %d",
                               street, tr.status_code)
                missed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("Needs DP task for %r failed (%s)", street, e)
            missed += 1
    logger.info("Needs DP tasks: %d created, %d need hand follow-up.", made, missed)


def _tag_groups(csv_path: Path) -> tuple[list[str], dict[str, list[dict]]]:
    """Split the CSV's Tags column into (common_tags, per_row_tags).

    common_tags: tags present on EVERY row (safe to apply wizard-level, which
    tags all records uniformly). per_row_tags: tag -> rows carrying it, for
    tags only SOME rows have — these must be pushed per-row after the main
    upload (wizard-level would stamp them on the wrong records; 2026-08-14).
    """
    import csv as _csv
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    sets = [{t.strip() for t in (r.get("Tags") or "").split(",") if t.strip()}
            for r in rows]
    common_set = set.intersection(*sets) if sets else set()
    # keep first-seen order for the wizard
    common: list[str] = []
    for r in rows:
        for t in (r.get("Tags") or "").split(","):
            t = t.strip()
            if t and t in common_set and t not in common:
                common.append(t)
    per_tag: dict[str, list[dict]] = {}
    for r, s in zip(rows, sets):
        for t in sorted(s - common_set):
            per_tag.setdefault(t, []).append(r)
    return common, per_tag


async def _push_per_row_tags(p, headless: bool,
                             per_tag: dict[str, list[dict]]) -> bool:
    """Push each non-common tag onto only its rows: one mini 'Add Data'
    upsert-by-address per tag, each in a FRESH browser (back-to-back wizard
    runs on one page fail with 'Could not find file input element';
    fresh-browser-per-upload is the proven pattern from fix_tags_20260814).
    """
    email = os.environ.get("DATASIFT_EMAIL", "")
    password = os.environ.get("DATASIFT_PASSWORD", "")
    ok = True
    # Skip-trace scope tag first: the paid steps downstream depend on it.
    order = sorted(per_tag, key=lambda t: (not t.startswith("Skip Trace"), t))
    for tag in order:
        rows = per_tag[tag]
        safe = "".join(c if c.isalnum() else "_" for c in tag)[:40]
        out = Path("output") / f"tagpush_{safe}.csv"
        import csv as _csv
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f)
            w.writerow(_ADDR_COLS + ["Tags"])
            for r in rows:
                w.writerow([r.get(c, "") for c in _ADDR_COLS] + [tag])
        logger.info("Per-row tag push: %r onto %d record(s)...", tag, len(rows))
        browser = await p.chromium.launch(headless=headless)
        page = await (await browser.new_context(
            viewport={"width": 1280, "height": 800})).new_page()
        try:
            if not await login(page, email, password):
                logger.error("Per-row tag push: login failed for %r", tag)
                ok = False
                continue
            up = await upload_csv(page, out, mode="add", list_name="PROBATE",
                                  existing_list=True, finish=True)
            if up.get("success"):
                logger.info("Per-row tag push: %r done.", tag)
            else:
                logger.error("Per-row tag push FAILED for %r: %s — push %s "
                             "by hand.", tag, up.get("message"), out)
                ok = False
        finally:
            await browser.close()
    return ok


async def _wait_for_wizard_close(page, timeout_ms: int = 60000) -> bool:
    """True once the Review heading is hidden (wizard closed = upload committed)."""
    try:
        await page.locator(REVIEW_HEADING).first.wait_for(state="hidden", timeout=timeout_ms)
        return True
    except PwTimeout:
        return False


async def _skip_trace_week(page, list_name: str, tag: str,
                           settle_s: int) -> bool:
    """Fire DataSift's own skip trace on JUST this upload's rows, after the
    import settles. Scoped by the per-upload BATCH tag (not the week tag —
    with daily uploads the week tag matches every prior day's already-traced
    records and skip trace is pay-per-record). The uploaded Tracerfy/court
    phones stay — DataSift's numbers get ADDED alongside.
    """
    logger.info("Upload committed. Waiting %ds for DataSift to import the rows "
                "before skip trace (so the tag filter finds them)...", settle_s)
    await page.wait_for_timeout(settle_s * 1000)
    # A brand-new tag takes up to ~35 MIN to appear in the tag-filter dropdown
    # (2026-08-14: mini-upload at 12:37 was first filterable ~13:11; the old
    # 3-attempt/8-min budget could never reach that). Retry every 5 min for
    # ~45 min, reloading the page each round — a failed attempt leaves the
    # filter panel in a state where 'Search for tags' is no longer found.
    for attempt in range(8):
        if attempt:
            logger.info("Tag %r not filterable yet — waiting 5 min and retrying "
                        "(%d/7)...", tag, attempt)
            await page.wait_for_timeout(300000)
        try:
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
        except Exception as e:  # noqa: BLE001
            logger.warning("Page reload before attempt failed (%s)", e)
        logger.info("Skip tracing this upload's rows only (tag=%r)...", tag)
        res = await skip_trace_records(page, list_name, filter_tag=tag)
        if res.get("success"):
            logger.info("DataSift skip trace started: %s", res.get("message"))
            return True
    logger.error("DataSift skip trace did NOT start: %s — run it by hand: "
                 "Records -> filter tag %r -> Select all -> Send To -> Skip Trace.",
                 res.get("message"), tag)
    return False


async def run(csv_path: Path, list_name: str, week: int | None, year: int,
              review_wait_min: float, auto_finish: bool, headless: bool,
              skip_trace: bool = True, skiptrace_settle_s: int = 90,
              tier_step: bool = True, tier_settle_s: int = 600,
              text_touches: bool = True, touch_sender: str = "Oren",
              batch_tag_override: str | None = None,
              backfill: bool = True) -> None:
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

            # Setup "When?" = the date the cases were pulled from the county —
            # the scrape date stamped in the CSV filename (per Oren 2026-07-29).
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", csv_path.name)
            pull_date = f"{m.group(2)}/{m.group(3)}/{m.group(1)}" if m else None
            # Per-upload BATCH tag: with daily uploads, the week tag covers
            # every prior day's records too — skip trace / Trestle / touches
            # must scope to just tonight's rows or they re-process (and
            # re-charge for) the whole week nightly (Oren, 2026-07-29).
            batch_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else \
                __import__("datetime").datetime.now().strftime("%Y-%m-%d")
            batch_tag = batch_tag_override or f"NC Upload {batch_date}"
            # Wizard tags are uniform across the whole upload: apply only the
            # tags EVERY row shares; per-row tags are pushed after commit
            # (2026-08-14 bug: row 1's tags used to stamp all records).
            common_tags, per_row_tags = _tag_groups(csv_path)
            if per_row_tags:
                logger.info("Mixed-tag CSV: %d common tag(s) at the wizard %s; "
                            "%d tag(s) pushed per-row after commit: %s",
                            len(common_tags), common_tags, len(per_row_tags),
                            {t: len(r) for t, r in per_row_tags.items()})
            logger.info("Uploading %s into existing list '%s' (stopping at Review; "
                        "pull date %s; batch tag %r)...",
                        csv_path.name, list_name, pull_date or "today", batch_tag)
            result = await upload_csv(page, csv_path, mode="add",
                                      list_name=list_name, existing_list=True,
                                      finish=False, pull_date=pull_date,
                                      extra_tags=[batch_tag],
                                      tags_override=common_tags)
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

            # ── Re-push phones by property address ──
            # "Add Data" KEEPS an existing record's contact data on merge:
            # phone columns in the CSV are silently discarded for records that
            # already existed (old bulk lists). Week 31: every merged record
            # lost its Tracerfy/court number. This dedicated update path adds
            # them; harmless for newly-created records (numbers already there,
            # DataSift dedupes identical phones).
            if committed:
                try:
                    import csv as _csv
                    with csv_path.open(newline="", encoding="utf-8-sig") as _f:
                        _rows = list(_csv.DictReader(_f))
                    _cols = ["Property Street Address", "Property City",
                             "Property State", "Property ZIP Code"] + \
                            [f"Phone {i}" for i in range(1, 10)]
                    _phone_rows = [
                        {c: (r.get(c) or "") for c in _cols} for r in _rows
                        if any((r.get(f"Phone {i}") or "").strip() for i in range(1, 10))
                    ]
                    if _phone_rows:
                        _pcsv = csv_path.with_name(csv_path.stem + "_phones.csv")
                        with _pcsv.open("w", newline="", encoding="utf-8-sig") as _f:
                            _w = _csv.DictWriter(_f, fieldnames=_cols)
                            _w.writeheader()
                            _w.writerows(_phone_rows)
                        logger.info("Re-pushing phones for %d row(s) by property "
                                    "address (merge-proofing)...", len(_phone_rows))
                        from datasift_uploader import upload_phones_by_address
                        pres = await upload_phones_by_address(page, _pcsv)
                        if not pres.get("success"):
                            logger.warning("Phones-by-address push failed: %s — "
                                           "merged records may be missing their "
                                           "uploaded numbers.", pres.get("message"))
                except Exception as e:  # noqa: BLE001
                    logger.warning("Phones-by-address push failed (%s)", e)

            # ── Per-row tags (tags not shared by every row) ──
            # Fresh browser per tag upload; the skip-trace scope tag goes
            # first because the paid steps below filter on it.
            if committed and per_row_tags:
                if not await _push_per_row_tags(p, headless, per_row_tags):
                    logger.warning("Some per-row tag pushes failed — the "
                                   "tagpush_*.csv files in output/ can be "
                                   "uploaded by hand (Add Data -> PROBATE).")

            # ── Fire DataSift's own skip trace on just this week's rows ──
            # Scope to the CSV's per-row "Skip Trace <stamp>" tag when present:
            # the export withholds that tag from "Heirs of" placeholder rows
            # (tagged "Needs DP" instead), so a non-person like "Heirs Shands"
            # never burns a paid trace. Older CSVs without the tag fall back
            # to the batch tag (traces every uploaded row, as before).
            traced = False
            if committed and skip_trace:
                if week is None:
                    logger.warning("Skip trace requested but --week not set — can't scope the "
                                   "per-week tag, so SKIPPING it to avoid tracing the whole list. "
                                   "Pass --week N (or --no-skip-trace to silence this).")
                else:
                    trace_tag, n_traceable, n_needs_dp = _trace_scope_from_csv(csv_path)
                    if trace_tag:
                        logger.info("Trace scope from CSV: tag %r covers %d row(s); "
                                    "%d 'Heirs of' placeholder row(s) excluded (Needs DP).",
                                    trace_tag, n_traceable, n_needs_dp)
                        traced = await _skip_trace_week(page, list_name, trace_tag,
                                                        skiptrace_settle_s)
                    elif n_needs_dp:
                        logger.info("All %d uploaded row(s) are 'Heirs of' placeholders — "
                                    "SKIPPING the paid skip trace entirely (a trace on "
                                    "a non-person name can never return a phone).",
                                    n_needs_dp)
                    else:
                        traced = await _skip_trace_week(page, list_name, batch_tag,
                                                        skiptrace_settle_s)

            # ── Needs DP tasks: a visible next step for placeholder rows ──
            # "Heirs of" rows are never traced (Needs DP tag instead), so
            # without this they'd sit phoneless in "01. Skipped No Numbers"
            # with nothing scheduled. A filter preset was Oren's first choice
            # but the account is at "Filter presets limit reached!" (8/14),
            # so each row gets a DataSift task instead — surfaces in the
            # task presets; the DP push completes it when research resolves.
            if committed:
                await _create_needs_dp_tasks(page, csv_path)
        finally:
            await browser.close()

    # ── Trestle tier step: score the phones the skip trace just added and
    # tag dial priorities on the records. Runs AFTER the upload browser
    # closes (trestle_tier_step opens its own session) and only when the
    # skip trace actually started — without it there are no new phones,
    # and the pipeline already scored its own numbers pre-upload.
    if traced and tier_step and week is not None:
        # Batch tag, not week tag: score/touch ONLY tonight's uploaded rows —
        # daily cadence means the week tag would re-run prior days nightly.
        logger.info("Waiting %d min for the DataSift skip trace to finish, then "
                    "running the Trestle tier step (tag=%r)...",
                    tier_settle_s // 60, batch_tag)
        await asyncio.sleep(tier_settle_s)
        try:
            from trestle_tier_step import run as tier_run
            rc = await tier_run(batch_tag, dry_run=False, headless=headless)
            if rc == 0:
                logger.info("Trestle tier step complete — dial-priority tags are live.")
                # Text touches ride on the tier step's success: the week's
                # records now carry their final phones, so export -> generate
                # 4 personalized SMS drafts -> upsert into Text Touch 1-4.
                if text_touches:
                    try:
                        from text_touch_step import run as touch_run
                        trc = await touch_run(batch_tag, sender=touch_sender,
                                              export_csv=None, list_name=list_name,
                                              dry_run=False, headless=headless)
                        if trc == 0:
                            logger.info("Text touches written — callers copy the "
                                        "next touch straight off the record.")
                        else:
                            logger.error("Text-touch step exited %d — run by hand: "
                                         "python text_touch_step.py --week %d", trc, week)
                    except Exception as e:  # noqa: BLE001
                        logger.error("Text-touch step failed (%s) — run by hand: "
                                     "python text_touch_step.py --week %d", e, week)
            else:
                logger.error("Trestle tier step exited %d — run it by hand: "
                             "python trestle_tier_step.py --week %d", rc, week)
        except Exception as e:  # noqa: BLE001
            logger.error("Trestle tier step failed (%s) — run it by hand: "
                         "python trestle_tier_step.py --week %d", e, week)
    elif committed and tier_step and not traced and week is not None:
        logger.warning("Skip trace didn't start, so the tier step was skipped — after "
                       "running the skip trace by hand, run: "
                       "python trestle_tier_step.py --week %d", week)

    # ── Tier backfill sweep (approved Oren 2026-08-14): the batch tier step
    # above only scores THIS upload's phones. Phones that entered records any
    # other way since the last upload — DP pushes, per-record "Skip Trace
    # Owner" re-traces, trace results landing after the settle window — never
    # get dial-priority tags.
    #
    # 2026-08-20: switched from trestle_backfill_step (Phone Enrichment CSV
    # export) to trestle_api_backfill (DataSift API). The export was proven to
    # return only a SUBSET of each record's phones — it showed 0/1/1 phones on
    # records the API reported as having 3/5/2 — so the export-based sweep kept
    # reporting "every phone carries a tier tag" while 20 phones sat untiered
    # in '02. Ready to Call', some for 3+ days. Reading the record over the API
    # sees every phone.
    #
    # Scope = the '02. Ready to Call' preset (what Oren actually looks at) plus
    # the last 7 days of 'NC Upload' batch tags. The 7-day window is what makes
    # it self-healing: DataSift's own skip trace often writes new phones AFTER
    # this sweep runs, and those late arrivals get picked up on a later night
    # instead of sitting untiered forever.
    if backfill:
        try:
            from trestle_api_backfill import run_sweep
            logger.info("Tier backfill sweep (API; RTC preset + last 7 days "
                        "of upload batches; also fills in Mobile/Landline/"
                        "VOIP, which the CSV upload cannot carry)...")
            # Budget, not a tripwire. This was $1.00 (= 66 phones) and the
            # sweep used to ABORT when the untiered backlog cost more than the
            # cap — tagging nothing, not even the free cached phones. Since
            # nothing got scored nothing got cached, so the next night's cost
            # was higher still: the cap tripped every night and Ready to Call
            # filled up with untiered phones. run_sweep now spends up to this
            # number and defers the rest, so the ceiling is real spend, and a
            # night's normal volume (a batch's skip trace can add ~5 phones per
            # owner) fits instead of being thrown away.
            sweep_budget = float(os.environ.get("TRESTLE_SWEEP_MAX_COST", "5.0"))
            brc = await asyncio.to_thread(
                run_sweep, preset="02. Ready to Call", tags=None,
                recent_days=7, apply=True, max_cost=sweep_budget,
                headless=headless)
            if brc == 0:
                logger.info("Tier backfill sweep complete.")
            elif brc == 4:
                logger.warning("Tier backfill sweep hit its $%.2f budget — it "
                               "tagged what it could and the rest drains on the "
                               "next run. Raise TRESTLE_SWEEP_MAX_COST to clear "
                               "it faster.", sweep_budget)
            elif brc == 5:
                logger.error("Tier backfill sweep could not resolve the "
                             "'02. Ready to Call' preset — Ready-to-Call records "
                             "were NOT swept. Check the preset name/access.")
            else:
                logger.warning("Tier backfill sweep exited %d — run by hand: "
                               "python trestle_api_backfill.py --apply", brc)
        except Exception as e:  # noqa: BLE001
            logger.warning("Tier backfill sweep failed (%s) — run by hand: "
                           "python trestle_api_backfill.py --apply", e)

    # ── Text-touch backfill sweep (2026-08-22): the batch text-touch step
    # above is nested inside `if rc == 0` of the tier step, which is itself
    # gated on the skip trace having STARTED. Any night that chain broke, the
    # batch got no drafts at all and nothing ever went back for them. Worse,
    # DP pushes rename the owner AFTER the drafts are written, so records that
    # DID get touches were left greeting "whoever handles <address>" once a
    # real heir name landed on them — 51 records with no drafts and 21 with
    # wrong-name drafts were sitting in '02. Ready to Call' when this shipped.
    #
    # Same shape as the tier sweep: read over the API (never the Phone
    # Enrichment export, which is a subset view), scope = the RTC preset Oren
    # actually calls from + the last 7 days of upload batches, and write with a
    # per-record custom-field PATCH so there is no address-matched Add Data
    # upsert that could duplicate his hand-entered rows. Free — no API spend.
    if text_touches:
        try:
            from text_touch_api_backfill import run_sweep as touch_sweep
            logger.info("Text-touch backfill sweep (API; RTC preset + last 7 days "
                        "of upload batches)...")
            src = await asyncio.to_thread(
                touch_sweep, preset="02. Ready to Call", tags=None,
                recent_days=7, apply=True, sender=touch_sender)
            if src == 0:
                logger.info("Text-touch backfill sweep complete.")
            else:
                logger.warning("Text-touch backfill sweep exited %d — run by hand: "
                               "python text_touch_api_backfill.py --apply", src)
        except Exception as e:  # noqa: BLE001
            logger.warning("Text-touch backfill sweep failed (%s) — run by hand: "
                           "python text_touch_api_backfill.py --apply", e)


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
    ap.add_argument("--review-wait", type=float, default=0.0,
                    help="Minutes to wait for a manual Finish before auto-finishing "
                         "(default 0 = finish immediately; Oren 2026-08-13)")
    ap.add_argument("--no-auto-finish", action="store_true",
                    help="Never auto-click Finish; close uncommitted if no human acts")
    ap.add_argument("--no-skip-trace", action="store_true",
                    help="Don't fire DataSift's own skip trace after commit "
                         "(default: skip-trace this week's rows, scoped by the week tag)")
    ap.add_argument("--skiptrace-settle", type=int, default=90,
                    help="Seconds to wait after commit for DataSift to import the rows "
                         "before skip trace, so the tag filter finds them (default 90)")
    ap.add_argument("--no-tier-step", action="store_true",
                    help="Don't run the Trestle tier step after the skip trace "
                         "(default: wait --tier-settle, then score + tag dial priorities)")
    ap.add_argument("--tier-settle", type=int, default=600,
                    help="Seconds to wait after the skip trace starts before the "
                         "Trestle tier step exports (default 600 = 10 min, so "
                         "DataSift's new phones are on the records)")
    ap.add_argument("--no-text-touches", action="store_true",
                    help="Don't write Text Touch 1-4 SMS drafts after the tier step")
    ap.add_argument("--no-backfill", action="store_true",
                    help="Skip the post-upload tier backfill sweep (default: sweep "
                         "the list for phones missing dial-priority tags — DP "
                         "pushes, re-traces — rolling 90-day window, $1 cost cap)")
    ap.add_argument("--touch-sender", default="Oren",
                    help="First name signing the text touches (default: Oren)")
    ap.add_argument("--batch-tag", default=None,
                    help="Override the per-upload batch tag (default: 'NC Upload "
                         "<scrape date>'). Use when running a SECOND upload the "
                         "same day so the follow-up steps don't re-process the "
                         "first batch.")
    ap.add_argument("--headless", action="store_true", help="Run browser headless")
    args = ap.parse_args()

    asyncio.run(run(Path(args.csv), args.list_name, args.week, args.year,
                    args.review_wait, not args.no_auto_finish, args.headless,
                    skip_trace=not args.no_skip_trace,
                    skiptrace_settle_s=args.skiptrace_settle,
                    tier_step=not args.no_tier_step,
                    tier_settle_s=args.tier_settle,
                    text_touches=not args.no_text_touches,
                    touch_sender=args.touch_sender,
                    batch_tag_override=args.batch_tag,
                    backfill=not args.no_backfill))


if __name__ == "__main__":
    main()
