# Guide: crm-sequences

> Source: https://learn.datasift.ai/crm-sequences (Day 4 module, fetched 2026-08-28)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      CRM Automation

# CRM Sequences& Automation

      Build trigger-based workflows that run your CRM while you close deals.

        14 min read
CRM Trilogy: Lead Management · Events

## Why Sequences Change Everything

    Every time a lead's status changes, someone on your team should do something. Sequences make that "someone" automatic.

    Most operators lose deals in the gap between "something happened" and "someone acted on it." A lead comes in at 2 PM. Nobody calls until tomorrow. A lead ghosts you. Nobody starts a nurture drip.

    Sequences close that gap. They watch for a specific event (the **trigger**), check if the situation matches your rules (the **conditions**), then execute one or more actions automatically. No human delay. No forgotten steps.

    **Records vs. Leads: the line that matters.** Prospecting records get cold calls, texts, and mailers through your sequential marketing flow. When someone says "I'm interested," you flip their status to New Lead, which activates the 26 pre-built sequences. Before New Lead is outbound. After is inbound management.

#### Do This

        Set a sequence for Ghosting Nurture. When a lead moves to the Ghosting phase, one status change starts a casual 45-day SMS drip, creates a follow-up task, and moves the card to your nurture board. Zero manual steps.

#### Not This

        Manually create a task, start a drip, and move a SiftLine card every time a lead ghosts you. By lead number 20, you will forget at least one step.

    Sequences supplement your STABM routine. They do not replace it. On every record going in and out, you still check Status, Task, Assignee, Board, and Messages. STABM is the cockpit. Sequences are the autopilot.

    Sequence Anatomy

## Inside a Sequence

    Every sequence follows the same structure: one trigger, optional conditions, one or more actions. Click each part to understand its role.

#### Sequence Name

        Give it a clear, descriptive name you can find later. Use a naming convention: **[Trigger Type] - [What It Does]**. Example: "Status Ghosting - Nurture Drip + Task" or "New Lead - Assign Round Robin."

        You will also assign it to a folder. Folders keep your sequence list from becoming a junk drawer.

#### Trigger (One Per Sequence)

        The event that starts the automation. Each sequence gets exactly **one trigger**. If you need the same actions to fire on two different triggers, create two sequences.

        10 trigger types available: Status Change, Assignee Change, Tags Added/Removed, Lists Added/Removed, Task Created/Completed, SiftLine Card Created/Moved.

#### Conditions (Optional Filters)

        Conditions narrow when the trigger fires. Without conditions, the sequence runs on **every** record that matches the trigger. With conditions, it only runs when additional criteria are met.

        Example: Trigger = "Status changes to New Lead." Condition = "Property has tag: Probate." Result: only probate leads get this sequence's actions.

#### Actions (One or More)

        What happens when the trigger fires and conditions pass. You can stack multiple actions in a single sequence: change a status, assign the property, create a task, add a tag, send an SMS, and move a SiftLine card. All from one trigger.

        12 action types available. Actions execute immediately (no delays). For delayed actions, pair with a Drip Campaign.

    A sequence cannot be triggered by an action from another sequence. If Sequence A adds Tag X, and Sequence B triggers on Tag X, Sequence B will not fire. DataSift enforces this to prevent infinite automation loops.

## Creating a Sequence A-Z

    Walk through the exact creation flow. Each step includes the screenshot so you know exactly what you are looking at.

        1

#### Open the Sequences Page

          Navigate to Sequences in the left sidebar. You will see your existing sequences (or the 26 pre-built ones if your account was created after April 16, 2025). Click **Create Sequence** in the top right.

            The sequences page with default folder organization. New accounts get five pre-built folders: Acquisitions, Deep Prospecting, default, Lead Management, and Transactions.

        2

#### Select Your Trigger

          Choose the event that starts this sequence. You get exactly one trigger per sequence. The most common: **Property Status Change** (fires when a lead moves to a new status like New Lead, Dead, or Hot).

            10 trigger types. Status Change and Tags Added cover 80% of use cases.

        3

#### Add Conditions (Optional)

          Conditions filter which records get the actions. Skip this step if you want the sequence to run on every record that matches the trigger. Add conditions when you need to target a subset.

            Conditions use AND logic. Every condition must be true for the sequence to fire.

        4

#### Configure Your Actions

          Add one or more actions. Common combos: Change Status + Create Task + Add Tag. Or: Assign Property (round robin) + Send SMS + Create Card. Stack as many as you need.

            The task assignment toggle. If "Assign to property assignee" is on but the record has no assignee, the task will not be created.

        5

