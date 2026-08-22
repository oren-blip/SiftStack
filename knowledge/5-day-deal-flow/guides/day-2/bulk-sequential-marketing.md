# Guide: bulk-sequential-marketing

> Source: https://learn.datasift.ai/bulk-sequential-marketing (Day 2 module, fetched 2026-08-21)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      Marketing Execution

# Bulk Sequential Marketing

      One flat cadence over the whole validated universe. Load big. Never double-send.

        18 min read
        ·
        Companion: Niche Sequential Marketing

    The Framework

## Same Principle. Different Scale.

    Bulk answers one operator question: "I want to run a big campaign today, who do I load?" One flat cadence over the entire validated universe.

    The bulk universe is every record carrying a Priority 1, Priority 2, or Tier 2 tag. Not a new list. The same records the niche folders already work, viewed through a volume lens.

    FTM stays in its own lane, folders 05 and 06, with its weekly blitz rhythm. Fresh courthouse pulls never mix into the bulk queue.

      The bolt-on: folder 09 holds call stages 00 through 08, folder 10 holds the Mail 01-06 rotation. Same two counters as the niche folders.

        0

        Call Attempts

        0

        Mail Pieces

        0

        Record Universe

    Live counts from the Knox + Blount build, July 2026. 10,069 of those records are callable after suppression. Yours will differ.

        Cheapest

        Cold Call

        ~$0.03-0.06

        Cheap

        SMS follow-up

        ~$0.01/touch

        Mid

        Direct Mail

        ~$0.50-2.00

        Expensive

        Deep Prospecting

        ~$1.50-4.00

    The cost ladder. This orders your spend, not your sequence. Calls and mail both start Day 1; the expensive touches wait for the records that survive them.

    Bulk and niche run at the same time by design. Every preset reads the same two counters, so a dial or a send from any view advances the record everywhere. No double-dialing, no double-sending.

    Mail does not wait for calls. The first handwritten letter is due the day a record enters the system, while the call attempts are happening. The old call-first-then-mail gate is gone.

## Niche vs. Bulk

    Ordering versus volume. The two lenses share records, counters, mail, and suppression. Only the question changes.

         |
           | Aspect | Niche Folders (01-08) | Bulk Folders (09-10)

           | Operator Question | "Who do I dial first?" | "Who do I load for a big campaign?"

           | Dialing Style | Prioritized daily dialing, top down: Hottest, Strong, FTM, Tier 2 | Mass campaign loads and new dialer seats

           | Call Attempts | 3 per cadence | 6; attempts 4-6 are the extended runway

           | Mail Sequence | Same 6-piece rotation | Same 6-piece rotation

           | Suppression | Same universal stack | Same universal stack

           | Attempt Counters | Shared with bulk | Shared with niche, which is why both can run at once

           | Records Covered | One tag per folder pair | Union of Priority 1, Priority 2, and Tier 2

           | Best For | A dial hour worked in priority order | Filling a predictive dialer for a week

    **When to use which:** niche folders for prioritized daily dialing, Hottest first. Bulk when volume matters more than ordering: a mass campaign load or a new dialer seat.

## Score Before You Dial

    Trestle scores every number 0-100 by activity, eliminating roughly 50% of dead numbers, protecting caller IDs from spam flags, and doubling dialing efficiency.

          81-100

          Dial First

#### Highest Priority

          Active numbers with highest answer probability. Call these first.

            These are your best numbers. Load Dial First records into your dialer as the priority queue. Your callers connect more often, close faster, and burn fewer caller IDs on dead lines. Tag in DataSift: "Dial First".

          61-80

          Dial Second

#### Second Priority

          Good numbers. Solid answer rates. Second pass after Dial First is exhausted.

            Still strong numbers worth calling. Run these after your Dial First batch is complete. Some may have lower activity because the owner uses a secondary phone. Tag in DataSift: "Dial Second".

          41-60

          Dial Third

#### Moderate Priority

          Hit or miss. Some connect, some do not. Third pass when time allows.

            These numbers show some activity but are not reliably answered. Worth attempting if your team has bandwidth. Skip if you are short on callers. Tag in DataSift: "Dial Third".

          21-40

          Dial Fourth

