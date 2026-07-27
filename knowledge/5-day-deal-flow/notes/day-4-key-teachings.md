# Day 4 — Sales, Lead Management & Deal Analysis (2026-07-16)

Distilled from [day-4-2026-07-16.md](../transcripts/day-4-2026-07-16.md) (~2h 5m).

> ⚠️ **This day's transcript is closed captions with NO speaker labels.** Ty Garrett hosts and Tyler
> Austin, Phil Loesch, and Micah Redden are clearly present from context, but the transcript cannot
> prove who said what. Attributions below are inferred from content and flagged where uncertain —
> **do not quote anyone from Day 4 as definitive without checking the recording.**

Ty's own framing: *"Today is all about the sales stuff — lead management, some cool AI workflows with
comping, rehab estimations, and a couple new skills that rate the quality of a call."* `[00:01:44]`

---

## 1. The 4 Pillars of Motivation, and how to grade a lead `[00:24:43]`

Four questions, asked on the prospecting call:
**reason for selling · timeline · condition of the property · asking price.**

**Price is king.**
> **If the asking price is below 80% of the Zestimate, that's a hot lead — full stop.**
> Otherwise you want at least **two of the four** landing warm-or-hot.

Live example: seller wants **$135K** on a property with a **$243K** Zestimate. *"We're immediately
going to walk this property. I don't even need to hear anything else."* `[00:31:47]`

The guide has an interactive version that recalculates cold/warm/hot as you click — Ty used it to
onboard two new hires.

---

## 2. The 75 custom fields `[00:26:16]`

A structured field set covering the full sales process, grouped to mirror its phases: qualifying
questions → property condition/mechanics → title & ownership → valuation & rehab → appointment and
next steps. A Claude workflow can create all 75 for you.

**Why structure beats transcripts** (this reads like Tyler): `[00:34:59]`
> *"Every conversation is different, which means every transcript is different. But what we know is
> we need these ~30 questions answered… When you're using AI to do underwriting, it's really
> effective to have custom fields with that information so there's one central place for it."*

SmrtPhone can transcribe and summarize calls, but it costs extra and *"it's not going to have it in
the exact 75 fields we recommend. It's cookie cutter."*

**Title & ownership matters most on obituary data** `[00:27:57]`
> *"If someone says 'yeah, I inherited it from my parents' — 'have you gone through the probate
> process yet?' If they say no, that's a really big flag, because there are probably more people who
> need to sign this than this person thinks there are."*

**Whisper for the team** was a big unlock — callers voice-dictate their notes instead of typing. `[00:30:16]`

**The handoff problem Ty is solving for:** *"We get a lot of leads, but we're struggling to get them
back on the phone."* So prospectors gather pillars 1–3 and hand off to a closer who goes **to the
property** — *"it's much easier to set an appointment and go out there than to set an appointment to
call them."* `[00:28:46]`

---

## 3. STABM — the framework that makes everything else fire `[00:55:51]`

> *"This is one of the most important frameworks of the entire day."*

When a prospector converts a record into a lead, they must complete all five **before** it leaves the
marketing side:

| | |
|---|---|
| **S** | **Status** → change to *New Lead* |
| **T** | **Task** assigned |
| **A** | **Assignee** — the lead manager |
| **B** | **Board** — add to Lead Management, phase *New Lead* |
| **M** | **Messages** — notes in the message board |

**Changing the status to New Lead is the trigger** that fires the default automation, which then
assigns the board and task for you. `[01:00:50]`

> *"If you don't do STABM, none of this other stuff clicks together."*

And it applies even solo: *"If it's just you doing this, you still need to do all of it, because
otherwise the properties you're marketing to and the properties that are actually leads are all in
the same bucket. You'll start double-calling people."* `[00:59:02]`

Once STABM is done, the record **disappears from your marketing presets** (they suppress anything
already being worked), so you never double-dial. `[00:59:52]`

---

## 4. The lead lifecycle and follow-up cadence `[00:38:04]`

Unlike the marketing side, Ty considers this **objective** — mirror it rather than invent your own.
It ships built into every account.

