---
name: build-custom-fields
description: Auto-build the complete 7-folder, 75-field custom field structure in the user's DataSift account using the DataSift API. Use when user says "build my custom fields", "create custom fields", "run the custom field skill", "set up custom fields", "install the lead management custom fields", or anything similar. Requires the user to be logged into DataSift in Chrome with the Claude Chrome Extension connected. Pulls their auth token from browser localStorage and POSTs every field to apiv2.reisift.io in about 60 seconds.
---

# Build Custom Fields

You are setting up the 7-folder, 75-field lead management custom field structure in the user's DataSift account. This skill uses the DataSift API directly — not the UI — to create every field in under a minute.

## Prerequisites Check

Before running, verify ALL of these. If any are missing, stop and tell the user clearly what to do.

1. **`.datasift-config.json` exists** in the working folder. If missing, tell the user to run `setup-my-training` first.
2. **Claude Chrome Extension is connected** (use `mcp__Claude_in_Chrome__tabs_context_mcp` to check).
3. **User is logged into DataSift** at https://app.datasift.io or https://app.reisift.io in the connected Chrome tab.
4. **`field-definitions.json` reference file** loads correctly from `references/field-definitions.json`.

## Workflow

### Step 1: Orient the user and confirm they're ready

Tell the user what's about to happen:

> "I'm going to create 7 folders and 75 custom fields in your DataSift account using the API. This takes about 60 seconds.
>
> Before I start, confirm:
> 1. You're logged into DataSift at app.datasift.io in Chrome
> 2. The Claude Chrome Extension shows as connected
>
> Ready? Say 'go' and I'll start."

Wait for explicit "go" / "yes" / "ready".

### Step 2: Verify the user is on a DataSift page

Use `mcp__Claude_in_Chrome__tabs_context_mcp` to get the active tab. If no DataSift tab is open, ask the user to navigate to app.datasift.io and say "go" again.

### Step 3: Grab the auth token from localStorage

Run this JavaScript in the DataSift tab via `mcp__Claude_in_Chrome__javascript_tool`:

```js
localStorage.getItem('rs_token')
```

If it returns `null` or empty, the user isn't actually logged in. Tell them to log in and try again.

### Step 4: Auto-create the 7 groups via API (do NOT ask user to create them manually)

The DataSift API supports creating groups. You create them programmatically — the user does NOT touch the UI for this step.

Run this as a single batch inside `mcp__Claude_in_Chrome__javascript_tool`. The script:
1. GETs existing groups to avoid duplicates
2. Creates any missing groups via POST
3. Returns the `{ name → id }` mapping for all 7

```js
const TOKEN = localStorage.getItem('rs_token');
const HEADERS = {
  "Accept": "application/json, text/plain, */*",
  "Authorization": "Bearer " + TOKEN,
  "X-REISIFT-UI-VERSION": "2022.02.01.7",
  "Content-Type": "application/json"
};
const GROUPS_URL = "https://apiv2.reisift.io/api/internal/custom-fields/groups/";

const GROUP_NAMES = [
  "Qualifying Questions",
  "Property Condition - General",
  "CapEx Assessment",
  "Property Debts & Encumbrances",
  "Title & Ownership",
  "Deal Intelligence",
  "Appointment & Next Steps"
];

// 1) Fetch existing groups
const existingResp = await fetch(GROUPS_URL + "?limit=100", { headers: HEADERS });
const existingJson = await existingResp.json();
const existingGroups = existingJson.results || existingJson.data || existingJson;
const existingByName = {};
for (const g of existingGroups) {
  existingByName[g.name || g.label] = g.id;
}

// 2) Create any missing groups
const groupMap = {};  // name -> id
const created = [];
const skipped = [];
const failed = [];

for (const name of GROUP_NAMES) {
  if (existingByName[name]) {
    groupMap[name] = existingByName[name];
    skipped.push({ name, id: existingByName[name], reason: "already exists" });
    continue;
  }
  const payload = {
    entity_type: "property",
    name: name,
    is_active: true
  };
  try {
    const resp = await fetch(GROUPS_URL, {
      method: "POST",
      headers: HEADERS,
      body: JSON.stringify(payload)
    });
    if (resp.status === 201 || resp.status === 200) {
      const body = await resp.json();
      groupMap[name] = body.id;
      created.push({ name, id: body.id });
    } else {
      const err = await resp.text();
      failed.push({ name, status: resp.status, error: err.slice(0, 200) });
    }
  } catch (e) {
    failed.push({ name, error: e.message });
  }
  await new Promise(r => setTimeout(r, 150));
}

({ groupMap, created, skipped, failed });
```

**Error handling:**

- If the group-create POST returns `400` with a message about `name` vs `label` field, retry with `{ entity_type: "property", label: name, is_active: true }` instead.
- If the GET returns the group list in a different shape (e.g., nested under `.results` vs `.data` vs top-level array), the code above already handles the three most common shapes.
- If `failed` contains any groups, report them to the user before proceeding. Do not try to create fields in groups that failed — those fields will fail too.

Save the final `groupMap` (name → id) in memory. You'll use it in Step 7 to resolve each field's `group_id`.

### Step 5: Confirm group creation with the user

Show a summary:

```
Groups ready:
  ✓ Qualifying Questions (ID: 318) — created
  ✓ Property Condition - General (ID: 319) — created
  ✓ CapEx Assessment (ID: 320) — created
  ✓ Property Debts & Encumbrances (ID: 321) — already existed
  ✓ Title & Ownership (ID: 322) — created
  ✓ Deal Intelligence (ID: 323) — created
  ✓ Appointment & Next Steps (ID: 324) — created

Now creating 75 fields...
```

