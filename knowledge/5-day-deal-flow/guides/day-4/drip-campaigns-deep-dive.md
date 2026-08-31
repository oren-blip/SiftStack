# Guide: drip-campaigns-deep-dive

> Source: https://learn.datasift.ai/drip-campaigns-deep-dive (Day 4 module, fetched 2026-08-28)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

    CRM Campaigns

# Drip Campaigns Deep Dive

    The system that follows up when you can't

      12 min read
      Part 4 of 4: CRM Quartet
6 Templates

## Drips Are Not Sequences

    Sequences fire immediately. Drips add time. That one difference changes everything about how you follow up with leads who aren't ready yet.

    Research shows that 80% of motivated sellers need 5+ follow-ups before they commit to selling. Most investors quit after the first attempt. Drip campaigns bridge that gap automatically.

    Your DataSift account ships with 26 pre-built sequences. Zero pre-built drip campaigns. That is by design. Drips are personal. Your market, your tone, your cadence. This page gives you the templates to build them right.

       | Element | Sequences | Drip Campaigns

       | **Timing** | Immediate on trigger | Configurable delays (min/hr/days)

       | **Best for** | New lead outreach, notifications | Long-term nurture, re-engagement

       | **Actions** | SMS, Email, Task (instant) | SMS, Email, Task (delayed)

       | **Pre-built** | 26 in default account | None. You build your own.

       | **How they connect** | Sequences trigger drips | Drips run on the timeline

      A sequence is a mousetrap: it fires the moment the trigger trips. A drip is an IV bag: one droplet at day 15, 45, 90, still half full months later.

#### Do

        Use drips for leads you have already tried reaching. Ghosted leads, not-interested leads, aged data. The drip keeps working while your team handles live prospects.

#### Don't

        Replace manual follow-up with drips on active leads. New Lead, Cold, Warm, and Hot leads are active pipeline. They get manual calls first. Cold leads are NOT on drips. Drips support your callers. They never replace them.

    **The three design rules for every drip.** Break one and you double-contact leads or stall the whole engine.

    1. Drips supplement manual follow-up. They never replace it. The human call always comes first.

    2. The receiving sequence (New Lead, Cold, Warm, Hot) that a re-engaging lead lands in MUST include a "Remove from Drip Campaign" action. Skip this and the lead gets manual calls AND drip texts at the same time.

    3. No task conflicts. Do not add drip tasks to records that already have a sequence task loop running. Pick one or the other per record.

    Personalization matters even in automation. Make it feel human. Merge fields are the minimum. Read your drip texts out loud. If they sound like a robot wrote them, rewrite.

    The Framework

## Anatomy of a Drip Campaign

    Four building blocks. Every drip campaign uses these same four elements.

#### Step Types: SMS, Email, Task

      **SMS** requires a carrier integration (smrtPhone, Twilio, or Plivo). Best for urgent, time-sensitive touches. Cost is roughly $0.01 per message.

      **Email** works via Gmail integration. Available on all plans. Best for longer nurture and informational follow-ups. Use drip emails for cold outreach at scale instead of sequence emails.

      **Task** creates a follow-up task assigned based on the preset's due date, not the drip delay. Pairs a human touchpoint with the automated messages.

#### Delays: The Timing Engine

      Every step after the first gets a configurable delay. Set by **minutes** (0-59 for response chains), **hours** (1-23 for same-day follow-up), or **days** (1-365 for long-tail nurture).

      All SMS and email actions send between **8 AM and 9 PM** based on your account timezone. Messages scheduled outside that window hold until 8 AM the next day.

#### Carrier Selection

      SMS drips require **smrtPhone**, **Twilio**, or **Plivo** integration. Kixie, Smarter Contact, and Launch Control are not compatible.

      You must comply with **A2P 10DLC** regulations. Large-volume sends affect connectivity and spam rates.

      If your smrtPhone numbers don't appear in the drip builder, open any record and click the refresh phone icon in the 1:1 communication section.

#### Merge Fields: Make It Personal

      Available merge fields include **{First Name}**, **{Last Name}**, **{Property Address}**, **{Agent Name}**, and **{Company}**.

      Records missing a merge field value will show a blank space. A text reading "Hi , this is about" with missing fields looks worse than no text at all.

## Building Your First Drip Campaign

    Six steps from zero to running. The entire setup takes under five minutes once you know what the drip should do.

        1

