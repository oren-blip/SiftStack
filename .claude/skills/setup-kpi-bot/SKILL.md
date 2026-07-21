---
name: setup-kpi-bot
description: Set up the daily KPI Slack bot for the user's real estate business. Use when user says "set up my KPI bot", "configure the KPI bot", "install the daily KPI reporter", "run the KPI bot setup", or anything similar. Walks the user through Google Cloud service account creation, Slack webhook setup, fills in their .env config, copies the KPI tracking Google Sheet template, tests the first run, then schedules it as a Cowork scheduled task to auto-run weekdays at 5 PM. Requires Python 3.8+ and network access to sheets.googleapis.com and hooks.slack.com.
---

# Setup KPI Bot

You are installing and configuring the DataSift KPI Slack bot for a customer. The bot pulls from their KPI Google Sheet daily and posts a formatted summary to Slack at 5 PM on weekdays.

## What You're Delivering

At the end of this skill, the customer will have:
1. `kpi-bot/` folder in their working directory with the Python script + their config
2. Their own KPI Google Sheet (copied from the template) connected via service account
3. A Slack webhook posting to the channel of their choice
4. A Cowork scheduled task that runs the bot automatically at 5 PM weekdays
5. A "Run Now" command they can execute any time

## Prerequisites Check

Verify ALL of these before starting. If any are missing, stop and fix first.

1. **Python 3.8+** available — test `python3 --version` via Bash
2. **Network allowlist** includes `sheets.googleapis.com`, `oauth2.googleapis.com`, `hooks.slack.com`
3. **Working folder** is connected and writable
4. **`.datasift-config.json` is optional** — if it exists, read `company_name` from it to pre-fill. If not, ask the user for their company name during setup.

## Workflow

### Step 1: Orient the user

Show them what's ahead:

> "Setting up your KPI bot takes about 15-20 minutes. Here's the flow:
>
> 1. I'll copy the bot files + KPI Sheet template into a `kpi-bot/` folder in your workspace
> 2. You'll upload the KPI Sheet template to Google Sheets (your own account)
> 3. You'll set up a Google Cloud service account (~10 min) — I'll walk you through it
> 4. You'll set up a Slack incoming webhook (~3 min) — I'll walk you through it
> 5. I'll fill in your config, run a test, and schedule the bot to run at 5 PM every weekday
>
> Ready? Say 'start' when you are."

### Step 2: Copy bot files to working folder

Create a `kpi-bot/` folder in the working directory and copy these files from the plugin's `references/bot-files/`:

- `kpi_slack_bot.py` → `kpi-bot/kpi_slack_bot.py`
- `requirements.txt` → `kpi-bot/requirements.txt`
- `.env.template` → `kpi-bot/.env.template`
- `KPI-Tracking-Template.xlsx` → `kpi-bot/KPI-Tracking-Template.xlsx`
- `KPI-REFERENCE.md` → `kpi-bot/KPI-REFERENCE.md`
- `service_account.json.template` → `kpi-bot/service_account.json.template`

Install Python dependencies:

```bash
cd /path/to/working/folder/kpi-bot
pip3 install -r requirements.txt --break-system-packages
```

If pip fails, tell the user: "Install manually with `pip3 install gspread google-auth requests`."

### Step 3: Upload the KPI Sheet template to Google Sheets

Tell the user:

> "I've saved `kpi-bot/KPI-Tracking-Template.xlsx` in your workspace. This is the KPI sheet with all the tabs and formulas the bot expects (Leads Summary, First to Market, Lead Management, Acquisition, etc.).
>
> Do this now:
>
> 1. Open https://sheets.google.com
> 2. Top-left: **+ (Blank)** or **File → Import**
> 3. Upload `KPI-Tracking-Template.xlsx` (choose 'Replace spreadsheet' or 'Create new spreadsheet')
> 4. Rename the sheet to something meaningful — e.g., `{company_name} KPIs`
> 5. Open the sheet and copy the URL from your browser
>
> Paste the URL here when done."

Parse the URL to extract the spreadsheet ID (the string between `/d/` and `/edit`). Save this for Step 6.

### Step 4: Google Cloud service account setup

Read `references/google-cloud-setup.md` and walk the user through it **one step at a time**. Do not dump the whole document at them. After each step, wait for confirmation ("done" / "next"), then move to the next.

Key milestones to confirm:
- ✅ Google Cloud project created
- ✅ Google Sheets API enabled
- ✅ Service account created and JSON key downloaded
- ✅ Service account email shared with the KPI Sheet (Viewer access)

When they've downloaded the JSON key, tell them:

