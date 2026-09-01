@echo off
REM === NC probate daily run -- one-command end-to-end pipeline (2-day window) ===
REM
REM Same 6-step orchestration as nc_weekly_run.bat, but scrapes the last
REM 2 days instead of 7. Intended for daily Task Scheduler invocation.
REM A 2-day window (vs 1) catches filings Odyssey indexes late.
REM
REM Steps:
REM   1. Fresh NC scrape (last 2 days, --skip-obituary --no-skip-trace)
REM   2. Merge raw scrapes into ISO-week-tagged files
REM   3. Refresh manual archive index from XLSX in Downloads
REM   4. Polish pipeline (audit, repair, filters, dedup, beneficiary promotion)
REM   5. eCourts name-search backfill for remaining blank Case No.
REM   6. Consolidate multi-week workbook with per-county colors
REM
REM Logs to logs\nc_daily_run.log
REM
REM Usage:
REM   scripts\nc_daily_run.bat              ^<- last 2 days (default)
REM   scripts\nc_daily_run.bat 2026-05-25   ^<- from a specific date

cd /d "D:\SiftStack"

REM Hold the machine awake for the whole run. The 8/3 run died when the PC
REM idle-slept into Modern Standby mid-step (23:41); the 8/4 run died to a
REM restart. Re-exec this bat under keep_awake.py, which holds a SYSTEM
REM power request until the run exits. Display still sleeps normally; a
REM user-initiated restart still kills the run -- nothing prevents that.
if not defined NC_KEEPAWAKE (
    set NC_KEEPAWAKE=1
    "D:\SiftStack\.venv\Scripts\python.exe" scripts\keep_awake.py -- cmd /c "%~f0" %*
    exit /b
)

REM Skip on weekends + NC court holidays. is_workday.py exits 1 if today
REM is Sat/Sun or any holiday in the NC General Court of Justice calendar
REM (see scripts\is_workday.py for the list).
"D:\SiftStack\.venv\Scripts\python.exe" scripts\is_workday.py >> "logs\nc_daily_run.log" 2>&1
if errorlevel 1 (
    echo === Daily run skipped %DATE% %TIME% -- non-workday === >> "logs\nc_daily_run.log"
    echo Skipping run: today is a weekend or NC court holiday.
    exit /b 0
)

REM Acquire pipeline lock -- refuses if another pipeline (daily or weekly) is running.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire daily
if errorlevel 1 (
    echo === Daily run aborted %DATE% %TIME% -- pipeline lock held === >> "logs\nc_daily_run.log"
    exit /b 1
)

set SINCE=%1
if "%SINCE%"=="" (
    for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-2).ToString('yyyy-MM-dd')"') do set SINCE=%%i
)

REM Global time budget (build 2026-08-04). A typical night finishes in ~2.5h;
REM the 8/3 run was still going at 5.5h when it died mid-step, losing the
REM whole back half (workbook + report). Any heavy step still running at the
REM deadline is killed by scripts\step_timeout.py and the run MOVES ON, so
REM consolidate + report always land. Default 270 min (6PM start -> done by
REM 10:30PM). Override:  set NC_RUN_MAX_MINS=N   (0 = no budget).
if "%NC_RUN_MAX_MINS%"=="" set NC_RUN_MAX_MINS=270
set NC_RUN_DEADLINE_EPOCH=
if not "%NC_RUN_MAX_MINS%"=="0" (
    for /f %%i in ('D:\SiftStack\.venv\Scripts\python.exe -c "import time,os;print(int(time.time())+int(os.environ.get('NC_RUN_MAX_MINS','270'))*60)"') do set NC_RUN_DEADLINE_EPOCH=%%i
)
set STEPT="D:\SiftStack\.venv\Scripts\python.exe" scripts\step_timeout.py --

echo. >> "logs\nc_daily_run.log"
echo ====================================================== >> "logs\nc_daily_run.log"
echo === Daily run started %DATE% %TIME% (since %SINCE%) === >> "logs\nc_daily_run.log"

