@echo off
REM === Monthly SiftMap sold-property sweep (DataSift "Managing Sold Properties") ===
REM
REM Runs on the 1st of each month (Task Scheduler: "SiftStack Sold Sweep").
REM For each of the 7 NC counties:
REM   1. SiftMap search: last month's sold properties (min sale $1,000 to
REM      exclude deed transfers)
REM   2. Add to account with tags "Sold" + "Sold YYYY-MM" ("Do not replace
REM      owners" toggled OFF so buyer info updates)
REM      -> records matching existing leads get the tag merged on; the
REM         "Sold Property Cleanup" sequence then pulls them out of marketing
REM   3. Delete the strangers: newly-added records that were never our leads
REM      (month Sold tag + Date Added = today). Existing leads keep their
REM      original Date Added so they can never match the delete filter.
REM
REM Logs to logs\manage_sold_monthly.log
REM
REM Usage:
REM   scripts\manage_sold_monthly.bat                 ^<- headless (scheduled)
REM   scripts\manage_sold_monthly.bat --watch         ^<- visible browser (supervised run)
REM   Extra args are passed through to main.py manage-sold.

cd /d "D:\SiftStack"

set HEADLESS=--headless
set EXTRA=
:parseargs
if "%~1"=="" goto run
if /I "%~1"=="--watch" (
    set HEADLESS=
) else (
    set EXTRA=%EXTRA% %1
)
shift
goto parseargs

:run
echo. >> "logs\manage_sold_monthly.log"
echo ====================================================== >> "logs\manage_sold_monthly.log"
echo === Sold sweep started %DATE% %TIME% === >> "logs\manage_sold_monthly.log"

REM Record the launch environment — run outcomes have differed by WHO/WHAT
REM launched the bat (2026-07-31 login debugging), so keep an env trail.
echo === ENV %DATE% %TIME% === >> "logs\env_sweep_history.txt"
set >> "logs\env_sweep_history.txt"

cd /d "D:\SiftStack\src"
REM Runs on the 28th: prior month's tail (recordings mature ~4 weeks) plus
REM the current month so far — billed to the quota that expires at month end.
"D:\SiftStack\.venv\Scripts\python.exe" main.py manage-sold ^
    --counties Cabarrus,Catawba,Gaston,Iredell,Lincoln,Mecklenburg,Rowan ^
    --months-back 1 --include-current %HEADLESS% %EXTRA% >> "..\logs\manage_sold_monthly.log" 2>&1

if errorlevel 1 (
    echo === Sold sweep FAILED %DATE% %TIME% === >> "..\logs\manage_sold_monthly.log"
    exit /b 1
)
echo === Sold sweep finished %DATE% %TIME% === >> "..\logs\manage_sold_monthly.log"
exit /b 0
