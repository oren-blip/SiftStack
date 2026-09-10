@echo off
REM === Court PR catch-up: ask the court about stuck cases, push what it names ===
REM
REM WHY (2026-09-10, Oren found Houser 26E001025-170 by hand): the court is only
REM asked about a case while its ISO week is LIVE -- a few nightly passes, then
REM auto_archive_weeks.py puts the week away and nothing ever asks again. Any
REM case whose parties were indexed after that window keeps whatever name the
REM pipeline guessed on filing day. Houser was filed 9/2, the court listed two
REM co-executors the next morning, and the CRM was still mailing a guessed
REM sister "Kathryn Kate" eight days later. 291 archived rows were in that state
REM when this job was written.
REM
REM Three steps, in this order, and they must stay together:
REM   1. nc_cold_case_parties.py --apply   ask the court about archived stuck
REM      rows (newest filing first), write the real PR + mailing + beneficiaries
REM      back into the frozen weekly CSV, and queue each healed case for a
REM      DataSift push. Court calls only -- the expensive GIS/Zillow half of a
REM      polish is deliberately not re-run (see that script's header).
REM   2. pr_upgrade_step.py --queued      push the NAME to DataSift.
REM   3. fix_court_pr_mailing_20260904.py push the MAILING ADDRESS by API.
REM
REM Step 3 is not optional. pr_upgrade_step updates the name and SILENTLY leaves
REM the old mailing address (11 of 14 on 2026-09-04, no warning), which produces
REM "right person, wrong address" -- worse than not pushing, because it looks
REM correct. The API owner.address PATCH in step 3 is the write that persists.
REM The queue is snapshotted before step 2 because pr_upgrade_step clears it.
REM
REM Scheduled: Task Scheduler "SiftStack Court PR Catchup", weekdays 08:00.
REM Well clear of the 07:00 tier sweep, the 12:00 Parties top-up and the 17:00
REM nightly; takes the pipeline lock anyway. Log: logs\nc_court_pr_catchup.log
REM
REM Knobs:  NC_COLDCASE_MAX_CALLS  court calls per run (default 40, ~1/min when
REM         the court is throttling -- keep this under an hour of work)
REM Manual: scripts\nc_court_pr_catchup.bat --dry-run   (asks nothing, pushes
REM         nothing; prints the queue both steps would work)

cd /d "D:\SiftStack"

set LOG=logs\nc_court_pr_catchup.log
set PY="D:\SiftStack\.venv\Scripts\python.exe"
set SNAPSHOT=output\.pr_push_inflight.txt
if not defined NC_COLDCASE_MAX_CALLS set NC_COLDCASE_MAX_CALLS=40

REM Read-only preview: what the court would be asked, and what the mailing pass
REM would write for whatever is queued right now. Step 2 is left out on purpose
REM -- pr_upgrade_step opens a browser even in --dry-run.
if /I "%~1"=="--dry-run" (
    echo === Court PR catch-up DRY RUN %DATE% %TIME% ===
    %PY% nc_cold_case_parties.py --max-calls %NC_COLDCASE_MAX_CALLS%
    %PY% fix_court_pr_mailing_20260904.py --queued
    exit /b 0
)

REM Hold the machine awake for the duration (~1h worst case).
if not defined NC_KEEPAWAKE (
    set NC_KEEPAWAKE=1
    %PY% scripts\keep_awake.py -- cmd /c "%~f0" %*
    exit /b
)

%PY% scripts\pipeline_lock.py acquire court_pr_catchup >> "%LOG%" 2>&1
if errorlevel 1 (
    echo === Court PR catch-up skipped %DATE% %TIME% -- pipeline lock held === >> "%LOG%"
    exit /b 0
)

echo. >> "%LOG%"
echo === Court PR catch-up started %DATE% %TIME% === >> "%LOG%"

echo [1/3] Asking the court about archived stuck cases... >> "%LOG%"
%PY% nc_cold_case_parties.py --apply --max-calls %NC_COLDCASE_MAX_CALLS% >> "%LOG%" 2>&1

REM Snapshot the queue: step 2 empties it, step 3 still needs the list.
if exist output\pr_push_queue.txt (
    copy /Y output\pr_push_queue.txt "%SNAPSHOT%" >nul
) else (
    break > "%SNAPSHOT%"
)

echo [2/3] Pushing court PR names to DataSift... >> "%LOG%"
%PY% pr_upgrade_step.py --queued --headless >> "%LOG%" 2>&1

echo [3/3] Pushing court mailing addresses (API)... >> "%LOG%"
%PY% fix_court_pr_mailing_20260904.py --apply --from-file "%SNAPSHOT%" >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%

%PY% scripts\pipeline_lock.py release >> "%LOG%" 2>&1
echo === Court PR catch-up done rc=%RC% %DATE% %TIME% === >> "%LOG%"
exit /b %RC%