#### Configure Action Details

          Each action type has its own configuration panel. For task actions, you can choose an existing Task Preset or create a new task inline. For card actions, select the destination board and column.

            Task presets must be created on the Tasks page first. If you have not created any, this dropdown will be empty.

        6

#### Name, Save, and Activate

          Give the sequence a descriptive name, choose a folder, and save. The sequence starts as active (toggled on). You can toggle it off from the sequences page at any time.

            Use a clear naming convention. You will thank yourself when you have 15+ sequences.

        7

#### Verify in the Activity Log

          After the sequence fires for the first time, check the Activity Log on any affected record. The sequence name appears next to each automated action. This is how you confirm it is working correctly.

            Every action taken by a sequence is logged with the sequence name and timestamp.

    Phil Loesch learned the hard way: do not set up sequences without understanding what each action does. Use the help articles and DataSift support chat first. One misconfigured sequence on thousands of records takes hours to clean up.

## When to Use Each Trigger

    The Events Deep Dive lists all 10 triggers, 13 conditions, and 12 actions. This section teaches you **when** to use each one.

      One trigger fires, both conditions must pass, one action runs. Every sequence is this wiring.

        Triggers
        Conditions
        Actions

          Lead enters your pipeline Most Common

            **Trigger: Property Status Change**

            Fires when a record's status changes to any value you specify. This is the trigger behind the 26 pre-built sequences (all fire on "New Lead" status). Also used for Ghosting Nurture (status = Ghosting), Not Interested campaigns, and Hot Lead alerts.

            **When to use:** Any time a status change should automatically create work, reassign ownership, or start a communication cadence.

          Team member gets reassigned

            **Trigger: Property Assignee Change**

            Fires when a property's assignee changes. Use this to auto-create an introductory task for the new owner, send a notification SMS, or move the lead to the new team member's SiftLine board.

            **When to use:** Teams with multiple callers or lead managers who pass leads between roles.

          Data gets segmented by tag

            **Trigger: Tags Added / Tags Removed**

            Fires when a tag is added to or removed from a record. Tags are how you segment data. Adding a "Probate" tag can trigger a specialized follow-up sequence. Removing a "Do Not Call" tag can trigger re-entry into calling queues.

            **Important:** If you apply a tag during initial upload (not after), the sequence will not fire. The trigger watches for changes after the record is created.

          Lead added to or removed from a list

            **Trigger: Lists Added / Lists Removed**

            Fires when a record joins or leaves a list. Lists are broader groupings than tags. Example: adding a lead to a "Hot Leads Q1" list triggers a task for the closer to review it that day.

          Work gets created or completed

            **Trigger: Task Created / Task Completed**

            Task Created fires when any task is added to a record. Task Completed fires when a task is marked done. Use Task Completed to chain work: "When the initial call task is done, create a follow-up task for 48 hours later."

          SiftLine card created or moved

            **Trigger: Card Created / Card Moved**

            Fires when a SiftLine card is created on a board or moved between columns. Card Moved is powerful for deal progression: moving a card from "Offer Sent" to "Under Contract" can auto-create transaction tasks, notify your team, and update the lead status.

          Filter by lead temperature

            **Conditions: Property Status / Property Status Change**

            "Property Status is" checks the current status. "Property Status changes from X to Y" checks the transition. Use the transition version when the same trigger (e.g., Tag Added) should behave differently for Hot vs. Cold leads.

          Filter by team member

            **Conditions: Property Assignee / Property Assignee Change**

            Route actions to specific team members. "Property assignee is John" ensures only John's leads get this sequence's actions. Useful when different team members have different workflows.

          Filter by data segment

            **Conditions: Property Tags / Property Doesn't Have Tags / Property Tags Added / Property Lists / Property Isn't on Lists / Property Lists Added**

            The most granular filtering. Combine tag and list conditions to target precise segments. Example: "Has tag: Probate" AND "Is on list: High Value Properties" AND "Doesn't have tag: Do Not Contact."

          Filter by SiftLine position

            **Conditions: Card Board & Column / Card Has Task / SiftLine Card Moved**

            Check where a card sits on your SiftLine boards. "Card is on Acquisitions board, Under Contract column" can gate actions to only fire for deals that have progressed to a specific stage.

          Create follow-up work

            **Actions: Create New Task**

            Auto-generate tasks with specific due dates, descriptions, and assignees. You can use Task Presets (create them on the Tasks page first) or build tasks inline. Toggle "Assign to property assignee" to route the task to whoever owns the record.

            **Watch out:** If the record has no assignee and "Assign to property assignee" is enabled, the task will not be created. Assign the property first.

          Move leads through the pipeline

            **Actions: Change Property Status / Create New Card / Move Card / Duplicate Card / Delete Card**

            Automate pipeline progression. A lead going Hot can auto-create a card on the Closer's SiftLine board. A lead going Ghosting can move the card to a nurture column. Status changes cascade through your system, triggering other sequences downstream.

          Organize and segment data

            **Actions: Add/Remove Property Tags / Add/Remove Property Lists / Clear Property Tasks**

            Keep your data clean automatically. When a lead goes Dead, remove it from the "Active Leads" list and clear its open tasks. When a deal closes, clear all open tasks so they do not clutter your task view.

          Start or remove a drip campaign

            **Actions: Start Drip Campaign / Remove from Drip Campaign**

            Drips are for leads that exited the active pipeline. A move to Ghosting starts the 45-day Ghosting Nurture. A move to Not Interested starts the 90-day Not Interested Nurture. The drip supplements manual follow-up, it never replaces it.

            **Mandatory safeguard: Remove from Drip Campaign on re-entry.** When a ghosting or not-interested lead replies, the receiving sequence (New Lead, Cold, Warm, or Hot) MUST include a "Remove from Drip Campaign" action. Skip it and the lead gets call tasks AND drip texts at once.

          Delegate and distribute

            **Action: Assign Property**

            Reassign a record to a specific user or use **round robin** to distribute evenly across multiple team members. Round robin assignment is the foundation of scalable lead distribution once you reach Phase 3: The Manager.

          Communicate instantly

            **Actions: Send SMS / Send Email**

            Send immediate messages when a trigger fires. Requires smrtPhone, Twilio, or Plivo for SMS. Requires Gmail for email. These fire **instantly** with no delay. For time-delayed messages, use Drip Campaigns instead.

            See the SMS & Email section below for the full setup walkthrough.