#### Low Priority

          Mostly inactive. Only dial these if every other tier is exhausted.

            Low activity suggests the number may be disconnected or rarely used. Calling these burns dialer time with minimal return. Only attempt after all higher-priority tiers are complete. Tag in DataSift: "Dial Fourth".

          0-20

          Drop

#### Do Not Call

          Dead, disconnected, or confirmed inactive. Remove from calling queue entirely.

            Calling these numbers wastes dial time and risks your caller IDs getting flagged as spam. Remove them completely. If the record has no other numbers above 20, tag it Mail Only; its mail sequence keeps running either way. Tag in DataSift: "Drop".

    **What this costs:** Trestle scores at ~$0.015 per number. For 5,000 records with 3 numbers each, that is $225. The cost of calling 7,500 dead numbers without scoring? Burned caller IDs, wasted hours, and spam flags that take weeks to clear.

      [Watch the Trestle walkthrough](https://www.loom.com/share/84b3ebc9b75c4c4d98e29d450f3df3a9) to see how to attach phone scores to DataSift.

## Before You Load the Dialer

    Two decisions and three setup steps. The bulk pair is already built; your job is to find it and load it.

#### Scale to a power dialer for volume days

        A multi-line dialer runs 250-350 dials per caller per day. Scale up once click-to-dial proves ROI.

#### Work a 10,000-record queue on click-to-dial

        Click-to-dial covers 150-200 dials a day. Fine for niche queues. Too slow for the bulk universe.

#### Score phones with Trestle first

        Tag every number before loading into your dialer. Eliminates ~50% dead numbers. Protects your caller IDs.

#### Dial raw, unscored lists

        Calling unscored numbers burns caller IDs on dead lines. One spam flag costs weeks of recovery.

        ReadyMode campaign setup. One power dialer option for working the Bulk - 02 Ready to Call export.

        Smarter Contact campaign builder. An SMS option for cheap follow-up touches after a call attempt.

### Setup Steps

        1

#### Find Folders 09 and 10

          Open Filter Presets and find **09 BULK - CALL** and **10 BULK - MAIL** in the 01-20 stack. Every preset you need already lives inside them.

        2

#### Confirm the Skip Funnel

          Open Bulk - 00 Needs Skipped and Bulk - 01 Skipped No Numbers. Records without callable phones wait there, not in your dial queue.

        3

#### Load the Queue

          Export Bulk - 02 Ready to Call and load it into your dialer. The preset name is the instruction.

      The full 01-20 preset stack. The bulk pair sits at 09 and 10, after the four niche CALL/MAIL pairs and ahead of Deep Prospecting and Reactivation.

## Skip Trace

    Two presets catch records that cannot ring yet. The dial queue stays clean because these wait here.

    Every bulk preset shares one filter shape. Blue inclusion chips define the universe: Priority 1, Priority 2, and Tier 2. Red exclusion chips carry the universal suppression stack. A call attempts value sets the stage.

          00
          Bulk - 00 Needs Skipped
          Skip Trace

               |  | Parameter | Setting

                 | Tags (OR) | Include: Priority 1, Priority 2, Tier 2

                 | Universal Suppression | Exclude: done/dead statuses, recently sold, Low/Negative Equity lists, dead neighborhoods, Not Single Family, Mail Only

                 | Numbers | No

                 | Skiptraced | No

              The bulk skip funnel: Priority 1, Priority 2, and Tier 2 in blue, the suppression stack in red.

              **Why:** No phone on file, never skip traced. The action is the preset name: skip trace the list. 366 records were waiting here on the live Knox + Blount build.

              I found this preset

          01
          Bulk - 01 Skipped No Numbers
          Skip Trace

               |  | Parameter | Setting

                 | Tags (OR) | Include: Priority 1, Priority 2, Tier 2

                 | Universal Suppression | Exclude: the same stack as every marketing preset

                 | Numbers | No

                 | Skiptraced | Yes

              Skip traced, still nothing callable. Mail keeps working these records.

              **Why:** Skip traced and still no number. These records cannot ring, so mail is their channel. The Mail 01-06 rotation below covers them from Day 1.

              I found this preset

## The Six-Attempt Ladder

    Bulk - 02 Ready to Call is the big queue. Presets 03 through 08 walk every record through six attempts.

      Six rungs, six attempts, one shared counter. Above rung six there is no rung: the record drops to deep prospecting.

          02
          Bulk - 02 Ready to Call
          Calling

               |  | Parameter | Setting

                 | Tags (OR) | Include: Priority 1, Priority 2, Tier 2

                 | Universal Suppression | Exclude: full stack, including Mail Only on call presets

                 | Numbers | Yes

                 | Call Attempts | 0 to 0

              The volume shot: Bulk - 02 Ready to Call applied, 965 pages at 10 records per page. A queue this size is why bulk exists.

              The big queue criteria: the whole validated universe at zero call attempts.

              **Why:** Has a number, zero dialer attempts. This is the load list for a volume day: 9,743 records sat here on the live build. Export, load, dial.

              I loaded this queue

          03-08
          Bulk - 03 to 08: Call Attempts 1 to 6
          Calling

               |  | Parameter | Setting

                 | Call Attempts | N to N, where N is the attempt number (1 through 6)

                 | Everything else | Identical to Bulk - 02

              Call Attempts 1 to 1 inside bulk. The same counter every niche folder reads.

              **Why:** One preset per attempt count. The predictive dialer increments the counter and the record walks the ladder on its own. Nobody moves anything by hand.

              I confirmed all six attempt presets

    Bulk call and niche call read the same attempt counter. Dial a record from bulk and it advances in its niche cadence too, so there is no double-dial conflict.

    Attempts 4-6 are bulk's extended runway. The niche cadences stop at three; bulk keeps pressing to six while the record keeps receiving its tier mail. That overlap is deliberate multi-channel pressure, not a bug.

      Anatomy of Bulk - 08 Call Attempt 6. Blue chips define the universe: Priority 1, Priority 2, Tier 2. The red stack is universal suppression. Call Attempts reads 6 to 6.

## The Six-Piece Mail Rotation

    Folder 10 runs the exact rotation the niche mail folders run, over the whole universe. Six typed presets, one monthly pull each.

          01-06
          Bulk - Mail 01 to 06
          Mail

               |  | Parameter | Setting

                 | Direct Mail Attempts | One value per preset: Mail 01 reads 0 pieces sent, Mail 02 reads 1, through Mail 06 at 5

                 | Last Direct Mailed | A month or more ago (Mail 02 onward)

                 | Tags (OR) | Include: Priority 1, Priority 2, Tier 2

                 | Universal Suppression | Exclude: full stack; Mail Only records stay in

                 | Vacant Mailing | Excluded automatically

                Bulk Mail 01: Direct Mail Attempts 0 to 0 over the whole universe, vacant mailing excluded.

                Bulk Mail 02: one piece sent, month spacing enforced by the Last Direct Mailed window.

              **Why:** Each preset is a literal instruction: print this list, send the named piece. The rotation alternates handwritten letter (about $1.75), family postcard, and soft-offer check, then repeats.

              I confirmed all six mail presets

### The Live Queue

         |  | Preset | Piece | Live count

           | Mail 01 | Handwritten Letter | 9,325 due now

           | Mail 02 | Family Postcard | 0, fills a month after the first send wave

           | Mail 03 | Soft-Offer Check | 0

           | Mail 04-06 | Rotation repeats | 0

    Knox + Blount live counts, July 2026. Every 0 fills on schedule as the counter advances.

      Bulk - Mail 01 Handwritten Letter applied: 925 pages of records due their first piece. This list is due the day it exists.

### The Six Rules

- Mail runs parallel with calling from Day 1. No call prerequisite.

- Never the same piece type two months in a row. The rotation bakes it in.

- Month spacing is automatic. Monthly pulls can never double-mail.

- Vacant owner mailing addresses are excluded.

- Mail Only records enter the same sequence on Day 1.

- After piece 6 the record exits mail.

    **Pick one pull convention per month:** sends increment the one shared mail counter. Pulling monthly sends from bulk or from the niche folders produces the same sequence. Choose one source per month purely for budgeting clarity.

      Piece anatomy and exact Sift Mail per-piece pricing live in the Direct Mail Mastery guide.

## One Record, Two Lenses

    Proof the counters are shared, then the three ways a record leaves the machine.

    Here is the same record, Joshua Lane, sitting at Call Attempt 1 in two folders at once. One dial moved it in both. No sync job, no duplicate. One counter.

        Hottest - 03 Call Attempt 1. The record's niche home.

        Bulk - 03 Call Attempt 1. Same record, same attempt count, volume lens.

### Where Bulk Records Exit

#### Convert

        A status change (lead, under contract, sold) pulls the record out of all cold marketing instantly.

#### Suppress

        Any suppression trigger (recently sold match, equity list, dead neighborhood) removes it from every flow at once.

#### Exhaust

        After attempt 6 and piece 6 the record leaves the sequences. Deep Prospecting (folder 11) works the expensive touches next.

    Not interested is not dead. Reactivation (folder 12) re-enters those records on timers. The live account is configured at 15 days for foreclosure headed to auction, 45 for probate, 90 for other FTM, and 45 for Tier 2.

    **Not interested vs. never answered:** a seller who said no re-enters through a Reactivation timer. A record that never picked up exhausts the six attempts first, then surfaces for rehash. Different people, different re-entry paths.

## Protect Your Caller IDs

    Two tools. Three steps. The difference between a phone number that works for months and one that gets flagged in a week.

#### Free Caller Registry

        Register all dialing numbers every 90 days. Free. Reduces spam likelihood across carriers.

        [freecallerregistry.com](https://freecallerregistry.com/fcr/)

#### Trestle Phone Scoring

        Score before dialing. Dead/disconnected numbers trigger spam flags when called. Remove them before they burn your IDs.

        [trestleiq.com](https://trestleiq.com/)

### Protection Workflow

        1

#### Score Phones with Trestle

          Tag results in DataSift: Dial First, Dial Second, Dial Third, Dial Fourth, Drop.

        2

#### Register with Free Caller Registry

          Register every dialing number your team uses. Set a 90-day calendar reminder to re-register.

        3

#### Load Only Scored Records

          Only load Dial First, Dial Second, and Dial Third into the dialer. Drop records never enter it.

    Your caller IDs are currency. One spam flag and the number is toast for weeks. Trestle scoring plus Free Caller Registry is the insurance: $0.015 per number plus free registration, versus hundreds of missed connections from a burned number.

## Track Your Progress

    Check off each step as you confirm it in your account. Progress syncs with the checkboxes above.

      0 / 10 steps

        Folders 09 BULK - CALL and 10 BULK - MAIL located

        Bulk - 00 Needs Skipped confirmed

        Bulk - 01 Skipped No Numbers confirmed

        Bulk - 02 Ready to Call loaded in the dialer

        Attempt ladder 03-08 confirmed

        Mail 01-06 rotation confirmed

        Suppression chips verified on one preset

        Phone scoring run through Trestle

        Caller IDs registered, 90-day reminder set

        Monthly mail pull convention chosen

      5-DAY DEAL FLOW CHALLENGE

### Next live cohort: Monday, August 17 to August 21

      5 days live with Ty. 34 interactive modules. A community of 1,047+ investors. Save your seat in the next cohort. Already enrolled? Use this guide as your between-session refresher.

        Save Your Seat →

## Next Steps

    Tools, guides, and reference material for your bulk sequential marketing setup.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### Niche Sequential Marketing

Companion guide: the four niche folder pairs, staged cadences, Day 1 mail

#### Direct Mail Mastery

Piece anatomy and exact Sift Mail pricing for all three mailer types

#### Phone Scoring & Spam Management

Scoring, tagging, the five dial tiers, and caller ID spam monitoring

#### Team Structure & Sequential Marketing

Day 2 core guide: hiring order, roles, and caller KPIs

      [#### Bulk Filter Tutorial

Official DataSift help article with step-by-step screenshots](https://intercom.help/reisift/en/articles/12558490-bulk-sequential-marketing-filters)
      [#### Trestle Scoring Walkthrough

Loom video: how to attach phone scores to DataSift](https://www.loom.com/share/84b3ebc9b75c4c4d98e29d450f3df3a9)

        Reset All

  ×
