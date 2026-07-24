# Day 3 — Deep Prospecting (2026-07-15)

Distilled from [day-3-2026-07-15.md](../transcripts/day-3-2026-07-15.md) (2h 48m).
Timestamps link back into the transcript. **Speakers are real names on this day** — Ty Garrett,
Tyler Austin, Phil Loesch, and named students — so attribution here is reliable.

Ty's framing: *"Hopefully the lightest day in terms of content, and probably the most flashy, fun day
on top of it."* `[00:04:40]`

---

## 1. Correction from Day 2: the Vacant list was missing

Ty shipped the county list framework without **Vacant**, and calls it his own mistake. `[00:06:55]`

Cause: when a transaction happens, DataSift strips certain distressors so they don't leak into the
next version of the list — and vacancy got stripped with them. The caveat now shown in the tool:
*"the vacancy flag only survives the newest month of recorded sales."*

Why it matters:
- Knox County typical gross profit on **Vacant = $179,000** — higher than AI 90–100. `[00:06:55]`
- **Bolt Vacant onto any list and it cuts the list ~50%+, and what's left is nearly all real.**
  Knox worked example: 200,000 county-wide → AI score + SFR = **2,241** → + Vacant = **539**. `[00:10:41]`
- Over half of Ty's and Phil's last 10–12 contracts were **senior homeowner or vacant**. `[00:11:35]`

> *"If you bolt on vacant into anything, it will do well, I promise."*

Vacancy data comes **straight from USPS** — if USPS doesn't have it, DataSift doesn't. Some counties
have no vacant records at all, and that's usually rural coverage, not a bug. `[00:24:18]`

On the $150 professional plan, pulling Vacant alone (Knox: 1,602 records → ~1,000 after buy box and
sold suppression) and running the Day 2 sequential flow against it is *"as close to a guarantee of
traction as I could possibly give you."* `[00:06:55]`

**Framework updates shipped:** multi-county select (stacked, labeled by county) and Excel export. `[00:06:55]`

---

## 2. AI score details (mostly a pricing/decision guide)

- The AI score's technical name is the **off-market investor score**. Three models exist: off-market
  investor, on-market, and realtor. `[00:27:53]`
- Both models predict **90 days out**. `[01:55:07]`
- Pricing: **$1,250/mo for the first county, $500 per additional county**, bulk pricing on large ones.
  It costs DataSift ~**$90,000/month** to run the model. `[00:12:19]` `[01:52:06]`
- **Don't buy it if your county doesn't rank it highly.** Ty repeatedly talked people out of it —
  Jefferson County AL, one Michigan county — telling them to run notice of default + bad credit +
  obituary instead and save the money. `[01:17:31]`
- **The realtor model is more accurate than the investor model.** Only ~5–10% of US transactions go
  to investors, so there is ~9x more training data for "who will list with an agent." Knox realtor
  AI 95+: 2,100 records, **one listing per 1.7 properties**. Realtor data comes nationwide with the
  AI plan. `[01:52:06]` `[01:54:03]`
- Ty's tin-hat aside: things legally excluded from the models (HIPAA-type health events) are exactly
  what drives cash sales to investors — which is why high-intent **inbound/SEO** captures what the
  models can't. `[01:54:03]`
- Non-disclosure states (e.g. Missouri) show **no typical gross profit** because there's no sale
  data; the framework is deliberately more conservative there. Fall back to vacant, senior
  homeowner, and AI. `[00:22:43]`

---

## 3. What deep prospecting is

> *"You're trying to find the people that are very difficult to reach, or that you've not been able
> to reach through your other marketing efforts."* `[00:28:55]`

**The headline number:** `[00:28:55]`

> **Raw marketing to obituary data → 5–7% contact rate.
> Running deep prospecting → 50–70% contact rate. Roughly 10x.**

Two other under-worked entry points:

- **Return mail.** *"No one really does anything with their return mail. It's by far and wide one of
  the highest ROIs."* If mail bounced AND calls failed, something is going on — very often a
  deceased owner. `[00:28:55]`
- **Zero numbers across every skip-trace source** (see §6).

Ty's deep-prospecting filter preset stacks: obituary list present **+** 4+ call attempts exhausted
**+** return mail **+** vacant on *both* mailing and property address **+** no phone numbers left
**+** has equity. Obituary is the one list he makes a hard requirement. `[00:28:55]`

> *"What makes wholesaling really, really profitable is having the deep prospecting flow inside it,
> because these are the deals that are the largest ones… these are people that really just haven't
> been reached by anyone else, and when there's no saturation, you get way bigger spreads."* `[00:41:35]`

