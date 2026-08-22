# Guide: phone-scoring-trestle

> Source: https://learn.datasift.ai/phone-scoring-trestle (Day 2 module, fetched 2026-08-21)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      Phone Scoring & Spam Guide

# Phone Scoring & Spam Management

      4.75x Higher Connect Rates. From Blind Dialing to Precision Calling.

          16 min read

## You Don't Have a Lead Problem. You Have a Dialing Problem.

    Everyone thinks the bottleneck is more leads. It's not. It's dialing 2,000 numbers when 1,000 of them are dead.

      Your callers sit down with 500 numbers and start dialing. Half the time: a disconnected tone, a fax machine, dead silence. They burn 150 dials to connect with maybe 4 people. That's a 2-3% connect rate, industry average for blind dialing.

      Three things happen behind the scenes. Every dead dial trains carrier algorithms to flag your number as spam. Callers lose momentum: nobody stays sharp after 75 dead dials in a row. And cost per contact doubles because half your dialer time produces zero conversations.

    Your caller ID is a depreciating asset. Every dead number you dial is a withdrawal from that account. Score first, dial second. Protect the asset that makes every other investment work.

      Every dead dial drains the caller ID battery. Put the score filter upstream and the drain stops.

#### Do This

        Score every phone number with Trestle before loading into your dialer. Remove dead numbers. Call highest-activity numbers first.

#### Not This

        Dial blind and hope for the best. Burn through numbers sequentially without scoring. Wonder why your caller IDs keep getting flagged.

    150 dials/day minimum per caller. If 50% are dead, that's 75 wasted dials at $0.03-0.06 per dial. That's $2.25-$4.50 per day per caller in pure waste. Per month: $50-100 per caller in burned resources, plus degraded caller IDs that take weeks to recover.

    Core Framework

## The 5-Tier Dial Priority System

    Trestle scores every phone number 0-100 based on real activity data. These five tiers tell you exactly what to do with each score range.

        881

        43.4%

        Dial First

        Score 81-100

        99

        4.9%

        Dial Second

        Score 61-80

        102

        5.0%

        Dial Third

        Score 41-60

        671

        33.1%

        Dial Fourth

        Score 21-40

        275

        13.6%

        Drop

        Score 0-20

      43.4%

      5%

      33.1%

      13.6%

      Highest priority
      Lowest priority

#### Dial First (Score 81-100)

        30.3%
Correct Rate

        1.9%
Dead Rate

        881
Phone Numbers

      Call and text immediately. These are your best numbers with the highest activity scores. Load them first into your dialer. In a niche sequential campaign, these are your Day 1 priority. In bulk, these fill your ReadyMode queue first.

#### Dial Second (Score 61-80)

        11.1%
Correct Rate

        11.1%
Dead Rate

        99
Phone Numbers

      Call after burning through Dial First. Strong activity, solid contact potential. These numbers are active lines. Combined with Dial First, you have 92% of all correct numbers in your dataset.

#### Dial Third (Score 41-60)

        8.8%
Correct Rate

        12.7%
Dead Rate

        102
Phone Numbers

      Call if capacity allows. Moderate activity. Correct numbers do appear in this range. Dial 1-3 is the safe conservative approach since correct numbers still show up in tiers 2 and 3. Worth the dial time if your callers have bandwidth.

#### Dial Fourth (Score 21-40)

        1.0%
Correct Rate

        34.6%
Dead Rate

        671
Phone Numbers

      Low priority. Call last if there's still time, but consider routing these to direct mail only. Only 1% correct rate means 99 out of 100 dials here produce nothing. Your callers' time is better spent on Tiers 1-3.

#### Drop (Score 0-20)

        0.7%
Correct Rate

        33.0%
Dead Rate

        275
Phone Numbers

      Do not dial. Dead, disconnected, or disposable numbers. Remove from call lists entirely. Every dial here burns your caller ID reputation for a 0.7% chance of reaching someone. Send direct mail to the property address instead.

    **The insight:** Dial First + Dial Second = 980 phones (48.3%) with 92% of all Correct numbers. Dial Fourth + Drop = 946 phones (46.7%) with only 8% of Correct but 82% of all Dead numbers. Tagging cuts the list nearly in half.

## 2,000 Records. One Clear Answer.

    We ran 2,000 phone records through Trestle's scoring API and cross-referenced every score against actual DataSift phone status data. Here's what the numbers show.

        0

        Records Analyzed

        0

        Avg Score: Correct

        0

        Avg Score: Dead

        0

        Connect Rate Jump

        Before Phone Scoring
        After Phone Scoring

