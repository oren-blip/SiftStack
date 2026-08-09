@echo off
REM === Resume the nightly pipeline from the polish step (steps 4-7) ===
REM
REM Use when a nightly run died AFTER the scrape+merge finished (steps 1-3
REM in logs\nc_daily_run.log) but before the workbook landed -- e.g. the PC
REM slept (8/3) or was restarted (8/4) mid-back-half. The scrape rows and
REM merged week files already on disk are reused; this just re-runs:
REM   4. Polish pipeline
REM   5. eCourts name-search backfill
REM   5.5 Deep prospecting + all-cases skip trace/score
REM   5.7 PDF phone backfill
REM   6. Consolidate multi-week workbook
REM   6.5 Apply late-arriving case docs
REM   7. Daily report
REM
REM Logs append to logs\nc_daily_run.log (same file as the nightly).
REM Budget: 180 min default (set NC_RUN_MAX_MINS=N to change, 0 = none).
REM
REM Usage:
REM   scripts\nc_backhalf_resume.bat

cd /d "D:\SiftStack"

REM Hold the machine awake for the whole run. See scripts\keep_awake.py.
if not defined NC_KEEPAWAKE (
    set NC_KEEPAWAKE=1
    "D:\SiftStack\.venv\Scripts\python.exe" scripts\keep_awake.py -- cmd /c "%~f0" %*
    exit /b
)

REM Acquire pipeline lock -- refuses if another pipeline is running.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire backhalf
if errorlevel 1 (
    echo === Back-half resume aborted %DATE% %TIME% -- pipeline lock held === >> "logs\nc_daily_run.log"
    exit /b 1
)

if "%NC_RUN_MAX_MINS%"=="" set NC_RUN_MAX_MINS=180
set NC_RUN_DEADLINE_EPOCH=
if not "%NC_RUN_MAX_MINS%"=="0" (
    for /f %%i in ('D:\SiftStack\.venv\Scripts\python.exe -c "import time,os;print(int(time.time())+int(os.environ.get('NC_RUN_MAX_MINS','180'))*60)"') do set NC_RUN_DEADLINE_EPOCH=%%i
)
set STEPT="D:\SiftStack\.venv\Scripts\python.exe" scripts\step_timeout.py --

echo. >> "logs\nc_daily_run.log"
echo ====================================================== >> "logs\nc_daily_run.log"
echo === Back-half resume started %DATE% %TIME% === >> "logs\nc_daily_run.log"

echo [4/6] Polish pipeline (audit, repair, filters, beneficiary promotion)...
%STEPT% "D:\SiftStack\.venv\Scripts\python.exe" fix_addresses_and_prep.py >> "logs\nc_daily_run.log" 2>&1

echo [5/6] eCourts name-search backfill for remaining blank Case No....
%STEPT% "D:\SiftStack\.venv\Scripts\python.exe" backfill_case_numbers_from_ecourts.py >> "logs\nc_daily_run.log" 2>&1

echo [5.5/6] Deep prospecting + all-cases skip trace/score...
if "%NC_DEEP_PROSPECT%"=="0" (
    echo   skipped -- NC_DEEP_PROSPECT=0 >> "logs\nc_daily_run.log"
) else (
    %STEPT% "D:\SiftStack\.venv\Scripts\python.exe" nc_deep_prospect.py --all-cases >> "logs\nc_daily_run.log" 2>&1
)

echo [5.7/6] PDF phone backfill (cover sheet / family history / funeral bill)...
if "%NC_PDF_PHONES%"=="0" (
    echo   skipped -- NC_PDF_PHONES=0 >> "logs\nc_daily_run.log"
) else (
    %STEPT% "D:\SiftStack\.venv\Scripts\python.exe" nc_phone_backfill.py --limit 25 >> "logs\nc_daily_run.log" 2>&1
)

echo [6/6] Consolidating multi-week workbook...
"D:\SiftStack\.venv\Scripts\python.exe" consolidate_weeks.py >> "logs\nc_daily_run.log" 2>&1

echo [6.5/7] Applying late-arriving case docs to archived weeks...
if "%NC_LATE_DOCS%"=="0" (
    echo   skipped -- NC_LATE_DOCS=0 >> "logs\nc_daily_run.log"
) else (
    "D:\SiftStack\.venv\Scripts\python.exe" apply_late_docs.py >> "logs\nc_daily_run.log" 2>&1
)

echo [7/7] Daily report (file + email)...
"D:\SiftStack\.venv\Scripts\python.exe" scripts\daily_report.py >> "logs\nc_daily_run.log" 2>&1

"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_daily_run.log" 2>&1

echo === Back-half resume done %DATE% %TIME% === >> "logs\nc_daily_run.log"
echo. >> "logs\nc_daily_run.log"

echo.
echo === DONE ===
echo Latest workbook: output\FTM_2026_NC_Estates_throughWeek*.xlsx
echo Full log: logs\nc_daily_run.log
