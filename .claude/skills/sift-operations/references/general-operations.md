# General Sift Operations

Reference for navigation, tags, lists, statuses, filters, skip tracing workflows, and general Sift configuration.

## Sift Navigation

| Section | Location | Purpose |
|---------|----------|---------|
| Properties | Left sidebar → Properties | View and manage all property records |
| SiftLine | Left sidebar → SiftLine | Kanban boards for visual workflows |
| Sequences | Left sidebar → Sequences | Automation setup and management |
| Drip Campaigns | Left sidebar → Drip Campaigns | Delayed SMS/Email campaigns |
| Events | Left sidebar → Events | Tasks and appointments |
| Settings | Left sidebar → Settings | Account configuration |

## Property Statuses

### Default Statuses (Accounts After 4/16/2025)

| Status | Purpose | Board Phase |
|--------|---------|-------------|
| New Lead | Fresh lead just entered the system | New Lead |
| No Contact New Lead | Attempted contact, no response | No Contact |
| Cold Lead | Low interest/engagement | Cold |
| Warm Lead | Moderate interest/engagement | Warm |
| Hot Lead | High interest, actively engaged | Hot |
| Ghosting Lead | Was engaged, stopped responding | Ghosting |
| Dead Lead | No longer a viable lead | Dead |
| Not Interested | Explicitly said not interested | — |
| Listed | Property is listed on market | — |
| Sold | Property has been sold | — |
| Under Contract | Deal is under contract | Under Contract |
| Closed | Deal has closed | Closed |

### Custom Statuses
Create custom statuses in Settings → Property Statuses. Custom statuses can be used as sequence triggers and conditions.

## Tags

### What Tags Are
Tags are labels attached to property records for categorization and filtering. They're used in filter presets and as sequence triggers/conditions.

### Common Tag Uses

| Tag | Purpose |
|-----|---------|
| `courthouse data` | First-to-market niche data identifier |
| `dataflik` | Bulk/stacked data identifier |
| `probate` | Probate-sourced records |
| `foreclosure` | Foreclosure-sourced records |
| `return mail` | Mail was returned (bad address) |
| `High Value` | High-value property/deal |
| `DNC` | Do Not Call |
| `Closed 2025` | Deals closed in current year |

### Managing Tags
- **Add tags manually**: Open property → Tags section → Add tag
- **Add tags via upload**: Include a "Tags" column in your CSV
- **Add tags via sequence**: Use "Add Property Tags" action
- **Filter by tags**: Use "Any Tags (OR)" or "All Tags (AND)" filter blocks

### Tag Triggers in Sequences
- **Property Tags Added** — triggers when a specific tag is added
- **Property Tags Removed** — triggers when a tag is removed

**Important**: Tag triggers only work for manual tag additions, NOT for tags added via uploads.

## Lists

### What Lists Are
Lists are collections of property records, typically organized by data source, niche, or marketing campaign.

### Common List Uses
- Separate records by data source (e.g., "Knox County Probates Q1 2025")
- Organize by niche (e.g., "Pre-Foreclosures", "Tax Delinquent")
- Track marketing campaigns (e.g., "March Mail Campaign")

### Managing Lists
- **Create lists**: Properties → Lists → Create New List
- **Add to lists via upload**: Specify list during CSV upload
- **Add to lists via sequence**: Use "Add Property Lists" action
- **Filter by lists**: Use "Any Lists (OR)" or "All Lists (AND)" filter blocks

## Filters & Filter Presets

### Filter Categories

| Category | Filter Blocks Available |
|----------|----------------------|
| General | Any Lists, Any Tags, All Tags, Params & Others, Phone Statuses |
| Property Filters | Property Status, Last Updated Field, Property Type, Equity |
| Marketing | Call Attempts, Direct Mail Attempts, Last Called, Last Direct Mailed, SMS Attempts |
| Contact | Contact Name, Contact Email, Phone Number |

### Key Filter Blocks Explained

**Call Attempts**: Filter by number of call attempts (Min/Max). Used in sequential presets to segment by marketing progress.

**Direct Mail Attempts**: Filter by number of mail pieces sent. Used to move records from calling to mailing stages.

**Params & Others**: Multi-purpose filter including Numbers (Yes/No), Skiptraced (Yes/No), Vacant Mailing (Yes/No).

**Phone Statuses**: Filter by phone number status (Correct, Wrong, Dead, DNC, etc.). Critical for routing to Deep Prospecting.

**Last Updated Field**: Filter by when a specific field was last updated. Used for quarterly re-engagement presets.

### Creating Filter Presets

1. Go to **Properties**
2. Build your filter using filter blocks
3. Click **"Save as Preset"**
4. Name the preset and select a folder
5. Save

### Preset Folders
Organize presets into folders (e.g., "Niche Sequential", "Bulk Sequential") for easy navigation.

## Skip Tracing Workflow

### What Skip Tracing Does
Skip tracing finds phone numbers and contact information for property owners.

### Standard Skip Tracing Flow in Sift

1. **Upload data** — import property records via CSV
2. **Apply tags/lists** — categorize records by source
3. **Filter for unskipped records** — use "Needs Skipped" preset (Numbers: No, Skiptraced: No)
4. **Run skip trace** — select records and run through Sift's skip trace provider
5. **Check results** — use "Skipped No Numbers" preset to find records without results
6. **Move to calling** — records with numbers appear in "Ready to Call" preset

### Skip Trace Providers in Sift
Sift integrates with multiple skip trace providers. Configure in Settings → Integrations.

## User Roles & Permissions

| Role | Sequences | Records | Tasks |
|------|-----------|---------|-------|
| Sensei (Owner) | Full access | All records | All tasks |
| Super Admin | Full access | All records | All tasks |
| Admin | Full access | All records | All tasks |
| Marketer | Can create/edit | All records | Assigned tasks |
| Lead Manager | View only | Own + assigned | Assigned tasks |
| Acquisitions | No access | Own records only | Assigned tasks |
| Dispositions | No access | Own records only | Assigned tasks |
| Researchers | No access | Own records only | Assigned tasks |
| Prospectors | No access | Own records only | Assigned tasks |

## Default Account Inventory (After 4/16/2025)

### SiftLine Boards
Lead Management, Acquisitions, Transactions, Wholesale, Flips, Rentals

### Sequences
Lead Management, Acquisitions, and Transactions automations

### Task Presets
Call New Lead, No Contact New Lead, Nurture New Lead, Cold/Warm/Hot Follow-up, Make Offer, Offer Follow-Up, Send Back to LM

### Filter Presets
My Tasks, Acquisitions, Lead Management, Transactions, REISift Base Presets

### Property Statuses
New Lead, No Contact New Lead, Cold/Warm/Hot Lead, Ghosting Lead, Dead Lead, Not Interested, Listed, Sold, Under Contract, Closed

## Integrations

### Communication
- **smrtPhone** — calling and SMS
- **Twilio** — SMS
- **Plivo** — SMS
- **Gmail** — email

### Calendar
- **Google Calendar** — sync events and tasks

### Skip Trace
- Multiple providers available in Settings → Integrations
