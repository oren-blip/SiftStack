@echo off
REM ---------------------------------------------------------------------------
REM Two-way SMS agent - inbound poll.
REM
REM Reads the smrtPhone SMS log, classifies anything new, and (at PHASE>=2)
REM posts a Slack handoff when a reply reads like a live seller.
REM
REM Safety comes from .env, not from this file:
REM   SMS_AGENT_PHASE=2     escalate to Slack; does not draft or send
REM   SMS_AGENT_DRY_RUN=1   blocks every CRM write AND every send
REM   SMS_AGENT_ANSWER_WHO=0 closes the one path that queues without a phase gate
REM Change those in .env deliberately. Do not add overrides here.
REM
REM --pages 1 is 200 log rows, far more than a 10-minute window can produce.
REM Anything already processed is skipped on its event key, so overlap is free.
REM ---------------------------------------------------------------------------

cd /d D:\SiftStack
if not exist logs mkdir logs

echo. >> logs\sms_agent_poll.log
echo ===== %DATE% %TIME% ===== >> logs\sms_agent_poll.log

REM Task Scheduler's PATH has no dotenv-equipped python; use the venv explicitly.
D:\SiftStack\.venv\Scripts\python.exe src\sms_agent\cli.py reconcile --pages 1 >> logs\sms_agent_poll.log 2>&1
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
  echo *** reconcile exited %RC% >> logs\sms_agent_poll.log
)

exit /b %RC%