## Single-Step vs. Multi-Step Sequences

    Not every sequence needs five actions. Know when to keep it simple and when to stack.

        Single-Step
        Multi-Step

          Actions per Sequence
          1

          Setup Time
          2 min

          Failure Points
          1

          Easy to debug

          Best For
          Simple routing

### When to Use Each Pattern

#### Single-Step Works When

        One trigger needs one outcome. "Status = Ghosting? Start the nurture drip." "Tag = Probate? Assign to the niche specialist." Clean, testable, easy to debug when something breaks.

#### Multi-Step Works When

        One trigger needs a cascade. "New Lead? Assign round robin + create call task + add to Active Leads list + send welcome SMS + create SiftLine card." Five actions from one event. Saves creating five separate sequences.

    A sequence cannot trigger another sequence. If Sequence A adds Tag X and Sequence B triggers on Tag X, Sequence B will not fire. No chaining. Build every needed action into a single sequence.

    **Sequences vs. Drip Campaigns:** Sequences fire actions **immediately**. Drip Campaigns allow **delays** between events (minutes, hours, days). Need to send an SMS now and another in 7 days? Use a sequence to trigger the drip campaign, then the drip handles the timing. They work together.

## Your Default Sequence Library

    Accounts created after April 16, 2025 come pre-loaded with 26 sequences in three categories. All 26 activate on one trigger: status change to "New Lead."

    Master the default build before you touch a single sequence. The stack: 5 SiftLine boards (Lead Management, Acquisitions, Transactions, Wholesale/Flips, Rentals), 10 active statuses (New Lead, No Contact New Lead, Cold, Warm, Hot, Ghosting Lead, Dead Lead, Not Interested, Under Contract, Closed), and 26-27 pre-built sequences. Renaming a status the sequences fire on silently breaks every automation.

        Lead Management Essential
        Acquisitions
        Transactions

#### What These Do

          Lead Management sequences handle the moment a record becomes a lead. They auto-assign ownership, create initial call tasks, set follow-up cadences, tag for segmentation, and move cards onto your lead management SiftLine board. These are the sequences that enforce speed-to-lead.

          Assignment & Distribution Sequences

            Auto-assign new leads via round robin or direct assignment. Create the initial SiftLine card on your lead management board. These fire first so every other sequence has an assignee to route tasks to.

            **Customization:** Configure round robin with your team members. If you are a solo operator, set assignment to yourself and focus on the task creation sequences instead.

          Task Creation Sequences

            Auto-generate the first call task, follow-up tasks, and qualification tasks. Uses Task Presets you have configured on the Tasks page. Each task gets assigned to the property assignee with a due date.

            **Customization:** Adjust task presets to match your follow-up cadence. If you call within 1 hour, set the initial task due date accordingly. The pre-built defaults assume a standard workflow.

          Tagging & List Sequences

            Auto-add tags for source type, property type, and lead temperature. Add the record to your "Active Leads" list. These keep your data organized without manual input, so your filters and reports stay accurate.

