# Guide: crm-tasks

> Source: https://learn.datasift.ai/crm-tasks (Day 4 module, fetched 2026-08-28)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      CRM Execution

# CRM Tasks &Task Presets

      The difference between operators who close 2 deals a month and 20 is not more leads. It is fewer missed follow-ups.

          18 min read

CRM Quartet: Lead Mgmt, Events, Sequences

## Your CRM Is Built. Now Work It.

    Sequences are live. Events are configured. But none of that matters if tasks pile up and leads go cold.

    Most operators spend weeks setting up their CRM. Sequences fire. Tags apply. Statuses change. Then Monday morning the task queue shows 47 overdue tasks. They cherry-pick three easy ones, skip the rest, and wonder why deals keep falling through.

    The gap is not in setup. It is in execution. Every task is a promise to a lead: "Someone will follow up." Break that promise and the lead goes cold. Break it enough times and your pipeline dies.

    This page assumes you have completed the Events Deep Dive and Sequences guide. Tasks are the atomic unit those systems produce. If you have not set up your Events system, start there first.

#### Do This

- Work tasks by priority: overdue first, then by lead temperature

- Batch similar tasks together for speed

- Close every task with a next action or a disposition

- Build presets before enabling sequences

#### Not This

- Cherry-pick easy tasks and ignore the hard ones

- Leave tasks open past their deadline without rescheduling

- Create tasks without assignees or deadlines

- Manually recreate the same task type every day

## Task Creation A-Z

    Three entry points, one outcome: every lead gets a next action with a deadline and an owner.

    Create tasks from three places in DataSift: the Events page, the Records list, or inside an individual property record. Creating from within a record auto-links the property. Creating from the Events page requires you to attach one manually.

        1

#### Navigate to your entry point

          Open the Events page for bulk task creation. Or open an individual property record for context-linked tasks. From the records page, select one or more properties to create tasks in batch.

            Create tasks from the Events page, Records list, or individual record.

        2

#### Select the Task tab

          Click "Add New Event" and select the Task tab. If you are inside a property record, the address auto-fills. From the Events page, you will need to search for and select the property.

        3

#### Choose your assignment method

          Assign to a specific user, a role, a custom user group, or use Round Robin for even distribution. See the Assignment Strategy section below for when to use each method.

            Assignment options: specific user, role, custom group, or Round Robin.

        4

#### Set the deadline

          Toggle "All day" for tasks due by end of business. Uncheck it to set a specific time for urgent tasks. Hot lead callbacks need a specific hour. Nurture follow-ups can be all-day.

            All-day toggle vs. specific time deadline.

        5

#### Configure recurrence (optional)

          Toggle "Repeat Task" for recurring follow-ups. Choose daily, weekly, bi-weekly, or monthly frequency. Enable "Skip Weekends" to roll Saturday and Sunday tasks to the following Monday.

            Recurrence frequency and Skip Weekends toggle.

        6

#### Add notes and save

          Add a description with context: what to say, what to look for, what outcome to push for. This turns a generic "follow up" into an actionable task. Save to create the task and trigger any connected Google Calendar sync.

    Always create tasks from within the property record, not the Events page. The property links automatically. From the Events page you have to manually search for and attach the property. It takes 10 extra seconds per task, which adds up to hours over a month.

## The Assignment Matrix

    Four assignment methods. The right one depends on your team size and the task specificity.

#### Self-Assign (Solo + General Tasks)

        You are the team. Assign every task to yourself. The value of tasks for solo operators is not delegation. It is discipline. Tasks enforce a rhythm: you cannot skip follow-ups when the system reminds you daily.

- Use All-Day deadlines for flexible scheduling

- Set daily recurrence for prospecting tasks

- Review your task queue each morning as part of STABM

#### Round Robin (Team + General Tasks)

        General tasks like "call new lead" or "follow up on no-contact" should be distributed evenly. Round Robin prevents one person from getting overloaded while others sit idle.

- Select "Round Robin" in the assignment dropdown

- Choose "Users Round Robin" to pick specific team members

- Distribution is even across selected users

          Round Robin distributes tasks equally across selected team members.

