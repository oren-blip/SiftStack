# Day 2 — Niche Sequential Marketing (2026-07-14)

Distilled from [day-2-2026-07-14.md](../transcripts/day-2-2026-07-14.md) (3h 54m).
Timestamps link back to the exact spot in the transcript — grep the transcript for `[HH:MM:SS]`.

Ty's framing for the day: *"Today is all about building out all of the sequential marketing flows.
This is quite different from the approach we've used in the past."* `[00:03:45]`

---

## 1. The strategic shift: bulk is dead

> *"I'm quintupling down on niche. We've scrapped bulk altogether. We're just not doing it anymore."* `[00:10:35]`

Bulk presets remain in his account **only for demo/education**. Everything real now runs through the
niche sequential flow — including SiftMap data that used to be treated as bulk.

**Why:** he used the API to find properties they had marketed to that transacted *without them ever
making contact*. On AI 90–100 in Knox County the doors-per-deal is 22.6 across a 2,300-record list —
they were closing 3–5 and missing ~95% of the capturable market share. `[00:12:49]`

Contact now takes **3–4 attempts per record**. `[00:11:00]`
Lead volume and contact rates are dropping industry-wide, but **lead quality is going up** — the
people who still respond are more distressed. `[00:12:25]`

> *"The harder something is to do, the fewer people will actually do it. That's exactly why these
> processes work so well."* `[00:57:00]`

---

## 2. Doors Per Deal (the county list framework)

The tool Ty published for the challenge. Ranks every available list in your county.

| Concept | Meaning |
|---|---|
| **Doors Per Deal** | How many single-family doors on that list per one investor transaction. Lower = better. |
| **Lift vs baseline** | County baseline DPD ÷ list DPD. **Use this number, not the priority label.** Notice of Default at 20x = twenty times more effective than blind county-wide marketing. `[00:19:51]` |
| **Priority 1/2/3** | Blends efficiency *and* capturable market share. A tiny hyper-efficient list lands in Priority 2/3 because you'd exhaust it in two days. `[00:18:13]` |
| **"Verify supply"** (P3) | List is so small (e.g. 49 records) the ratio isn't statistically trustworthy — pull it in SiftMap and confirm the volume is real. `[01:38:55]` |
| **Typical gross profit** | Property value − average investor purchase price. **Check this before committing to a list.** Notice of Default ≈ $153K gross vs. bad-credit-out-of-state ≈ **−$5K**. Negative means that list sells at market and is inherently less profitable. `[00:22:02]` |
| **Institutional share** | >15% is getting high; 20%+ = Opendoor-style market. Harris County TX is 39.2%. `[00:30:07]` |

- Property value shown is a **Zestimate-style as-is value, NOT ARV**. A $200K value is usually
  $225–250K ARV after full renovation. `[00:22:02]`
- Built on ~12 months of data across 3,200 markets. **Refresh every 6 months**, not more. `[01:00:00]`
- Coverage differs wildly county to county. A list missing here but present elsewhere = a coverage
  gap, and **that gap is exactly what first-to-market should backfill**. `[00:28:11]`

### AI scores
- ~1,800 data points per household, including credit-type signals that can't be exposed as filters
  because targeting on them directly would be discriminatory (same reason Meta won't let you target
  low-income housing but its algorithm still finds them). `[00:15:35]`
- **The 90–100 band is not automatically best** — sometimes 80–90 is more efficient. The framework
  tells you which. `[00:43:02]`
- **Don't buy AI data if you don't need it.** In one Michigan county the plain distressor lists beat
  AI 90–100 outright. `[00:38:42]`
- AI data matters most where distress-list coverage is sparse (wealthier states — MA, NY — have
  thinner distress coverage because residents are more financially stable). `[00:15:35]`

### Where to start
FTM takes ~20–30 days to stand up. SiftMap data takes ~2 days.
**Start with SiftMap for cash flow, build FTM in parallel.** `[00:26:23]`
No SiftMap budget? Professional plan ($150/mo) + the **Vacant** list alone works. `[01:31:31]`

### Focus
> *"You can just focus on one county and do all this and expand outward and do way more than one deal
> per month. It's very sexy to think about doing a bunch of different areas, but you probably don't
> need to."* `[01:49:57]`

> *"If you hit all of these combinations together, you're going to cover 85% of all transactions."* `[02:38:15]`

---

## 3. Team structure (the replacement ladder)

Hiring order, cheapest-leverage first:

1. **Administrative VA** — $500–700/mo, Philippines. Marketing flows, deep prospecting, mail, KPIs,
   reports, closing docs, TC work. Used to take 3–5 people; now one person + Claude. `[00:43:31]`
2. **Prospector** — cold-calls records to get a hand-raise.
3. **Lead manager** — owns the pipeline of hand-raises, screens motivation.
4. **Closer** — presents solutions: cash → downsell to novation → downsell to listing.
5. **Sales manager / Operations manager.**

- **The owner should stay in the closer/acquisitions seat as long as possible.** Highest-leverage,
  most expensive to replace, hardest to train. `[00:43:31]`
- Ty is **collapsing 2–4 into one role** — prospector who grows into lead manager who grows into
  closer. A new hire got a contract in her first week of calling. Reason: it's very hard to get
  someone back on the phone across a handoff. `[00:50:12]`
- **Latin America (Colombia)** for sales — cultural proximity, sarcasm and social cues land.
  ~$750/mo Egypt, ~$1,000 LatAm, $1,000–1,500 Mexico. Best hire: US-raised, moved back to Colombia. `[00:50:12]`
- If you don't want a team, fine — **someone still has to do every one of these jobs.**

> *"The wholesaling sector is a marketing and sales game. Building a portfolio and managing flips is
> an inconsequential skillset in comparison."* `[00:43:31]`

---

## 4. What "sequential marketing" actually means

> **Cheapest marketing touch → most expensive marketing touch, tracking every action at the property
> and individual level.** `[00:57:00]`

The failure it fixes: you can't say how many times 123 Main St has been called, texted, mailed, or
knocked. Most people buy a list, ship it to an agency or a bulk texter, and track nothing — so they
never learn what it actually takes to get a result.

The conveyor belt:

```
skip trace → skip/no numbers → ready to call → call attempt 1 → 2 → 3
                    ↓                                            ↓
             direct mail campaign              ┌─── deep prospecting (no numbers left)
             (nobody else can reach            ├─── rehash (numbers left, never contacted)
              these people either)              └─── not-interested campaign (correct number verified)
```

**Niche vs bulk — the actual difference:** niche uses **click-to-dial** (SmrtPhone Chrome extension);
bulk uses a **multi-line dialer** (ReadyMode, Kixie, CallTools). That's it. `[00:57:00]`

Why not multi-line: dialing 3 lines at once means when two people answer, one gets hung up on.
> *"For every 10 people on this list, that is a transaction. Why would you ever want to multi-line
> dial them? What if you actually reached the person and you hung up on them?"* `[01:46:25]`

DataSift has no phone system and never will. It integrates; SmrtPhone is the recommendation. `[00:57:00]`

### Organize by TAGS, not lists
- `Priority 1` → hottest, `Priority 2` → strong, `FTM` → pulled directly from the county,
  `Bulk Stacked` → anything going to an agency/multi-line/bulk mail. `[00:57:00]`
- When saving a SiftMap filter: **turn ON auto-add**, **do NOT replace owners**, and
  **do NOT add to lists** — pulling into the records page populates lists automatically. Only set the tag. `[01:05:49]`
- An empty preset folder means the criteria match zero properties, or you never hit **Save**. `[01:17:01]`
- The buy box lives inside the preset: value range, SFR only, AI band, **not listed on MLS**,
  exclude recently sold, and suppress the neighborhoods/ZIPs you don't want. `[00:57:00]` `[01:55:55]`
- `Free and clear` is not its own list — it's the **100% equity** filter. `[01:38:14]`
- `Other lien` = liens where the county didn't standardize the lien type. `[01:37:25]`
- Notice of default ≈ notice of foreclosure; don't overthink the distinction. Final judgment is
  anchored to the mortgage. `[00:42:24]` `[01:39:39]`

---

## 5. The call process (the exact cadence)

> *"This is one of those times where it's like, yes, it has to be this. I've tested it an absurd
> amount, and just trust me."* `[00:57:00]`

**4 full attempts on every phone number of every property.** Each attempt = **call + voicemail + text**
on each number.

Per number, set a disposition every time: `dead` (skull), `no answer`, or `correct` + a status
(e.g. *not interested*). Be loose about "correct" — if the voicemail greeting names the owner, mark
it correct. `[01:16:00]`

When every number on a record is done, change **call attempts 0 → +1**. That single field is what
moves the record to the next stage of the conveyor. `[02:02:55]`

### A prospector's day, in order `[02:31:00]` `[02:45:49]`
1. **Not-interested campaign** (best contact rate 8–9am, and the number is already verified)
2. **Rehash** (monthly ritual, not daily)
3. **Call attempt 3** → **2** → **1** → **ready to call**