#### Open Drip Campaigns

          Click **Drip Campaigns** in the left sidebar of your DataSift account.

          The Drip Campaigns section lives in the left sidebar navigation.

        2

#### Add New Campaign

          Click **Add New Campaign**. Name it something descriptive. "Ghosting Nurture 45-Day" beats "Drip 1."

          Name your campaign something descriptive. Include the cadence so you can identify it at a glance.

        3

#### Drag and Drop Steps

          Drag SMS, Email, or Task steps into the campaign builder. Each step appears in order.

          The drag-and-drop builder. Add steps and configure delays between them.

        4

#### Set Delays Between Steps

          Configure the time between each step using minutes, hours, or days. The first step fires immediately on enrollment.

          Delays can be set in minutes, hours, or days. The dropdown appears between each step.

        5

#### Select Carrier and Phone Number

          For SMS steps, select your smrtPhone, Twilio, or Plivo number. If numbers don't appear, refresh them from any record's 1:1 communication section.

          Select which smrtPhone number to send from. Each SMS step can use a different number.

        6

#### Write Your Messages and Save

          Write your SMS or email copy using merge fields. Save the campaign. It is now ready for enrollment.

          Type @[variable_name] to insert merge fields. Keep SMS under 150 characters for best delivery.

## The Two Drip Campaigns

    Drips are for leads that EXITED the active pipeline: Ghosting Nurture and Not Interested Nurture. Active leads (New Lead, Cold, Warm, Hot) get manual follow-up.

#### 1. Ghosting Nurture

You made contact, then they went silent. Patient, casual touches.

#### 2. Not Interested Nurture

They answered. They said no. Circumstances change.

#### Ghosting Nurture

      These are leads who engaged at some point and then stopped responding. The record moves to the Ghosting phase. The drip keeps a casual, no-pressure line open while your team works live prospects.

        **Trigger**Record moves to the Ghosting phase

        **Cadence**45-day cycle, 4 touches, about 142 days total

        **Tone**Casual, no pressure. "Still here if you need me."

        **Success metric**Reply rate. Any response moves them back to active.

#### Not Interested Nurture

      These leads answered and explicitly said no. That is valuable. They fit your criteria. They just were not ready. 20-30% of all platform deals come from leads who initially said "not interested."

        **Trigger**Disposition set to "Not Interested"

        **Cadence**90-day cycle with a 14-day buffer, 4 cycles, about 360 days. Each cycle = SMS plus a manual call task.

        **Tone**Respectful patience. "The offer still stands."

        **Success metric**Re-engagement rate. Leads moving back to active.

    **Dead leads get no drip.** No task either: Dead is handled through marketing filters, not the CRM follow-up engine. There is no "Dead Lead Revival" drip. Cold leads are not on drips: active pipeline, manual follow-up.

## Six Drip Campaigns You Can Build Today

    Copy-paste-ready campaigns with SMS copy, delay timing, and sequence wiring. Build Templates 1 and 2, the canonical drips. Templates 3-6 are niche and non-standard variants.

      1. Ghosting Nurture (45-Day Cycle)4 SMS**Use case:** Lead engaged, then went silent and moved to the Ghosting phase. 45-day cycle, 4 touches, about 142 days total. Casual and no pressure.
S
Immediate
"Hi {First Name}, this is {Agent Name} with {Company}. We chatted about {Property Address} and then lost touch. No worries at all. If you want to pick it back up, just reply to this text."

S
+ 45 Days
"Hey {First Name}, circling back on {Property Address}. No pressure. If you ever want to explore your options, I'm here."

S
+ 45 Days
"{First Name}, still thinking of you on {Property Address}. Whenever the timing feels right, reach out. I'm easy to work with."

S
+ 45 Days
"{First Name}, one last casual check-in on {Property Address}. Circumstances change and I want to make sure you have my number. Reply anytime."

**Wire it up:** Sequence trigger = Record moves to the Ghosting phase. Action: Add to this drip. The receiving sequence on re-entry MUST include a "Remove from Drip Campaign" action so a reply does not get manual calls and drip texts at once.

      2. Not Interested Nurture (90-Day Cycle)4 SMS4 Tasks**Use case:** Lead dispositioned not interested, non-distressed property. 14-day initial buffer to respect the "no," then a 90-day cycle, 4 cycles, about 360 days total. Each cycle is an SMS plus a manual call task.
S
+ 14 Days (buffer)
"Hi {First Name}, I completely understand that {Property Address} isn't something you're looking to sell right now. If that ever changes, my number is right here."

