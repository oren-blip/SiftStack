# Google Cloud Setup — Service Account for Sheets Access

The KPI bot reads your Google Sheet using a **service account** — a non-human Google identity that can authenticate without a password. You grant the service account read access to your sheet, and the bot uses its JSON key to authenticate.

This is a one-time setup. Takes about 10 minutes.

## Step 1: Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Sign in with any Google account (personal or workspace — doesn't matter which, but remember which one)
3. Top bar → click the project selector (left of the search bar) → **New Project**
4. Name it something like `datasift-kpi-bot` → click **Create**
5. Wait for the project to finish creating (top-right notification), then select it from the project selector

## Step 2: Enable the Google Sheets API

1. In the left sidebar: **APIs & Services → Library**
2. Search for **Google Sheets API** → click it → click **Enable**
3. Wait ~10 seconds for it to activate

## Step 3: Create a service account

1. Left sidebar: **APIs & Services → Credentials**
2. Top bar: **+ Create Credentials → Service Account**
3. Service account name: `kpi-bot` (or any name you'll remember)
4. Service account ID: auto-fills — leave it
5. Click **Create and Continue**
6. Grant role: **Viewer** (or skip — the role doesn't matter for Sheets access, which is granted per-sheet)
7. Click **Continue → Done**

## Step 4: Generate a JSON key

1. Back on the Credentials page, click the service account you just created (click the email address)
2. Top tabs: click **Keys**
3. **Add Key → Create New Key → JSON → Create**
4. A JSON file downloads automatically. **This is your `service_account.json` — treat it like a password.**

## Step 5: Find the service account email

1. While still on the service account page, copy the email at the top (looks like `kpi-bot@datasift-kpi-bot.iam.gserviceaccount.com`)
2. You'll need this in the next step

## Step 6: Share your KPI Google Sheet with the service account

1. Open your KPI Google Sheet
2. Top right: **Share**
3. Paste the service account email (`...@...iam.gserviceaccount.com`)
4. Set permission to **Viewer**
5. **Uncheck "Notify people"** (service accounts can't receive email anyway)
6. Click **Share**

## Step 7: Get your Spreadsheet ID

Look at your sheet's URL:
```
https://docs.google.com/spreadsheets/d/1AbCd2ef3gH4iJkL5mNoPqR6sTuVwXyZ/edit
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      This is your spreadsheet ID
```

Copy everything between `/d/` and `/edit`. That's the value for `KPI_SPREADSHEET_ID`.

## Step 8: Save the JSON key

Rename the downloaded JSON file to exactly `service_account.json` and place it in the same folder as `kpi_slack_bot.py`.

## Troubleshooting

- **"The caller does not have permission"** — you forgot Step 6 (share the sheet with the service account email)
- **"Requested entity was not found"** — wrong `KPI_SPREADSHEET_ID` value. Double-check the URL
- **"Google Sheets API has not been used in project..."** — you skipped Step 2. Enable the Sheets API
- **"Invalid JWT Signature"** — corrupted JSON key. Delete the key in Credentials, generate a new one
