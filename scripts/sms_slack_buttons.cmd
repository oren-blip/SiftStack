@echo off
REM ---------------------------------------------------------------------------
REM Two-way SMS agent - Slack button listener (Socket Mode).
REM
REM Holds a websocket open to Slack so tapping "Approve & send" on a phone
REM actually does something. Unlike the 10-minute poll this is LONG-RUNNING:
REM it starts once and stays up. Task Scheduler should run it At Log On with
REM "restart on failure", not on a repeating interval.
REM
REM No public URL, no tunnel, no cloud box: the connection is outbound, so the
REM buttons work from anywhere while this desktop is on. If the desktop is off,
REM taps do nothing until it comes back - the draft simply stays held, which is
REM the same state it would have been in anyway.
REM
REM Safety still comes from .env. The buttons call the same store/worker code
REM the typed commands do, so quiet hours, per-number caps and suppression all
REM apply exactly as before.
REM ---------------------------------------------------------------------------

cd /d D:\SiftStack
if not exist logs mkdir logs

echo. >> logs\sms_slack_buttons.log
echo ===== started %DATE% %TIME% ===== >> logs\sms_slack_buttons.log

REM Task Scheduler's PATH has no dotenv-equipped python; use the venv explicitly.
D:\SiftStack\.venv\Scripts\python.exe src\sms_agent\cli.py slack-listen >> logs\sms_slack_buttons.log 2>&1
set RC=%ERRORLEVEL%

echo *** listener exited %RC% at %DATE% %TIME% >> logs\sms_slack_buttons.log
exit /b %RC%