Always oldest-first so you never dial the same person twice in one day. `Shift + →` advances to the
next record. Never dial a number more than 4 times — but **never delete bad numbers** either.
`[02:06:09]` `[03:08:35]`

---

## 6. Scripts

**Standard opener — curiosity, not intent.** `[01:59:08]`
> *"Evan?" … "Hey, I was just calling to see if you had any plans for 115 Lunar Way."*

Never lead with "are you interested in selling." The opener is a fork: keeping it / renting it /
selling it. Then pivot into the **4 Pillars of Motivation**: timeline, condition, reason for selling,
asking price.

Asking price is the least reliable pillar — *"once we're in person, that price comes down real fast."*
If they're on a genuinely motivated list, treat them as motivated regardless of the number they say.

**Voicemail:** *"Hey Evan, this is Ty. Just give me a call back whenever you get a chance."*
**Do not mention the property address in the voicemail.**

**Follow-up text (mirrors the opener):**
> *"Hey, it's Adriana. Just left you a voicemail seeing if you had any plans for the property. No
> pressure at all, just let me know one way or the other."*

**Foreclosure script — the only place you name the distress, and you do it softly:** `[02:06:51]` `[03:39:22]`
> *"Hey David, my name's Ty. I was just calling to see if you even knew that Knox County had filed
> your property for auction on July 16th. Do you have any plans for that, or is there any way we can
> help with that?"*

Most owners know they're in foreclosure but **don't realize the auction is that close**. The call
also signals you're not a random dialer. Same reason for personalized door-knock packets.

**Stop dialing foreclosures 3 days before auction** (Ty's team can still close with cash inside that
window). Most people should stop a week or more out. `[02:10:29]`

**Not-interested re-approach:** *"Hey, I was just calling to see if you still don't have any interest
in selling, or if anything's changed."* Keep it simple. `[02:50:21]`

---

## 7. The three exits after 4 attempts `[02:33:41]`

| Exit | Trigger | Cadence |
|---|---|---|
| **Deep prospecting** | No numbers at all, or every number dead | Day 3 topic |
| **Rehash** | 3+ attempts, numbers still callable, never made contact | Every 30 days (10 days for foreclosures). Do it as a monthly ritual — 1st of the month — not daily `[03:53:00]` |
| **Not interested** | Verified *correct* number + status "not interested" | 30–45 days for FTM foreclosure/probate; 45–90 for SiftMap data. **Run daily.** |

Motivation shifts. A foreclosure seller who tells you to get lost 60 days out is a different person
30 days out with the auction unsolved — **that's why tracking the correct number matters so much**.

> *"Roughly every 75 to 100 correct-number not-interested you get ends up becoming a deal within 12
> months, at a minimum."* — and they log ~10–15 of those per day. `[02:44:38]`

Tighten cadences from evidence: when you lose a deal, check when you last touched them vs. when they
converted, and shorten accordingly. Cadence varies by market and by law (Georgia foreclosure ≠ Florida
foreclosure). `[02:12:31]`

---

## 8. Real KPIs — one prospector, one day `[02:41:35]`

| Metric | Value |
|---|---|
| Records touched | 79 |
| Dials | 234 |
| Answered | 146 (**62.4% answer rate**) |
| Conversations > 60s | 10 |
| Correct numbers | 10 |
| Not interested | 10 |
| Talk time | 1h 29m |
| **Leads** | **3** |

Targets: **150–200 dials/day per person**, ~3–4 numbers per record, **2–5 leads/day**. `[01:47:20]`

**The math checks out against doors-per-deal:** 79 records ÷ 3 leads ≈ 26, against a published DPD of
22.6 for AI 90–100 in Knox County. `[02:48:12]`

Three prospectors, ~2 weeks into the new process, and nowhere near through AI 90–100 alone.
> *"It takes longer, but we squeeze more out of it than we would through other means."* `[02:49:24]`

---

## 9. Trestle phone scoring — "the biggest lever of the day" `[02:50:45]`

Trestle scores each phone number 0–100 on **actual send/receive activity** for calls and texts.
~1.5¢ per number, ~$200/mo per prospector. No affiliation — Ty just rates the tool.

Tiers (from the **Phone Validator** skill):

| Score | Tag |
|---|---|
| 81–100 | Dial First |
| 61–80 | Dial Second |
| 41–60 | Dial Third |
| 21–40 | Dial Fourth |
| 0–20 | Drop |