REM Archive finished weeks. A closed week stays live for the Mon+Tue runs --
REM Friday's cases need a 2nd/3rd night, because LandPortal / phone / doc
REM fetches are rationed per night, and a county GIS outage returns a false
REM "no parcels" that only a later pass recovers. Weeks older than last week
REM go at once: an un-archived week is re-polished from scratch EVERY night
REM forever (nothing ages out on its own -- see scripts\auto_archive_weeks.py),
REM a permanent ~1h45m each. Archived weeks keep getting their Wills hunted for
REM 30 days; apply_late_docs.py lands them. To hold a week live longer, delete
REM output\archive_week<N>_done\.
echo [guard] Auto-archiving finished weeks...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\auto_archive_weeks.py >> "logs\nc_daily_run.log" 2>&1

echo [guard] GIS smoke test (stale-endpoint detection)...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\gis_smoke_test.py >> "logs\nc_daily_run.log" 2>&1
if errorlevel 1 (
    echo *** WARNING: GIS smoke test FAILED -- one or more county endpoints may have drifted *** >> "logs\nc_daily_run.log"
    echo *** WARNING: GIS smoke test FAILED -- continuing daily run, but inspect logs\nc_daily_run.log ***
)

echo [1/6] Fresh NC scrape (since %SINCE%)...
%STEPT% cmd /c scripts\nc_weekly_scrape.bat %SINCE% >> "logs\nc_daily_run.log" 2>&1

echo [2/6] Merging raw scrapes by ISO week...
"D:\SiftStack\.venv\Scripts\python.exe" prepare_weekly_input.py >> "logs\nc_daily_run.log" 2>&1

echo [3/6] Refreshing manual archive index...
"D:\SiftStack\.venv\Scripts\python.exe" build_manual_archive_index.py >> "logs\nc_daily_run.log" 2>&1

echo [4/6] Polish pipeline (audit, repair, filters, beneficiary promotion)...
%STEPT% "D:\SiftStack\.venv\Scripts\python.exe" fix_addresses_and_prep.py >> "logs\nc_daily_run.log" 2>&1

echo [5/6] eCourts name-search backfill for remaining blank Case No....
%STEPT% "D:\SiftStack\.venv\Scripts\python.exe" backfill_case_numbers_from_ecourts.py >> "logs\nc_daily_run.log" 2>&1

REM Deep prospecting -- ON by default. --all-cases: Tracerfy + Trestle EVERY
REM row's contact (PR or discovered heir) so the whole sheet has phones +
REM dial-priority before DataSift upload; heir research still runs on no-contact
REM rows. NC_DP_MAX_ROWS caps the research subset (tracing itself is uncapped).
REM To turn OFF for a run:  set NC_DEEP_PROSPECT=0
echo [5.5/6] Deep prospecting + all-cases skip trace/score...
if "%NC_DEEP_PROSPECT%"=="0" (
    echo   skipped -- NC_DEEP_PROSPECT=0 >> "logs\nc_daily_run.log"
) else (
    %STEPT% "D:\SiftStack\.venv\Scripts\python.exe" nc_deep_prospect.py --all-cases >> "logs\nc_daily_run.log" 2>&1
)

REM Backfill PR phone (+ email) from case-attached PDFs (Estates Action Cover
REM Sheet / Family History Affidavit / Paid Funeral Bill) for rows the skip
REM trace left without a Phone 1. Bounded by --limit so it never blows the
REM ~1/min Odyssey doc throttle. Off-switch:  set NC_PDF_PHONES=0
echo [5.7/6] PDF phone backfill (cover sheet / family history / funeral bill)...
if "%NC_PDF_PHONES%"=="0" (
    echo   skipped -- NC_PDF_PHONES=0 >> "logs\nc_daily_run.log"
) else (
    %STEPT% "D:\SiftStack\.venv\Scripts\python.exe" nc_phone_backfill.py --limit 25 >> "logs\nc_daily_run.log" 2>&1
)

echo [6/6] Consolidating multi-week workbook...
"D:\SiftStack\.venv\Scripts\python.exe" consolidate_weeks.py >> "logs\nc_daily_run.log" 2>&1

