@echo off
REM === NC probate weekly run -- one-command end-to-end pipeline ===
REM
REM Runs the full sequence:
REM   1. Fresh NC scrape (last 7 days, --skip-obituary --no-skip-trace)
REM   2. Merge raw scrapes into ISO-week-tagged files
REM   3. Refresh manual archive index from your XLSX in Downloads
REM   4. Polish pipeline (audit, re-search, repair, residential collapse,
REM      property-value backfill, $500K cap, heir-occupied filter,
REM      PR mailing fallback, commercial drop, dedup, beneficiary
REM      promotion, Heirs-of fallback)
REM   5. eCourts name-search backfill for any remaining blank Case No.
REM   6. Consolidate multi-week workbook with per-county colors
REM
REM Logs to logs\nc_weekly_run.log
REM
REM Usage:
REM   scripts\nc_weekly_run.bat              ^<- last 7 days
REM   scripts\nc_weekly_run.bat 2026-05-18   ^<- from a specific date

cd /d "D:\SiftStack"

REM Acquire pipeline lock -- refuses if another pipeline (daily or weekly) is running.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire weekly
if errorlevel 1 (
    echo === Weekly run aborted %DATE% %TIME% -- pipeline lock held === >> "logs\nc_weekly_run.log"
    exit /b 1
)

echo. >> "logs\nc_weekly_run.log"
echo ====================================================== >> "logs\nc_weekly_run.log"
echo === Weekly run started %DATE% %TIME% === >> "logs\nc_weekly_run.log"

echo [1/6] Fresh NC scrape...
call scripts\nc_weekly_scrape.bat %1 >> "logs\nc_weekly_run.log" 2>&1

echo [2/6] Merging raw scrapes by ISO week...
"D:\SiftStack\.venv\Scripts\python.exe" prepare_weekly_input.py >> "logs\nc_weekly_run.log" 2>&1

echo [3/6] Refreshing manual archive index...
"D:\SiftStack\.venv\Scripts\python.exe" build_manual_archive_index.py >> "logs\nc_weekly_run.log" 2>&1

echo [4/6] Polish pipeline (audit, repair, filters, beneficiary promotion)...
"D:\SiftStack\.venv\Scripts\python.exe" fix_addresses_and_prep.py >> "logs\nc_weekly_run.log" 2>&1

echo [5/6] eCourts name-search backfill for remaining blank Case No....
"D:\SiftStack\.venv\Scripts\python.exe" backfill_case_numbers_from_ecourts.py >> "logs\nc_weekly_run.log" 2>&1

echo [6/6] Consolidating multi-week workbook...
"D:\SiftStack\.venv\Scripts\python.exe" consolidate_weeks.py >> "logs\nc_weekly_run.log" 2>&1
echo [7/7] Daily report (file + email)...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\daily_report.py >> "logs\nc_daily_run.log" 2>&1


"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_weekly_run.log" 2>&1

echo === Weekly run done %DATE% %TIME% === >> "logs\nc_weekly_run.log"
echo. >> "logs\nc_weekly_run.log"

echo.
echo === DONE ===
echo Latest workbook: output\FTM_2026_NC_Estates_throughWeek*.xlsx
echo Full log: logs\nc_weekly_run.log