#### Self + Notes (Solo + Role-Specific Tasks)

        Wearing multiple hats? Use the task description to note which role the task requires: "Closer hat: review comps and prepare offer" vs "Data Manager hat: pull new probate records."

- Prefix task names with the role: "[Closer] Review offer on 123 Main St"

- Batch tasks by role when working your queue

- Track time per role to see where you spend your day

#### Role / Custom User Group (Team + Role-Specific Tasks)

        Acquisition tasks go to closers. Prospecting tasks go to callers. Research tasks go to data managers. Assign by role or create custom user groups for cross-functional teams.

- Use "Assign by Role" for standard team structures

- Create Custom User Groups for specialized teams (e.g., "Senior Closers" vs "Junior Closers")

- Pair task assignment with record assignment for restricted roles

    Round Robin is the default answer for teams of two or more. Override it only when the task requires specific expertise. A closer reviewing a counter-offer needs that specific closer, not whoever is next in rotation.

## Task + Record Assignment

    The number one silent failure in team CRM setups. A task exists, but the team member cannot see the record.

    Four DataSift roles are restricted: Prospectors, Acquisitions, Dispositions, and Researchers. They only see property records directly assigned to them. Give a Prospector a task without the property record and the task shows in their Events tab, but the property stays locked.

        Task Only (Broken)
        Task + Record (Working)

#### Broken State

        Task assigned to Prospector. Property record NOT assigned. The Prospector sees "Call New Lead" in their task queue. They click it. No property details load. No phone number. No address. No context. The task sits unworked. The lead goes cold.

#### Working State

        Task assigned to Prospector. Property record ALSO assigned to Prospector. They click the task, see the full property record, phone numbers, notes, and history. They make the call. The system works as designed.

    **When assigning tasks to Prospectors, Acquisitions, Dispositions, or Researchers, always assign the property record to them first.** Without record assignment, they see the task but cannot access the property. Zero errors in the console. Zero warnings. An invisible wall.

       |
         | Role | Record Visibility | Action Required

         | Sensei / Super Admin / Admin | All records | None. Tasks work automatically.

         | Marketer | All records | None. Tasks work automatically.

         | Prospector | Assigned records only | Assign record before or alongside task.

         | Acquisitions | Assigned records only | Assign record before or alongside task.

         | Dispositions | Assigned records only | Assign record before or alongside task.

         | Researcher | Assigned records only | Assign record before or alongside task.

### How to Assign Records

        Assign the property record to the team member before creating the task.

        With record assignment, the team member sees the full property details.

## Deadline Pattern Library

    Temperature is the follow-up cadence: Hot every 2 days, Warm every 15, Cold every 45. Match deadline and recurrence settings to that cadence.

      Hot ticks every 2 days, warm every 15, cold every 45. Skip Weekends bumps a Saturday deadline to Monday.

        Hot Leads
        Warm Leads
        Cold Leads
        Nurture

#### Hot Lead Follow-Up

        **Recurrence (the cadence that defines Hot):** Follow up every 2 days.

        **First-contact speed (separate from the cadence):** On a brand-new hot lead, make the first attempt within 1-2 hours of the trigger. Set a specific time (not all-day) so that first task fires as an urgent notification.

        **Skip Weekends:** Off. Hot leads do not wait for Monday.

        Temperature is the follow-up cadence, not the motivation count. The 4 Pillars (Reason, Timeline, Condition, Price) and the price band set the starting temperature; the situation can override it. A foreclosure with an auction date stays Hot regardless of stated motivation.

#### Warm Lead Maintenance

        **Recurrence (the cadence that defines Warm):** Follow up every 15 days.

        **Deadline:** All-day task, 15 days from last contact.

        **Skip Weekends:** On. Saturday tasks roll to Monday.

        A single pillar of motivation usually sets the starting temperature at Warm, but the cadence is what makes it Warm. A 15-day cadence keeps you present without being aggressive. The Skip Weekends toggle ensures tasks land on workdays when you are in the CRM.

