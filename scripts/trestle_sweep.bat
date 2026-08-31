@echo off
REM === Standalone Trestle tier + line-type sweep ===
REM
REM Phones land on DataSift records at all hours and independently of our
REM uploads: DataSift's own skip trace finishes minutes-to-hours after the
REM 8 PM upload, DP / SmartSkip pushes go through the API, and Oren re-traces
REM records by hand in the UI. Until 2026-08-30 the only tier sweep ran INSIDE
REM upload_netnew_datasift.py -- so any night with nothing net-new (and every
REM weekend) ran no sweep at all, and "02. Ready to Call" filled up with
REM untiered phones again. This job runs the same sweep on its own clock.
REM
REM What it does: trestle_api_backfill.py --apply
REM   * scope = "02. Ready to Call" (statusless) + last 7 days of NC Upload tags
REM   * scores untiered phones via Trestle (score cache = free; --max-cost caps
REM     fresh spend per run) and uploads Dial First..Drop phone tags
REM   * fills Mobile/Landline/VOIP from the cache (free)
REM
REM Scheduled: Task Scheduler "SiftStack Tier Sweep", daily 07:00 + 13:00,
REM EVERY day (no workday gate -- a Friday-night phone must be tiered by
REM Monday morning). Log: logs\trestle_sweep.log

cd /d "D:\SiftStack"

REM Hold the machine awake for the duration (~5-10 min).
if not defined NC_KEEPAWAKE (
    set NC_KEEPAWAKE=1
    "D:\SiftStack\.venv\Scripts\python.exe" scripts\keep_awake.py -- cmd /c "%~f0" %*
    exit /b
)

REM Never overlap the nightly build (it runs this same sweep after its upload)
REM or the noon Parties top-up.
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py acquire tier_sweep >> "logs\trestle_sweep.log" 2>&1
if errorlevel 1 (
    echo === Tier sweep skipped %DATE% %TIME% -- pipeline lock held === >> "logs\trestle_sweep.log"
    exit /b 0
)

echo. >> "logs\trestle_sweep.log"
echo === Tier sweep started %DATE% %TIME% === >> "logs\trestle_sweep.log"
"D:\SiftStack\.venv\Scripts\python.exe" trestle_api_backfill.py --apply --max-cost 2 --headless >> "logs\trestle_sweep.log" 2>&1
set RC=%ERRORLEVEL%
"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\trestle_sweep.log" 2>&1
echo === Tier sweep done rc=%RC% %DATE% %TIME% === >> "logs\trestle_sweep.log"
exit /b %RC%