| Status | Task cadence | Phase |
|---|---|---|
| **New Lead** | Call **same day** | New |
| **No Contact New Lead** | **Daily for 3–5 days** (default 3) | Unqualified |
| **Nurture New Lead** | **Weekly for 3–6 months** (default 3) | Unqualified |
| **Cold Lead** | Every **45 days** | Qualified |
| **Warm Lead** | Every **15 days** | Qualified |
| **Hot Lead** | Every **1–2 days**, sometimes same day | Qualified |

> *"When a lead is hot, do not let it settle. More than likely they're talking to other people, and
> if they're serious they'll just find the solution before you can provide it."*

**Timeline usually overrides price for temperature.** *"Even if they want to sell at 50% of market
value, if they don't want to sell for a couple months it's always going to be a cold or warm
follow-up because of the timeline."* `[00:41:19]`

**Move leads by dragging boards, not by editing statuses.** `[01:05:50]`
> *"The only status change that happens manually is New Lead. After that, do everything through the
> board."*
Changing a status directly instead of moving the card breaks the automations. Some users have
inverted this by choice, but the default build assumes board-driven movement — that's how the
interviewed power users were doing it.

**Foreclosure-specific tweak:** rather than rebuilding every cadence, just mark everything hot
(every 2 days). *"We already know they're motivated — they're going to auction."* `[00:45:14]`

---

## 5. Statuses, tags, and the ones people misuse

