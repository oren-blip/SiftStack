# Guide: niche-sequential-marketing

> Source: https://learn.datasift.ai/niche-sequential-marketing (Day 2 module, fetched 2026-08-21)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      Marketing Execution

# Niche Sequential Marketing

      Every Record Gets Worked. Two Channels From Day One.

          15 min read

    The Framework

## Calls and Mail Run Together

    Every niche record works two channels at once. A staged call cadence and a 6-piece mail rotation both start Day 1. Nothing waits.

        Cold Call

        ~$0.03-0.06/touch

      →

        SMS Follow-Up

        ~$0.01/touch

      →

        Direct Mail

        ~$0.50-2.00/touch

      →

        Deep Prospecting

        ~$1.50-4.00/touch

    That is a cost ladder, not a timeline. Calls and mail start together on Day 1. Deep prospecting waits for the records both channels miss.

        27

        Touches in 72 hours

        3 + 6

        Call attempts plus mail pieces, two channels per record

        20-30%

        Deals from not-interested follow-ups

    Spend cheap touches freely, expensive touches selectively. A call costs a nickel, a text a penny, a handwritten letter about $1.75, deep prospecting up to $4.00. Real money only chases records both channels missed. On deceased or sensitive lists, drop the cold text.

    Touch quality is saturation-driven. Fresh first-to-market lists connect on the standard cadence with cheap touches. A saturated list like foreclosure needs a higher-caliber caller and premium touches to stand out. Match effort to saturation.

    One record proves the whole model. Pull up any lead in the live build and it holds a place in both channels at once.

        One record sitting in Hottest - 03 Call Attempt 1, its place in the call channel.

        The same record, same moment, due in Hottest - Mail 01 Handwritten Letter. One queue per channel.

## 72 Hours. 3 Attempts. Every Number.

    Each niche lead gets a 3-day phone blitz while its first mail piece is already on the way.

      One record, three stamps in 72 hours. The handwritten letter launched on day 1 lands as the phone blitz ends.

        Day 1

#### First Attempt + Mail 01

- Call every number on the record

- Leave voicemail if no answer

- Send follow-up text

- Mail 01 handwritten letter triggers (about $1.75), no call prerequisite

        Day 2

#### Second Attempt

- Call every number again

- Leave voicemail (different script)

- Send different text message

- Mailer is in transit

        Day 3

#### Third Attempt

- Final call pass on all numbers

- Leave voicemail (urgency angle)

- Final text variation

- Mailer arrives (1-3 day delivery)

        DO: Click-to-Dial
        Use smrtPhone for one-at-a-time calling. Niche leads are high-value, first-to-market records. They deserve a personal touch, not a power dialer blast.

        DON'T: Power Dialer for Niche
        Power dialers burn through lists fast but create a terrible first impression. Save ReadyMode for bulk campaigns with thousands of records.

    Use Trestle phone scoring before you start calling. Numbers scored 81-100 (high activity) go to the top. This cuts your trash number rate by about 50% and means your first calls reach real people, not disconnected lines.

### Channel Cost Breakdown

       |
         | Order | Channel | Cost Per Touch | When to Use

         | 1 | Cold Calling | ~$0.03-0.06 | First touch, every time. Primary outreach, click-to-dial

         | 2 | SMS / Text | ~$0.01 | Follow-up after call attempts. Never the first touch, dropped on sensitive lists

         | 3 | Direct Mail | ~$0.50-2.00 | Triggers Day 1 alongside the first call, then a typed 6-piece staged sequence

         | 4 | Deep Prospecting | ~$1.50-4.00 | Unreachable leads, all channels exhausted

    Never send the same mailer type two months in a row. Rotate between handwritten letters (forever stamp, about $1.75), family-style postcards, and soft-offer checks. Validated across 980,000 mailers.

## The Machine You Are Working Inside

    Twenty folders, four niches, two counters. Open Filter Presets in DataSift and the whole system reads top to bottom.

    Folders 01-08 are the niche CALL/MAIL pairs. Folders 09-10 run the bulk layer. Folder 11 is Deep Prospecting, folder 12 is Reactivation, and the rest are operations views. Dial order is folder order.

      The full 20-folder stack. An operator reads this panel top to bottom and always knows what to work next.

### The Four Niches

    Live counts below come from the Knox + Blount build, July 2026. Yours will differ.

       |  | Niche | Folder Pair | Who Enters | Live Size

         | Hottest | 01 CALL / 02 MAIL | Priority 1 tag: AI score 90+ or a hottest two-list combo | 3,667 tagged

         | Strong | 03 CALL / 04 MAIL | Priority 2 tag: AI 70-89 or a strong combo | 9,288 tagged

         | FTM | 05 CALL / 06 MAIL | FTM tag: direct-from-county uploads, 0-7 days fresh | Dozens, rolling weekly

         | Tier 2 broad | 07 CALL / 08 MAIL | Tier 2 tag minus both priority tags | ~1,100 ready to call

    **The common mistake: mixing the vocabulary.** Tier numbers are provenance, where the data came from. Priority words like Hottest and Strong are urgency. Never mix the two.

      The niche entry tags: Priority 1 (3,667 records) and Priority 2 (9,288) stamped on top of Tier 2 provenance.

