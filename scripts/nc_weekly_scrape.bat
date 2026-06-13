@echo off
REM NC probate weekly scrape -- manual or scheduled invocation.
REM
REM Standard NC flags (different from TN):
REM   --skip-obituary   obituary_enricher used to be hardcoded for TN; it is
REM                     now state-aware. --skip-obituary stays on as a safety
REM                     gate for non-NC states; --nc-obituary (added below
REM                     as DEFAULT-ON 2026-06-13) overrides it specifically
REM                     for NC notices and runs the Tier 2 Serper/Firecrawl
REM                     enricher. To DISABLE for a single run, set
REM                     NC_OBITUARY=0 before invoking this script.
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
REM   set NC_OBITUARY=0 ^& scripts\nc_weekly_scrape.bat   ^<- A/B opt-OUT

cd /d "D:\SiftStack"

set SINCE=%1
if "%SINCE%"=="" (
    for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-7).ToString('yyyy-MM-dd')"') do set SINCE=%%i
)

REM NC obituary enrichment defaults to ON as of 2026-06-13 (A/B rollout flipped).
REM Set NC_OBITUARY=0 in the shell env to opt OUT for a single run.
if "%NC_OBITUARY%"=="" set NC_OBITUARY=1
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