**Only dial First + Second.** Same lead / correct-number / not-interested output from ~400 dials
instead of ~1,000. It also protects your caller ID from spam flags.
Phil, in the room: *"Every single record, every single time. Trestle, Trestle, Trestle. And we only
call 1 and 2. Some people do 3, but we found no results."* `[03:08:20]`

**Order matters: skip trace in ALL sources first, THEN Trestle.** `[03:07:37]`
For FTM data Ty skips in three places — DataSift + Tracerfy + Informium — then scores everything:
*"you go from like 15 numbers to 3 or 4. It's insane."* Multi-source skip tracing is **not** worth it
for SiftMap data — too costly for the return. `[01:19:24]`

The skip-trace provider's own "last seen active" rating is not comparable — that's just the last
bureau report date. `[02:56:00]`
Landlines: don't text them; Trestle drops most of them anyway. `[03:36:15]`

**Workflow:** records page → select ~100 (not 2,500 — cost) → Manage → Export → download CSV →
Claude with the Phone Validator skill + Trestle API key → output CSV → back into DataSift via
**Update data → Tagging phones by phone numbers** (Miscellaneous tab). `[02:56:00]`

---

## 10. Caller Reputation Monitor (free) `[03:02:07]`

Free (IPQS free plan — *"don't buy any of their upsell garbage"*). Claude logs into your dialer,
pulls each caller's numbers, checks health, and tracks answer rate. Below Ty's empirical threshold it
auto-flags the number so you stop burning marketing effort on a spam-labeled line.

**Rotation: switch to the next number about every 25 dials.** That alone keeps them out of the spam box.

Phil's cheaper alternative, untested by Ty at the time: each morning and evening, call the prospecting
number from a real phone, stay connected 15 minutes, and let the *prospecting* number hang up.
Result claimed: **one spam number in 6 months, only 2 numbers per caller.** `[03:06:04]`

Ty's verdict on paid alternatives: Call Reputation ID costs thousands and isn't worth it.

---

## 11. Text Touch Builder `[03:18:23]`

Built from Ty's Obsidian vault of texting patterns that worked across the 5,000+ DataSift community.
Generates **4 touches, uniquely worded per record**, so carriers can't fingerprint the message.

The universal 4-touch structure: **identity check → did it go through → are you going to consider
selling → breakup text.**

- Send the text, then call **10–20 minutes later**. Batch 5–10 records of texts, then dial back through them. `[03:34:13]`
- On attempt 1, the *same* touch-1 text goes to every number on the record. Attempt 2 uses touch 2. `[03:36:17]`
- **Do not run this on obituary / deep-prospecting data** — you'd put a decedent's name in a text to
  their relatives. `[03:30:06]`
- Spin tokens in fixed positions do **not** work as well as genuine per-record variation. `[03:38:33]`
- Editing a skill: **Customize → ⋯ → Edit with Claude**. Dictate the change; it rewrites the skill. `[03:31:04]`

Why Phil texts before calling: it culls the junk early ("I'm not selling" saves you 4 wasted attempts),
surfaces useful corrections ("that's my mom's house"), and lifts answer rate because the number is
already familiar when it rings. *"It's on the margins. It just makes everything a little bit better."* `[03:21:03]`

⚠️ Ty tested plain copy-paste texting for one day — great connect rates — and **everything went to spam
on day 2**. Per-record uniqueness is the fix. `[03:22:21]`

---

## 12. Deceased / obituary data — the relatives rule

Tyler's segment. **The single most important stat of the day for probate work:** `[02:16:00]`

> **Skip-tracing only the decedent reaches 5–7% of cases (12% if lucky).
> Working the relatives puts them at 47–50% in the first week.**

> *"You need to make sure your team understands that they are calling relatives, not homeowners…
> Not all relatives are decision-makers, but all relatives have to make a decision."* `[02:17:05]`

**The failure mode that loses deals:** the caller reaches Sally, one of three heirs. Sally says no.
The team marks the lead dead and stops calling the other numbers — never reaching John or Joe. One of
*them* files probate later and somebody else gets the deal.

Process: skip trace in Sift → **SmartSkip** for immediate kin → add relatives' phone numbers and names
(plus last-4) to the message board → then other relationship-data sources. Tyler uses **DirectSkip**
(IDI data) over Forewarn; Forewarn is free if you're a licensed agent. The requirement is
**relationship data, not just the single person you're skip tracing.** `[02:16:00]`

