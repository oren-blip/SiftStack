@echo off
REM Daily NC FTM re-enrich + parcel-recovery — invoked by Windows Task Scheduler.
REM Picks up the latest output\nc_estates_ftm_*.csv and tries to fill any
REM remaining blanks (executor data via Tyler eCourts Parties API, missing
REM parcels via county GIS endpoints). Caches in output\.ecourts_hex_cache.json,
REM output\.reenrich_fills.json, and output\.reenrich_tried_empty.json mean
REM each run picks up where the last left off.
REM
REM Logs append to logs\daily_reenrich.log. Review periodically.

cd /d "D:\SiftStack"

echo. >> "logs\daily_reenrich.log"
echo === Daily run %DATE% %TIME% === >> "logs\daily_reenrich.log"

"D:\SiftStack\.venv\Scripts\python.exe" reenrich_ftm_executors.py >> "logs\daily_reenrich.log" 2>&1
"D:\SiftStack\.venv\Scripts\python.exe" recover_parcels.py >> "logs\daily_reenrich.log" 2>&1

echo === End %DATE% %TIME% === >> "logs\daily_reenrich.log"
