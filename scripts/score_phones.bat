@echo off
REM ===================================================================
REM  One-click Trestle phone scoring for the latest weekly upload.
REM  Run this AFTER DataSift skip-trace has finished (Skiptrace column
REM  shows a date, not "Never").
REM
REM  Usage:
REM    score_phones.bat          -> current ISO week's tag
REM    score_phones.bat 28       -> a specific week number
REM
REM  It (1) shows the Trestle cost estimate for free, (2) asks you to
REM  confirm, then (3) exports the tagged records, scores every phone,
REM  and re-uploads the dial-priority tiers to DataSift.
REM ===================================================================
setlocal
cd /d D:\SiftStack

REM Derive the tag in Python (proper ISO weeks; PowerShell 5.1 lacks ISOWeek).
REM Optional arg %1 forces a specific week number.
for /f "usebackq delims=" %%t in (`"D:\SiftStack\.venv\Scripts\python.exe" scripts\current_week_tag.py %1`) do set TAG=%%t

echo.
echo ============================================================
echo   Trestle phone scoring
echo   Tag: "%TAG%"
echo ============================================================
echo.
echo Reminder sequence:  upload net-new  -^>  skip-trace  -^>  (wait til done)  -^>  this
echo.
echo [1/2] Cost estimate (free, nothing charged)...
"D:\SiftStack\.venv\Scripts\python.exe" src\main.py phone-validate --tag "%TAG%" --estimate

echo.
set /p GO=Score these phones + push dial tiers to DataSift? (Y/N):
if /i not "%GO%"=="Y" (
    echo Cancelled - nothing charged.
    goto :end
)

echo.
echo [2/2] Scoring + tagging (spends ~$0.015 per unique phone)...
"D:\SiftStack\.venv\Scripts\python.exe" src\main.py phone-validate --tag "%TAG%"

:end
endlocal
echo.
pause
