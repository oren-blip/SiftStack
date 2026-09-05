@echo off
REM === Cabarrus GIS probe + polish-only recovery (manual, Oren 2026-09-04) ===
REM
REM Week 36 lost 16 of its 24 Cabarrus rows on 2026-09-04 when the county's
REM ArcGIS "Parcels/MapServer" service was STOPPED mid-run (HTTP 200 with
REM {"code":500,"message":"Service Parcels/MapServer not started"}). Those rows
REM are INCOMPLETE, not "owns nothing", and the week stays unarchived until a
REM clean run. The next scheduled build is Tue 09/08 -- Mon 09/07 is Labor Day.
REM
REM This does NOT scrape: on a weekend the courts file nothing, so there is
REM nothing new to fetch. It re-runs the polish pass, which re-hits the county
REM GIS for every blank-parcel row (misses are never cached), then rebuilds the
REM workbook.
REM
REM It REFUSES to run while Cabarrus is still down, so it cannot burn a pass
REM re-dropping the same rows.
REM
REM   scripts\cabarrus_recheck.bat            <- probe, then polish if up
REM   scripts\cabarrus_recheck.bat --probe    <- probe only, change nothing

cd /d "D:\SiftStack"

"D:\SiftStack\.venv\Scripts\python.exe" scripts\cabarrus_probe.py
if errorlevel 1 (
    echo.
    echo Cabarrus GIS is still DOWN -- not running. Try again later.
    exit /b 0
)

if "%1"=="--probe" (
    echo Probe only: Cabarrus is UP. Re-run without --probe to recover Week 36.
    exit /b 0
)

REM Take the same lock the nightly uses, so this can never collide with a build.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire daily
if errorlevel 1 (
    echo Pipeline lock held -- another run is going. Aborting.
    exit /b 1
)

echo. >> "logs\nc_daily_run.log"
echo === Cabarrus recheck started %DATE% %TIME% === >> "logs\nc_daily_run.log"

"D:\SiftStack\.venv\Scripts\python.exe" scripts\gis_smoke_test.py >> "logs\nc_daily_run.log" 2>&1
"D:\SiftStack\.venv\Scripts\python.exe" fix_addresses_and_prep.py >> "logs\nc_daily_run.log" 2>&1
"D:\SiftStack\.venv\Scripts\python.exe" consolidate_weeks.py >> "logs\nc_daily_run.log" 2>&1

echo === Cabarrus recheck done %DATE% %TIME% === >> "logs\nc_daily_run.log"

"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release daily
echo.
echo Done. Cabarrus rows recovered into Week 36 -- see logs\nc_daily_run.log
