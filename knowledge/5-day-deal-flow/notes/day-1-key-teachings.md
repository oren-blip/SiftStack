# Day 1 — Market Research & Data Strategy (2026-07-13)

Distilled from [day-1-2026-07-13.md](../transcripts/day-1-2026-07-13.md) (3h 18m).
**Named speakers** — attribution is reliable. Ty Garrett hosts; Tyler Austin (co-founder) and Phil
Loesch (power user) contribute throughout.

This is the foundation day: the mental models everything else sits on.

---

## 1. Who's teaching, and why it should be believed

DataSift has three owners — **Ty Garrett** (marketing/data, acting CMO), **Tyler Austin** (sales),
and **Rami** (behind the scenes). DataFlik (Ty + Rami) merged with REI Sift (Tyler) in 2025 to
become DataSift; you'll still hear both legacy names. `[00:39:12]`

Ty and Tyler's own real estate businesses do about **$3M/year in revenue**, run explicitly as R&D
for what gets taught. ~5,300 people in the community; 115 on this call. Cohorts run monthly.

⚠️ **Recordings are sunset each cohort** — the Challenge Hub only holds the most recent. Download
anything you want to keep. `[00:48:16]` (This library is exactly that hedge — and Ty endorses the
approach: *"download all the recordings, transcribe those, put all the guides in one place, and then
ask Claude how to do something, and it will respond just as well as me and Tyler."* `[02:17:15]`)

Realistic timeline: *"If you do everything step by step by step, it'll take you like 90 days to get
everything set all the way up."* `[00:38:31]`

---

## 2. Pendulum Theory — the philosophical anchor `[00:48:35]`

Every marketing channel cycles. A YouTuber or educator says something works, everyone piles on,
saturation kills it, and the pendulum swings. What worked in 2018 ≠ 2021 ≠ 2023.

> *"Everything I'm trying to teach throughout this challenge is designed to defend against that
> pendulum swinging away from something that you have gone all in on."*

**PPC/PPL are the case study.** You bid against everyone else on "sell my house fast [city]." When
the channel gets hot, costs climb until you're just burning money. You control none of it.

Outbound data-first is the antidote because the metrics hold: you learn how many dials produce how
many correct numbers, how many not-interesteds, how many leads — and *that stays stable for years*.
People have run first-to-market / niche sequential / deep prospecting since 2019 and it still works.

Cost-per-contract numbers from the room, which frame the whole week:
- **Abe** — $10,500 per contract last quarter, driven by PPL/PPC. `[00:17:38]`
- **Phil** — **under $1,000**, doing exactly this system. `[01:06:47]`
- **Hunter** — FTM only (lis pendens + probate), **1–2 contracts/week**, lead manager on a $3K/mo
  salary. Ty estimates well under $2,000/contract. `[00:30:18]`

---

## 3. Doors Per Deal — introduced here

**Definition:** list size ÷ investor transactions over 6 months. **Lower is better.**

Knox County worked examples: `[00:48:35]`

| List | Size | Deals (6mo) | Doors/deal |
|---|---|---|---|
| High equity (alone) | 68,886 | 193 | **356.9** |
| Absentee + low income | 1,779 | 51 | **34.9** |
| Bad credit + low income | — | — | **~55** |
| AI score 95+ | — | — | **21.7** |
| **First to market** | — | — | **50–75** |

**The uncomfortable finding: first-to-market is 50–75 doors per deal — NOT as efficient as the best
SiftMap combinations.** They believed otherwise for years and only proved it once they had API
access. It does *not* mean stop doing FTM (see §4).

Also on the sheet: **typical gross profit** per list. In zip 37921 the baseline is $105K, but
bad-credit-out-of-state runs **negative** (investors buying at or over market — likely creative
deals), while **notice of default is $153K** — the most distressed people produce the biggest spreads. `[00:48:35]`

Mechanics:
- **Two-list combos only.** Three-way combos create 1,000+ permutations, hit diminishing returns, and
  are unmanageable in the UI. `[01:35:14]`
- Overlap is expected — a record may carry 3–4 distressors. The combo just requires that **two be
  true**. (Tyler) `[01:36:42]`
- Tier labels on the sheet: **50 doors per deal or higher = "volume"**, below that = "strong." `[01:34:35]`

---

## 4. The marketing funnel — why you run FTM *and* SiftMap `[01:31:19]`

This is the model that makes the whole week cohere. Built from **500+ transactions** across Ty's and
Tyler's businesses.

| Funnel stage | Seller psychology | Lists | Sales cycle | Saturation |
|---|---|---|---|---|
| **Top** | Unaware there's even a problem | FTM obituary, pre-probate, probate | **4–7 months** | ~Zero |
| **Middle** | Aware of some options | Senior homeowner, vacant, absentee stacks | Faster | Low |
| **Bottom** | Must make a decision now | Foreclosure, notice of default, auction 30 days out | Fastest | **Maxed out** |

- **Top of funnel builds the pipeline.** An obituary hits and the family isn't even thinking about
  the property yet. Nobody is calling them.
- **Bottom of funnel keeps the lights on** — but everyone else is calling them too.
- **Match touch quality to saturation.** Low-cost touches (call, text) work fine on unsaturated FTM
  data. Saturated foreclosures need **high-quality touches** — door knock, handwritten mail. `[00:48:35]`

Ty's foreclosure packet gets a **hot lead roughly 1 in 8–9 doors**: manila envelope, homeowner name
and property address, the notice inside for their own reference, and a **handwritten note** on the
outside. They knock when the **auction is ~45 days out**. `[01:29:36]` `[01:35:46]`

### The 85% claim `[01:20:04]`
> *"SiftMap distressors + AI data + our driving-for-dollars AI model covers **85% of all investor
> transactions nationally**. So when everyone's like 'I need to do PPL' — no, you don't."*

Inbound comes *after* you've maximized this, not instead of it.

---

## 5. First to market — where the data actually lives `[01:54:49]`

Only three places:
1. **Online portal**
2. **In-person at the courthouse terminal** — Ty's probate data came this way; someone physically goes
3. **Public notice sites / newspapers** — Ty's foreclosures (tnpublicnotice.com)

Details worth knowing:
- Knox County requires **two newspaper public notices** to foreclose. Notices are unstandardized free
  text — the address lands in a different spot every time, which is why naive scraping fails.
- **Newspaper → notice site delay is about one day.** `[02:24:27]`
- Notice sites are effectively free (~$97/yr for saved searches).
- **Provider delay varies wildly by county**: Ty's Knox ~15 days, Tyler ~4–5 days, LA County same
  day. That delay is the entire original reason FTM works. `[00:48:35]`
- DataSift pays **$80–90K/month** for raw list data across all 3,200 counties.

> *"Do NOT try to pull all of this first-to-market data at once your first time. You will end up not
> doing it — you're gonna fall off the wagon. Pick one thing: lis pendens or auction, probate, tax
> sale, or tax delinquency. One niche, one county."* `[02:17:49]`

### Being "first to market" with provider data — the trick `[01:37:39]`
Save a SiftMap filter for your best doors-per-deal combination and **turn auto-add ON**.

Every record that newly enters that combination has *just* hit the providers — so nobody has
marketed to them yet. That makes SiftMap data behave like FTM data.

> *"This is the way. I'm going to say it nice and slow. This is the way you can be first to market
> with provider data."*

It only works if you already know the right combinations, which is what doors per deal gives you.

---

## 6. Two filter mechanics that matter more than they sound

**Sold suppression.** `[01:45:31]`
Build a per-county "recently sold" filter covering the last 3 years, auto-add on, which flips status
to Sold so those records are never marketed again.

> *"When you scale, you start obliterating money on mailers for people who already transacted. Your
> callers get through 50 records a day and 5 of them were sold. It's terrible, and most people don't
> even consider it… This is a game of 100 golden BBs. There is no one silver bullet."*

**Keep unknown equity.** `[01:37:39]`
Most people filter equity ≥30% — which silently drops every property with no equity data, and in
non-disclosure states that's the majority. Ty's approach: **explicitly suppress low equity and
negative equity, and keep unknown.** Same intent, far bigger usable list.

---

## 7. Obituary vs probate — the stat that reframes everything `[03:00:23]`

> **Of the obituary records they've tracked over ~6 months, only ~30% ever filed probate.
> *"You're basically missing 70% of the market by not hitting up the obituary data."***

Why: probate doesn't just happen. A family member has to understand the process and go file at the
county. Many never do. And **until probate is filed, nothing triggers anyone to market to it.**

Consequences Ty acted on:
- He has **paused first-to-market probate entirely** in favor of SiftMap obituary data. `[02:17:49]`
- Obituary data is *"first-to-market data quality from SiftMap"* — it lands one week after the
  obituary filing, with all the other distressors attached. Requires the **Expert plan**. `[02:53:38]`
- Asked directly whether to prioritize obituary or FTM probate: **obituary**, because saturation is
  far lower, the conversations are easier, and the spreads are bigger. `[03:03:57]`
- Minimum **3-month window** before outreach. Mail reads *"To the family of [Owner Name]."* `[02:58:16]`
- Obituary gets its **own marketing pipeline**, separate from everything else — *"if we just prospect
  to someone who's deceased, we're never going to reach them. It makes no sense otherwise."* `[03:02:34]`

---

## 8. Curative title — Ty's pick for the next big strategy `[00:23:59]`

Deceased owner(s) on title, ownership gray. You either get every heir to sign over, **buy out their
individual interests**, or force the sale.

Interest buyouts commonly run **$5–15K a piece** — sometimes far less.

**Faiz's deal, live on the call:** tax-delinquent list, property held in a trust, two heirs both out
of state. **$500 each.** All in for about **$1,000**, sold on the MLS, *"close to six figures."* `[00:24:52]`

Why it works is not the legal mechanics — it's that **saturation is near zero**. Nobody is talking to
a distant relative who doesn't care about the property. `[03:03:57]`

Alejandro (community member) has a 2-hour training on this posted publicly.

---

## 9. Market Finder — picking or excluding neighborhoods `[02:34:00]`

**How "investor transaction" is defined** (this is the number under everything, including doors per deal):
1. Track every transaction.
2. Find entities/individuals who bought **2+ properties in a 6-month window**.
3. Connect their entities by **uncovering the signing member**, sticky-matching mailing and property
   addresses.
4. Suppress government entities, mortgage companies, and other junk.

Result is a registry of real buyers; every purchase by one of them counts as an investor transaction.

**The star ratings catch traps.** One Knox neighborhood ranked top-15 by investor transaction volume
but scored **one star** — all 11 transactions were corporate teardowns and the median sale price was
**$4.2M**. Raw volume would have sent you into a luxury market with near-zero deal odds.

**Two valid strategies:**
- **Pick the top pockets and hammer them** — Phil rotates neighborhoods every couple of days.
- **Go county-wide and suppress the bad ones** — Ty, with 3 prospectors blanketing the county.

Ty applies suppression in the **records marketing preset, not in SiftMap** — because that way it also
filters his first-to-market data, which doesn't come from SiftMap. `[03:17:02]`

---

## 10. Claude setup (the Day 1 baseline) `[01:54:49]`

- **Pro plan** is enough for most people; Ty's team is on Max.
- Use the **desktop app**, not the browser.
- Settings: **Cowork on**, **Max effort**, grant folder access, and turn on **skip all approvals** —
  *"I don't want to babysit and approve every single thing."*
- **Model: Opus 4.8.** Ty calls it the most cost-effective and best overall at recording time.
  *"You can use Fable 5, but you will obliterate your usage really fast, and most people on this call
  should not need anything close to that level."* (By Day 3 he's on Fable 5 in Claude Code with RTK.)
- **WhisperFlow** for voice dictation — worth it when writing long prompts.

**A skill is a packaged workflow for one specific task.** Two are assigned on Day 1:
- **First-to-Market County Data skill** — finds where your county's data actually lives. Output: ~26
  data sources per county with list type, office, address, phone, portal URL, difficulty, verified
  y/n, and refresh cadence. *"You can't just Google 'foreclosure county data Knox County' — you will
  not find what you're looking for, I promise."*
- **Sift Market Research skill** — logs into Market Finder and produces the full zip/neighborhood
  star-rated report described in §9.

---

## 11. Upload behavior worth knowing

**Address normalization** (Tyler): Sift runs USPS normalization *plus* their own nationwide process,
so `123 Main St` and `123 Main Street NE` resolve to one unique record. You don't need to
pre-normalize scraped county addresses. `[02:08:32]`

**Turn off swap-owners on enrichment** if your contact is the executor — otherwise enrichment
overwrites your PR with the property owner of record. `[02:51:19]`

FTM uploads get enriched automatically on import (distressors, property details, neighborhood), as
long as you provide the core address fields. `[02:49:47]`

---

## 12. The four blueprints `[03:06:55]`

Ty asks people to identify their blueprint, because it changes the advice.

| | Who | What to do |
|---|---|---|
| **A — Launchpad** | ~$500/mo marketing. Starting out, rebooting after a failure, or a "burn student" from bad education | **First to market.** Slower, but the most tried-and-true path off the ground — unless you go bottom-of-funnel and door knock foreclosures |
| **B — Optimizer** | More money than time; W-2 job, transitioning out | **Hardest one to pull off.** Pick the least-resistance channel (mail). *"Thinking you can just hire out all the people and not put in the work is a fugazi."* Expect a 6–9am shift plus an evening shift |
| **C — Specialist** | Chasing 6–10 huge deals a year; curative title | **Deep prospecting.** Target death event + financial distress. Small lists — a vacant out-of-state foreclosure might be 50 properties total |
| **D — Scale Up** | Building for consistency and volume | **Everything, don't skip steps.** FTM *plus* all the top doors-per-deal SiftMap lists, scaled incrementally. **"Do not do inbound unless you have a lot of money"** — that's how people end up at $10–15K per deal |

---

## 13. Plan selection guide `[02:53:38]`

| Plan | What it unlocks |
|---|---|
| **Professional** (~$150/mo) | 8 marketing flows. Fine if you're starting out or FTM-only. Vacant alone works |
| **Business** | **Unlimited marketing flows.** The right pick if you're pulling from the county yourself |
| **Expert** | **Obituary data** + all the niche distressor lists + unlimited skip tracing. *"By far the best if you can afford it"* |
| **AI** ($1,250/mo first county, $500 each additional) | AI scores. If you're spending **>$5K/mo on marketing, just go AI** |

The $97 challenge fee is credited back to your account — existing users can ask support for it too.