> "Rename the file you just downloaded to exactly `service_account.json` and drag it into your `kpi-bot/` folder. Let me know when it's there."

Verify the file exists via Bash: `ls working/folder/kpi-bot/service_account.json`

### Step 5: Slack webhook setup

Read `references/slack-setup.md` and walk the user through it the same way — one step at a time. Key milestones:
- ✅ Slack app created
- ✅ Incoming Webhooks enabled
- ✅ Webhook authorized for the target channel
- ✅ Webhook URL copied

### Step 6: Write .env with all their values

Use AskUserQuestion (free-text) to capture:
- Slack Webhook URL (paste from Step 5)
- Company Name (pre-fill from `.datasift-config.json` if available)

Spreadsheet ID is from Step 3.

Write `kpi-bot/.env` with:

```
KPI_SPREADSHEET_ID=<id_from_step_3>
KPI_SLACK_WEBHOOK_URL=<url_from_step_5>
KPI_SERVICE_ACCOUNT_FILE=service_account.json
KPI_COMPANY_NAME=<their_company_name>
```

Remind them: "This `.env` file has secrets. Don't commit it anywhere public."

### Step 7: Test run

Run the bot once to confirm it works:

```bash
cd /path/to/working/folder/kpi-bot && python3 kpi_slack_bot.py
```

Watch for:
- ✅ Message appears in their Slack channel → success
- ❌ `The caller does not have permission` → Step 4 Step 6 was skipped (share sheet with service account)
- ❌ `Invalid webhook` → Step 5 webhook URL is wrong
- ❌ `KPI_SPREADSHEET_ID not set` → `.env` file wasn't written correctly
- ❌ `ModuleNotFoundError` → deps didn't install; run `pip3 install -r requirements.txt --break-system-packages`

Report exact errors to the user and help them fix. Do not proceed to scheduling until the test run succeeds.

### Step 8: Schedule the bot

Use `mcp__scheduled-tasks__create_scheduled_task` to schedule the bot to run weekdays at 5 PM local time:

```
taskId: datasift-kpi-bot
description: Daily KPI Slack update — runs weekdays at 5 PM
cronExpression: 0 17 * * 1-5
prompt: |
  Run the DataSift KPI bot.

  Execute this command via Bash:

  cd <absolute_path_to_working_folder>/kpi-bot && python3 kpi_slack_bot.py

  If the script returns a non-zero exit code, report the full stderr output so the user can debug.
  Otherwise, confirm in one line: "KPI update posted to Slack for {date}."
```

Use the absolute path to the working folder (you can get it from the cwd). Set `notifyOnCompletion: true` so the user sees when it runs.

### Step 9: Confirm and wrap up

Tell the user exactly what they have now:

> "Setup complete. Here's what you've got:
>
> ✅ **Bot folder**: `kpi-bot/` in your workspace
> ✅ **Google Sheet**: connected via service account
> ✅ **Slack webhook**: posting to your chosen channel
> ✅ **Scheduled task**: `datasift-kpi-bot` — runs weekdays at 5 PM local time
> ✅ **Tested**: first run succeeded
>
> **To run manually anytime:**
> - Say 'Run the KPI bot' in Claude, OR
> - Run `python3 kpi_slack_bot.py` in the `kpi-bot/` folder
>
> **To adjust the schedule:**
> - Ask Claude: 'Change the KPI bot schedule to [new time]'
>
> **To disable the auto-schedule:**
> - Ask Claude: 'Disable the KPI bot scheduled task'
>
> **KPI Reference**: `kpi-bot/KPI-REFERENCE.md` documents every tab, column, and metric the bot reads. Use this when you want to add new data to the sheet."

## Error Recovery

- **User gets stuck on Google Cloud step** → point them to `references/google-cloud-setup.md` troubleshooting section
- **User gets stuck on Slack step** → point them to `references/slack-setup.md` troubleshooting section
- **Service account JSON is malformed** → it has `{{PLACEHOLDER}}` values → they downloaded the template, not a real key. Send them back to Step 4 to generate a real key
- **Script fails on specific tabs** → this is expected behavior; the script handles missing/empty tabs gracefully and will still post the tabs that have data
- **Customer doesn't want auto-schedule** → skip Step 8 and tell them they can run it manually anytime

## Do NOT

- Do not hardcode Tyler's original Slack webhook or spreadsheet ID anywhere — those were stripped on purpose
- Do not skip the test run (Step 7). A bot that posts garbage to Slack daily is worse than no bot
- Do not commit `.env` or `service_account.json` to any git repo, even accidentally
- Do not attempt Google Cloud or Slack setup steps automatically — those require the user's authenticated session and manual clicks
