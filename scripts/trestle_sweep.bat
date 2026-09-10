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
REM What it does, in order:
REM
REM   1. trestle_api_backfill.py --apply
REM      * scope = "02. Ready to Call" (statusless) + last 7 days of NC Upload tags
REM      * scores untiered phones via Trestle (score cache = free; --max-cost caps
REM        fresh spend per run) and uploads Dial First..Drop phone tags
REM      * fills Mobile/Landline/VOIP from the cache (free)
REM
REM   2. text_touch_api_backfill.py --apply        (added 2026-09-10)
REM      * scope = NSM call stages 02-05 + last 7 days of NC Upload tags
REM      * writes Text Touch 1-4 on records that have none (MISSING) and
REM        re-renders drafts left stale by a DP/court owner rename (DRIFT)
REM      * FREE -- no API spend -- and idempotent, so a re-run is a no-op on
REM        records that are already correct
REM
REM      Why it lives here: the text-touch sweep used to run ONLY inside
REM      upload_netnew_datasift.py. On 2026-09-09 the build logged "nothing
REM      net-new to upload tonight", so that script never started and the
REM      sweep never fired -- by the next afternoon "02. Ready to Call" held
REM      133 records with all four boxes blank and 5 still greeting a renamed
REM      owner. That is the same failure this job was created to fix for the
REM      phone tiers on 2026-08-30; the text-touch twin needed the same clock.
REM      Tiers run first on purpose -- touches render off the record after
REM      that night's phones have landed on it.
REM
REM Scheduled: Task Scheduler "SiftStack Tier Sweep", daily 07:00 + 13:00,
REM EVERY day (no workday gate -- a Friday-night phone must be tiered by
REM Monday morning). Log: logs\trestle_sweep.log

cd /d "D:\SiftStack"

REM Hold the machine awake for the duration (~25-35 min: the tier sweep is
REM ~5-10, the text-touch sweep reads ~700 records at roughly 1/sec on top).
REM keep_awake wraps the whole bat, so it scales with whatever the run takes.
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

REM Text touches next. Deliberately NOT gated on RC above: it is free and
REM idempotent, and a failed tier run must never leave callers staring at
REM blank text boxes. That nesting is exactly what broke the batch step.
echo. >> "logs\trestle_sweep.log"
echo === Text-touch sweep started %DATE% %TIME% === >> "logs\trestle_sweep.log"
"D:\SiftStack\.venv\Scripts\python.exe" text_touch_api_backfill.py --apply >> "logs\trestle_sweep.log" 2>&1
set TRC=%ERRORLEVEL%
echo === Text-touch sweep done rc=%TRC% %DATE% %TIME% === >> "logs\trestle_sweep.log"
if "%RC%"=="0" set RC=%TRC%

"D:\SiftStack\.venv\Scripts\python.exe" scripts\pipeline_lock.py release >> "logs\trestle_sweep.log" 2>&1
echo === Tier sweep done rc=%RC% %DATE% %TIME% === >> "logs\trestle_sweep.log"
exit /b %RC%
