# Lead Management Sequences

Complete configurations for lead management workflows. Clearly distinguishes between what's included in default accounts vs. what you need to build.

## Default vs. Custom Sequences

### Included in Default Accounts (After 4/16/2025)

| Item | Description | Action Required |
|------|-------------|-----------------|
| Lead Management Board | SiftLine board with phases for lead lifecycle | None, ready to use |
| Default Sequences | Automations for status changes and card movements | Review and toggle on/off |
| Task Presets | Call New Lead, No Contact New Lead, Nurture New Lead, Cold/Warm/Hot Follow-up | Customize assignees if needed |
| Property Statuses | New Lead, No Contact New Lead, Cold/Warm/Hot Lead, Ghosting Lead, Dead Lead | None, ready to use |

### NOT Included (Custom Build Required)

| Item | Description | Why Build It |
|------|-------------|--------------|
| Follow-up chain sequences | Task completion triggers next task (A01 → A02 → A03) | Automates cadence without manual intervention |
| Custom cadence timing | Specific intervals for your market | Tailors follow-up frequency to your business |
| Temperature-based drip triggers | Add to drip campaigns on status change | Automates long-term nurture |

## Default Lead Flow

| Status | Default Task Created | Default Frequency |
|--------|---------------------|-------------------|
| New Lead | Call New Lead | Due immediately (1 day) |
| No Contact New Lead | No Contact New Lead | Due daily (3-5 days) |
| Cold Lead | Cold Follow-up | Due every 45 days |
| Warm Lead | Warm Follow-up | Due every 14 days |
| Hot Lead | Hot Follow-up | Due every 7 days |

## Custom Sequence Configurations

### New Lead Intake Sequence

**Note**: Default accounts include a version. Build only if you need custom behavior.

| Component | Setting |
|-----------|---------|
| **Trigger** | Property Status Change |
| **Condition** | From "Any" to "New Lead" |

**Actions (in order)**:
1. **Assign Property** — Lead Manager (or round-robin if multiple)
2. **Clear Property Tasks** — Removes existing tasks from previous workflows
3. **Create New Card** — Board: Lead Management, Phase: New Lead
4. **Create New Task** — "Call New Lead", Due: 0 days, Toggle: Assign to property

**Optional Add-ons**: Send SMS notification, Send Email, Add to Drip Campaign

### Hot Lead Sequence

| Component | Setting |
|-----------|---------|
| **Trigger** | Property Status Change |
| **Condition** | From "Any" to "Hot Lead" |

**Actions**:
1. Move Card to "Hot" phase on Lead Management board
2. Create Task: "HOT Follow-Up A01" (Due: 1 day)
3. (Optional) Add to Drip Campaign: "Hot Lead Nurture"

### Warm Lead Sequence

| Component | Setting |
|-----------|---------|
| **Trigger** | Property Status Change |
| **Condition** | From "Any" to "Warm Lead" |

**Actions**:
1. Move Card to "Warm" phase on Lead Management board
2. Create Task: "WARM Follow-Up A01" (Due: 15 days)

### Cold Lead Sequence

| Component | Setting |
|-----------|---------|
| **Trigger** | Property Status Change |
| **Condition** | From "Any" to "Cold Lead" |

**Actions**:
1. Move Card to "Cold" phase on Lead Management board
2. Create Task: "COLD Follow-Up A01" (Due: 45 days)

## Follow-Up Chain Sequences (Custom Build Required)

**Important**: NOT included in defaults. Build each individually.

### How Follow-Up Chains Work

```
Task "HOT Follow-Up A01" completed
    → Sequence "Hot A01 Complete" triggers
    → Creates Task "HOT Follow-Up A02" (Due: 1 day)
    → Task "HOT Follow-Up A02" completed
    → Sequence "Hot A02 Complete" triggers
    → Creates Task "HOT Follow-Up A03" (Due: 1 day)
    → (Pattern continues...)
```

### Building a Follow-Up Chain

