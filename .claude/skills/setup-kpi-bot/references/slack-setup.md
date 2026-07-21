# Slack Setup — Incoming Webhook for KPI Posts

The KPI bot posts to Slack using a **Slack Incoming Webhook** — a URL you can POST to that delivers a message to a specific channel. Takes about 3 minutes.

## Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Sign in to your Slack workspace (the one where you want KPIs posted)
3. Click **Create New App → From scratch**
4. App name: `KPI Bot` (or any name)
5. Pick the workspace → click **Create App**

## Step 2: Enable Incoming Webhooks

1. In the left sidebar of your new app: **Features → Incoming Webhooks**
2. Toggle **Activate Incoming Webhooks** to On
3. Scroll down → click **Add New Webhook to Workspace**

## Step 3: Pick a channel

1. Slack will ask which channel the webhook should post to
2. Choose the channel where you want your daily KPI updates (e.g., `#kpis`, `#leadership`, `#team`)
3. Click **Allow**

## Step 4: Copy the webhook URL

1. After authorizing, you're back on the Incoming Webhooks page
2. A new webhook appears at the bottom — copy the **Webhook URL**
3. It looks like: `https://hooks.slack.com/services/YOUR/WEBHOOK/PATH`
4. This is the value for `KPI_SLACK_WEBHOOK_URL` in your `.env` file

## Step 5: Test the webhook (optional)

Paste this in your terminal, replacing the URL with yours:

```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"KPI Bot test message"}' \
  https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

You should see "KPI Bot test message" appear in your chosen Slack channel.

## Security Note

**Treat the webhook URL like a password.** Anyone with this URL can post messages to your Slack channel. Never commit it to git or share it publicly.

## Troubleshooting

- **"no_service"** — webhook URL is invalid or was revoked. Regenerate it
- **"channel_not_found"** — the channel was deleted or renamed. Regenerate the webhook for the new channel
- **Messages not appearing** — confirm you authorized the app in your workspace (Step 3). Re-authorize if needed
- **Want to post to a different channel?** — create a new webhook. One URL = one channel