#### Cold Lead Re-engagement

        **Recurrence (the cadence that defines Cold):** Follow up every 45 days.

        **Deadline:** All-day task, 45 days from last contact.

        **Skip Weekends:** On.

        Zero pillars usually sets the starting temperature at Cold, but Cold is not dead. They gave you a phone number. They are not ready yet. A 45-day check-in avoids annoyance but keeps you first in line when their situation changes.

        Cold leads are NOT on drips. Drips are for leads that exited the active pipeline (Ghosting or Not Interested). Cold gets a manual call task every 45 days. Only exception: a solo operator who will never hire a lead manager.

#### No Contact / Nurture Sequence

        **The status stays "No Contact New Lead" through both phases below.** What changes is the TASK, not the status.

        **Phase 1, the "No Contact New Lead" task (Days 3-5):** Daily recurrence. You are still trying to reach them. Three attempts per day (part of the 27-touch attempt grid).

        **Phase 2, the "Nurture New Lead" task (Week 2+):** Weekly recurrence for 3-6 months. They never answered but the numbers are valid. "Nurture New Lead" is a task stage, not a separate status.

        **Skip Weekends:** On for the weekly Nurture task. Off for the daily No Contact task (you need every day of the attempt window).

        The shift from the daily "No Contact New Lead" task to the weekly "Nurture New Lead" task happens after your initial attempt cycle exhausts. Switch to a maintenance cadence and let time do the work.

### Deadline Controls in DataSift

        The All Day toggle creates a flexible deadline without a specific time.

        Uncheck All Day to set a specific time. Use for hot lead tasks.

        Recurrence options: daily, weekly, bi-weekly, monthly.

        Skip Weekends rolls Saturday/Sunday tasks to Monday.

    The Framework

## The Preset Pyramid

    Three layers of task presets. Start with defaults. Customize for your market. Then build custom workflows for your unique operation.

    Task presets eliminate the daily friction of recreating the same tasks. Build them once, attach them to sequences, and they fire automatically every time a status changes or a trigger condition is met.

        Layer 1: Default Presets (Use As-Is)

            DataSift ships three default preset groups. For solo operators in Phase 1, these cover 90% of your task needs without modification.

            **Lead Management:** Call New Lead, No Contact New Lead, Nurture New Lead, Cold Follow-Up, Warm Follow-Up, Hot Follow-Up

            **Acquisitions:** Make Offer, Offer Follow-Up, Send Back to Lead Management

            **Transactions:** Process New Contract, Follow Up with Seller and Title, Close Out Deal

            **Assignee:** The defaults ship assigned to Sensei (the account owner). Before you hire, change each preset from Sensei to User Round Robin and select your lead manager(s). Auto-created tasks then distribute evenly instead of dumping on the owner.

            Best practice: 3-6 tasks per preset group. More than that creates noise. Fewer leaves gaps.

        Layer 2: Customized Defaults (Edit for Your Market)

            Take the default presets and adjust three things for your operation:

            **Assignees:** Change from Account Owner to the correct team member or role. Default presets assign everything to the account owner, which breaks when you hire.

            **Deadlines:** Adjust timing for your market speed. If your market moves fast (Phoenix, Dallas), tighten deadlines. Slower markets (rural, Midwest) can use longer windows.

            **Descriptions:** Add your specific scripts, comp criteria, or offer templates to the task description. A task that says "call lead" is less actionable than one that says "call lead, reference probate filing date, ask about timeline to sell."

        Layer 3: Custom Presets (Build Your Own)

            Custom preset groups for workflows unique to your operation:

            **Wholesale:** Send to buyers list, follow up with top 3 buyers, schedule closing, confirm assignment fees

            **Rentals:** Tenant walkthrough, property manager intro, insurance verification, lease signing, first rent collection

            **Deep Prospecting:** Skip trace research, heir tree check, courthouse records pull, Ancestry.com search, owner swap in CRM

            **External Integration:** Zapier task relay, attorney package send, investor portal update

            Name your custom groups clearly. Use the pattern: **[Department] - [Workflow]**. Examples: "Acquisitions - Wholesale" or "Research - Deep Prospecting."