T
Same day
Task: "Call {First Name} re: {Property Address}. Not-interested cycle 1 check-in."

S
+ 90 Days
"Hey {First Name}, touching base about {Property Address}. Things change and I wanted to make sure the offer stands if you need it."

T
Same day
Task: "Call {First Name} re: {Property Address}. Not-interested cycle 2 check-in."

**Wire it up:** Sequence trigger = Disposition change to Not Interested. Action: Add to this drip campaign. Repeat the SMS-plus-call-task pair every 90 days for 4 cycles. The active sequence on re-entry MUST include a "Remove from Drip Campaign" action.

      3. Not-Interested Probate (45-Day)3 SMS1 Task**Use case:** Probate lead who said not interested. 45-day cadence matches probate settlement timelines.
S
Immediate
"Hi {First Name}, I understand dealing with {Property Address} is a lot right now. No rush. If the estate process gets complicated or you need options, I'm here."

S
+ 45 Days
"Hey {First Name}, checking in on {Property Address}. Probate timelines can shift and I wanted you to know the offer is still available."

T
+ 45 Days
Task: "Call {First Name}. Probate 90-day checkpoint on {Property Address}."

S
+ 45 Days
"{First Name}, one more check-in on {Property Address}. The estate timeline may have moved along. Reply if you'd like to revisit."

**Wire it up:** Same not-interested trigger with a condition filtering for probate-tagged records. Route probate leads here instead of the 90-day general drip.

      4. Not-Interested Foreclosure (15-Day)3 SMS**Use case:** Pre-foreclosure or foreclosure lead who said not interested. Compressed 15-day cadence because auction timelines move fast.
S
Immediate
"Hi {First Name}, I understand the timing wasn't right for {Property Address}. Auction dates can move quickly. I want to make sure you have options. My number is right here."

S
+ 15 Days
"{First Name}, quick check-in on {Property Address}. If the timeline has changed, I can still help. Just reply."

S
+ 15 Days
"Last follow-up on {Property Address}, {First Name}. The offer stands if you need it."

**Wire it up:** Same not-interested trigger with a condition filtering for foreclosure or pre-foreclosure tags. The 15-day cadence respects compressed auction timelines.

      5. Warm Lead Nurture (Non-Standard)2 SMS1 Email1 Task**Non-standard. Use with caution.** Warm is an ACTIVE pipeline status. Warm leads get manual follow-up every 15 days, not a drip. Only consider this if you will never hire another lead manager. If you run it, the Warm sequence MUST have a "Remove from Drip Campaign" action and no conflicting task loop, or you double-contact.
S
Immediate
"Hi {First Name}, this is {Agent Name}. Following up on our conversation about {Property Address}. Take your time. When you're ready, I'm here."

E
+ 30 Days
Subject: "Still thinking about {Property Address}?"
Body: Brief, personal check-in. Reference the prior conversation. No hard sell.

S
+ 30 Days
"Hey {First Name}, circling back on {Property Address}. Anything change on your end?"

T
+ 30 Days
Task: "Call {First Name}. Warm lead 90-day re-qualification for {Property Address}."

**Wire it up:** Sequence trigger = Status change to Warm. The email at 30 days adds a different channel. The task at 90 days forces a human re-qualification call.

      6. Speed-to-Lead Supplement (Non-Standard)2 SMS1 Task**Non-standard. Use with caution.** New Lead is the most active phase in your pipeline. It needs a same-day manual call, not a drip. A drip here risks texting a lead your caller is already working. If you run it as a backstop, the New Lead sequence MUST include a "Remove from Drip Campaign" action and must not collide with the New Lead task loop.
S
Immediate
"Hi {First Name}, this is {Agent Name} with {Company}. Reaching out about {Property Address}. Would love to connect. What's a good time to chat?"

S
+ 24 Hours
"Hey {First Name}, following up on my message about {Property Address}. I have some options that might interest you. Feel free to call or text back."

T
+ 48 Hours
Task: "Call {First Name} re: {Property Address}. New lead, 2 texts sent, no response. Manual follow-up needed."

**Wire it up:** Sequence trigger = Status change to New Lead. This supplements your caller's manual outreach. The task at 72 hours catches leads that didn't respond.

    Build the two canonical drips first: Ghosting Nurture and Not Interested Nurture. Those two recapture leads that left your active pipeline. They run on their own while your team works live prospects. Master those before you touch the non-standard templates below.

      Next 5-Day Deal Flow Challenge: Monday, September 21 to September 25. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## The Delay Ladder

    Three rungs. Each delay unit serves a different purpose. Mixing them without intention creates confusing cadences.

        Minutes (0-59)
        Hours (1-23)
        Days / Weeks