If any group failed, stop and report. Do not continue to field creation.

### Step 6: Load field definitions

Read `references/field-definitions.json`. This file contains:
- 7 group definitions with `order` numbers matching Step 4 order
- 75 field definitions, each with `group_order`, `label`, `field_type`, `placeholder`, and (for selects) `options`

### Step 7: Build and POST each field

For each field in the definitions:

1. Resolve `group_order` (1-7) → group name → `group_id` using the `groupMap` from Step 4
2. Build the payload:

```js
// For non-dropdown fields:
{
  "entity_type": "property",
  "group_id": <mapped_id>,
  "label": <field.label>,
  "field_type": <field.field_type>,
  "required": false,
  "is_active": true,
  "placeholder": <field.placeholder>
}

// For dropdown (select) fields, add:
"options": field.options.map(o => ({ "label": o }))
```

3. POST to `https://apiv2.reisift.io/api/internal/custom-fields/` with the required headers:

```
Accept: application/json, text/plain, */*
Authorization: Bearer <token>
X-REISIFT-UI-VERSION: 2022.02.01.7
Content-Type: application/json
```

4. Add a 150ms delay between calls to avoid rate limiting.

**CRITICAL — run this as a single JavaScript loop in the browser, not 75 separate tool calls.** The entire batch should execute client-side inside one `mcp__Claude_in_Chrome__javascript_tool` call. Collect success/failure counts in an array and return the summary.

Example batch script skeleton:

```js
const TOKEN = localStorage.getItem('rs_token');
// groupMap is name → id from Step 4. The field-definitions.json lists each group
// by `order` (1-7); resolve order → name → id from the groups list in field-definitions.
const GROUPS_BY_ORDER = { 1: "Qualifying Questions", 2: "Property Condition - General", 3: "CapEx Assessment", 4: "Property Debts & Encumbrances", 5: "Title & Ownership", 6: "Deal Intelligence", 7: "Appointment & Next Steps" };
const FIELDS = [ ... ]; // 75 field defs from references/field-definitions.json

const results = { success: [], failed: [] };

// groupMap from Step 4 (name -> id). Reuse it here.
for (const f of FIELDS) {
  const groupName = GROUPS_BY_ORDER[f.group_order];
  const groupId = groupMap[groupName];
  if (!groupId) {
    results.failed.push({ label: f.label, error: `No group_id found for "${groupName}" — Step 4 failed for this group` });
    continue;
  }
  const payload = {
    entity_type: "property",
    group_id: groupId,
    label: f.label,
    field_type: f.field_type,
    required: false,
    is_active: true,
    placeholder: f.placeholder
  };
  if (f.options) {
    payload.options = f.options.map(o => ({ label: o }));
  }

  try {
    const resp = await fetch("https://apiv2.reisift.io/api/internal/custom-fields/", {
      method: "POST",
      headers: {
        "Accept": "application/json, text/plain, */*",
        "Authorization": "Bearer " + TOKEN,
        "X-REISIFT-UI-VERSION": "2022.02.01.7",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    if (resp.status === 201) {
      results.success.push(f.label);
    } else {
      const err = await resp.text();
      results.failed.push({ label: f.label, status: resp.status, error: err });
    }
  } catch (e) {
    results.failed.push({ label: f.label, error: e.message });
  }
  await new Promise(r => setTimeout(r, 150));
}

results;
```

### Step 8: Report results

Show the user a clean summary:

```
Done. Created 73 / 75 fields.

Failed:
- "Roof Notes" (status 400: duplicate label)
- "Plumbing Notes" (status 400: duplicate label)

What to do about failures:
- Duplicate label (400): field already exists with that name. Safe to ignore or delete the existing one and re-run.
- Unauthorized (401): your token expired. Refresh DataSift and re-run.
- Rate limit (429): increase delay, re-run only the failed fields.
```

### Step 9: Verify in DataSift UI

Tell the user:

> "Open **Settings → Custom Fields → Fields tab** to see them all. They're grouped by the 7 folders you created. Each property record in DataSift will now have these fields available during intake calls."

## Field Type Mapping Reference

The DataSift API uses these values (from CUSTOM_FIELDS.md):

| Intent | API `field_type` | DataSift UI Label |
|---|---|---|
| Dropdown (single select) | `select` | Dropdown (single) |
| Number | `number` | Number |
| Single-line text | `text_input` | Single line |
| Multi-line text | `text` | Multi line |
| Date | `date` | Date picker |

**WARNING:** `text_input` and `text` are backwards from what you'd expect. `text` = multi-line textarea, `text_input` = single-line input. The `field-definitions.json` already uses the correct API values.

## Error Handling

- **401 Unauthorized** → token expired. Tell user to refresh DataSift and re-run.
- **403 Forbidden** → missing `X-REISIFT-UI-VERSION` header. Verify it's set to `2022.02.01.7`.
- **400 Bad Request** → usually a duplicate label in the same group. Report which field and move on.
- **429 Rate Limit** → increase delay to 300ms and retry only the failures.
- **Network error** → check Chrome extension is still connected, retry.

## Do NOT

- Do not hardcode group IDs. They're account-specific and must be discovered at runtime.
- Do not ask the user to create groups manually in the UI. The API supports it — create them programmatically in Step 4.
- Do not send all 75 fields without the 150ms delay — DataSift will rate limit.
- Do not modify the `field-definitions.json` file at runtime. It's reference data.
- Do not proceed to Step 7 (field creation) if any group failed to create in Step 4. Fix the group failure first.
