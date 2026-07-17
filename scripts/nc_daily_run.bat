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
call scripts\nc_weekly_scrape.bat %SINCE% >> "logs\nc_daily_run.log" 2>&1

echo [2/6] Merging raw scrapes by ISO week...
"D:\SiftStack\.venv\Scripts\python.exe" prepare_weekly_input.py >> "logs\nc_daily_run.log" 2>&1

echo [3/6] Refreshing manual archive index...
"D:\SiftStack\.venv\Scripts\python.exe" build_manual_archive_index.py >> "logs\nc_daily_run.log" 2>&1

echo [4/6] Polish pipeline (audit, repair, filters, beneficiary promotion)...
"D:\SiftStack\.venv\Scripts\python.exe" fix_addresses_and_prep.py >> "logs\nc_daily_run.log" 2>&1

echo [5/6] eCourts name-search backfill for remaining blank Case No....
"D:\SiftStack\.venv\Scripts\python.exe" backfill_case_numbers_from_ecourts.py >> "logs\nc_daily_run.log" 2>&1

REM Deep prospecting -- ON by default. --all-cases: Tracerfy + Trestle EVERY
REM row's contact (PR or discovered heir) so the whole sheet has phones +
REM dial-priority before DataSift upload; heir research still runs on no-contact
REM rows. NC_DP_MAX_ROWS caps the research subset (tracing itself is uncapped).
REM To turn OFF for a run:  set NC_DEEP_PROSPECT=0
echo [5.5/6] Deep prospecting + all-cases skip trace/score...
if "%NC_DEEP_PROSPECT%"=="0" (
    echo   skipped -- NC_DEEP_PROSPECT=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" nc_deep_prospect.py --all-cases >> "logs\nc_daily_run.log" 2>&1
)

REM Backfill PR phone (+ email) from case-attached PDFs (Estates Action Cover
REM Sheet / Family History Affidavit / Paid Funeral Bill) for rows the skip
REM trace left without a Phone 1. Bounded by --limit so it never blows the
REM ~1/min Odyssey doc throttle. Off-switch:  set NC_PDF_PHONES=0
echo [5.7/6] PDF phone backfill (cover sheet / family history / funeral bill)...
if "%NC_PDF_PHONES%"=="0" (
    echo   skipped -- NC_PDF_PHONES=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" nc_phone_backfill.py --limit 25 >> "logs\nc_daily_run.log" 2>&1
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

echo [7/7] Daily report (file + email)...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\daily_report.py >> "logs\nc_daily_run.log" 2>&1


"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_daily_run.log" 2>&1

echo === Daily run done %DATE% %TIME% === >> "logs\nc_daily_run.log"
echo. >> "logs\nc_daily_run.log"

echo.
echo === DONE ===
echo Latest workbook: output\FTM_2026_NC_Estates_throughWeek*.xlsx
echo Full log: logs\nc_daily_run.log