### Creating Preset Groups

    Navigate to the Events page and select the Preset tab. From there, create groups to organize your presets, then add individual presets within each group.

        1

#### Open the Preset tab

          From the Events page, click the Preset option to see your existing preset groups and create new ones.

            Navigate to the Preset tab on the Events page.

        2

#### Create a group

          Click "Create Group" to start a new organizational folder. Name it clearly using the [Department] - [Workflow] pattern.

            Create a new group to organize related task presets.

        3

#### Add presets to the group

          Click "Add New Preset" within your group. Configure the task name, assignment, deadline, recurrence, and description. Each preset becomes a reusable template that sequences can reference.

            Add individual task presets within each group.

    Create presets BEFORE enabling sequences. Sequences reference presets by name. If the preset does not exist when the sequence fires, the task action silently fails. No error. No warning. A missing task and a lead that never gets called.

## Task Completion Workflow

    A completed task is not the end. It is the trigger for what happens next.

    Marking a task complete does five things in DataSift. Understanding this chain is the difference between using tasks as a checklist and using them as an engine.

      Every task completion is logged with timestamp and user in the activity log.

      The Completed tab shows all finished appointments and tasks across all records.

    The most powerful branch is the sequence trigger. A completed task can fire a "Task Completed" trigger in your sequences, which can create the next task, change a status, send a notification, or start a drip. One completion cascades into the next action.

## The Task Triage System

    Five steps every morning. Ten minutes. Zero leads forgotten.

    This is the "T" in STABM. The task queue is the heartbeat of lead management. Skip it and you are flying blind. Work it systematically and every lead has a next step.

      The Events tab task queue. This is where every day starts.

        1

#### Open Events Tab

        Start every day here. Not email. Not Slack. The Events tab shows your task queue. This is the "T" in STABM.

        2

#### Sort by Overdue

        Overdue tasks are already late. Handle them before anything new. Every overdue task is a lead losing confidence in you.

        3

#### Batch by Type

        All call tasks together. All follow-up texts together. All offer reviews together. Context-switching kills speed. Batching multiplies it.

        4

#### Work by Temperature

        Within each batch, hot leads first. Then warm. Then cold. Then nurture. Revenue lives in the hot leads.

        5

#### Set Tomorrow's Tasks

        Before logging off, ensure every active lead has a task scheduled for tomorrow. The golden rule: no lead without a next step.

        Filter by due date to see today's priority tasks.

        Managers can filter by team member to review individual workloads.

### Your Task Batching Plan

    Write down the order you will work your task types each day. This becomes your daily operating procedure.

      Next 5-Day Deal Flow Challenge: Monday, September 21 to September 25. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Task Execution Scorecard

    Four KPIs that tell you if your task system is working. Then rate yourself on five dimensions.

#### Completion Rate

        95%+

        Target: Complete 95% of daily tasks. Green >95%, Yellow 80-95%, Red

#### Overdue Rate

        <5%

        Target: Under 5% overdue. Zero overdue at end of day.

#### Time to Complete

        Same Day

        Hot: within 2 hours. Warm: within 48 hours. Cold: within 7 days.

#### Task Load

        40-60/day

        Per caller. Adjust based on task complexity and call duration.

### Lead Manager Daily Benchmarks

    Task completion is the system check. These are the activity numbers a single lead manager should hit every day. If the task queue is clean but these numbers are low, the problem is effort or list quality, not the CRM.

#### Dials Made

        150/day

        A floor, not a target. Below this and the pipeline starves.

#### Conversations

        25/day

        Real two-way conversations. Conversation rate ~15-20%. Below 15% is a list or number-quality problem.

#### Sent to AQS

        2-5/day

        Leads sent to Acquisitions. This is THE money metric. Everything else exists to drive this number.

#### Same-Day Contact

        100%

        Every new lead gets first contact the same day it comes in.

#### Leads Missing Tasks

        0

        Every day. No lead in the pipeline without a next dated task.