---

## 4. Obituary data — the mechanics

| Fact | Detail |
|---|---|
| **History depth** | Only back to **2026-01-01**. Anyone who died before that isn't in it. Stored month over month going forward. |
| **Source** | Public-record obituaries scraped, transformed, and anchored to a property owner. *"It is not perfect."* |
| **Delay** | Deliberate **1-week lag** into SiftMap (death on Jan 1 → appears Jan 8) so you're not first-to-market on someone who died that day. |
| **Calling sweet spot** | **3+ months** after the obituary. |
| **Mailing** | Tyler: start mailing **immediately**. Just understand it goes to the decedent's own mailing/property address, not the heirs. |
| **List transition** | Once probate is filed the record automatically flips from obituary to probate — no need to exclude probate from an obituary pull. |

**Tyler's play, and he calls it gold:** `[00:33:57]`

> *"In a year from now, in two years from now, you can filter by that obituary date on properties
> that had an obituary 16 months ago and still has not filed a probate. That's absolute gold."*

Why it works: if one person owns the property and dies with no one else on the deed, **the only
option is to find heirs**. The property can't sell without going through probate. So the estate that
never filed is a property that legally cannot transact until someone acts — and nobody is talking to
them.

> *"You're building intellectual property in your business that nobody else in your market has."* — Tyler

Ty and Tyler were about to start sending **exclusively handwritten mail** to obituary records:
*"to the family of [Name]…"* `[01:49:56]`

---

## 5. The four levels of deep prospecting `[00:41:35]`

| Level | What happens |
|---|---|
| **1 — Multi-source skip trace** | Every provider returns something different. **Three sources is the sweet spot.** |
| **2 — Verify the deed / ownership** | Read the actual deed at the register of deeds. Confirm whether probate ever happened. *"Oftentimes if you have to go past this point, there's almost always a deceased owner still on title with someone who's alive, or everyone on title is deceased."* |
| **3 — Confirm death, build the family tree** | Verify the person is deceased, map the heirs, identify **who the actual decision maker is**, then skip trace those heirs — again across all three sources. |
| **4 — Curative** | The messy end: some heirs want to sell, some don't, or ownership itself is gray. |

Historically this was 2–4 VAs producing **1–3 fully deep-prospected leads per person per day**.
Ty ran **25 properties simultaneously in about an hour** before the call. `[00:41:35]` `[01:06:14]`

---

## 6. Tyler's "no numbers anywhere" list — highest direct-mail ROI he has `[00:33:57]`

Skip trace across DataSift + SmartSkip + DirectSkip. The records that come back with **zero results
in all three** are the list.

Scale: of 100 properties processed, **10** had nothing anywhere.

Results he quoted:
- **137 postcards → 3 contracts → ~$70–90K.**
- A later ~150-postcard run produced an **$80K wholesale** — bought from a relative across the street
  from a property he'd mailed a year or two earlier; buyer demoed it and built two houses on the lot.
- He runs it about **every 6 months**.

> *"Opportunities are only opportunities if you put yourself in a position to actually capitalize on
> them."*

---

## 7. Deep Prospecting skill **v4** — what changed and what it costs

The big architectural change: **v4 replaced browser automation with APIs.** `[00:41:35]`

That's the fix for Claude refusing the work. Older versions had Claude logging into TruePeopleSearch
and similar, and *"Claude really does not like this from a privacy perspective."* (A student on Day 2
hit exactly this — Claude called it *"compiling a personal dossier on a private person."*) Going
through APIs is both permitted and far more stable.

**Tool stack:**

| Tool | Role | Cost |
|---|---|---|
| **Enformion** (Ty says "Informium") | Skip trace + **person search** | **$0.10** contact enrichment, **$0.10** person search — negotiated down from ~$0.35 list. **Not an affiliate link**; use the challenge link or you get list pricing. |
| **Tracerfy** | Second skip-trace source | — |
| **DataSift** | Third skip-trace source (unlimited on plan) | $97/mo |
| **Trestle** | Scores all resulting numbers | ~1.5¢/number |
| **Scrapfly** | Bypasses Cloudflare | free tier to test |
| **2Captcha** | CAPTCHA solving | — |

**Person search is the actual unlock:** feed it a name + DOB, get the parents back; search the
parents, get the siblings. That **programmatically builds the family tree** — which is what you
could not do before. `[01:03:00]`

**All-in cost: ~$0.50–0.75 per record.** `[01:06:34]`
Ty runs it on **every single obituary record**. `[01:07:11]`

