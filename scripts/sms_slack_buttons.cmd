@echo off
REM ---------------------------------------------------------------------------
REM Two-way SMS agent - Slack button listener (Socket Mode).
REM
REM Holds a websocket open to Slack so tapping "Approve & send" on a phone
REM actually does something, sends approved drafts when their window opens
REM (60s outbox clock), and since 9/7 also reads the smrtPhone SMS log for new
REM replies every 60s -- it replaced the 10-minute "SiftStack SMS Agent Poll"
REM task, which is left registered but Disabled.
REM
REM No public URL, no tunnel, no cloud box: the connection is outbound, so the
REM buttons work from anywhere while this desktop is on. If the desktop is off,
REM taps do nothing until it comes back - the draft simply stays held, which is
REM the same state it would have been in anyway.
REM
REM THIS FILE IS THE SUPERVISOR. Task Scheduler launches it through
REM sms_slack_buttons_hidden.vbs, which returns immediately, so as far as the
REM scheduler knows the job finished the moment it started; its own
REM restart-on-failure never fires. The loop below is what brings the listener
REM back if python dies. To stop it for real, kill the python.exe whose command
REM line contains "slack-listen" (see SLACK_BUTTONS.md); the loop then exits.
REM
REM Safety still comes from .env. The buttons call the same store/worker code
REM the typed commands do, so quiet hours, per-number caps and suppression all
REM apply exactly as before.
REM ---------------------------------------------------------------------------

cd /d D:\SiftStack
if not exist logs mkdir logs

:loop
echo. >> logs\sms_slack_buttons.log
echo ===== started %DATE% %TIME% ===== >> logs\sms_slack_buttons.log

REM Task Scheduler's PATH has no dotenv-equipped python; use the venv explicitly.
D:\SiftStack\.venv\Scripts\python.exe src\sms_agent\cli.py slack-listen >> logs\sms_slack_buttons.log 2>&1
set RC=%ERRORLEVEL%
echo *** listener exited %RC% at %DATE% %TIME% >> logs\sms_slack_buttons.log

REM Exit code 2 = misconfigured (missing tokens or slack_sdk). Looping on that
REM would just fill the log; a person has to fix it.
if "%RC%"=="2" exit /b 2

REM Deliberate stop (killed from outside) also lands here. A 15s pause keeps a
REM crash loop from hammering Slack or smrtPhone; the intentional-stop recipe
REM kills this cmd too, so it never comes back uninvited.
timeout /t 15 /nobreak >nul
goto loop