#### Conversation Rate

        15-20%

        Conversations divided by dials. Below 15% means fix the list or the phone numbers.

    Prioritize the queue before you dial: probate and foreclosure before high-equity cold, inbound replies before outbound attempts. Hard rule: every call ends with an appointment or a dated follow-up task. Neither means the lead silently drops.

## Task Strategy by Phase

    Your Deal Flow Ladder phase changes how you use tasks. Find your rung.

        Phase 1: Operator
        Phase 2: Delegator
        Phase 3: Manager
        Phase 4: Owner

#### Phase 1: The Operator

        All tasks self-assigned. You are every role: one county, one list, sequential marketing live. The value of tasks is not delegation. It is enforcing discipline when nobody is watching.

- **Presets:** Use Layer 1 defaults as-is. Do not overcomplicate.

- **Assignment:** Everything goes to you. No Round Robin.

- **Key risk:** Ignoring tasks because nobody holds you accountable. Set phone reminders for hot lead tasks.

- **Daily target:** 20-30 tasks per day across prospecting and follow-up.

        Full playbook: Phase 1, The Operator.

#### Phase 2: The Delegator

        You multiply touches: 4 full attempts per record, mail to non-responders, data and admin work off your plate. You review results, not work tasks.

- **Presets:** Customize Layer 2. Move data and admin task assignees off the Account Owner.

- **Assignment:** List hygiene and admin tasks go to your Data Manager. You keep seller conversations.

- **Key risk:** Tasks assigned but records not assigned to restricted roles. Audit weekly.

- **Hiring note:** Capital lets you compress hires, but the ladder still runs data and admin first.

        Full playbook: Phase 2, The Delegator.

#### Phase 3: The Manager

        You scale the team on overflow. Tasks are your management layer. Round Robin everything. Daily KPI review of completion rates per team member.

- **Presets:** Full Layer 2 customization + Layer 3 for each exit strategy (wholesale, rental, fix-and-flip).

- **Assignment:** Round Robin for general. Role-specific for acquisitions and transactions. About 2 callers per lead manager.

- **Key risk:** Task overload from too many sequences firing simultaneously. Audit sequence frequency weekly.

- **Manager role:** Sales Manager ($5,000-$6,000/mo) audits overdue tasks daily and coaches completion rates.

        Full playbook: Phase 3, The Manager.

#### Phase 4: The Owner

        The deep-prospecting motion: fewer leads, deeper execution. Your tasks are research-heavy: heir tree checks, courthouse pulls, Ancestry searches. Build custom presets for deep prospecting workflows.

- **Presets:** Build Layer 3 custom presets for deep prospecting (skip trace, heir tree, courthouse, owner swap).

- **Assignment:** Self or Data Manager ($500-$700/mo). Research tasks go to Data Manager.

- **Key risk:** Over-complicating presets. 3-4 custom presets is enough.

- **Daily target:** 10-15 deep research tasks. Quality over quantity.

        Full playbook: Phase 4, The Owner.

## Resources & Next Steps

    Companion guides, help articles, and reference materials.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, September 21 to September 25

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### The Intake Call: 75 Custom Fields

          The 7-folder, 75-field intake structure that feeds your task and qualification workflow.

#### Lead Management & CRM Automation

CRM Quartet companion: 4 Pillars, STABM, pipeline, Ghosting Nurture

#### Events Deep Dive

CRM Quartet companion: appointments, tasks overview, TCA model, default account

#### CRM Sequences & Automation

CRM Quartet companion: trigger-based workflows, TCA patterns, pre-built library

      [#### DataSift Help: Events Overview

Official help article on events, tasks, and task presets](https://intercom.help/reisift/en/articles/13244225-events-overview)
      [#### Deal Flow Tech Stack SOP

Full tech stack spreadsheet with tool pricing and configuration](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)
      [#### 5 Day Deal Flow Resource Hub

Critical resources across all 5 days of the Deal Flow Challenge](https://docs.google.com/spreadsheets/d/1bQBHLsxVwXbsbz9SBcfpatPaFgAIsICo/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)
      [#### Case Studies

Real operator results at every phase of the ladder](https://go.dataflik.com/case-studies-intermediate)

        Reset

  ×