#### Rung 1: Minutes

        Immediate response chains within a single outreach attempt. First SMS at 0 minutes, follow-up email at 30 minutes. A quick one-two punch before the lead forgets.

        Best for: Same-session response chains, immediate notification steps

        Watch out: More than 3 messages within an hour feels aggressive. Keep minute-based chains to 2 steps max.

#### Rung 2: Hours

        Same-day persistence. A morning SMS and an afternoon email if no response. Stays top-of-mind without crossing into "too much" territory.

        Best for: New lead initial contact windows, same-day follow-up pairs

        Watch out: Remember the 8 AM to 9 PM send window. A 6-hour delay set at 5 PM holds until 8 AM the next day.

#### Rung 3: Days and Weeks

        The long game. 15, 30, 45, 90-day intervals. This is where most drip campaigns live. Patient persistence over months. The lead's circumstances change. Your drip is there when they do.

        Best for: Ghosting Nurture and Not Interested Nurture re-engagement cycles

        Cadence guide: Foreclosure = 15 days. Probate = 45 days. General = 90 days. Dead leads = 90 days.

## Integration Setup

    SMS drips need a carrier. Email drips need Gmail. Get these connected before you build your first campaign.

    smrtPhone Integration (Recommended)**smrtPhone** is the most common carrier for DataSift drip campaigns. Connect under Settings, then your phone numbers appear in the drip builder.
If numbers don't appear, open any record and click the **refresh phone icon** in the 1:1 communication section.
Settings → Integrations → smrtPhone. Paste your API key and validate to connect.

Click the refresh icon to sync your smrtPhone numbers with the drip builder.

    Twilio or Plivo Integration**Twilio** and **Plivo** are alternative carriers. Both work identically in the drip builder.
**Not compatible:** Kixie, Smarter Contact, and Launch Control cannot send drip campaign SMS.

    Gmail Integration (Email Drips)Email drips work via **Gmail integration**. Available on all plans. No carrier purchase needed. Same 8 AM to 9 PM send window as SMS.
Use email for longer nurture sequences. Use SMS for urgent touches. The combination works better than either alone.
Settings → Integrations → Gmail. Click "Connect with Google" and authorize access.

#### Do

Set your account timezone under Settings before creating drips. Wrong timezone means texts at the wrong time.

#### Don't

Ignore A2P 10DLC registration. Non-compliance tanks deliverability and risks number suspension.

## Enrollment and Automation

    Two ways to get records into a drip. Manual for one-time batches. Automatic for hands-off systems.

        Manual Enrollment
        Automatic via Sequences

#### Manual: Filter, Select, Send

        From the Records page, filter your list. Select the records. Go to **Send to** and choose **Drip Campaigns**. Select the campaign. Done.

        Works well for one-time batches. Example: 500 ghosted leads from 6+ months ago into your Ghosting Nurture drip.

        Filter records, select them, then use Send to and Drip Campaigns to enroll.

#### Automatic: Attach to a Sequence

        Create a sequence with a status or disposition trigger. Add "Drip Campaign" as an action. Every lead that hits that trigger enters the drip automatically. Zero manual work.

        Your default account already has sequences for Lead Management, Acquisitions, and Transactions. Open any sequence, click "Make Changes," add a Drip Campaign action.

        Inside a sequence, add a Drip Campaign action. The drip fires when the trigger conditions are met.

        A complete sequence: status changes to Cold Lead, which triggers the AQ-Cold Follow Up drip campaign.

        **The Mara Garcia workflow:** Call a lead. Disposition as "not interested." A sequence fires. The sequence adds the lead to a quarterly drip. Fully hands-off after the initial call.

## Monitoring and Debugging

    Click View Details on any campaign to see its health. Four status categories tell you what is happening.

      ▶

#### Active

Currently processing. Waiting for their next delay.

      ✓

#### Completed

Finished all steps in the campaign.

      ✗

#### Failed

Missing primary phone or email. Data quality issue.

      −

#### Removed

Manually pulled from the campaign.

      The campaign list shows all your drips with key metrics. Click View Details to drill into individual records.

      View Details shows every record in the campaign with their current step, plus the full campaign action timeline.