### The Two Counters That Drive Everything

    Every record carries **predictivecall_attempts**, written by the dialer, and **directmail_attempts** plus a last-mailed date, written by each send. Every preset reads those same two counters. Dial or mail a record from any view and it advances everywhere at once.

      Both counters on one record. These two numbers decide which call stage and which mail piece it is due for.

    **One call home:** each record lives in exactly one call cadence. Strong excludes Priority 1 records, and broad Tier 2 excludes both priority tags. Nobody gets double-dialed by two niche cadences.

### The Daily Motion

        1

#### Open Filter Records

          Go to your property records and click "Filter Records" at the top of the list view.

        2

#### Expand Filter Presets

          The saved folders appear in order, 01 through 20. Every preset inside is a pre-built queue.

        3

#### Work Folders Top Down

          A dial hour goes to Hottest before Strong, Strong before FTM, broad Tier 2 last. Pull the preset, do what its name says.

        smrtPhone click-to-dial on a lead record. One click starts the call directly from your CRM.

## Call Stages 00-02: Skip Trace and Queue

    Every CALL folder holds the same six stage presets. The first three get records dialable, then queue them.

      Folder 01 expanded: six stage presets, one home per record, nothing to drag between stages.

          00
          Hottest - 00 Needs Skipped
          Skip Trace

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1 (Strong uses Priority 2, FTM uses FTM, and so on)

                 | Suppression | Exclude: the universal suppression stack (see the suppression section)

                 | Numbers | No

                 | Skiptraced | No

              Inside the live preset: Priority 1 in blue, the suppression stack in red, no numbers, not yet skip traced.

              **Why:** No phone, never skip traced. The entry gate for every fresh record. Operator action: run skip trace. Records that come back with numbers move themselves to 02 Ready to Call.

              I have set this up

          01
          Hottest - 01 Skipped No Numbers
          Skip Trace

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | Numbers | No

                 | Skiptraced | Yes

              Skip traced and still no callable number. These records leave the call lane and keep receiving mail.

              **Why:** Skip traced, still no number. Operator action: run a second-pass provider (Skip Genie, BeenVerified) or tag the record Mail Only. Mail Only removes it from every call preset while the full 6-piece mail rotation keeps working it.

              I have set this up

          02
          Hottest - 02 Ready to Call
          Call

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | predictivecall_attempts | 0 to 0

                 | Numbers | Yes

              The dial queue criteria: Priority 1 included, every exclusion in red, zero call attempts.

              **Why:** Has a number, zero dialer attempts. This is the live dial queue, 2,572 records deep in the Hottest folder of the live build. Load it and dial.

              The applied preset, filtering by Hottest - 02 Ready to Call. This grid is the day's dial work.

              I have set this up

## Call Stages 03-05: Attempts 1, 2, 3

    The dialer writes the counter and the counter moves the record. You never drag a lead between stages.

          03
          Hottest - 03 Call Attempt 1
          Call

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | predictivecall_attempts | 1 to 1

              Call Attempts reads 1 to 1. The dialer moved this record here on its own.

              **Why:** One dialer attempt logged. Day 2 of the blitz: call again with a different voicemail script and a varied text. Re-queue on the next pass.

              Hottest - 03 Call Attempt 1 applied: every record here has exactly one dialer attempt on the counter.

              I have set this up

          04
          Hottest - 04 Call Attempt 2
          Call

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | predictivecall_attempts | 2 to 2

              Same shape as attempt 1, Call Attempts now reads 2 to 2.

              **Why:** Two attempts down, Day 3 of the blitz. Final phone pass with the urgency voicemail. The mail channel keeps running the whole time.

              I have set this up

          05
          Hottest - 05 Call Attempt 3
          Call

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | predictivecall_attempts | 3 to 3

              Call Attempts 3 to 3. After this pass the record leaves the niche call cadence.

              **Why:** Three attempts complete. The record leaves the niche call cadence, and the Deep Prospecting exhausted view catches the un-contacted tail. Its mail sequence continues untouched.

              I have set this up

    Mail never pauses while calling escalates. A record on Call Attempt 2 still appears in its mail preset the day its next piece comes due.

