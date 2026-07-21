# Niche Sequential Presets

Complete preset map and consultative workflow for first-to-market (Tier 1) data marketing.

## What is Niche Sequential?

Niche Sequential marketing targets **first-to-market / Tier 1 data** such as probates, pre-foreclosures, tax sales, code violations, and other courthouse-sourced lists. These records are high-urgency and require manual click-to-dial calling.

### Key Characteristics

| Aspect | Setting |
|---|---|
| Data Type | First-to-market / Tier 1 |
| Calling Method | Manual click-to-dial |
| Urgency | High |
| Common Tags | `courthouse data`, `probate`, `foreclosure` |
| Preset Count | 12 presets (00-11) |

## Preset Map (Base Template)

**Folder Name**: `00. Niche Sequential`

| # | Preset Name | Purpose |
|---|---|---|
| 00 | Needs Skipped | New, unprocessed records with no phone numbers — need skip tracing |
| 01 | Skipped No Numbers | Skip traced but yielded no numbers — needs second attempt or manual research |
| 02 | Ready to Call | Records with phone numbers, zero call attempts — primary starting point |
| 03 | FTM Follow Up 1 | First follow-up call (1 attempt made) |
| 04 | FTM Follow Up 2 | Second follow-up call (2 attempts made) |
| 05 | FTM Follow Up 3 | Third and final follow-up call before next channel |
| 06 | Needs 1st Mail | Completed calling sequence (3+ attempts), ready for first mail piece |
| 07 | Mail Monthly | Long-term nurture — mail piece once per month |
| 08 | Vacant Mailing → DP | Vacant mailing address — send to Deep Prospecting |
| 09 | Return Mail → DP | Mail returned — bad address, needs Deep Prospecting |
| 10 | No Response DM → DP | Extended no contact via calls or mail — move to Deep Prospecting |
| 11 | Not Interested Qrtly | Re-engage quarterly with previously not-interested owners |

## Filter Configurations

### 00. Needs Skipped

| Filter Block | Category | Settings |
|---|---|---|
| Any Lists (OR) | General | Include first-to-market lists |
| Any Tags (OR) | General | Include data tag (e.g., `courthouse data`) |
| Property Status | Property Filters | **Do Not Include** → Any Statuses |
| Call Attempts | Marketing | Min: 0, Max: 0 |
| Params & Others | General | Numbers: No, Skiptraced: No |

### 01. Skipped No Numbers

| Filter Block | Category | Settings |
|---|---|---|
| Any Lists (OR) | General | Include first-to-market lists |
| Any Tags (OR) | General | Include data tag |
| Params & Others | General | Numbers: No, Skiptraced: Yes |

### 02. Ready to Call

| Filter Block | Category | Settings |
|---|---|---|
| Any Lists (OR) | General | Include first-to-market lists |
| Any Tags (OR) | General | Include data tag |
| Property Status | Property Filters | **Do Not Include** → Lead, Not Interested (closed statuses) |
| Call Attempts | Marketing | Min: 0, Max: 0 |
| Params & Others | General | Numbers: Yes |

### 03-05. FTM Follow Up 1, 2, 3

| Filter Block | Category | Settings |
|---|---|---|
| Any Lists (OR) | General | Include first-to-market lists |
| Any Tags (OR) | General | Include data tag |
| Call Attempts | Marketing | Min: X, Max: X (where X = attempt number) |
| Phone Statuses | General | **Do Not Include** → Correct |

### 06. Needs 1st Mail

| Filter Block | Category | Settings |
|---|---|---|
| Call Attempts | Marketing | Min: 4 (or custom max) |
| Direct Mail Attempts | Marketing | Min: 0, Max: 0 |
| Params & Others | General | Vacant Mailing: No |
| All Tags (AND) | General | **Do Not Include** → return mail |

### 07. Mail Monthly

| Filter Block | Category | Settings |
|---|---|---|
| Direct Mail Attempts | Marketing | Min: 1, Max: 12 |
| Last Direct Mailed | Marketing | Prior to Date → 1 month ago |
| Params & Others | General | Vacant Mailing: No |
| All Tags (AND) | General | **Do Not Include** → return mail |

### 08. Vacant Mailing → DP

| Filter Block | Category | Settings |
|---|---|---|
| Params & Others | General | Vacant Mailing: Yes |
| Phone Statuses | General | **Do Not Include at least one phone** → Correct, Correct DNC |

### 09. Return Mail → DP

| Filter Block | Category | Settings |
|---|---|---|
| Any Tags (OR) | General | Include → return mail |
| Direct Mail Attempts | Marketing | Min: 1 |

### 10. No Response DM → DP

| Filter Block | Category | Settings |
|---|---|---|
| Call Attempts | Marketing | Min: 4 |
| Direct Mail Attempts | Marketing | Min: 6, Max: 12 |
| Phone Statuses | General | **Do Not Include** → Correct |

### 11. Not Interested Qrtly

| Filter Block | Category | Settings |
|---|---|---|
| Property Status | Property Filters | Include → Not Interested |
| Last Updated Field | Property Filters | Field: Status, Date: Prior to 3 months ago |
| Params & Others | General | Numbers: Yes |

## Consultative Workflow

When helping a user build niche sequential presets:

### Step 1: Discovery
Ask about their specific niches, marketing channels, team structure, data tags, and call attempt cadence.

### Step 2: Design
Start from this base template and customize for their lists, tags, and attempt thresholds.

### Step 3: Present
Deliver the customized preset map as a document for review.

### Step 4: Implementation Guidance
Walk them through building each preset in order, starting with "00. Needs Skipped".