#### 2-3% Connect Rate

            Industry average for blind dialing. Your callers connect with 4-6 people per 200 dials.

#### ~50% Dead Numbers

            Half your list is disconnected, fax machines, or inactive lines. Every dead dial trains carriers to flag you.

#### Burned Caller IDs

            Dialing dead numbers degrades your caller ID reputation. Takes weeks to recover once flagged as spam.

#### Demoralized Callers

            75 dead dials in a row kills momentum. Your callers lose sharpness when most calls go nowhere.

#### 9.5% Connect Rate

            Split-tested with a VA. Connection rates jumped 4.75x by scoring and prioritizing numbers first.

#### Dead Numbers Removed

            Drop tier (0-20) and Dial Fourth (21-40) pulled from call lists. Only active lines hit the dialer.

#### Protected Caller IDs

            Fewer dead dials means carriers see legitimate calling patterns. Your numbers stay clean longer.

#### Priority-Ordered Dialing

            Callers hit the best numbers first. More conversations in fewer dials. Better energy, better results.

        Real before/after: connect rate improvement after implementing Trestle scoring.

        Key performance metrics from the 2,000-record phone scoring analysis.

        Full breakdown: score distribution, correct rates, and dead rates by tier.

    **Bimodal distribution:** Scores cluster at 30 (662 phones) and 100 (819 phones). Very little middle ground. The API is essentially saying "probably dead" or "probably active." There's no ambiguity in the data.

    **The "Wrong Number" insight:** Phones marked WRONG in DataSift still score 78.2 on average. The line is active, the person is wrong. Someone is using it: a relative, tenant, or other decision-maker at the property. Worth a deep prospecting look.

## Line Type Intelligence

    Not all phone types are what they appear. The Trestle API reveals line type data that DataSift's internal classification misses.

#### Mobile

        Avg score: 80.8. Best line type. High activity, textable, dialable. Your primary target.

#### FixedVOIP

        Avg score: 47.0. Internet-based lines that DataSift often categorizes as "Landline." Many are textable.

#### NonFixedVOIP

        Avg score: 46.5. Google Voice, TextNow, etc. Often miscategorized. Textable and dialable.

#### Landline

        Avg score: 30.2. True landlines. Lowest activity. Call-only, not textable. Often dead.

    **24% of DataSift "Landlines" aren't landlines.** Of 776 numbers DataSift classifies as landline, 134 are actually FixedVOIP and 53 are NonFixedVOIP. These are textable, dialable numbers you might be skipping because they look like landlines. Phone scoring reveals the truth.

         |
           | Phone Status | Line Type | Mean Score | Median | Count | Signal

           | CORRECT | Mobile | 97.3 | 100 | 263 | Strong

           | CORRECT_DNC | Mobile | 95.6 | 100 | 9 | Strong

           | WRONG | Mobile | 85.9 | 100 | 76 | Caution

           | NO_ANSWER | Mobile | 82.8 | 100 | 327 | Active

           | UNKNOWN | Mobile | 76.8 | 100 | 368 | Worth Dialing

           | CORRECT | FixedVOIP | 75.0 | 85 | 8 | Strong

           | CORRECT | Landline | 70.0 | 70 | 7 | Strong

           | UNKNOWN | NonFixedVOIP | 50.3 | 45 | 32 | Mixed

           | UNKNOWN | FixedVOIP | 48.2 | 30 | 106 | Mixed

           | DEAD | Mobile | 38.8 | 30 | 97 | Avoid

           | UNKNOWN | Landline | 29.9 | 30 | 337 | Low Value

           | DEAD | Landline | 28.2 | 30 | 236 | Avoid

## Get Trestle Running in 30 Minutes

    Six steps from zero to scored, tagged, and loaded into your dialer. The Claude phone validator skill automates most of the heavy lifting.

        1

