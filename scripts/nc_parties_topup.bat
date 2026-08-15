@echo off
REM === Midday eCourts Parties top-up ===
REM
REM Harvests a second throttle window (~noon) for the current week's
REM unresolved cases and stores answers in output\.nc_parties_cache.json.
REM The 5 PM nightly polish reads that cache first — each hit saves a
REM ~55s throttle wait. Never touches CSVs; safe to kill mid-run.
REM
REM Scheduled: Task Scheduler "SiftStack Parties Topup", daily 12:00
REM (weekends/holidays skipped below, same rule as the nightly).

cd /d "D:\SiftStack"

REM Hold the machine awake for the duration (worst case ~45 min).
if not defined NC_KEEPAWAKE (
    set NC_KEEPAWAKE=1
    "D:\SiftStack\.venv\Scripts\python.exe" scripts\keep_awake.py -- cmd /c "%~f0" %*
    exit /b
)

REM Skip weekends + NC court holidays.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\is_workday.py >> "logs\nc_parties_topup.log" 2>&1
if errorlevel 1 (
    echo === Topup skipped %DATE% %TIME% -- non-workday === >> "logs\nc_parties_topup.log"
    exit /b 0
)

REM Never run while a pipeline run is in flight (would steal its throttle slots).
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire topup
if errorlevel 1 (
    echo === Topup skipped %DATE% %TIME% -- pipeline lock held === >> "logs\nc_parties_topup.log"
    exit /b 0
)

echo. >> "logs\nc_parties_topup.log"
echo === Parties topup started %DATE% %TIME% === >> "logs\nc_parties_topup.log"
"D:\SiftStack\.venv\Scripts\python.exe" nc_parties_topup.py >> "logs\nc_parties_topup.log" 2>&1
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\nc_parties_topup.log" 2>&1
echo === Parties topup done %DATE% %TIME% === >> "logs\nc_parties_topup.log"