Other notes:
- Obituary records **automatically flip to the probate list** once probate is filed — no need to
  exclude probate from an obituary pull. `[00:14:33]`
- **Deep prospect every obituary record.** Skip-trace numbers alone almost never reach them. `[02:11:33]`
- A student hit Claude refusing deep prospecting as "compiling a personal dossier on a private person."
  Ty rebuilt the skill to avoid that framing — covered on Day 3. `[01:58:18]`

---

## 13. Recently-sold loss audit `[02:12:31]` `[02:19:53]`

Enable auto-add of recently-sold data, then review it **every morning** in a lead-management filter.
Sales team does it in the morning huddle: open the auto-add filter → View Properties from last night →
process each record → swap the `recently sold` tag for a `reviewed` tag so it drops out of the filter.

On each lost deal, check in this order:
**zip code → neighborhood → AI score → distressors → timeline (via activity log + call recordings).**

Losses by frequency: **cold leads > not interested > dead leads > ghosting > warm/hot.**
Dead leads that lose are usually fine (didn't fit the buy box, or a hedge fund overpaid). **Losing a
cold, warm, or hot lead you made an offer on is the one that should make you angry.**

Tyler runs a **weekly QA agent** over the whole sales pipeline every Sunday/Monday. They lose ~2 leads
a day out of ~1,157 in the pipeline.

> *"Use this as a way to understand what happens within the market and what people are willing to buy.
> That's the best thing you can do."*

Also worth auditing: the **skip / no-numbers** segment. Ty found a record that sold that they never
marketed to at all, because it had no phone numbers and no mail campaign behind it. `[02:14:14]`

---

## 14. Direct mail hack `[00:57:00]`

The records you skip traced that came back with **zero phone numbers** are your best first mail
campaign. If you can't reach them by call, voicemail, or text, **neither can anyone else** — low
competition, and it's a much smaller list than mailing everything.

---

## 15. Door knocking (V1, Ty's own weekend test) `[03:41:00]`

Upload the FTM foreclosure CSV (his was 28 properties) to Claude and ask for a door-knocking route.
Output: an optimal Google Maps route from his home address, ordered by distance/time, **plus a
personalized message per property** using the auction date from a custom field.

The packet — ~$10 each, 15 doors ≈ $150:
- manila envelope, homeowner name + address
- handwritten Post-it on the outside (*"so they know we couldn't have mailed it — we actually
  dropped it off"*)
- personalized note inside

15 doors → 3 conversations. Non-answers get the packet in the door, then a follow-up text through the
Trestle-scored flow (which produced leads on its own).

Tracking: repurpose the **direct-mail-attempts** or **RVM** counter as your knock counter, so the
conveyor works the same way. 3–5 knocks typical; up to 7 for a high-leverage property before auction.

**Do not send traditional mail on foreclosures** — it won't arrive in time, and it must not look like
it came from a mail carrier or like a certified/served document. `[03:48:00]`

---

## 16. Cold email `[03:16:24]`

Not Ty's channel, but a friend sent 2,500 cold emails off DataSift data and got **3 deals**.
- **Instantly** is the platform (*"the DataSift of email"*). ~50 emails per inbox, similar domains, warm up gradually.
- Verify the list first — **Kickbox** (bulk, cost-effective) or **ZeroBounce** / Instantly's built-in
  verifier at ~half a cent per email.
- **3 bounces on one domain sends you to spam.** You often get more emails back from skip tracing than
  phone numbers, so cleaning matters more here.
- Treat it exactly like any other channel: data + channel + tracked down the same conveyor,
  cheapest touch first.

Facebook/Meta: Ty does **not** believe in lookalike audiences off your own data — let Meta's algorithm
target. Inbound is being tested; possibly a 2027 challenge. `[03:12:57]`

---

## 17. Platform notes (as of 2026-07-14)

- **DataSift API**: deal-room members ~1 week out, whole community ~6 weeks. Will let Claude build all
  presets programmatically instead of clicking 35 of them. `[01:40:22]` `[02:24:36]`
- **Auto-update on the records page** shipping that quarter: system lists, beds/baths, AI scores refresh
  monthly with an approve/deny **Updates** tab. **Last sold date will NOT auto-update** — too risky
  (arm's-length? sold to a relative? reset the record?). `[02:25:24]`
- Preset folder nesting: prefix names with `01`, `02` to sort. `[01:17:01]`
- 10DLC approval: Twilio was a 3-week disaster; SmrtPhone walks you through it. `[03:34:25]`
- Whisper / voice dictation is worth it when writing skill edits. `[03:31:12]`
