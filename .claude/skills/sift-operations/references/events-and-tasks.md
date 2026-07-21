# Events, Tasks & Task Presets

Comprehensive reference for the Events section and how it integrates with Sequences and Drip Campaigns.

## What Are Events?

The **Events** section is the central hub for managing all appointments and tasks. Think of it as the container that holds every action item in your business.

### Events Section Features

| Feature | Description |
|---------|-------------|
| All Events Tab | View appointments and tasks combined |
| Appointments Tab | View only appointments |
| Tasks Tab | View only tasks |
| Date Filtering | Filter by Today, Tomorrow, Overdue, or custom range |
| User Filtering | Filter by assigned user or assigner |
| Task Presets | Access and manage reusable templates |
| Google Calendar Sync | Automatically sync with Google Calendar |

### Accessing Events
Navigate to **Events** in the left sidebar.

## Appointments

Appointments include additional features for scheduled meetings.

### Appointment vs. Task

| Feature | Appointment | Task |
|---------|-------------|------|
| Location | Yes (address or virtual) | No |
| Outcome Tracking | Yes | No |
| Recurrence | No | Yes |
| Due Date/Time | Yes | Yes |
| Property Association | Optional | Optional |

### Appointment Types
Property Walkthrough, Contract Signing, Inspection, Other.

### Creating Appointments
1. Go to Events or open a property record
2. Click "Create" or "Add new Event"
3. Select the **Appointment** tab
4. Enter name and select type
5. (Optional) Associate with a property record
6. Set location (auto-fills from property if associated)
7. Set date and time
8. Save

## Tasks

Tasks are action items that drive your daily workflow.

### Task Features

| Feature | Description |
|---------|-------------|
| Deadline | Due date and time (or "All Day") |
| Recurrence | Daily, weekly, bi-weekly, or monthly |
| Skip Weekends | Auto-move weekend tasks to Monday |
| Assignment | Assign to user, role, or round-robin |
| Property Association | Link to specific property record |

### Task Assignment Options

| Type | How It Works |
|------|--------------|
| Specific User | Assigned to one person |
| Role | Assigned to all users with that role |
| Users Round-Robin | Evenly distributes among selected users |
| Role Round-Robin | Evenly distributes among users in a role |

### Important Permission Notes

| Role | Record Access |
|------|---------------|
| Acquisitions, Dispositions, Researchers, Prospectors | Only see records assigned to them |
| Lead Managers | See records assigned to themselves and others (not unassigned) |
| Sensei, Super Admin, Admin | See all records |

**Critical**: When assigning tasks to Acquisitions, Dispositions, Researchers, or Prospectors, you MUST also assign the property record to them. Otherwise they cannot access the record.

## Task Presets

Reusable task templates that save time and ensure consistency.

### Why Use Task Presets
- Create tasks without re-entering details each time
- Used by sequences to auto-assign tasks based on triggers
- Maintain consistent naming across your team

### Creating Task Presets
1. Go to **Events** page
2. Click **"Configure Presets"** or **"Preset"** option
3. Create a new group (optional)
4. Click **"Add New Preset"**
5. Configure: task name, assignment, deadline, recurrence
6. Save

### Default Task Presets (Accounts After 4/16/2025)

| Preset Group | Tasks Included |
|---|---|
| Lead Management | Call New Lead, No Contact New Lead, Nurture New Lead, Cold Follow-up, Warm Follow-up, Hot Follow-up |
| Acquisitions | Make Offer, Offer Follow-Up, Send Back to LM |
| Transactions | Contract/title follow-ups, Seller follow-ups |

**Note**: All defaults assigned to Sensei. Teams should update assignees.

## How Events Connect to Sequences

```
Trigger fires (e.g., status change to "New Lead")
    → Sequence conditions checked
    → "Create New Task" action executes
    → Task created using Task Preset
    → Task appears in Events section
    → Task assigned to specified user/role
```

### Task Triggers in Sequences

| Trigger | When It Fires |
|---------|---------------|
| Task Created | When any task is created on a record |
| Task Completed | When a specific task is marked complete |

## How Events Connect to Drip Campaigns

```
Trigger fires (e.g., status change to "Dead Lead")
    → Sequence executes "Add to Drip Campaign"
    → Record added to drip campaign
    → Drip executes steps over time
    → SMS/Email sent at intervals
    → Final task created (appears in Events)
```

## The Complete Integration Flow

```
1. Property status changes to "New Lead"
    → Sequence: Creates task, card, adds to drip
2. Drip campaign runs over 7 days
    → Day 0: Welcome SMS → Day 1: Follow-up → Day 7: Final task
3. Task completed → User changes status to "Hot Lead"
4. New sequence triggers → HOT Follow-Up A01 task created
5. Task completed → Chain sequence → HOT Follow-Up A02
    → (Pattern continues through cadence)
```

### Key Integration Points

| From | To | Connection |
|------|-----|------------|
| Sequence | Task | "Create New Task" action |
| Sequence | Drip Campaign | "Add to Drip Campaign" action |
| Drip Campaign | Task | Task step in drip |
| Task Completion | Sequence | "Task Completed" trigger |
| All Tasks | Events | All tasks appear in Events |

## Viewing Event History

### Activity Log
Open property record → **Activity Log** — shows task creation, completion, appointment activity, and sequence-triggered events.

### Completed Events
1. **For a specific record**: Property record → Assigned Events → Completed tab
2. **For all records**: Events section → Completed tab → Filter by date/user

## Best Practices

1. **Use Task Presets** — create presets for any repeating task
2. **Connect Sequences to Presets** — use existing presets in sequences rather than ad-hoc tasks
3. **End Drips with Tasks** — add a task step at the end for human follow-up
4. **Check Events Daily** — use as your daily dashboard
5. **Assign Records with Tasks** — for restricted roles, always assign the property too
6. **Use Google Calendar** — enable sync for full visibility