**Ancestry and BeenVerified are dropped from the flow** — Enformion returns relatives and associates
programmatically, and Ancestry needs a headed browser, which breaks automation. `[01:32:00]`

Output: a research pack with the heir map, every phone number pre-tagged with its Trestle dial tier,
a property summary, and a suggested lead-with line — auto-posted into DataSift. `[01:05:09]`

Scrapfly + 2Captcha clear *"99.9%"* of sites. The known exception is **enterprise-grade Cloudflare**
(Fortune-500 tier). If both fail, you're not getting in. `[01:12:56]`

> *"If Claude still can't find these people, this is where you swap to the manual side — because if
> Claude can't find them, there's probably a really big deal hiding there somewhere."* `[00:57:02]`

---

## 8. Case study: the Daniel H. Williams foreclosure `[00:41:35]`

Ty's worked example, run end to end by the skill. Auction was ~2 weeks out (March 6); they could not
reach the owner.

What Claude did, in order:
1. Confirmed the property, owner, and that **taxes were paid**.
2. Flagged a discrepancy: the mailing address matched the property address (owner-occupied), and
   **Christine C. Williams appears as co-owner on tax records but is not on the 2016 deed of trust** —
   only Daniel is on title. *"This one block would take a person 30 minutes."*
3. Pulled the deeds from the register of deeds. Found the foreclosing debt was only **$25,000** —
   flagged that as odd, then correctly reasoned it was likely a **second lien or HELOC**.
4. Found the **prior $168,000 deed of trust** — the primary mortgage, granted to Daniel *and his wife*.
5. Totaled roughly **$247,000 of debt**. *"If this property is only worth $250K and they have $247K
   in debt, this is probably not even worth pursuing."*
6. Found his **obituary** — died 2025-07-20, about 8 months before the auction, which matches the
   foreclosure timeline in a non-judicial state. **The death explains the foreclosure**: payments
   stopped.
7. The obituary confirmed his wife Christine **predeceased him** — so both people on title are dead.
8. Built the family tree from the obituary: children, grandchildren, sisters, in-laws.
9. Identified the decision maker — son **Mitchell Williams, 71** — with address history and phones.

Ty then **hand-delivered a handwritten letter** to Mitchell's house. They called back. The family
saved the house so no deal, but: **they had no idea it was going to auction.**

> *"A lot of these people just would have called and mailed a person who was deceased, never gotten a
> call back, and called it a day."*

## Case study: Alexander Kong — $125–145K `[00:40:17]`

A driving-for-dollars record sitting for **2 years**: 10+ call attempts, direct mail, nothing.
Deep prospecting tracked down who the owner actually was, and found **a deed that wasn't legitimate**
— someone was trying to steal the house. They contacted the person who had sold it 10 years earlier,
put it under contract, and assigned it for **$125–145K, under 14 days from first contact**.

> *"How many people are actually going down this rabbit hole?"*

---

## 9. Volume, leads, and conversion

- **~500 records per month per caller** is Ty's planning number. `[00:26:11]`
- Faiz (student) got within a hair of a contract from **12 dials** — priority-1 stack of absentee +
  other liens + senior homeowner, 24 records. `[00:05:29]` `[00:26:49]`
- Ty's team at the time: **100–150 dials/day**, **2–3 leads/day per person**. `[02:15:29]`
- **Leads per contract: 10–15.** Phil independently reported "mid teens." Phil's first three weeks
  were 1-in-7 before it evened out. `[02:16:01]`
- Hiring: **one caller first**, then bolt on **mail** as the second channel before adding a second
  caller. *"There's going to be people who will never respond to a call or text, but a lot of people
  who would respond to mail"* — especially senior homeowners. `[01:48:49]`

---

## 10. Wiring it into DataSift

**Moving records into deep prospecting:** assign a user → set status to *deep prospecting* → add to a
**board**. Boards are how leads get managed once they're out of the marketing conveyor. `[02:06:36]`

**Automate the handoff with a sequence:** trigger on property tag *"no numbers left to call"* →
change property status to *deep prospecting*. `[02:08:52]`

**Sequences generally:** every account ships with **26 prebuilt sequences**. Ty says only one is
mandatory for everyone — the **sold-property cleanup** (tag `recently sold` → set status to Sold).
Tyler runs 50–60 sequences. `[00:13:52]`

**The sold-suppression filter is the biggest single productivity lift Ty names.** He's suppressing
**25,000** recently-sold records across his campaigns. `[02:32:22]`
> *"It's probably about 10% of all records, when you don't do this, are dead."*