### Common Issues

    SMS not sending: carrier not connectedSMS drips require smrtPhone, Twilio, or Plivo. Kixie, Smarter Contact, and Launch Control are not compatible with drips. Check Settings to verify your integration.

    Phone numbers not appearing in drip builderOpen any property record. Click the refresh phone icon in the 1:1 communication section. This syncs your carrier numbers with the drip builder.

    Messages sending at wrong timesAll drip messages send between 8 AM and 9 PM based on your **account timezone**. Check Settings then Profile to verify. Messages outside the window hold until 8 AM.

    High failure rate on a campaignFailed drips almost always mean missing contact data. SMS needs a primary phone number. Email needs a primary email. Review failed records weekly and update contact info.

    Organizing drips with foldersClick **Create Folder** to organize campaigns. Suggested folders: "Not Interested," "Dead Leads," "Nurture," "New Leads." Deleting a folder gives you the option to delete just the folder or the drips inside. Deleted drips cannot be recovered.
**Removing records from a drip:** You can remove a record from inside the campaign's View Details page, or directly from the record's property page.
From View Details, click the three dots next to any record to remove it from the campaign.

You can also remove a record from a drip directly from the record's property page.

    Check your Failed drips weekly. Every failed drip is a lead with bad contact data. That's not just a drip problem. That's a data quality problem. Fix the record, not just the drip.

## Drip Strategies by Phase

    Which drips to build first depends on your Deal Flow Ladder phase. Start with the campaigns that match your current deal flow.

        1: Operator
        2: Delegator
        3: Manager
        4: Owner

#### Phase 1: The Operator

        You are standing up the flow yourself: one county, one list, sequential marketing live. Build one drip: **Ghosting Nurture** (Template 1). It costs 5 minutes to set up and runs about 142 days. Add Not Interested Nurture (Template 2) once you have 50+ not-interested dispositions.

        Priority order: Template 1, then Template 2. Skip 3-6 until you have a team. Full playbook: Phase 1: The Operator.

#### Phase 2: The Delegator

        You are multiplying touches: 4 full attempts, mail to non-responders, data and admin off your plate. Drips are your leverage. Build the two canonical drips: Ghosting Nurture (Template 1) and Not Interested Nurture (Template 2). Wire both to sequences so they catch leads that leave the active pipeline.

        Priority order: Templates 1 and 2. Skip the non-standard templates (5, 6); active leads get manual follow-up. Full playbook: Phase 2: The Delegator.

#### Phase 3: The Manager

        You are scaling the team on overflow, never skipping a rung. Build the two canonical drips and your niche cadence variants, organized in folders. Your data manager maintains the drip library. Review failed drips weekly as part of data hygiene. Active leads stay on manual follow-up, so the non-standard templates stay off.

        Priority order: Templates 1 and 2, then niche variants 3 and 4. Folders: "Ghosting," "Not Interested," "Niche Cadences." Full playbook: Phase 3: The Manager.

#### Phase 4: The Owner

        You are running the deep-prospecting motion: probate, foreclosure, tax sale, every unreached door. Cadence matters more here than in any earlier phase. Build Templates 3 and 4 first (Probate 45-day, Foreclosure 15-day). Add Template 1, Ghosting Nurture, as your safety net.

        Priority order: Templates 3 or 4 (your niche), then Templates 1 and 2. Skip the non-standard templates; active leads get manual follow-up. Full playbook: Phase 4: The Owner.

## Continue Learning

    Drip campaigns connect to every other part of your CRM. Explore the companion pages and resources below.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, September 21 to September 25

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### Lead Management (Part 1)

4 Pillars, STABM, pipeline, and where drips fit

#### CRM Events (Part 2)

Task presets, appointments, and events drips create

#### CRM Sequences (Part 3)

TCA model, triggers, and how sequences activate drips

#### CRM Tasks (Part 4)

Task presets and the manual follow-up drips pair with

      [#### Drip Campaign SOP

Step-by-step setup guide for automated drip sequences](https://drive.google.com/file/d/1djiFq5AGuoaBIabftHfHihqMPu-R-UD7/view?usp=drivesdk)
      [#### DataSift Help: Drip Campaigns

Official help article with screenshots and FAQ](https://intercom.help/reisift/en/articles/12677375-drip-campaigns-overview)
      [#### Deal Flow Tech Stack SOP

Full tech stack spreadsheet with tool pricing](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)

 Reset

×