#### Create a Trestle Account

          Sign up at [trestleiq.com](https://trestleiq.com/?fpr=ty12). Important: you need a work email. Gmail, Yahoo, and other free providers won't be accepted. Cost is approximately $0.015 per phone number scored.

              Trestle account dashboard. Access your API key and manage scoring from here.

        2

#### Export Phone Numbers from DataSift

          Pull your contact list with phone numbers. The format Trestle needs is specific. See the screenshot below for the exact column structure required.

              CSV upload interface. Upload your exported phone numbers for batch scoring.

        3

#### Run the Claude Phone Validator Skill

          The phone validator skill automates the Trestle API scoring process. It submits your numbers, retrieves activity scores, and generates the 5-tier tag assignments automatically.

        4

#### Download Scored Results

          You get back every phone number with its 0-100 activity score and the recommended Dial First / Second / Third / Fourth / Drop tag.

        5

#### Apply Tags Inside DataSift

          Upload the scored results back into DataSift using the tagging logic shown below. Each number gets its priority tag. Your CRM now knows which numbers to call first.

        6

#### Load Prioritized Records into Your Dialer

          Filter by tag. Load Dial First into smrtPhone or ReadyMode. Call through those, then load Dial Second. Route Dial Fourth and Drop to direct mail only.

        The exact column format Trestle needs for phone number scoring.

        The 5-tier tagging logic to apply to your scored numbers inside DataSift.

        DataSift tag management. Apply Trestle scoring tags to organize your leads by dial priority.

        **Claude Phone Validator Skill:** Automates Trestle API scoring and tag generation. [Download the skill from Google Drive](https://drive.google.com/file/d/1VzNjMOj8Rf3zh0pR0DzFE2pOILyGcYoE/view?usp=sharing)

        See all available skills → Claude Skills for REI

        **Loom Walkthrough:** Step-by-step video from our head of support on attaching phone scores to DataSift using Trestle. [Watch the full walkthrough](https://www.loom.com/share/84b3ebc9b75c4c4d98e29d450f3df3a9)

    Cost math: ~$0.015 per number. 5,000 records with 3 phone numbers each = $225. Not scoring costs more: burned caller IDs that take weeks to recover, plus dialer hours wasted on numbers that never pick up. Cheapest insurance you'll buy.

## Understanding Phone Tags & Statuses

    DataSift tracks two things per phone number: status (what happened when you called) and tags (metadata you assign). Trestle scoring connects to both.

### Phone Status vs Activity Score

    Mean Trestle activity score by DataSift phone status. Higher scores correlate strongly with active, correct numbers.

         |
           | DataSift Status | Mean Score | What It Means

           | **CORRECT** | 95.3 | Reached the right person. Highest activity.

           | **CORRECT_DNC** | 89.0 | Right person, requested Do Not Call. Active line.

           | **WRONG** | 78.2 | Active line, wrong person. Deep prospecting opportunity.

           | **NO_ANSWER** | 75.8 | Line is active, nobody picked up. Worth retrying.

           | **UNKNOWN** | 53.4 | Never called. Mixed bag. Score helps prioritize.

           | **DEAD** | 31.8 | Disconnected, out of service. Remove from lists.

### Phone Tags

    Tags are metadata labels you attach to phone numbers inside DataSift. The Trestle workflow adds Dial First through Drop tags. You can also add relationship tags for skip tracing context.

      Trestle Priority Tags (Dial First through Drop)

          These are the five tags from the scoring workflow: **Dial First** (81-100), **Dial Second** (61-80), **Dial Third** (41-60), **Dial Fourth** (21-40), and **Drop** (0-20). Upload via CSV after running the Claude phone validator skill. Tags persist on the record for filtering and dialer queue management.

      Relationship Tags (Skip Tracing Context)

          When skip tracing returns multiple numbers for a property, tag each with the relationship: **Daughter**, **Husband**, **Son**, **Wife**, **Grandchild**, **Relative**. Tag **Spanish Speaking** for language routing. Callers then know who they're reaching before the conversation starts.

      Adding & Managing Tags

          Three ways to add phone tags: **Within individual records** (click the phone number, add tag), **CSV bulk upload** (match by phone number column), or **During data import** (map tag column on upload). Tags can be edited, merged, or bulk-removed from the Phone Tags management page.

## Free Caller Registry

    Phone scoring removes dead numbers from your list. Free Caller Registry removes your numbers from spam databases. Number Verifier tells you when a carrier flags you anyway.

        1

#### Register Your Numbers

        Go to [freecallerregistry.com/fcr](https://freecallerregistry.com/fcr/) and register every outbound phone number your team uses for cold calling.

        2

#### Wait for Processing

        Registration takes effect within a few days. Your numbers get flagged as legitimate business callers across carrier databases.

        3

#### Re-Register Quarterly

        Set a recurring task in DataSift every 3 months. Registrations expire. Re-register to maintain clean caller ID reputation.

    **Free. Takes 5 minutes. Re-register every 3 months.** Register every outbound number your team dials from. It won't fix a number already flagged as spam, but it keeps clean numbers from getting flagged in the first place. Registration is prevention. The next section is detection.

        **Claude Caller Reputation Monitor Skill:** Registration keeps clean numbers clean. This skill catches the ones that slip. Carriers never tell you a number got flagged, so it reads your own SmrtPhone call log daily and watches answer rates per caller ID. It flags numbers trending toward spam labels, manages warm-up, rest, and rotation with dial caps, and writes a health dashboard plus a recommended dial pool. Run it alongside Trestle: Trestle scores the numbers you dial, the monitor protects the numbers you dial from. [Download the skill from Google Drive](https://drive.google.com/file/d/1K9bB9u2ZmVlQKFJ3XLaLfLvSoGZLYoYI/view?usp=sharing)

        See all available skills → Claude Skills for REI

    The skill's docs reference several third-party lookup services: Telnyx, Nomorobo, Numverify. Skip those. Pair the monitor with IPQualityScore (IPQS) as your only outside reputation check. The IPQS free tier covers a normal number pool, and the monitor's own answer-rate signal does the heavy lifting.

## Number Verifier: Watch Your Own Caller IDs

    Trestle grades the number you are calling. Number Verifier grades the number you are calling from. Same operation, opposite ends of the call.

    This is the piece that pairs with Trestle and finishes the job. You can scrub a list perfectly, tag every number Dial First, and still connect at 2% because AT&T decided your caller ID is a robocall. Carriers never send you a notice. The flag just lands, your answer rate drops, and your callers assume the data got worse.

    Number Verifier puts real devices on real carrier networks and calls your numbers every day. It reports back exactly what the person on the other end sees when you ring them. Sign up at [app.numberverifier.com](https://app.numberverifier.com/).

### One Number, Three Different Answers

    The same caller ID can read clean on two carriers and burned on a third. Here is 865-273-0270 on the same day across all three major networks.

        Device flags for 865-273-0270. AT&T shows Spam Risk. T-Mobile and Verizon show the number and city clean.

    That single AT&T flag is roughly a third of your market refusing to pick up, and nothing in your dialer reports it. Without a device-level view you would blame the list, buy more data, and burn the replacement numbers the same way.

### Reading the Device History Grid

    One row per caller ID, one column per day, three dots per day for AT&T, T-Mobile, and Verizon. Green means the call landed clean. Red means the carrier labeled it. A dash means no scan ran that day.

        Device history for the VHB Main campaign. Every day carries three carrier readings per number.

    Read the row, not the dot. One red dot on a single day is noise. A red dot that repeats on the same carrier across consecutive days is a flag that stuck, and that number costs you connects every hour it stays in the dialer.

         |
           | What the row shows | What it means | What we do

           | **Three green, every day** | Clean across the network | Dial full volume. No action.

           | **One red, isolated day** | Single scan, not a pattern | Note it, keep dialing, recheck tomorrow.

           | **One carrier red, 2+ days** | Flag stuck on one network | Submit remediation. Cut that number's daily dials.

           | **Two or three red, 2+ days** | Burned network-wide | Pull it from the dialer. Remediate. Rest it.

           | **Dash** | No scan ran that day | No signal. Do not read into it.

    Naming matters more than it looks. We label every number after the caller who dials from it, so the grid reads Adriana - 8 and Tinaa - 9 instead of ten identical 865 numbers. When a row turns red we know which seat drove it, on which day, and what changed in that caller's pace.

### Three Layers, Not One

    Each layer does one job the other two cannot.

#### Trestle

        Scores the numbers you dial. Removes dead lines before a caller ever sees them.

#### Free Caller Registry

        Registers your outbound numbers as legitimate business callers. Prevention, not detection.

#### Number Verifier

        Tells you when a caller ID gets flagged anyway, on which carrier, on which day.

## Set Up Number Verifier in 20 Minutes

    Seven steps to a daily read on every caller ID your team dials from. Do it once, then it becomes a two-minute morning check.

        1

#### Create Your Account

          Sign up at [app.numberverifier.com](https://app.numberverifier.com/). Plans are sized by how many numbers you monitor, so count your outbound caller IDs before you pick one. Our VHB Main pool runs 21 numbers.

        2

#### Create One Campaign per Dialing Operation

          Campaigns group numbers so the reporting stays readable. One campaign per brand or per market. Ours is VHB Main. If you dial two brands from two number pools, keep them apart or you will chase the wrong flag.

        3

#### Add Every Outbound Number

          Add numbers one at a time on the Phone Numbers screen, or use Import Numbers for a bulk CSV. Do not sample. A number you skip is a number you dial blind.

              The Phone Numbers screen. Carrier, date added, last device reading, and last remediation, per caller ID.

        4

#### Name Each Number After the Caller Who Uses It

          Use the optional Name field. Adriana - 8, Tinaa - 9, Adriana - 14. That one habit turns a wall of 865 numbers into a report you can act on, because every flag maps to a seat and a day of dials.

        5

#### Confirm the Carrier Reads Correctly

          The Carrier column shows who issued the number. Ours reads TELNYX because that is what sits behind smrtPhone. If a number shows the wrong carrier, treat its reporting as unreliable until support confirms it.

        6

#### Check Device History Every Morning

          Open Device History before your callers sit down. Scan yesterday's column for red. Anything red for a second consecutive day comes out of the dialer that morning, not that afternoon.

        7

#### Remediate and Rotate

          Submit remediation on flagged numbers, and use Assisted Remediation for the ones that will not clear on their own. The Remediate column tracks your last submission date. Rest the number while it processes and dial from a clean one.

    **The rotation rule that keeps numbers alive:** spread dials across the pool instead of hammering one caller ID. A number carrying 400 dials a day gets flagged. The same 400 dials split across four numbers usually does not. Number Verifier shows you where that line sits in your market instead of making you guess.

    Once the daily read is stable, automate it. Webhooks push flag events into your own stack, API Flags and API History expose the same data programmatically, and the Integrations screen connects it to the tools you already run. Pair it with the Claude Caller Reputation Monitor skill above. Number Verifier reports the carrier's verdict, and the skill reads your own answer rates per caller ID, so you catch the slide before the flag lands.

        **Number Verifier:** Daily device-level caller ID monitoring across AT&T, T-Mobile, and Verizon, with remediation built in. [Start at app.numberverifier.com](https://app.numberverifier.com/).

## Real Results from Real Operators

    Phone scoring isn't theoretical. Here's what happens when operators implement the 5-Tier system.

#### Joshua English

        Split-tested Trestle phone scoring with a VA. Connection rates jumped from 2-3% to 9.5%. A 4.75x improvement from one change: scoring numbers before dialing.

#### 93.6% Accuracy

        93.6% of Correct phones score 70 or above. And 88.4% of Dead phones score 30 or below. The scoring model is reliable.

        Operator feedback on Trestle implementation and connect rate improvement.

## Phone Scoring in Your Marketing Pipeline

    Phone scoring sits between skip tracing and dialing. It's the quality gate that ensures only active numbers reach your callers.

      Data Pull
      →
      Skip Trace
      →
      Phone Score
      →
      Tag & Filter
      →
      Load Dialer
      →
      Call

#### Niche Sequential (200-500 records)

        Score all numbers. Call Dial First through Dial Third over 3 days using click-to-dial (smrtPhone). Route Dial Fourth to direct mail only. Drop gets removed entirely.

#### Bulk Sequential (5,000+ records)

        Score all numbers. Load only Dial First + Dial Second into ReadyMode power dialer. Remaining tiers get routed to SMS-only or direct mail. Never waste dialer lines on low-score numbers.

    **Cross-references:** For the full niche sequential workflow, see the Niche Sequential Marketing Guide. For team structure and daily Data Manager workflows (including Trestle scoring at 11 AM), see the Team Structure Guide.

      Next 5-Day Deal Flow Challenge: Monday, August 17 to August 21. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Tools & References

    Everything you need to implement phone scoring in your operation.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

      [#### Trestle Phone Scoring

Sign up for Trestle API access. Requires work email.](https://trestleiq.com/?fpr=ty12)
      [#### Free Caller Registry

Register your outbound numbers. Free. Re-register quarterly.](https://freecallerregistry.com/fcr/)
      [#### Number Verifier

Daily caller ID spam monitoring across AT&T, T-Mobile, and Verizon.](https://app.numberverifier.com/)
      [#### Claude Phone Validator Skill

Download the Claude skill that automates Trestle scoring.](https://drive.google.com/file/d/1VzNjMOj8Rf3zh0pR0DzFE2pOILyGcYoE/view?usp=sharing)
      [#### Claude Caller Reputation Monitor Skill

Download the Claude skill that watches your caller IDs for spam flags.](https://drive.google.com/file/d/1K9bB9u2ZmVlQKFJ3XLaLfLvSoGZLYoYI/view?usp=sharing)
      [#### Phone Analysis Report

Full 2,000-number study with Trestle scoring data.](https://drive.google.com/file/d/1vpA5TBLAUVm23_FRC_opoklWMeXufDbQ/view?usp=sharing)
      [#### Loom Walkthrough

Step-by-step video on attaching phone scores to DataSift.](https://www.loom.com/share/84b3ebc9b75c4c4d98e29d450f3df3a9)

#### Niche Sequential Marketing

Full 3-day cadence workflow with 12 filter presets.

      [#### Deal Flow Tech Stack SOP

Complete tech stack with pricing for every phase of the Deal Flow Ladder.](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)

          Reset

  ×
