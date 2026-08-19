# Day 1 — Market Research & Data Strategy (2026-08-17, August cohort)

Distilled from [day-1-2026-08-17.md](../transcripts/day-1-2026-08-17.md) (3h 43m).
**Named speakers** — attribution is reliable. Ty Garrett hosts solo; **Tyler Austin never speaks**
(Ty says he "will be here somewhere on this call, maybe sometime today" but he doesn't appear).
Phil Loesch (power user, first-cohort OG, 11 months in, Kansas City) contributes throughout;
Mason (DataSift social media) appears briefly; Sam O'Neill (FTM case-study power user) speaks early.
The rest are attendees asking questions.

Next month is the **one-year anniversary — 12 challenges in a row, every month**. `[00:02:02]`
~89 people on the call (Nadine's count at open). Longest day to date: 4h 40m.

---

## 1. What changed since the July cohort

The big ones, in rough order of impact:

1. **The DataSift API shipped.** *"This will be the first time that we are rolling out our API,
   which is, like, a fancy way of saying, giving Claude full access to your account."* `[00:03:32]`
   Beta-gated to the **Deal Room** (private Slack, ~100 users, calls every ~2 weeks); requires
   **Business annual, Expert annual, or AI monthly**. Full public release *"end of September for the
   next challenge is the target"* (Ty also says "next month… or in October" earlier). `[00:30:44]`
   `[03:23:29]` Why gated: scale testing, plus abuse — someone scraped their Google Street View API
   off the records page, *"which costs us a shitload of money."* `[03:24:24]`
2. **Doors Per Deal is a rebuilt web tool, not the July spreadsheet.** *"This is a totally new
   version from the last cohort, where now it tells you the actual order to market in from the
   market share perspective, and tells you the unique property count when you add all these lists
   together."* `[00:50:15]` It now dedupes every record going down the line, shows cumulative market
   share, auto-pushes small-deal-size lists (low equity) to the bottom, and merged near-duplicate
   lists (notice of default ≡ final judgment — only one foreclosure type per market now). `[01:43:41]`
   `[01:44:48]` Some 3-list combos are now included (July taught two-list combos only), though Ty
   "kept it very simple" and left most out as redundant. `[01:27:20]`
3. **The Download Excel button now generates a per-county First to Market roadmap** — where every
   list physically lives at the county level (office, portal, process). This supersedes the July
   "First-to-Market County Data skill" homework as the primary FTM discovery path. `[00:52:28]` `[01:45:26]`
4. **Claude model advice changed:** July was "Opus 4.8, avoid Fable 5 or you'll obliterate usage."
   Now: *"For most of what we're doing here, you could just use the Opus 5 model. For, like, the
   very complex things, you can use Fable"* — his example being a comp run on a property plus an
   adjacent splittable lot with a new-build. `[00:11:28]` Troubleshooting ladder for a stubborn
   install: Sonic 5 → Opus 5 → Fable. `[02:30:52]`
5. **One-command skill install.** A repo link installs the whole **agent org chart: 74 agents,
   9 divisions, 22 Claude skills (20 skills + 2 plugins) on 1 install command** — replacing July's
   one-by-one downloads (~30 min across the week). Ty built the link *"like 2 hours ago."* `[02:01:37]`
   `[01:15:11]` Returning users: tell Claude to pull only what's new and not touch edited skills. `[02:39:41]`
6. **New workflows since July:** Deep Prospecting **version 5** `[02:33:10]`; an **obituary mail
   skill**; the **call reputation system**; **two-way SMS agents** ("an autonomous AI agent that
   replies to texts for you"); and an API-integrated preset manager / CRM operations component that
   *"one-shot"* builds all the record filter flows — *"this would have taken me, like, a week to set
   all this up before."* `[02:36:26]` `[02:37:44]`
7. **Obituary vs FTM probate stance softened.** July: Ty had paused FTM probate entirely for
   obituary data. Now he pulls **8 FTM lists — liens, tax delinquent, tax sale, foreclosure,
   probate, obituary, code violations, condemned properties** — *"more for KPIs for you guys than
   for myself, to be honest."* `[03:29:11]` `[03:40:20]` New obituary timing data replaces the flat
   3-month rule: estate/probate opens in months 1–3; they're split-testing marketing at 1 month vs
   3+ months and finding sales cycles start month 3 onward, *"with a ton of them being in that 1–2
   year range."* `[01:00:25]` (July's "only ~30% ever file probate" stat is not repeated.)
8. **AI-plan threshold lowered:** July said ">$5K/mo marketing, just go AI." Now: **$3,000–5,000/mo
   spend with 6 months of runway** is where it starts to make sense. `[01:36:49]`
9. **Raw data spend** quoted as **$90,000/month** (July: "$80–90K"). `[00:52:28]`
10. Smaller: Ty says he swapped **from Manus to Claude in January** `[02:28:40]`; DataSift made the
    **INC 5000** (~#3,000–3,100 fastest-growing US private companies); **305 documented case
    studies**; Rami is now described as "more on the sales side" (July: "behind the scenes");
    Claude Cowork "came out 6 months ago." `[00:11:28]` `[00:31:41]`

---

## 2. Doors Per Deal v2 — the framework the whole day sits on `[00:31:41]`

**Definition unchanged:** how many properties you must market to to get in front of one investor
transaction. New in v2 is the **baseline**: blindly marketing every single-family home in Knox
County = **166 doors per deal** (153,000 SFHs ÷ 927 investor transactions over 6 months). Everything
is measured as lift against that. The tool is powered by DataSift's sold-properties function and was
built with the new API. It standardizes on **single-family only** ("the numbers are pretty roughly
the same" across property types).

Per-list columns: doors per deal, **typical gross profit** (as-is value minus typical purchase
price — *not* ARV-based, and absent in non-disclosure states), and **institutional share** (>20% =
saturated iBuyer/institution territory; ~10% is normal). `[00:31:41]`

**The cumulative stack is the key mechanic.** Lists are ordered to capture the most market share for
the least records; each row's "total live doors" is the deduped cumulative count of all rows above
it. Ty's Knox Priority 1: notice of default (75) → probate (cum. 119) → free & clear + senior +
vacant (cum. 456) → AI score 95+ (cum. **1,457**) = **8.3% of all market transactions**:

> *"To get in front of 77 transactions, you only have to market to 1,457 people. That is an insane
> stat."* `[00:46:30]`

Live proof: two callers dedicated to exactly those lists → **4 contracts in the last 2 weeks**.
`[00:46:30]` Both contracts he deal-reviews from last week scored **above 95** on AI data. `[00:58:02]`

Worked extremes (Knox): **low equity is the 35th and last list — average deal size $4,000, 571
doors per deal** — vs senior + free & clear + vacant at **$169,000 average deal size**. The tool now
auto-suppresses small-deal-size lists to the bottom. `[01:41:31]` Nadine's Denver pull: notice of
default + senior = **2.9 doors per deal**; built live in SifMap it comes to 48 properties. `[02:58:13]`

**Universal performers right now: vacant and seniors.** `[01:41:31]` But lists are hyper-localized —
Ty has no estate-sale list in Knox; Denver has two senior combos in the top 5; judicial states have
12-month foreclosure cycles. Don't copy his order. `[01:40:15]`

Guidance: don't deviate from the printed order (*"the amount of engineering that went into creating
this is far past what everyone on this call will be able to do"*) `[01:05:26]`; most people only
need the ~1,457-level stack, not all 9,000 `[00:50:41]`; the AI row sits 4th not 1st because the
models maximize market share per record, not raw doors-per-deal `[01:03:45]`.

---

## 3. First to market — SifMap delay, the Excel roadmap, and auto-add

**The delay that makes FTM work:** notice of default and probate run **~20 days behind** in SifMap
vs pulling straight from the county (providers generally 20–30 days). Free & clear / senior / vacant
have **no delay** — they don't come from the county. `[00:52:28]` `[01:19:34]`

**Decision workflow** (repeated verbatim to several askers): *"Can I get it from the county? If yes,
and [SifMap says] small sample size, I'm going to pull it from the county, because it's saying that
SifMap has low coverage of it."* `[01:50:10]` Free & clear + pre-probate + senior flagged small?
*"Just do obituary data for that. It's the same thing."* `[01:49:42]` Lists you can't get at the
county (out-of-state + tired landlord combos, AI scores) — pull from SifMap regardless.

**Where FTM data lives** (unchanged trio, now with the Excel roadmap): online portals (easiest —
"up and running in a day"), in-person courthouse terminals, notice websites. Courthouse runners:
use a title company contact or **TaskRabbit, ~$100/week**; photos → Dropbox/Google Drive → transcribed
→ auto-fed into Sift. Tennessee specifics from the Excel: non-judicial state; **the first market
signal is the appointment of a substitute trustee recorded at the Register of Deeds — it hits the
ROD index before the newspaper ads**; tnpublicnotice.com + ForeclosureTennessee.com (centralized
after a 2025 state law). `[03:29:11]`

> *"The harder it is to get your data, the more money that you are going to make."* `[01:17:19]`

> *"There's really no excuse for you to not pull in first-to-market data anymore… you can automate,
> like, 99% of it."* `[01:03:07]` (Sam O'Neill: manual FTM took him 4–5 hours per county; with
> SiftStack it's ~30 minutes. `[00:29:08]`)

FTM volume expectation: **1–200 records/month per list** — negligible vs SifMap rungs, so just bring
it all in. Exception: demographic outliers (Tyler in Florida has ~3x Ty's probate volume). `[01:28:46]`

**Being first-to-market with provider data** (July's §5 trick, still core): save the doors-per-deal
combo as a SifMap preset with **Auto Add New Records ON** + a tag. The list dropdown shows each
property the day it entered the combination — market to those immediately. Ty's 35 presets were
**all auto-created via the API**; doing it by hand "was what you did for, like, that week." `[02:41:48]`
Building the presets/marketing flows via Claude *without* the API means browser-clicking — "500 plus
clicks," token-hungry and unstable. Do it manually or get the API. `[03:04:32]` `[03:07:00]`

**Sold suppression** still running: the "Knox Recently Sold" auto-add preset caught **40 properties
in one day**, all auto-removed from marketing flows. `[03:18:13]`

**Equity hack** (unchanged from July, re-taught to Daniel for reverse-mortgage filtering): never
filter equity ≥30% — **suppress low + negative equity and keep unknown**. It also catches most
reverse mortgages. `[03:10:39]`

---

## 4. Obituary data — the timing model matured `[01:00:25]`

Obituary is *"the soonest that someone can ever hit a list."* Filing → matched to a property owner;
estate/probate typically opens **months 1–3**. Ty and Tyler are split-testing outreach at **1 month**
vs **3+ months** post-obituary; sales cycles mostly start month 3 and on, many landing in the
**1–2 year** range. Marketing at month 3 — before probate even opens — makes you *"by far the first
ones to market to them."*

Ty's volume: **~60–75 obituary records/month**, and he now deep-prospects **every** obituary-flagged
property rather than pre-filtering to tax-delinquent overlaps (~$300/mo more, worth it vs whittling
75 down to 10). `[01:32:10]` For curative-title hunters: obituary + deep prospecting beats waiting
on stale county tax-delinquent files; for one-off delinquency amounts, have Claude look up each
property on the county tax assessor's public payment portal — most counties must expose one. `[01:32:10]`

Curative from the room: Tomek — bought for **$50,000**, cleared the liens, subdividing, expecting to
sell **over $400K**. `[01:36:00]`

---

## 5. AI data — when to jump `[01:36:49]`

- Threshold: **$3,000–5,000/mo marketing spend with 6 months of runway**. Ty spends $10–15K/mo,
  Tyler similar. Zach at $10–15K/mo: "You should be on the AI." Duy at $5K/mo but new to data:
  *"If you've never used data from a marketing perspective, don't start with AI. Go to the expert
  plan."* `[01:23:48]` Kashif at $500/mo: Professional at $150/mo + two FTM lists (tax + foreclosure),
  nothing else. `[01:10:38]`
- Why it earns its price: **Pender County, NC** — all-lists needs **5,000 records for 55%+ market
  share; AI data reaches the same share with 1,400 records** — *"cut your marketing budget by, like,
  70%."* `[01:55:52]` Knox equivalent: 11% share via ~2,400 all-list records vs 8.3% via 1,457 with AI.
- AI shines in small/rural counties where list coverage is thin — the models use credit and income
  data no provider list exposes, and *"predict it without needing it."* `[01:56:46]`
- The models predict who will hit distress lists **before** they land there — Phil's observed
  "redundancy" is the point; the residual ~600–700 AI-only records in Ty's 1,457 stack "you would
  have probably never reached any other way." `[00:52:28]`
- The trade: going AI-only means accepting **opportunity loss** — 40 sales in one day flowed through
  Knox records Ty never even called. `[03:18:13]` And it's a smaller list: if AI drops to 11th in
  your county (Faiz, Middlesex MA), you don't need it. `[01:57:50]`

---

## 6. Market analysis — suppress, don't shortlist `[02:01:37]`

Same skill as July (Sift Market Research → Market Finder), same doctrine, said twice for emphasis:
*"I want to suppress the areas either at the neighborhood or the zip code level that I do not want
to be in, as opposed to shortlisting."* Same Old City example: top-15 in raw investor transactions
(11), **1 star**, median sale price **$4.2M** — outlier-flagged luxury teardown pocket.

New concrete detail on his records setup: **41,000 records** in the account; the "Ready to Call"
preset (Priority 1 lists + neighborhood suppression + low/negative-equity suppression + single-family
+ **$100K–$700K buy box**) filters that to **112 records**. `[02:22:55]` Suppression lives in the
records filter presets so it also covers FTM data. Zip include/exclude lives under Advanced
Geography in SifMap. `[03:00:35]`

Skill quirk to expect: it may stop at 17 of 48 zips — tell it to finish, *"almost like you would
tell a VA."* `[02:01:37]`

---

## 7. Claude setup — the three levels `[02:19:30]`

New explicit framing: **Claude Chat** ("a glorified search engine") → **Claude Cowork** (creates
documents, acts on your behalf — everything taught today) → **Claude Code** (the big automations,
SiftStack, sustained FTM pulls; covered Day 3). Plans: free / $20 / $100 / $200 — start at **$20**,
most will creep to $100–200; Ty's on $200. `[00:11:28]`

- Skills install resistance is expected — Claude treats the repo as an untrusted internet link.
  Fixes: enable the permissions in the Day 1 settings guide; say it came from Ty (Phil trained his
  that way `[02:15:59]`); escalate model Sonic 5 → Opus 5 → Fable `[02:30:52]`; worst case, manual
  File → Download → Customize → Skills → Add per skill. `[02:16:09]`
- **API >> browser automation**: browser mode logs into Chrome and clicks like a human; the API is
  *"instantaneous… far less tokens, and the reliability is much higher."* Nearly every Sift feature
  is now API-callable. `[02:34:14]` Kristopher's MLS variant (non-disclosure comping): Phil — *"ask
  your MLS if they have an API… works way faster, uses less tokens."* `[01:13:42]`
- Long-term bet: *"I'm betting on Claude… I think they're probably the best platform in the world
  for this particular thing."* OpenAI "kind of got smoked by Claude in the last 6 months"; Codex
  migration is possible but painful. Ty uses **OpenRouter** when he needs other models. `[02:28:40]`
- Automation economics: John's SiftStack API bill of **$0.49/day** is fine — *"you never want to
  automate anything that costs more than the labor would be to produce it."* `[03:28:46]`

---

## 8. KPIs and money numbers dropped along the way

- **Marketing spend, defined:** software + physical ad dollars + salary of the marketing-focused
  person, ÷ deals = fully loaded cost per deal. **Ty: $1,300–1,800/contract.** Starting out expect
  **~$3,000–4,000**, dropping as not-interested/rehash campaigns mature. Cold caller pay: **$1,100/mo**. `[01:46:50]` `[01:48:12]`
- **Caller capacity: 200–250 records/week taken all the way through the marketing process** (Phil
  runs 250–300/wk; both agree 3–4 call attempts before connecting, 5 attempts to exhaust). `[00:50:41]` `[00:48:53]`
- **New-hire benchmark:** caller hired ~5 weeks ago — **~180 calls/day, just over 1,000 records
  worked, 3 contracts in her first month** (full detail promised Day 2). `[03:21:15]`
- **Not-interested campaigns produce 20–30% of ALL deal volume across the entire platform.**
  Recycle verified correct numbers every 45–90 days. Faiz: 2 contracts since last challenge off one
  call-through, before any rehash or mail. `[01:59:01]`
- Channel order for an account already doing call/VM/text: add **direct mail → email → door
  knocking**, then expand geography. Email is "the new thing" — being bolted into the next cohort. `[01:36:49]` `[02:00:44]`
- Saturated-market escape hatch: go to the **secondary market next door — ~80% less saturation**
  (Knox → Blount, ~10 legit buyers). Caveat: only if you can close/take deals down yourself;
  wholesale-only operators should stay in the primary MSA. `[01:08:30]` `[01:23:48]`

---

## 9. Plans and pricing said out loud

| Plan | Number heard | Notes |
|---|---|---|
| Professional | **$150/mo** | The $500/mo-budget answer: this + 1–2 FTM lists (+ vacant on SifMap) |
| Expert | **$499/mo** (Maria: "the $4.99 a month one") | Monthly Expert does NOT get the API yet |
| AI | $1,250/mo first county (transcribed as "$12.50 per month") | Built for scale; gets API on monthly |
| Deal Room / API | Business annual, Expert annual, or AI monthly | Full release target end of September |

$97 challenge fee credited back — existing users message support, new users use the signup code. `[00:11:28]`

---

## 10. Odds and ends worth keeping

- **Divorce** (Jalen's niche): not in Ty's FTM pulls — *"every time we've gotten a divorce
  opportunity, usually the judge wants it sold for the highest amount to split the proceeds…
  You could do novations on them."* `[03:20:26]`
- **Zombie** = a vacant foreclosure. `[01:51:10]`
- Texas 21-day notice-to-sale cycle = treat notice of default as the last-stage list and sprint;
  Ty does the same with his 30-day window. `[01:07:14]`
- High institutional share in a tiny county is usually one portfolio purchase skewing the number —
  don't overthink it (Pender: 346 investor transactions/6mo). `[01:55:35]`
- Day 2 teaser: two-way SMS automation flags "interested," stops the drip, routes to the
  prospecting team. `[03:25:41]`
- Transcripts of the sessions will be posted (Zoom's own transcription has been stuck since last
  month; Ty is running them through a transcription pipeline). `[03:22:41]`
- One market first, always: *"if you feel like you're inconsistent… it's probably because you bit
  off too much. That leads us to doing just one county."* `[02:22:04]`

---

## 11. Day 1 homework `[03:08:00]` `[03:42:13]`

1. Run Doors Per Deal for your county; pick **1–5 SifMap lists** and build them as saved presets
   with Auto Add + tag (Nadine's Denver walkthrough is the template `[02:58:13]`).
2. Hit **Download Excel** and pick **1–3 FTM niches** (start with probate, foreclosure, or tax);
   investigate the pull process from the First to Market tab.
3. Run the market analysis skill (Claude Cowork) to identify zips/neighborhoods to **suppress**
   tomorrow when the marketing flows get built.
4. Install the skill repo via the one-shot link; give Claude your Sift login (and API key if in the
   Deal Room). Don't market to anything yet — *"watch day 1 through 3 before you do anything."* `[01:05:59]`
