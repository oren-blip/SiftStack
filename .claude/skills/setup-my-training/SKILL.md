---
name: setup-my-training
description: Personalize the DataSift Lead Management Training for this customer's business. Run this FIRST before any other skill in the datasift-lead-management plugin. Use when user says "set up my training", "personalize my training", "run setup", "run the setup skill", "start the lead management plugin", "first time setup", or anything similar. Collects company name, user name, lead manager names, phone provider, and lead sources via AskUserQuestion and saves them to .datasift-config.json in the working folder so other skills in the plugin can use them.
---

# Setup My Training

You are setting up the DataSift Lead Management plugin for a new customer. This skill collects the personalization details that every other skill in this plugin depends on. Run it first.

## What This Skill Does

Collects information via a conversational survey flow, validates the answers, and writes them to `.datasift-config.json` in the current working folder. Other skills in this plugin (`build-custom-fields`, `generate-training-manual`) read this config file to customize their output.

## Workflow

### Step 1: Confirm working folder

Before asking any questions, confirm you have a working folder. If not, tell the user:

> "Before we start, you'll need to create a folder for your DataSift training files and link it here in Cowork. Once the folder is linked, say 'Ready' and I'll run the setup."

Do not proceed until a working folder is connected.

### Step 2: Check for existing config

Check if `.datasift-config.json` already exists in the working folder using the Read tool.

- **If it exists**: Show the user what's currently configured and ask whether to keep it, update individual fields, or start over.
- **If it doesn't exist**: Proceed to Step 3.

### Step 3: Run the survey

Use AskUserQuestion to collect these answers. Ask them one at a time — do not batch into a single multi-question call. Each answer should feel natural, not like a form.

---

**Question 1 — Company name:**
Ask: "What's the name of your business? (This is what we'll put in your training materials instead of 'Florida Cash Real Estate'.)"
Expect free-text input.

---

**Question 2 — User's name:**
Ask: "What's your name? (The person running this setup and leading the team.)"
Expect free-text input.

---

**Question 3 — Team setup:**
Ask: "Do you have lead managers on your team, or are you running this yourself?"
Options:
- I have lead managers — I'll list their names
- I run lead management myself — just me for now
- I have a mix — me plus other team members

If they have lead managers or a mix, follow up: "Great — list their first names, separated by commas. Example: Maria, Kevin, Sarah."

---