#### What These Do

          Acquisitions sequences manage the deal progression after a lead is qualified. They handle offer tracking, contract tasks, due diligence steps, and communication with the seller during the acquisition process.

          Offer & Contract Sequences

            When a lead's status changes to "Offer Sent" or "Under Contract," these sequences create the next set of tasks: send contract to title, schedule inspection, set earnest money deadline. They move the SiftLine card to the appropriate acquisitions column.

            **Customization:** Update task presets with your title company's specific requirements and your market's standard timelines.

          Due Diligence Sequences

            Auto-create inspection tasks, appraisal follow-ups, and title search reminders. These ensure nothing falls through the cracks during the 30-45 day contract period when multiple deadlines run in parallel.

#### What These Do

          Transactions sequences handle the closing process and post-close follow-up. They manage the handoff from acquisitions to disposition, track closing documents, and automate post-close relationship maintenance.

          Closing & Disposition Sequences

            When a deal moves to "Closing" or "Closed," these sequences archive the lead, update tags, remove from active lists, and create any post-closing tasks (recording documents, sending thank-you messages, requesting referrals).

          Post-Close Follow-Up

            Relationships do not end at closing. These sequences can trigger a 30/60/90-day check-in drip campaign to maintain the relationship for referrals. For wholesalers, they can notify your buyers list of available inventory.

### Activation Checklist

    Review and activate these categories in order. Check each box as you verify the sequences match your workflow.

        Assignment sequences configured with your team members (or yourself for solo)

        Task presets created on the Tasks page before enabling task sequences

        SiftLine boards set up with the columns your sequences reference

        Tagging and list sequences reviewed for your specific data categories

        Tested with one record: changed status to New Lead and verified all actions fired

      0/5 completed

      Next 5-Day Deal Flow Challenge: Monday, September 21 to September 25. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## SMS & Email Through Sequences

    Send instant messages when a trigger fires. No delay. The lead gets your text or email the moment the event happens.

        SMS Setup
        Email Setup

        **Prerequisite:** You must integrate with **smrtPhone**, **Twilio**, or **Plivo** before SMS actions will work. Kixie, Smarter Contact, and Launch Control are not supported for sequence-based SMS.

            1

#### Add an SMS Action to Your Sequence

              Open your sequence, click "Make Changes," then "Add new Action" and select **Send SMS**. The message composer opens.

                The SMS composer. Type your message and insert variables for personalization.

            2