**Tags, not lists.** Confirmed again: only tag on import — lists auto-populate, and auto-update is
coming to the records page. `[01:56:06]`

**Custom fields — the mistake everyone makes:** *Groups* are just categories (Miscellaneous,
Qualifying Questions, etc.). You add the actual field under **Fields**. For an auction date or
obituary date, set field type to **date picker**, then you can filter by fixed range / since / prior
to. `[02:27:59]` `[02:28:53]`

**Absentee out-of-state** is expressed as two filters: *Is owner absentee? **Yes*** + *Is in-state?
**No***. Ty had to ask his own team about this one. `[02:43:56]`

**Equity is an estimate, always.** Bulk mortgage data + estimated principal paydown + the valuation
model. *"You will not know the exact equity unless you take it to a title company."* `[02:19:32]`

**Corporate/institutional owners:** very hard to reach a real decision maker. Phil, on trying:
*"We tried that pretty hard too, and it resulted in squat."* `[02:40:27]`

---

## 11. SiftStack — Ty's Claude Code setup `[01:18:13]`

Three tiers of Claude, in Ty's words:
1. **Chat** — *"a glorified Google search."*
2. **Cowork** — controls your computer, executes tasks, produces files.
3. **Claude Code in VS Code** — *"anything you could possibly imagine from a creation perspective."*

**Ty no longer uses Claude Cowork at all.** Everything runs in VS Code, 5–10 jobs at once. `[01:26:05]` `[01:36:38]`

> *"Claude Code inside VS Code is where you have a lot less… I don't want to say guidelines, but you
> know how Claude denies you when you're trying to do something? That won't really happen."* `[01:26:52]`

This is also why 25 simultaneous deep-prospecting runs are possible and aren't on Cowork.

**Setup:** public repo at `github.com/DataSift-Ty-Personal/SiftStack`. Hand Claude the link and it
deploys everything and pulls in every challenge skill; Ty's pushes sync back to you. Budget **3–5
days** of dedicated time. `[01:29:14]`

⚠️ Matthew Larkin flagged live on the call that **someone had pushed a Nebraska merge request into
Ty's public repo** — maintain your own fork rather than depending on his. `[01:31:45]`

**Model and mode settings Ty recommends:** `[02:10:59]`
- Swap models with `/` → *Switch Model*. He alternates **Fable 5** (flagship) and **Opus 4.8**.
- Stay on **auto** — it plans before executing, then proceeds.
- Leave effort on **max**.
- Usage is weekly-reset; he deliberately runs his allocation down each week.
- **RTK ("Rust Token Killer")** — `github.com/rtk-ai/rtk`, open source. Ty claims it cuts usage
  ~**80%** and lets you stay on Fable 5.

Other SiftStack jobs he mentioned: scraping public notices (Scrapfly backend, screenshots, PDF
parsing, enrichment), deal analysis, uploading into DataSift, the caller-reputation system logging
into SmrtPhone, KPI reports, and **posting daily first-to-market notices into Slack** for the team. `[01:39:03]`

**Hiring for this:** *"I don't even think real estate's necessary — that's the easiest part. It's more
about familiarity with Claude, AI workflows, automation. An engineering-type mind."* ~$1,000/mo
Philippines, ~$1,500 Latin America. One person now covers what was a 2–3 person team a year ago. `[02:48:07]`

---

## 12. How to make your own skill `[02:00:18]`

Ty's live demo — the pattern is: do the task once, then ask for the skill.

> *"I want you to take this list of properties and sort through it and only find the distress lists
> or vexations that an actual real estate investor would want to market to — foreclosures, probate,
> tax-based delinquency, code violations. Process all the data in this list. And once you've gone
> through the entire process and I've verified it, prompt me and remind me to **create a skill that
> replicates this entire process**, so going forward we can just use that instead."*

He also shared a lightly-tested **commercial classifier** skill — resolves the ambiguity in county
"commercial" tags (self-storage vs medical office vs strip mall) and estimates multifamily unit
counts. Tested on ~5 properties; treat as beta. For commercial, chain it: classify → consolidate
addresses → use the deep prospecting skill to find the **signing member of the entity** → skip trace
that person via Enformion's business flow. `[02:03:05]`

---

## 13. Day 4 preview (per Ty)

Sales day: lead management, sequences, drip campaigns, **rehab cost estimating**, **full comping
workflows**, and an AI workflow that takes a call transcript + audio and **scores the rep on a
rubric** — opener quality, objections missed, closing. Ty: *"probably the most powerful in the entire
challenge."* `[02:48:41]`