**Property temperature is separate from lead temperature** (Tyler's usage): `[01:10:10]`
> *"Everything about the lead is cold — probate's still going, they're not sure they want to sell,
> AI score is low. However, it's in a location I would give my right pinky toe for. Then I change the
> **property** temperature to hot, and we filter cold leads against property temperature to prioritize."*
>
> **Cold leads account for ~75% of your pipeline** — that's why prioritizing within them matters.

**"Not interested but they'll have to sell eventually"** → status **Long-Term Follow-Up**, and it
belongs in a **prospecting flow, not the lead management board**. `[01:11:55]`
> *"The lead management board should only be people that did raise their hand."*
Treat them like a tighter not-interested cadence — every 45 days rather than every 6 months.
*"They convert very well, actually."*

**Do Not Market tag** — suppressed everywhere in the pipeline. Used when something enters from SEO or
a re-upload that you'd never work (vacant land, mobile homes, wrong market). One user renamed theirs
to *Ignore* because staff kept confusing "do not market" with "do not call." `[01:13:34]`

**Mail Only tag** — for people who got genuinely angry on the phone but whose property you still want.
Keeps the opportunity alive on a channel that won't provoke them. `[01:15:11]`

**Prospecting status** simply means *"the team has actively started the new sequential process on
this record."* Deep prospecting is a different bucket entirely — obituary data goes straight there. `[01:08:35]`

**Recently-sold review** (Tyler's process, matching Day 2 §13): `[01:04:02]`
Build a filter under Lead Management for *pipeline statuses AND tag = recently sold*. The lead
manager reviews those each morning and manually moves them to **Lost Deal**, which fires a sequence
that clears tasks, sets the status, and removes the card.
> *"You could automate it. However, I personally would rather my lead manager take ownership over
> moving that record — **and letting it hurt a little bit**."*

---

## 6. AI call scoring — three new coach skills `[01:16:00]`

**Cold Caller Coach · Lead Manager Coach · Closer Coach** — added the morning of Day 4, explicitly
labeled unfinished. *"If it's not perfect, don't come with pitchforks."*

**The synthetic audience** underneath them: `[01:16:49]`
Ty exported a large volume of **real seller calls** and built **personas** from them — *"this is
someone who's a tired landlord; what do they sound like, what do they feel like"* — from 40–50 calls
per persona. The coach skills use those personas to model how a seller would have responded to what
your rep actually said.

Trained on roughly **300 calls**, with the rubric **blended from ~20 different sources** rather than
one methodology. `[01:30:18]`

**Output:** a summary, then per-call detail with links to the recording, scored **out of 5** across
criteria. Work the lowest scores. A real example from the transcript — the seller said *"I've owned
the property for 48 years, I'm getting too old to take care of it"* and the rep said **"uh-huh" and
moved on**, missing the motivation entirely. `[01:27:10]`

**Setup:** it can log into SmrtPhone itself via a **Playwright automation** Ty built (SmrtPhone has
no API), pull the calls, and run on a **scheduled task** — his output lands in Slack for Rami to
review. `[01:31:05]`

**💡 The token-saving tip (Phil, confirmed by Ty):** don't transcribe with Claude. `[01:20:00]`
> Run the audio through **Gemini Flash** instead — *"one of the best audio transcription models in
> the world,"* at about **$0.002 per minute**, and faster. Ty: *"You're on the right track, because
> I literally use Gemini."*

**Coaching rhythm:** daily 30-minute huddle in a perfect world; **weekly best-call + worst-call** is
the realistic minimum. *"You don't just want to be like, this is bad, this is bad. Give praise where
praise is deserved."* `[01:28:46]`

Ty also stores calls over time to show progress — *"here's your first call, here's your 30th, look
how far you've come."* On day one, *"sounding like a human and not reading a script"* was scoring
zero straight across for the new hires. `[01:31:52]`

> *"Historically, sales management is something very few companies ever get to, because it's an
> expensive hire. This democratizes that."* And for solo operators: upload your own calls and
> self-coach.

---

## 7. Comping workflow `[01:38:10]`

**Draw the boundary yourself.** This is the step Ty stresses hardest:
1. Put the address into Google Maps.
2. `Win + Shift + S` to screenshot.
3. **Hand-draw a polygon** around the area comps may come from.
4. Upload that image alongside the address.

> *"It doesn't have to be perfect. The main thing is I don't want it to pull in comps over here —
> this pocket is very, very different from that area."*

Rules he applies: **don't cross interstates, don't cross railroad lines**, and watch for clusters of
**apartment buildings**, which drag down surrounding single-family values.

**Output** — a full Excel workbook:
- Executive summary, final ARV with **low / mid / high**, and a **confidence level**
- Subject property detail
- Each comp with **distance**, **condition pulled from the listing photos and description**, sale price
- **Adjustments** per comp (e.g. +$10K because the subject is larger)
- Market phase — buyer's / seller's / balanced

> *"These are appraising frameworks. The problem is when investors try to do this, they don't know
> what to anchor to from an adjustments perspective."* **Ty was an appraiser before all this** and
> built his own training plus textbooks into the skill — *"that's a really good way to build out
> skills, by the way."* `[01:43:35]`

**Non-disclosure states are handled** — the skill detects the state and switches to an
available-data workflow. Phil, in a non-disclosure state: *"I'd say it's somewhere between 95%+
accurate."* `[01:44:23]`

⚠️ **Read the output, don't just take the number.** Ty's live example had **no bed count** anywhere —
not in the county auditor, not in SiftMap — so Claude made assumptions and flagged its own confidence
as *low-to-moderate*. He caught it only by reading. `[01:41:15]`

---

## 8. Rehab estimator `[01:56:22]`

**Photos change everything.** Without them Claude assumes, and assumptions are where hallucinations
come from. With photos, the whole run takes **5–10 minutes**.

For virtual investors: **Investor Boots** — nationwide boots-on-the-ground, **$75–100** for an
inspection with a full photo set. A 20-page photo PDF or a Drive/Dropbox folder works. `[01:37:21]`

**Output includes:**
- Cost comparison of **full rehab vs. wholetail**
- Estimates by phase — demo/cleanup, paint, flooring, kitchen, baths…
- **Material specs down to the SKU.** Ty gave it API access to his Home Depot and Amazon accounts, so
  it prices real SKUs: *"interior paint for a 2,100 sq ft house with 4 rooms — $6,195 all in,"* and
  a materials tab naming *"Sherwin-Williams SuperPaint or equivalent, flat/eggshell."*
- **Per-room condition / rehab action / notes**, read from the photos — *"these are original 1960s
  cabinets, very dated, not salvageable for the flip"*
- A checklist you hand straight to the GC or subs, plus a budget tracker

> *"If you've tried to build a rehab estimate and a scope of work before — this used to take me hours,
> and I was still wrong on a lot of it."*

**Calibrate it to your actual costs** `[01:48:21]`
> *"I'm uploading a scope of work and an estimate I got from my contractor. Take these real numbers
> and adjust all of the rehab cost estimations accordingly."*
Run 2–3 real contractor SOWs through it and *"it will be near perfect after that."* Your subs will
also like you for it, because you can hand them the output.

**Use it as a dispo negotiating document.** When a buyer lowballs, send the report:
*"this is the most defendable way to prove them wrong."* `[01:59:25]`

**And it removes emotional bias** — from closers on commission and from owners who want the deal:
*"the price is this. It removes that whole 'well, maybe it's worth this.'"* `[02:01:45]`

---

## 9. The two-scenario analysis (worked example) `[01:50:43]`

Ty's actual prompt, on a rough property on a couple of acres, sight unseen:

> *"Can you run the comping skill and portions of the rehab skill that you feel are necessary to do a
> complex estimation of value for two separate scenarios — one where we do a teardown and two new
> builds side by side, and the other where we buy and do a full gut, and see what the ARV would be.
> This property is going to be in rough shape, but we haven't seen it and we don't have photos."*

What came back:
- New-construction comps for the area over 12 months, plus active spec pricing from builders like D.R. Horton
- Demolition and hard construction costs
- Comps split into **bucket A (unrenovated / dated / as-is)** and **bucket B (renovated)**
- Full gut ≈ **$133,000** with a **15% contingency** (Ty notes he'd normally use 5–10%; the unknowns
  justified more here)
- New build path: two homes at ~$310K each = ~$620K, netting ~$123K **before** land acquisition
- **Recommendation: do the full renovation, offer $95–115K** against a $135K asking price

> *"If you tried to do all that by hand it would take you the whole day."*

And the point behind it: *"Investors, especially folks starting out, spend the vast majority of their
time figuring out what to offer instead of the highest-leverage revenue-generating tasks — making
offers and closing deals."*

---

## 10. Odds and ends

- **Plugins are effectively dead.** *"I don't use a lot of the plugins anymore. Just upload the
  skills, it'll do the same thing."* A plugin was only ever a bundle of skills; asking Claude to use
  two skills together achieves the same result. `[00:12:51]`
- **Fixing a SiftStack output that's wrong** — the iterative loop Ty uses verbatim: `[00:17:37]`
  > *"I found an error where the property addresses seem slightly inaccurate versus what you scraped
  > from the county auditor. Go back, verify the issue, fix it, run it again, and it should look like
  > X. **If it doesn't, run this in a loop until it's fully correct.** Once done, let me know and I'll
  > check it again. And when we've verified it all, **update the claude.md file and all the memory
  > files so we don't make the same mistake twice.**"*
  >
  > *"It would be like correcting an employee that was making a mistake."*
- **Test SiftStack uploads with 5 records**, delete them, repeat, until the process is right — don't
  pollute your account with test data. `[00:23:09]`
- **SiftStack build time: 2–5 full days**, ~40 hours. *"You're basically replicating what a software
  engineer would do."* `[00:11:10]`
- **Curative title needs cash.** *"It's hard to do without cash, because you have to buy out the
  interest, even if it's a couple thousand bucks."* Said to a brand-new investor with minimal
  capital. `[00:08:41]`
- **Nail one niche.** *"If I ask you how you'd take someone through the probate process, you should
  be able to rattle that off, because you'll have to do it on the fly with a seller — and train your
  team on it."* `[00:10:20]`
- The senior-homeowner + vacant + free-and-clear + absentee stack came up again as *"that dream
  stack… I would highly recommend everyone consider senior homeowners and vacant. That seems to be
  where a lot of our deals are coming from right now."* `[01:08:35]`