## The 6-Piece Mail Rotation

    Six presets per MAIL folder, staged on pieces sent. Each one is a literal print-this-list, send-this-piece queue.

       |  | Preset | Piece | Who Shows Up

         | Mail 01 | Handwritten letter, forever stamp (about $1.75) | Never mailed. Due immediately, day one, no call prerequisite

         | Mail 02 | Family-style postcard | 1 piece sent, a month or more ago

         | Mail 03 | Soft-offer check | 2 pieces sent, last one a month plus

         | Mail 04 | Handwritten letter (rotation restarts) | 3 sent, due again

         | Mail 05 | Family-style postcard | 4 sent, due again

         | Mail 06 | Soft-offer check | 5 sent, due again. Piece 6 is the exit

      Folder 02 expanded: six piece presets. The preset name tells you exactly what to print and send.

### The Six Rules

- 1**Mail runs parallel to calling.** The first handwritten letter goes out while the phone attempts happen, not after.

- 2**Never the same piece type two months in a row.** The rotation bakes it in. You send whatever the preset names.

- 3**Month spacing is automatic.** A record reappears only when its last piece is a month old, so monthly pulls can never double-mail.

- 4**Vacant owner mailing addresses are excluded.** The preset filters them out before you ever export.

- 5**Mail Only records ride the same sequence from day one.** There is no separate mail-only flow anymore.

- 6**After piece 6 the record exits mail.** By then it has had every cheap and mid-cost touch. What is left escalates to Deep Prospecting.

          01
          Hottest - Mail 01 Handwritten Letter
          Mail

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack (Mail Only stays IN here)

                 | directmail_attempts | 0 to 0

                 | Vacant Mailing | No

              Direct Mail Attempts 0 to 0 and Vacant Mailing set to No. Never mailed means due today.

              **Why:** Never mailed, due day one, no call prerequisite. Export this list monthly and send the handwritten letter. In the live build, 2,696 Hottest records sat here on day one.

              Hottest - Mail 01 Handwritten Letter applied: the records due their first piece right now.

              I have set this up

          02+
          Mail 02-06: The Rotation Pattern
          Mail

               |  | Parameter | Setting

                 | Niche tag | Include: Priority 1

                 | Suppression | Exclude: the universal suppression stack

                 | directmail_attempts | n to n (Mail 02 reads 1 to 1, up through Mail 06 at 5 to 5)

                 | Last direct mailed | A month or more ago

                 | Vacant Mailing | No

                Mail 02: one piece sent, and the Last Direct Mailed window only admits records a month or more out.

                Mail 03: two pieces sent. The same date window keeps the month spacing automatic.

              **Why:** Each preset catches records with n pieces sent whose last piece is a month or more old. The piece type follows the rotation, restarting the letter at Mail 04.

              I have set these up

      The Mail 01 drawer: DIRECT MAIL ATTEMPTS 0-0 plus month spacing is why a monthly pull can never double-mail anyone.

    **The monthly ritual:** open each mail preset, export the list, send the named piece. The counters handle everything else.

## What Keeps Every List Clean

    One suppression stack sits inside every marketing preset. Six exclusions, applied everywhere, so junk never reaches a caller or a mailbox.

- 1**Done and dead statuses.** Sold, under contract, not interested, DNC, dead lead, and the rest of the terminal set. Actively worked cold statuses stay in.

- 2**The recently sold tag.** SiftMap's recently-sold feed flags records that sold, and they exit every flow at once.

- 3**Low and negative equity lists.** The sub-20-percent equity band loses money on average. This now includes FTM records.

- 4**The 15 dead neighborhoods.** Measured investor activity of one deal or fewer. No marketing dollars go there.

- 5**Not Single Family.** Excluded on the priority flows, which target houses.

- 6**Mail Only, on CALL presets only.** Those records have no callable phone. Mail is their channel, so they stay in every mail flow.

    Open any preset drawer and the stack reads at a glance. Red chips are exclusions, blue chips are inclusions.

      The Ready to Call drawer: one blue Priority 1 inclusion, then the full red exclusion stack doing the cleaning.

### Where Records Exit

#### Convert

        A status change (lead, under contract, sold) pulls the record out of all cold marketing instantly.

#### Exhaust

        Three call attempts and six mail pieces with no contact. Deep Prospecting and Reactivation catch the tail.

#### Suppress

        Any suppression trigger, a recent-sale match or an equity list, removes it from every flow at once.

## Escalation and Re-Entry

    Two folders catch what the cadences miss. Deep Prospecting takes the unreachable, Reactivation brings back the timed-out.

