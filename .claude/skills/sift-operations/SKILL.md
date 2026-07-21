---
name: sift-operations
description: >
  This skill should be used when the user asks anything about REI Sift operations,
  including "how do I set up a sequence", "build a sequence", "create a sequence",
  "sequence workflow", "sequential presets", "filter presets", "preset map",
  "SiftLine boards", "board workflow", "move cards between boards",
  "drip campaigns", "drip setup", "events", "tasks", "task presets",
  "tags", "filters", "skip tracing workflow", "list management",
  "property statuses", "lead management", "acquisitions workflow",
  "transactions workflow", "follow-up cadence", "round-robin assignment",
  "Sift automation", "how does Sift work", "Sift help", "Sift walkthrough",
  or any question about configuring, troubleshooting, or optimizing
  workflows inside REI Sift. Also trigger for "what sequences should I build",
  "how to organize my marketing", "niche sequential", "bulk sequential",
  "pendulum theory", "call attempts filter", "mail attempts filter",
  "deep prospecting workflow", or "Sift best practices".
version: 1.0.0
---

# REI Sift Operations Encyclopedia

Complete operational knowledge base for REI Sift. Provides reference documentation and step-by-step walkthroughs for every major Sift feature.

## How to Use This Skill

When a user asks a Sift question:

1. **Identify the domain** — determine which area of Sift the question falls into
2. **Load the right reference** — read the appropriate reference file(s) for detailed configurations
3. **Respond in hybrid format** — give a brief concept explanation, then provide the step-by-step walkthrough
4. **Generate docs when useful** — for complex preset maps or sequence plans, create a markdown or Excel file the user can keep

## Domain Routing Table

| User Question About | Reference File to Read |
|---|---|
| Sequences (general), how sequences work, sequence anatomy | `references/sequences-core.md` |
| Lead management sequences, follow-up chains, temperature cadences | `references/lead-management-sequences.md` |
| Acquisitions sequences, offer follow-up, offer outcomes | `references/acquisitions-sequences.md` |
| Board-to-board workflows, moving/duplicating cards between boards | `references/board-workflows.md` |
| Drip campaigns, SMS/email nurture, delayed follow-ups | `references/drip-campaigns.md` |
| Events, tasks, task presets, appointments, Google Calendar | `references/events-and-tasks.md` |
| Designing/ideating custom sequences, naming conventions | `references/sequence-ideation.md` |
| Sequential presets (niche), first-to-market filter presets | `references/niche-sequential-presets.md` |
| Sequential presets (bulk), stacked data filter presets | `references/bulk-sequential-presets.md` |
| Filter configurations, exact filter block settings | `references/filter-configurations.md` |
| General Sift operations, navigation, tags, lists, statuses, skip tracing | `references/general-operations.md` |
| Troubleshooting sequences, drips, tasks, or presets | `references/troubleshooting.md` |

**Important**: Always read the relevant reference file(s) before answering. Multiple references may be needed for complex questions.

## Response Format

Follow this hybrid format for every response:

### 1. Concept Brief (2-4 sentences)
Explain what the feature is and why it matters. Ground the user.

### 2. Step-by-Step Walkthrough
Provide numbered, click-by-click instructions they can follow inside Sift. Include exact field names, menu locations, and settings.

### 3. Configuration Details
For sequences: show the trigger, condition, and action(s) in a table.
For presets: show the filter blocks and their settings.
For workflows: show the full flow from trigger to outcome.

### 4. Best Practices & Tips
Include 2-3 actionable recommendations specific to what they're building.

### 5. File Output (when appropriate)
For complex configurations (preset maps with 5+ presets, multi-sequence workflows, full cadence plans), generate a markdown file the user can reference later. Save to the workspace folder.

## Core Sift Concepts (Quick Reference)

### The Sift Automation Ecosystem

| Component | What It Is | Where to Find It |
|---|---|---|
| Sequences | Automations triggered by status/card/tag changes | Left sidebar → Sequences |
| Drip Campaigns | Delayed SMS/Email sequences over time | Left sidebar → Drip Campaigns |
| Events | Container for tasks and appointments | Left sidebar → Events |
| Tasks | Individual action items with deadlines | Events section or property records |
| Task Presets | Reusable task templates used by sequences | Events → Configure Presets |
| SiftLine | Kanban boards for visual workflow management | Left sidebar → SiftLine |
| Filter Presets | Saved filter configurations for quick data segmentation | Properties → Presets |

### Integration Flow

```
Status Change → Sequence Triggers → Creates Task (from Preset) → Task appears in Events
                                 → Adds to Drip Campaign → Drip sends SMS/Email over days
                                 → Moves/Creates Card on SiftLine

Task Completed → Can trigger another Sequence → Creates next Task in chain
```

### Default Account Setup (Accounts After 4/16/2025)

Included by default: Lead Management, Acquisitions, and Transactions boards with pre-built sequences, task presets, and filter presets. See `references/general-operations.md` for the complete default inventory.

### Sequence Limits by Plan

| Plan | Sequence Limit |
|---|---|
| Essentials (grandfathered) | 3 |
| Professional | 8 |
| Business | Unlimited |

### User Permissions for Sequences

Roles that can create/edit sequences: Sensei, Super Admin, Admin, Marketer.

## Sequential Marketing Strategies

### Niche vs. Bulk

| Aspect | Niche Sequential | Bulk Sequential |
|---|---|---|
| Data Type | First-to-market / Tier 1 (probates, foreclosures) | Tier 2/3 (stacked lists, AI-enriched) |
| Calling Method | Manual click-to-dial | Multi-line power dialer |
| Urgency | High | Low to Medium |
| Preset Count | 12 presets (00-11) | 9 presets (00-08) |

### The Pendulum Theory

Marketing activities sequenced from lowest to highest cost per touch:
SMS → Cold Calling → Direct Mail → Deep Prospecting → Door Knocking

### The 3 Core Workflow Questions

1. What new data needs to be processed (skip traced)?
2. What data is ready for its first marketing touch?
3. What data has been marketed to but requires follow-up?