**Question 4 — Phone provider:**
Ask: "What phone system does your team use for dialing sellers?"
Options:
- smrtPhone
- Twilio
- Plivo
- Another provider (I'll specify)
- None yet — I'm still setting this up

If "Another provider", follow up with free-text for the name.

---

**Question 5 — Website / SEO / PPC leads:**
Ask: "Do you have a website that generates seller leads? (This could be Carrot, a custom site, Investor Carrot, REI Blackbook, or any website where sellers fill out a form.)"
Options:
- Yes — I'll tell you about it
- No — I don't have a website for leads yet

If YES, ask two follow-ups:

5a: "What platform or website do you use? (e.g., Carrot, custom site, InvestorCarrot)"
Free-text input.

5b: "What inbox or queue in your phone system handles website leads? (e.g., in smrtPhone this might be called 'Online Inbounds' or 'Website Leads')"
Free-text input. Hint: "If you're not sure, you can check your phone system later and update this."

---

**Question 6 — Pay-Per-Lead:**
Ask: "Do you use a Pay-Per-Lead (PPL) provider?"
Options:
- Yes — I'll tell you the provider
- No — I don't use PPL

If YES, ask two follow-ups:

6a: "Which PPL provider? (e.g., PropertyLeads, USLeadList, Motivated Sellers, BatchLeads)"
Free-text input.

6b: "What inbox or queue handles your PPL leads? (e.g., 'PPL Inbounds' in smrtPhone)"
Free-text input.

---

**Question 7 — Direct mail inbox:**
Ask: "What inbox or queue handles responses from your direct mail campaigns? (e.g., 'Inbound Leads' or 'Direct Mail Inbox' in your phone system)"
Free-text input. Hint: "Most people name this something like 'Inbound Leads' or 'DM Inbounds'."

---

**Question 8 — Cold calling:**
Ask: "Does your team do outbound cold calling?"
Options:
- Yes — we have callers on the team
- No — we don't cold call right now

---

### Step 4: Confirm and save

Summarize everything in a clean table. Group the lead sources together:

```
Here's what I captured:

| Field | Value |
|-------|-------|
| Company Name | Acme Home Buyers |
| Your Name | John Smith |
| Lead Managers | Maria, Kevin |
| Phone Provider | smrtPhone |

Lead Sources:
| Source | Active | Details |
|--------|--------|---------|
| Website | Yes | Platform: Carrot, Inbox: "Online Inbounds" |
| Pay-Per-Lead | No | — |
| Direct Mail | Yes | Inbox: "Inbound Leads" |
| Cold Calling | Yes | — |

Does this look right?
```

If yes, write to `.datasift-config.json` using this schema:

```json
{
  "company_name": "Acme Home Buyers",
  "user_name": "John Smith",
  "team_setup": "has_lead_managers",
  "lead_managers": ["Maria", "Kevin"],
  "phone_provider": "smrtPhone",
  "lead_sources": {
    "website": {
      "active": true,
      "platform": "Carrot",
      "inbox": "Online Inbounds"
    },
    "ppl": {
      "active": false,
      "provider": null,
      "inbox": null
    },
    "direct_mail": {
      "active": true,
      "inbox": "Inbound Leads"
    },
    "cold_calling": {
      "active": true
    }
  },
  "created_at": "2026-04-15T00:00:00Z",
  "plugin_version": "0.1.7"
}
```

**Schema rules:**
- `company_name` and `user_name`: strings, always present
- `team_setup`: one of `"has_lead_managers"`, `"solo"`, `"mixed"`
- `lead_managers`: array of strings (empty array if solo)
- `phone_provider`: string
- `lead_sources.website.active`: boolean
- `lead_sources.website.platform`: string or null (e.g., "Carrot", "InvestorCarrot", "Custom Site")
- `lead_sources.website.inbox`: string or null (e.g., "Online Inbounds")
- `lead_sources.ppl.active`: boolean
- `lead_sources.ppl.provider`: string or null (e.g., "PropertyLeads")
- `lead_sources.ppl.inbox`: string or null (e.g., "PPL Inbounds")
- `lead_sources.direct_mail.active`: boolean (always true — everyone does direct mail)
- `lead_sources.direct_mail.inbox`: string (e.g., "Inbound Leads")
- `lead_sources.cold_calling.active`: boolean
- `created_at`: ISO 8601 timestamp
- `plugin_version`: matches `.claude-plugin/plugin.json` version

### Step 5: Confirm completion and point to next steps

After the file is written, tell the user exactly what to do next:

> "Setup complete. Your config is saved at `.datasift-config.json`.
>
> Next steps — run these when you're ready:
>
> 1. **Build your custom fields**: Say 'Run the custom field skill' to auto-create all 7 folders and 75 fields in your DataSift account. (You'll need to be logged into DataSift in Chrome with the Claude Chrome Extension connected.)
>
> 2. **Generate your training manual**: Say 'Generate my training manual' to get your personalized training HTML and Word document.
>
> You can run them in any order."

## Output Requirements

- Write `.datasift-config.json` to the current working folder only. Do not write anywhere else.
- Never skip the confirmation step — always show the summary table and wait for "yes" before writing.
- Do not invent data. If the user skips or cannot answer a question, write `null` for that field and warn them that other skills may produce incomplete output.

## Edge Cases

- **User closes mid-survey**: Don't write a partial config. If they come back, restart from Step 2.
- **User wants to change one field later**: They can re-run this skill and choose "update individual fields" in Step 2.
- **Working folder has no write permission**: Stop and tell the user the folder must be writable.
- **User doesn't know their inbox names**: Write `null`, warn that the training will use generic names ("your inbound inbox") for those slots. They can update the config later and re-generate.