### Folder 11: Deep Prospecting (All Tiers)

    The expensive-touch layer, $1.50-4.00 per touch: deeper skip tracing, door knocks, drive-bys. Five presets sort the tail by what went wrong. Full playbook in the Deep Prospecting guide.

       |  | Preset | Who Lands There

         | 01 No/Bad Phone | Skip trace came back empty or every number is wrong

         | 02 Obituary/Deceased | Owner is deceased. Research the heir

         | 03 Exhausted Call | Finished the niche call attempts, never answered

         | 04 Return Mail | A piece bounced back. The address is wrong

         | 05 Vacant | Property flagged vacant. Nobody home to reach

      Folder 11 expanded: five reasons a record went unreachable, each with its own expensive-touch queue.

### Folder 12: Reactivation

    Not-interested records re-enter on timers. This is how the live account is configured, tuned to each niche's deadline pressure.

        15

        Foreclosure Headed to Auction

        The auction date does not wait. Shortest leash in the system.

        45

        Probate

        Estates settle slowly. Heirs change their mind after the initial grief passes.

        90

        Other FTM

        The rest of the courthouse lists re-enter quarterly.

        45

        Tier 2 Not Interested

        Distressor records that said no get a mid-length timer.

    **Do not skip reactivation.** These leads already picked up once. The number works. The only variable is timing, and 20-30% of platform deals come from exactly these follow-ups.

              Folder 12 in the live account: four Not Interested timers and the Rehash queue.

          NI
          Not Interested Re-Entry
          Recycle

               |  | Parameter | Setting

                 | Property Status | Include: Not Interested

                 | Last status update | Older than the niche timer (15 / 45 / 90 / 45 days)

              The live 15 day timer for foreclosure records that said not interested.

              **Why:** They answered once, so the number works. When the timer lapses the record surfaces here for a fresh pass. Circumstances change: tax bills pile up, family situations shift.

          RH
          Never-Answered Rehash
          Recycle

               |  | Parameter | Setting

                 | predictivecall_attempts | At the cadence max (3 niche, 6 bulk)

                 | Property Status | No disposition set

                 | Phones | Correct numbers on file

              Rehash Ready: records that finished the cadence without ever answering.

              **Why:** Correct numbers, zero conversations, cadence finished. These records re-enter after a rest and get another pass. Volume tools work here; the personal-touch rule belongs to fresh niche records.

## External Mailing Tracking

    Sift Mail records sends automatically. Using an outside mail house? Three habits keep the shared counter honest.

        1

#### Tag Each Mailing Batch

          After exporting a list for external mailing, add a tag using the format **"DM MM/YYYY"** (e.g., "DM 03/2026"). This creates a timestamp trail.

        2

#### Increment Mail Attempts

          Increase Direct Mail Attempts for every mailed record. A send recorded anywhere advances the record in every mail view, niche and bulk alike. Skip this and records sit stuck in Mail 01.

        3

#### Tag Return Mail

          When mailers come back, add the **"Return Mail"** tag. The Deep Prospecting Return Mail preset catches them automatically.

      Sift Mail Tracks Itself
      Pieces sent through Sift Mail increment the counter automatically, so the rotation stays accurate with zero bookkeeping. Piece anatomy and per-piece pricing live in the Direct Mail Mastery guide.

## Preset Setup Checklist

    Confirm each preset exists in your account. Progress syncs with the checkboxes inside the accordions above.

      0 / 13 presets

      00 Needs Skipped

      01 Skipped No Numbers

      02 Ready to Call

      03 Call Attempt 1

      04 Call Attempt 2

      05 Call Attempt 3

      Mail 01 Handwritten Letter

      Mail 02 Family Postcard

      Mail 03 Soft-Offer Check

      Mail 04 Handwritten Letter

      Mail 05 Family Postcard

      Mail 06 Soft-Offer Check

      Universal suppression verified on every preset

      5-DAY DEAL FLOW CHALLENGE

### Next live cohort: Monday, August 17 to August 21

      5 days live with Ty. 34 interactive modules. A community of 1,047+ investors. Save your seat in the next cohort. Already enrolled? Use this guide as your between-session refresher.

        Save Your Seat →

## Keep Building

    Tools, guides, and references to support your niche sequential marketing setup.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

Bulk Sequential MarketingThe companion guide: folders 09-10, six call attempts over the whole universe

Direct Mail MasteryPiece anatomy and Sift Mail per-piece pricing for all three mailer types

      [Niche Sequential Filters Help ArticleOfficial DataSift setup documentation](https://intercom.help/reisift/en/articles/12543919-niche-sequential-marketing-filters)

Team Structure & Sequential MarketingDay 2 core guide: hiring, roles, 27-touch SOP

Deep Prospecting GuideFolder 11 escalation: the 4-level research framework for unreachable leads

      [Deal Flow Tech Stack SOPComplete tool stack with pricing and setup guides](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)
      [Critical Resource Hub83 tools and resources across all 5 days](https://docs.google.com/spreadsheets/d/1bQBHLsxVwXbsbz9SBcfpatPaFgAIsICo/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

 Reset All

×