REM Apply Wills/Applications that landed AFTER their week was archived. The
REM polish does this for live weeks (Step -1.5) but skips archived ones, so
REM without this a late doc is fetched, parsed, cached -- and applied to
REM nothing. Pure + idempotent: a JSON lookup, no network, seconds. Must run
REM after the scrape (which drains the doc queue) and before the report
REM (which is the ONLY place these surface -- an archived week is not in the
REM workbook). Off-switch:  set NC_LATE_DOCS=0
echo [6.5/7] Applying late-arriving case docs to archived weeks...
if "%NC_LATE_DOCS%"=="0" (
    echo   skipped -- NC_LATE_DOCS=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" apply_late_docs.py >> "logs\nc_daily_run.log" 2>&1
)

REM Auto-upload tonight's NETNEW rows to DataSift (Oren approved unprompted
REM uploads 2026-08-19). Runs BEFORE the report so the email's "waiting for
REM upload" line shows the post-upload state. Skips cleanly when tonight
REM produced no NETNEW rows. Off-switch:  set NC_AUTO_UPLOAD=0
echo [6.8/7] Auto-uploading net-new rows to DataSift...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\auto_upload_netnew.py >> "logs\nc_daily_run.log" 2>&1

REM Renaming a DataSift record does NOT move its mailing address, so a
REM hand PR-correction leaves the previous heir's address under the new
REM heir's name and the next mail drop goes to the wrong house. Caught 2 of
REM 15 that way on 2026-08-23. Read-only (GETs + a local snapshot), non-fatal,
REM ~2.5 min for ~250 records. Flags stay in the log every night until the
REM mailing is fixed. Off-switch:  set NC_MAILING_DRIFT=0
echo [6.9/7] CRM owner/mailing drift check...
if "%NC_MAILING_DRIFT%"=="0" (
    echo   skipped -- NC_MAILING_DRIFT=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" audit_owner_mailing_drift.py >> "logs\nc_daily_run.log" 2>&1
)

REM Sold suppression. Oren asked (2026-08-23) for Ty's Day-2 "recently sold
REM auto-add" so the monthly sweep goes away and sold houses drop out daily.
REM That SiftMap toggle needs SiftMap Pro ($297/mo, not subscribed), so this
REM does the same job free and more accurately: county GIS by parcel is the
REM sale feed (on 2026-08-01 it caught 13 transfers SiftMap caught ZERO of,
REM and it carries August sale dates while DataSift's own data stops at July).
REM Tagging "Sold" is enough on its own -- the 12 NSM presets now exclude that
REM tag AND any sale since 2023-01-01, so no sequence has to fire (bulk tag
REM adds do NOT fire sequences on this account). HEIR TRANSFERs are never
REM suppressed: estate settled + title cleared = hot re-target lead.
REM Also flags any transfer dated on/after the estate's file date (a 90-day
REM window alone let a Jan-2026 sale on a Week-50 case stay in the mail lane
REM until Aug 2026), reads Cabarrus sales from the OpenData/Tax_Parcels layer
REM (the Parcels layer has no sale fields at all), and once a week
REM (--crm-legacy) also sweeps the ~2,000 "Courthouse Data" records that
REM predate the 2026 workbook.
REM ~17 min for ~1,000 parcels (+~35 min on the weekly legacy day), non-fatal.
REM Off-switch:  set NC_SOLD_SWEEP=0
echo [6.95/7] Sold sweep (county GIS -^> DataSift "Sold" tag)...
if "%NC_SOLD_SWEEP%"=="0" (
    echo   skipped -- NC_SOLD_SWEEP=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" sold_audit.py --since-days 90 --crm-legacy >> "logs\nc_daily_run.log" 2>&1
    "D:\SiftStack\.venv\Scripts\python.exe" push_sold_tags.py --apply >> "logs\nc_daily_run.log" 2>&1
)

echo [7/7] Daily report (file + email)...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\daily_report.py >> "logs\nc_daily_run.log" 2>&1


"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_daily_run.log" 2>&1

echo === Daily run done %DATE% %TIME% === >> "logs\nc_daily_run.log"
echo. >> "logs\nc_daily_run.log"

echo.
echo === DONE ===
echo Latest workbook: output\FTM_2026_NC_Estates_throughWeek*.xlsx
echo Full log: logs\nc_daily_run.log
