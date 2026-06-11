@echo off
REM === NC probate DAILY SCRAPE-ONLY -- accumulate raw cases, no workbook ===
REM
REM Pulls the last 2 days of NC probate filings and leaves the raw
REM timestamped CSV in output\ (nc_estates_ftm_YYYY-MM-DD_HHMMSS.csv).
REM It does NOT merge, polish, or build the workbook -- that happens once
REM a week in nc_weekly_run.bat, which picks up ALL the raw scrapes the
REM daily runs accumulated and dedupes them by (County, Case No.).
REM
REM A 2-day window (vs 1) gives redundancy: a single missed day is still
REM covered by the next day's run.
REM
REM Logs to logs\nc_daily_scrape.log
REM
REM Usage:
REM   scripts\nc_daily_scrape.bat              ^<- last 2 days (default)
REM   scripts\nc_daily_scrape.bat 2026-05-25   ^<- from a specific date

cd /d "D:\SiftStack"

REM Skip on weekends + NC court holidays. is_workday.py exits 1 if today
REM is Sat/Sun or any holiday in the NC General Court of Justice calendar.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\is_workday.py >> "logs\nc_daily_scrape.log" 2>&1
if errorlevel 1 (
    echo === Daily scrape skipped %DATE% %TIME% -- non-workday === >> "logs\nc_daily_scrape.log"
    echo Skipping scrape: today is a weekend or NC court holiday.
    exit /b 0
)

REM Acquire pipeline lock -- refuses if another pipeline (daily or weekly) is running.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire daily
if errorlevel 1 (
    echo === Daily scrape aborted %DATE% %TIME% -- pipeline lock held === >> "logs\nc_daily_scrape.log"
    exit /b 1
)

set SINCE=%1
if "%SINCE%"=="" (
    for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-2).ToString('yyyy-MM-dd')"') do set SINCE=%%i
)

echo. >> "logs\nc_daily_scrape.log"
echo ====================================================== >> "logs\nc_daily_scrape.log"
echo === Daily scrape started %DATE% %TIME% (since %SINCE%) === >> "logs\nc_daily_scrape.log"

echo Scraping NC probate filings (since %SINCE%)...
call scripts\nc_weekly_scrape.bat %SINCE% >> "logs\nc_daily_scrape.log" 2>&1

"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_daily_scrape.log" 2>&1

echo === Daily scrape done %DATE% %TIME% === >> "logs\nc_daily_scrape.log"
echo. >> "logs\nc_daily_scrape.log"

echo.
echo === DONE ===
echo Raw cases accumulated in output\ -- workbook builds weekly (nc_weekly_run.bat).
echo Full log: logs\nc_daily_scrape.log