#### Insert Variables for Personalization

              Click the variable menu to insert dynamic fields. Available: **@Owner First Name**, **@Owner Last Name**, **@Property Full Address**, **@City**, **@State**, **@Zip**, and **@User First/Last Name** (your team member's name).

                Variables auto-populate from the record's data. If a field is empty, the variable renders blank.

            3

#### Choose Who Receives the Message

              Three options: **Primary number** (starred contact), **All verified numbers** (every checkmarked contact on the record), or a **custom number** you type in. For most workflows, primary number is the right choice.

                Primary = starred number. All verified = every number with a checkmark. Custom = manual entry.

        All sequence SMS messages are sent between 8 AM and 9 PM in your account's timezone. If a trigger fires at 11 PM, the SMS queues until 8 AM the next morning. This keeps you compliant without extra configuration.

        **Prerequisite:** You must connect your **Gmail** account to DataSift before email actions will work. For cold emailing at scale, use Drip Campaigns instead of sequences. Sequence emails are best for notifications, confirmations, and warm follow-ups.

            1

#### Add an Email Action

              In your sequence, add a new action and select **Send Email**. The email composer opens with a subject line field and a rich text body editor.

                The email composer supports formatting: bold, italic, underline, strikethrough, bullets, and numbered lists.

            2

#### Compose with Variables

              Same variable set as SMS: owner name, property address, city, state, zip, and your team member's name. Insert them into both the subject line and the body for full personalization.

                Variables work in both the subject line and body. Use @Owner First Name in the subject for higher open rates.

            3

#### Select Email Recipients

              Same three options as SMS: **primary email** (starred), **all verified emails**, or **custom email address**. Sequence emails send immediately when triggered. Same 8 AM-9 PM send window applies.

## Organizing with Folders

    Fifteen sequences are manageable. Fifty are a nightmare. Folders prevent the junk-drawer problem before it starts.

### Recommended Folder Structure

#### By Department

- Lead Management

- Acquisitions

- Transactions

- Marketing

#### By Trigger Type

- Status-Based

- Tag-Based

- Task-Based

- SiftLine-Based

#### By Team Role

- Caller Sequences

- Lead Manager

- Closer

- Admin/Owner

### Folder Setup Walkthrough

        1

#### Create a New Folder

          On the Sequences page, click **Create Folder** in the sidebar. Name it using your chosen convention. The default folder cannot be deleted or renamed.

            New folders appear in the sidebar. Click to view sequences inside.

        2

#### Name Your Folder

          Give it a clear, short name that matches your convention. Avoid abbreviations that other team members will not understand.

            Short, descriptive names. "Lead Management" beats "LM Seqs v2."

        3

#### Move Sequences into Folders

          Open any sequence, click the three-dot menu, and select **Move to Folder**. Choose the destination. You can also move sequences during creation by selecting a folder in the save dialog.

            Moving a sequence does not affect its trigger or actions. It is purely organizational.

        4

#### Search Across Folders

          Use the search bar to find sequences by name across all folders. This is faster than clicking through folders when you have 20+ sequences.

            Search queries match against sequence names, not folder names.

    Deleting a folder is permanent. If you delete a folder without first selecting what happens to its sequences, they move to the default folder. The sequences themselves are not deleted. But the organizational structure is gone forever.

## Sequences by Phase

    Your Deal Flow Ladder phase determines which sequences matter most and how many you need. Plan accordingly.

        Phase 1: Operator
        Phase 2: Delegator
        Phase 3: Manager
        Phase 4: Owner

### The Operator Professional: 8 Sequence Limit

        You are the entire team: one county, one list, sequential marketing live. Every sequence you create must save you time directly. With only 8 sequences available on the Professional plan, prioritize ruthlessly.

#### Priority Sequences (Choose 8)

- **New Lead Assignment** (assign to yourself + create first call task)

- **New Lead SiftLine Card** (auto-create card on your lead board)

- **Ghosting Nurture** (start 45-day cycle SMS drip, 4 touches, when status = Ghosting)

- **Not Interested Nurture** (90-day cycle with 14-day initial buffer, 4 cycles, each cycle = SMS plus a manual call task)

- **Hot Lead Alert** (create urgent task when status = Hot)

- **Offer Sent Tracking** (move card to Offer column + create follow-up task)

- **Under Contract Checklist** (create inspection/title/EMD tasks)

- **Closed Deal Archive** (clean up tags, lists, tasks)

        Everything else is manual until you upgrade to Business (unlimited sequences). Full playbook: Phase 1, The Operator.

### The Delegator Business+: Unlimited

        Multiply touches without multiplying your hours: 4 full attempts per record, mail to non-responders, data and admin off your plate. Automate every step you currently have to remember.

#### Key Sequences

- **Speed-to-lead SMS**: auto-text new inbound leads within seconds

- **Dual-path tagging**: separate sequences for FTM and Stacked Niche leads

- **Escalation sequences**: if a lead sits in No Contact for 5+ days, surface it

- All 26 pre-built sequences activated and customized

        Capital lets you compress hires, but the sequence layer comes first. Full playbook: Phase 2, The Delegator.

### The Manager Business+: Unlimited

        You scale the team on overflow, and sequences are the connective tissue between roles. Round robin distribution, role-specific task routing, escalation ladders.

#### Key Sequences

- **Multi-role round robin**: distribute leads across callers, then escalate to Lead Managers

- **Role-specific task presets**: different task chains for Callers vs. Lead Managers vs. Closers

- **Team notification sequences**: SMS alerts when high-value leads enter the pipeline

- **Escalation ladders**: auto-reassign if a lead has no activity for X days

        First hire: a Data Manager ($500-$700/mo) once deals fund it. Overflow triggers each next seat, about 2 callers per lead manager. Never a salesperson before the marketing layer. Full playbook: Phase 3, The Manager.

### The Owner Business+: Unlimited

        Own the machine: deep-prospect every unreached door and instrument your KPIs. Probate leads get a different cadence than tax lien leads. Deep prospecting leads get a different task chain than standard inbound leads.

#### Key Sequences

- **Niche-specific tagging**: auto-tag by property type on New Lead status

- **Deep prospecting task chain**: trigger L1-L4 research tasks when a lead is tagged for research

- **Genealogy research flag**: tag leads that need heir research for your Data Manager

- **Not Interested Nurture**: 90-day cycle for everyone who answered and said no (14-day initial buffer, 4 cycles, SMS plus a manual call task each cycle)

- **Periodic niche marketing**: separate from the Not Interested drip, run tighter Ghosting-style touches on time-sensitive niches like probate (45-day cycle)

- **KPI tracking sequences**: auto-tag leads at specific pipeline stages for reporting

        Full playbook: Phase 4, The Owner.

## When Sequences Break

    Sequences fail silently. No red alerts, no popup errors. A bell icon notification that most operators never check. Here is what breaks and how to fix it.

      Bell icon notification says sequence failed

        **Symptom:** A number appears on the bell icon in the top right corner of your account.

        **Cause:** One or more actions in the sequence could not execute. Common reasons: the target board or column does not exist, the tag or list was deleted, or the record has no assignee for a task that requires one.

        **Fix:** Click the bell icon, read the failure message, and update the sequence's action configuration to match your current boards, tags, and lists.

      Sequence exists but never fires

        **Symptom:** You change a status or add a tag, but nothing happens. Run count stays at 0.

        **Cause:** The sequence is toggled off, the trigger does not match the exact event (e.g., trigger is "Status changes to Hot" but you changed status to "Warm"), or the conditions exclude the record.

        **Fix:** Verify the toggle is on. Check the trigger matches your exact event. Remove conditions temporarily to test. If using tags applied during upload, remember: tags applied during record creation do not trigger "Tags Added" sequences.

      Wrong person gets assigned

        **Symptom:** Leads route to the wrong team member or always go to the account owner.

        **Cause:** Round robin is not configured, or it is configured with inactive team members. Without round robin, the default assignment goes to the account owner (Sensei).

        **Fix:** Edit the Assign Property action. Enable round robin and verify the team member list includes only active members with the correct roles.

      Duplicate actions on the same record

        **Symptom:** A record gets two tasks, two tags, or two card moves from what should be one event.

        **Cause:** Two sequences share overlapping triggers with no conditions to differentiate them. Both fire on the same event.

        **Fix:** Add conditions to one or both sequences to narrow their scope. Or consolidate the two sequences into one multi-step sequence.

      Hit the plan sequence limit

        **Symptom:** Cannot create new sequences. Error message about plan limits.

        **Plan limits:** Essentials (legacy) = 3 sequences. Professional = 8 sequences. Business = Unlimited.

        **Fix:** Consolidate: merge multiple single-step sequences with the same trigger into one multi-step sequence. Or upgrade to Business ($299/mo) for unlimited sequences. If you are on Professional, the 8 you choose should cover lead management first, acquisitions second.

      SMS or email not sending

        **Symptom:** Sequence runs (run count increases) but no message is delivered.

        **Cause:** Phone integration not connected (smrtPhone, Twilio, or Plivo required for SMS), Gmail not connected (required for email), or the record has no valid phone number or email address.

        **Fix:** Verify your integration is active in Settings. Check the record has a primary (starred) phone number or email. Check the failed messages in your integration dashboard.

## Resources & Next Steps

    Deep dives, companion guides, and reference materials.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, September 21 to September 25

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### Lead Management & CRM Automation

CRM Trilogy companion: 4 Pillars, STABM, pipeline, Ghosting Nurture

#### Events Deep Dive

CRM Trilogy companion: appointments, tasks, presets, TCA model, default account

      [#### DataSift Help: Creating Sequences

Official help article with full creation walkthrough](https://intercom.help/reisift/en/articles/6027453-how-to-create-sequences)
      [#### DataSift Help: Organizing with Folders

Folder creation, naming, moving, and searching sequences](https://intercom.help/reisift/en/articles/7231936-organizing-sequences-with-folders)
      [#### DataSift Help: SMS & Email

Sending automated SMS and email through sequences](https://intercom.help/reisift/en/articles/12704224-sending-sms-and-emails-with-sequences)
      [#### Deal Flow Tech Stack SOP

Complete tech stack spreadsheet with tool pricing and stack configurations](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)
      [#### 5 Day Deal Flow Resource Hub

All 83 resources across Days 1-5](https://docs.google.com/spreadsheets/d/1bQBHLsxVwXbsbz9SBcfpatPaFgAIsICo/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

        Reset

  ×
