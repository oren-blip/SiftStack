@echo off
REM Full private-money-lender harvest: search -> comment threads -> spreadsheet.
REM Ty, 5DDF Day 5: "private money real estate" -> Groups -> scrape them.
REM
REM   scripts\fb_lender_run.bat
REM   scripts\fb_lender_run.bat <gid,gid,gid>       (override the groups)
REM
REM Resumable: every stage skips work whose JSON already exists, so re-running
REM after a Facebook throttle or a reboot picks up where it stopped.
REM Only ONE Chrome may hold .fb_profile - do not run this alongside
REM fb_buyer_harvest.py or fb_group_harvest.py.

setlocal
cd /d D:\SiftStack
set PYTHONIOENCODING=utf-8

set GROUPS=%~1
if "%GROUPS%"=="" set GROUPS=realestateprivatemoneylenders,privatemoneylendersnetwork,452283690439454

set LOG=logs\fb_lender_run.log
if not exist logs mkdir logs

echo. >> %LOG%
echo ================================================== >> %LOG%
echo START %DATE% %TIME%  groups=%GROUPS% >> %LOG%

echo [1/3] harvest (search terms) >> %LOG%
python fb_lender_harvest.py --groups=%GROUPS% harvest >> %LOG% 2>&1
echo   harvest exit=%ERRORLEVEL% %TIME% >> %LOG%

echo [2/3] threads (the comments are where the individuals are) >> %LOG%
python fb_lender_harvest.py --groups=%GROUPS% threads --min-comments 3 >> %LOG% 2>&1
echo   threads exit=%ERRORLEVEL% %TIME% >> %LOG%

echo [3/3] build (spreadsheet) >> %LOG%
python fb_lender_harvest.py --groups=%GROUPS% build >> %LOG% 2>&1
echo   build exit=%ERRORLEVEL% %TIME% >> %LOG%

echo DONE %DATE% %TIME% >> %LOG%
endlocal
