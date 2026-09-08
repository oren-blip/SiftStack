# Slack buttons for draft approval

Built 2026-09-06 so drafts can be approved from a phone.

## Why this exists

The channel was fed by an **incoming webhook**, which can only post. A draft
arrived with three commands to copy, and the only place to paste them was the
desktop. Thirteen drafts sat unsent for four days because of it.

Buttons need Slack to send something *back*, and normally that means a public
HTTPS endpoint — which would drag in the Fly.io box and its login-expiry
problem (the JWT refresh needs Playwright, so it cannot run headless).

**Socket Mode inverts that.** The desktop dials *out* to Slack and holds the
connection open. Clicks arrive on a machine with no public address, no tunnel,
and no inbound firewall rule. The desktop already runs the 10-minute poll; it
holds this too.

## What a draft looks like once this is on

    *Draft reply - (704) 880-3936* (confidence 85%)
    > them: If something falls thru we'll contact you. Thank you
    > us:   Understood, thank you Deborah! Wishing you a smooth closing.
    https://app.reisift.io/records/properties/.../details

    [ Approve & send ]  [ I'll handle it ]  [ Not a lead ]  [ Wrong number ]

| Button | What it does |
|---|---|
| **Approve & send** | `approve` + `work` in one tap. Confirms first. Outside 8am–9pm it queues for the morning and says so. |
| **I'll handle it** | Pauses the thread, drops the draft, names you in the reason. The most-used answer. |
| **Not a lead** | Closes as a soft no. Nothing is texted back. |
| **Wrong number** | Suppresses the line locally, for good. Confirms first. |

A **hot-lead handoff** post gets two buttons of its own: **Got it** (records
who took it) and **Not a lead** (closes it out). Neither sends anything or
touches the CRM.

Once pressed, the buttons are **removed from the message** and replaced with a
line saying who pressed what and what happened. A draft either still has
buttons (needs you) or it does not (done) — no scrolling to work out which.

The handlers call the same `store` / `worker` functions the typed commands do.
Quiet hours, the 25/day/number caps and suppression all still apply, because
they live in `worker.drain_outbox` and a button cannot route around it.

## Setup (about 10 minutes, in Slack)

### 1. Create the app

api.slack.com/apps → **Create New App** → **Blank app** (Slack renamed "From
scratch" in 2026) → Continue → Create. The "From a manifest" route did NOT take
on 2026-09-06 (came out as an unconfigured "Demo App"); do it by hand.

### 2. Turn on Socket Mode

Left sidebar → **Socket Mode** → toggle **Enable Socket Mode** on. It will ask
for a token name (anything, e.g. `socket`) and generate an **app-level token
starting `xapp-`** with the `connections:write` scope.

**Copy that `xapp-...` token.** It is shown once.

### 3. Turn on Interactivity

Left sidebar → **Interactivity & Shortcuts** → toggle **Interactivity** on.
With Socket Mode already enabled there is **no Request URL to fill in** — the
field disappears. That is the whole point.

### 4. Give the bot permission to post

Left sidebar → **OAuth & Permissions** → **Bot Token Scopes** → Add:

- `chat:write`

### 5. Install it

Same page → **Install to Workspace** → Allow. Copy the **Bot User OAuth Token,
starting `xoxb-`**.

### 6. Invite the bot to the channel

In the Slack channel the agent already posts to, TYPE `@` and pick the app
from the popup, hit Enter, then click **Invite them** on the notice Slack shows.
Do not paste `/invite ...` from a code block — Slack renders it as a text
snippet and nothing happens (2026-09-06).

Then get the channel ID: click the channel name → **About** tab → the ID is at
the very bottom (starts with `C`). Or ask Claude — the Slack MCP can look it up.

### 7. Put the three values in `.env`

    SMS_AGENT_SLACK_BOT_TOKEN=xoxb-...
    SMS_AGENT_SLACK_APP_TOKEN=xapp-...
    SMS_AGENT_SLACK_CHANNEL=C0123456789

Check it took:

    python src/sms_agent/cli.py doctor

Should read `slack buttons  ON`.

### 8. Start the listener

    scripts\sms_slack_buttons.cmd

It survives a reboot as Task Scheduler job **"SiftStack SMS Slack Buttons"**
(registered 2026-09-06): At Log On, no execution time limit (`PT0S`), restart
up to 99x every minute, one instance only, hidden window via the VBS. This is
**long-running**, not a repeating interval like the poll. Log:
`logs\sms_slack_buttons.log`.

**The listener owns both clocks.**

- *Send clock, every 60s* — drains any `queued` row whose window has opened.
  Found on the very first live tap (11:33pm): Approve correctly parked the
  draft for 8am, and nothing in the system would have looked at the outbox
  again until the next tap. Only `queued` rows are ever due — a held draft
  still needs a human.
- *Inbound clock, every 60s* (Oren, 9/7) — reads the smrtPhone SMS log for new
  replies, classifies them, and posts hot-lead handoffs. This replaced the
  10-minute Task Scheduler job **"SiftStack SMS Agent Poll"**, which is left
  registered but **Disabled**. A "yes" now reaches Slack in about a minute
  instead of up to ten. `SMS_AGENT_INBOUND_INTERVAL=0` turns it off (re-enable
  the poll task if you do, or nothing reads inbound). Hourly heartbeat line in
  the log so liveness is visible without waiting for a reply.

- *Digest clock* — at 8am local (`SMS_AGENT_DIGEST_HOUR`, -1 off) posts the
  day's readout: drafts waiting, threads with a person. Once per day, keyed on
  the date, so a restart inside the hour cannot double-post.

**Two more things the agent now does on its own (2026-09-07):**

- **Nudges you when a handed-off seller texts again.** After a handoff the
  agent is silent to the seller by design; it used to be silent to you too, for
  14 days. Now any new text on a thread a person owns posts a short "they
  texted again" line -- at most once per 30 minutes per thread
  (`SMS_AGENT_FOLLOWUP_PING_MINUTES`, 0 off). No draft, no CRM write.
- **Answers "who is this?" without a tap** -- from the reviewed template pool,
  no model -- but ONLY when the message is provably fresh. The smrtPhone log has
  no per-message timestamp, so "fresh" means: first seen by an inbound pass that
  ran within `SMS_AGENT_WHO_FRESH_MINUTES` (5) of the previous pass, with an id
  above that pass's high-water mark. A backlog absorbed after downtime is never
  fresh and is drafted for approval instead. That is the 2026-08-24 incident
  (four stale answers queued to weeks-old questions) made structurally
  impossible rather than merely switched off.

**The .cmd is the supervisor, not Task Scheduler.** The hidden VBS launcher
returns instantly, so the scheduler believes the job finished the moment it
began and its restart-on-failure never fires. `sms_slack_buttons.cmd` loops:
if python dies it comes back after 15s (exit code 2 = misconfigured, no loop).

**To stop it on purpose**, kill both the loop and the listener, or the loop
brings it straight back:

    Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*slack-listen*') -or ($_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*sms_slack_buttons*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start it again with `Start-ScheduledTask "SiftStack SMS Slack Buttons"`. Do
the stop/start after any edit to `slack_buttons.py` — a running process does
not pick up code changes.

## Things worth knowing

- **The bot token takes over the whole channel feed.** Once `SLACK_BOT_TOKEN`
  and `SLACK_CHANNEL` are set, *every* escalation — hot leads, alerts, the
  campaign summary — posts as the bot instead of through the webhook. Point
  `SLACK_CHANNEL` at the same channel the webhook uses or the messages move.
- **Buttons never render without the app token.** `draft_for_approval` checks
  `config.slack_listener_ready()` and falls back to the copy-paste commands.
  A button that silently does nothing is worse than no button, because it
  looks handled.
- **If the desktop is off, a tap does nothing.** The draft just stays held,
  which is exactly where it would have been anyway. Nothing is lost; press it
  again when the machine is back.
- **`chat.update` is what removes the buttons.** If Slack refuses it (bot
  kicked from the channel, message too old) the action still ran — the message
  just keeps its buttons. Pressing again is safe: approve finds nothing held
  the second time, and the other three are idempotent.
- **Wrong number is local-only.** It suppresses the line in the agent's own
  database. It does *not* set phone status WRONG in DataSift, because
  `WRITE_SCOPE=opt_out` blocks that anyway and a half-write would be worse
  than an honest local one.

## Files

| File | Role |
|---|---|
| `slack_buttons.py` | Handlers, the Socket Mode listener, the 60s send clock and the 60s inbound clock |
| `escalate.py` | `action_buttons()`, `_post_api()` (chat.postMessage) |
| `config.py` | The three tokens, `slack_buttons_enabled()`, `slack_listener_ready()` |
| `cli.py` | `slack-listen`, and the `doctor` readout |
| `scripts/sms_slack_buttons.cmd` | Launcher AND supervisor loop (restarts python if it dies) |
| `selftest.py` | 12 offline checks — every action, no network, no tokens |
