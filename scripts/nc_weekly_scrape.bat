@echo off
REM NC probate weekly scrape -- manual or scheduled invocation.
REM
REM Standard NC flags (different from TN):
REM   --skip-obituary   obituary_enricher used to be hardcoded for TN; it is
REM                     now state-aware. We keep --skip-obituary by default
REM                     during the A/B rollout. To opt in for THIS run, set
REM                     NC_OBITUARY=1 before invoking this script -- it adds
REM                     --nc-obituary, which overrides --skip-obituary for
REM                     NC notices and uses the Tier 2 Serper/Firecrawl path
REM                     (no Knox Tax tier for NC). Example:
REM                       set NC_OBITUARY=1
REM                       scripts\nc_weekly_scrape.bat
REM   --no-skip-trace   DataSift's $97/mo unlimited skip-trace handles
REM                     phones + emails post-upload (auto-tag
REM                     skip_traced_YYYY-MM). Tracerfy ($0.02/contact) is
REM                     reserved for Phase 2 deep prospecting where DataSift
REM                     can't help (heirs identified from obituary that
REM                     aren't in the CSV yet).
REM
REM Usage:
REM   scripts\nc_weekly_scrape.bat                     ^<- last 7 days
REM   scripts\nc_weekly_scrape.bat 2026-05-18          ^<- from a specific date
REM   set NC_OBITUARY=1 ^& scripts\nc_weekly_scrape.bat   ^<- A/B opt-in

cd /d "D:\SiftStack"

set SINCE=%1
if "%SINCE%"=="" (
    for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-7).ToString('yyyy-MM-dd')"') do set SINCE=%%i
)

set NC_OBIT_FLAG=
if "%NC_OBITUARY%"=="1" set NC_OBIT_FLAG=--nc-obituary

echo. >> "logs\nc_weekly_scrape.log"
echo === NC weekly scrape from %SINCE% (%DATE% %TIME%) [nc_obituary=%NC_OBITUARY%] === >> "logs\nc_weekly_scrape.log"

"D:\SiftStack\.venv\Scripts\python.exe" src\main.py nc-daily ^
    --since %SINCE% ^
    --counties Cabarrus,Catawba,Gaston,Iredell,Lincoln,Mecklenburg,Rowan ^
    --types probate ^
    --skip-obituary ^
    %NC_OBIT_FLAG% ^
    --no-skip-trace ^
    >> "logs\nc_weekly_scrape.log" 2>&1

echo === End %DATE% %TIME% === >> "logs\nc_weekly_scrape.log"