**Step 1**: Create Task Presets for each step (HOT Follow-Up A01, A02, A03, etc.)

**Step 2**: Create a sequence for each transition:

**Example — Hot Follow-Up A01 Complete**:

| Component | Setting |
|-----------|---------|
| **Trigger** | Task Completed |
| **Condition** | Task Is: "HOT Follow-Up A01" |
| **Action** | Create Task: "HOT Follow-Up A02" (Due: 1 day) |

Repeat for each step in the cadence.

### Recommended Hot Lead Cadence (26 days, 15 sequences required)

| Task | Day | Due After Previous | Sequence to Build |
|------|-----|-------------------|-------------------|
| A01 | 1 | 1 day | Hot A01 Complete |
| A02 | 2 | 1 day | Hot A02 Complete |
| A03 | 3 | 1 day | Hot A03 Complete |
| A04 | 5 | 2 days | Hot A04 Complete |
| A05 | 7 | 2 days | Hot A05 Complete |
| A06 | 9 | 2 days | Hot A06 Complete |
| A07 | 11 | 2 days | Hot A07 Complete |
| A08 | 13 | 2 days | Hot A08 Complete |
| A09 | 15 | 2 days | Hot A09 Complete |
| A10 | 17 | 2 days | Hot A10 Complete |
| A11 | 19 | 2 days | Hot A11 Complete |
| A12 | 21 | 2 days | Hot A12 Complete |
| A13 | 23 | 2 days | Hot A13 Complete |
| A14 | 25 | 2 days | Hot A14 Complete |
| A15 | 26 | 1 day | Hot A15 Complete |
| A16 | 26 | 0 days | (End of chain) |

### Recommended Warm Lead Cadence (180 days)

| Task | Day | Due After Previous |
|------|-----|-------------------|
| A01 | 15 | 15 days |
| A02 | 25 | 10 days |
| A03 | 30 | 5 days |
| A04 | 45 | 15 days |
| A05 | 55 | 10 days |
| A06 | 60 | 5 days |
| (Pattern repeats every 30 days) |

### Recommended Cold Lead Cadence (360 days)

| Task | Day | Due After Previous |
|------|-----|-------------------|
| A01 | 45 | 45 days |
| A02 | 60 | 15 days |
| A03 | 90 | 30 days |
| A04 | 135 | 45 days |
| A05 | 150 | 15 days |
| A06 | 180 | 30 days |
| (Pattern repeats every 90 days) |

## Dead Lead Revival Sequence (Custom Build Required)

| Component | Setting |
|-----------|---------|
| **Trigger** | Property Status Change |
| **Condition** | From "Any" to "Dead Lead" |

**Actions**:
1. Move Card to "Dead" phase on Lead Management board
2. Create Task: "DEAD Follow-Up A01" (Due: 90 days)
3. (Optional) Add to Drip Campaign: "Dead Lead Re-engagement"

### Dead Lead Cadence (360 days, 4 sequences required)

| Task | Day | Due After Previous |
|------|-----|-------------------|
| A01 | 90 | 90 days |
| A02 | 180 | 90 days |
| A03 | 270 | 90 days |
| A04 | 360 | 90 days |

## Best Practices

1. **Start with defaults** — use them for 2-4 weeks before customizing
2. **Customize assignees first** — most common change is updating from Sensei to your team
3. **Build chains gradually** — add one chain sequence at a time, test before adding the next
4. **Test thoroughly** — manually trigger on a test record to verify
5. **Check Activity Log** — always verify execution in the property record
6. **Name consistently** — use "LM - Hot A01 Complete" format
7. **Organize with folders** — create a "Lead Management" folder

### Sequence Priority (Limited Plans)

| Priority | Sequence | Why |
|----------|----------|-----|
| 1 | New Lead Intake (if customizing default) | Foundation of your workflow |
| 2 | Hot Lead temperature change | Most valuable leads |
| 3 | Hot A01-A05 chain (first 5 follow-ups) | Highest-impact automation |
