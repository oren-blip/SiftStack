# Day 5 — Scaling & Operations (2026-07-17)

Distilled from [day-5-2026-07-17.md](../transcripts/day-5-2026-07-17.md) (2h 13m).
**Named speakers** — attribution reliable. Ty Garrett hosts; no Tyler Austin on this one.

The lightest day. Three tools (audit, KPI engine, hiring skill) plus the money and staffing model.

---

## 1. Why Ty won't sell you an agency — or be one `[00:04:00]`

Asked why DataSift doesn't just build county scrapers for everyone:

> *"The big reason first-to-market does well is the cost is very low to you, because you're pulling it
> in yourself. If we went in and just did that for you, it would remove that advantage."*

Same logic on hiring out:

> *"An agency says 'we'll do cold calling, $1,500 a month.' More than likely they're at a 50% gross
> margin — they're hiring someone for $750. You could just hire someone for $1,500 directly, train
> them, invest in them, and the returns will be far outsized over a long period of time."*

---

## 2. The audit — allocating resources `[00:34:51]`

> *"One of the hardest parts, not only about this business but all business, is the appropriate
> allocation of resources."*

You pick your blueprint (Day 1 §12) and monthly spend, enter expenses, then self-rate across
**marketing → sales → operations → KPIs**, in that order. 1 = not doing it at all, 5 = doing it at
the highest possible level. Output is a scorecard plus a prioritized low/medium/high action list.

**Work the categories left to right.** `[00:34:51]`
> *"It blows my mind how many people hire salespeople when they don't have enough leads coming in and
> haven't nailed the marketing side. They're just going to sit around and do nothing, you're going to
> panic, and you're going to hemorrhage money because you fixed the problems in the wrong order."*

On KPIs being last: *"KPIs are a little romanticized. People overthink them. At the end of the day we
just have to do the work every single day and hit the core goals — the 150 dials, X mailers."*

One audit question he singled out — *do you have a process to reach out to homeowners who ignored
previous campaigns?* (no numbers / all bad numbers / exhausted / return mail / vacant / not
interested / never reached):
> *"Most people do not have a process for it, and it's probably the equivalent of missing out on
> **30–50% of all transactions**."*

Cadence: monthly when starting out, quarterly once established. Export the results into Claude and
let it cross-reference the guides.

---

## 3. The money model `[00:34:51]`

**Use a fully-loaded cost per acquisition.** Roll prospector salary + DataSift + skip tracing +
deep-prospecting spend (Enformion etc.) into one "tools and marketing" bucket, divide by deals.
> *"Some people like to do this by just their raw marketing dollars out the door. I just think that's
> a lower-quality way to do it."*

Keep team salaries and true overhead (rent, utilities, insurance, QuickBooks) in separate buckets.

Ty's reference costs:

| Line | Monthly |
|---|---|
| Prospector — Egypt / Philippines | ~$750 |
| Prospector — Latin America | $1,000–1,250 |
| DataSift | ~$300 (business plan is where most start) |
| Direct mail | ~$500 to start |
| Bulk dialer (ReadyMode / SmartDialer) | ~$250 |
| Bulk SMS (Smarter Contact) | ~$800/mo, **billed quarterly** (~$2,400 up front) |
| **Trestle** | **~$200 per prospector** |
| SmrtPhone subscription + minutes | ~$250–300 |
| → **Budget ~$500/person for click-to-dial all-in** | |

⚠️ *"Watch that SmrtPhone bill — there's a thousand ways you can get charged and die by a thousand
cuts."* (storage and add-ons you don't need)

**Runway: 3–6 months of whatever your number is.** Ty's own is ~$8K/mo, so $24–48K reserve.

Why — **cash conversion cycle**: start marketing → contract at ~30–45 days → another 30–60 days to
close. Wholesale returns fast; take it down to flip and add 3–5 months.

> *"I loathe debt. The more debt you have for the longer period of time, the more risk you incur. If
> you can't sustain this for 3–6 months, please do not take out credit lines."*

Ty bootstrapped his own start by driving Uber alongside a W-2 and funneling that into the business.

---

## 4. KPI engine — metrics, benchmarks, and using them `[00:53:09]`

The **KPI Engine skill** sets up browser automations into every source of truth (SmrtPhone,
DataSift, Google Sheets), standardizes, and merges. Ty pipes the output into **Slack**.

**Track these, for prospecting:**
dials · answered · conversations >60s · conversations >120s · **correct numbers** · not-interested
generated · leads · appointments (= offers) · texts sent · unique records worked.

**The benchmark that matters most:** `[01:11:32]`
> **Answer rate below 50% means either a skip-trace problem or a phone-spam problem.**
> Ty's team runs **60–70%**, usually ~70%. If a single number's answer rate hits ~30%, it's almost
> certainly spam-flagged — replace it.

**What Trestle did to the correct-number rate:** `[01:08:04]`
> **2025: one correct number per 32 dials. Now: one per 10–15 dials.**
> *"We have to do 50% less work to hit the same KPIs."*

**Why correct numbers are as valuable as leads:**
Every **50–100 correct numbers** on an efficient list yields at least one transaction over 12 months.
The logic chains straight off doors per deal — if AI 90–100 is 22.6 doors per deal, then ~23 of the
correct numbers you're tracking will transact in six months. **The not-interested campaign is how
you're there when they do.**

**Don't just collect KPIs — make Claude act on them.** `[01:00:39]`
Ty's own example: contact rate was low, so he had Claude build a report and diagnose it. Claude's
first two hypotheses (wrong queue, refresh skip trace) were checkable; the real answer turned out to
be **he was dialing the wrong list**.
> *"KPIs are cool, but if you don't actually do anything with the actions it's kind of useless.
> Traditionally we'd read them and go 'this seems off' — based off vibes. This is empirical."*

Another use: ask for **correlations across your leads**. On a coaching call he found a client's leads
skewed to very low equity and very low typical gross profit, so they pulled those lists out entirely.

Note: the KPI skill doesn't measure connection rate — pair it with the **Caller Reputation Monitor**,
which checks per-number answer rates in SmrtPhone. `[01:17:40]`

Also mentioned: senior homeowners currently have a notably **high contact rate**. `[01:14:11]`

---

## 5. Hiring — the full workflow `[01:18:16]`

Cost: **$135 total for two hires.** (An agency headhunter is ~$3,000 per hire — only worth it for
C-level.)

**The funnel:**
1. **Post in 5–10 Facebook groups** for the target country/role. Expect ~100 responses from 5 groups,
   ~200 from 10. Format: **job title → pay → description**, with the email call-to-action further
   down. *"People are very money motivated — they want to see the price before they dive in."*
2. **Indeed, posted in the local country.** A US-based post will not reach someone in Mexico. Ty was
   told you can't post one job across multiple countries; **Micah Redden contradicted this live** —
   his account does it under one login/billing, he just can't duplicate a job across countries. Worth
   pushing support on.
   **Pay for the premium post — ~$10/day.** Ty's budget was $8/day in Colombia.
3. **Claude screens the applicants** against a rubric built by hand-reviewing ~50 candidates and
   feeding back corrections. Scores /10 on: English/accent level, real estate experience, cold
   calling or sales experience, plus three screening questions. Ty's three were: comfortable as a
   native-level English speaker? years of sales experience? **comfortable making 150+ click-to-dials
   per day?**
4. **Ask for a Loom video.** The exact wording matters:
   > ✅ *"Send a Loom video **to validate your identity and your resume**."*
   > ❌ Never *"so I can check your accent"* — *"you will offend them, and it screams that you're an
   > agency trying to bulk hire."*
5. **Watch ~10 Looms → pick ~5 → interview.** Use **two interviewers** — *"sometimes you have bad
   days and you just don't see talent in front of you."*
6. **Paid trial only for roles you can actually test** (design, video, admin). Not for callers — the
   system takes too long to learn.

Claude also **writes and sends the candidate messages** by logging into Indeed.

> *"This keeps it very objective"* — the same argument he makes for AI-scoring your own sales calls
> and comps.

### What a great hire looks like `[01:40:04]`
**Adriana** — raised in Atlanta, now in Colombia, 15–20 years of customer service. Scored **9.5**.
(The one 10 simply didn't reply fast enough.)
- **$1,100/month base + 2.5% of closed gross profit** she sources. A $10K assignment = $250.
- **~172 dials/day** average.
- First three days: training only, *"don't even look at SmrtPhone."*
- Within ~2.5 weeks she was taking leads all the way to a set appointment.

**Career path is the retention hack:**
> *"A lot of the time you're pouring this much training into people and they sign up for roles that
> have no career growth. Letting them see the path to closer makes retention better, and they perform
> way better."*
DataSift has ~30 employees and **one person has quit in seven years**.

**Door knockers** (Ty hasn't hired any, but knows the market): **$2–3K base + 10% commission.**
$3K if you're in California. *"The odds of getting someone full-commission are pretty low — just
think about it logically. Would you want to do that?"* `[01:44:34]`

**For admin/data-manager hires, screen for internet speed.** *"If they have slow internet, Claude is
going to be a disaster for them."* `[01:44:00]`

---

## 6. SOPs and onboarding `[01:56:55]`

Record a Loom (or use Fireflies/Lindy/Zoom's own transcript), then run it through the
**playbook-creator skill** → a fully mapped written process attached to the video.

> *"This does really, really well for Claude as well. When you make thorough SOPs, it can use them to
> create skills and automations on your behalf. So it's good for staff and good for Claude."*

Some operators run **200+ SOPs that Claude references** as its knowledge base.

**The reverse-onboarding trick** (from a friend of Ty's, he hadn't tried it yet but loved it): `[02:02:21]`
> Ask the new hire to record a Loom **explaining the process back to you**. Feed that to Claude and
> have it check comprehension against your SOPs and give coaching feedback.
> *"It's very hard to fabricate that they don't understand it — you can tell if they're just reading
> versus actually explaining it."* Better than a written test.

⚠️ **Transcribing and watching video burns a lot of Claude usage.** A student blew through his $100
plan doing exactly this to the challenge recordings; Ty offered to run the transcriptions himself.
`[00:33:30]` `[02:01:26]`

**Screenshots:** every screenshot in the Day 2 niche sequential guide — *including the blurs* — was
produced by Claude's Fable 5 model. *"Doing this manually is what an engineer, designer and
copywriter would have done for a week. I just QA'd it."*

---

## 7. Compliance, spam, and phone numbers

**DNC** — *"I'm not an attorney, consult yours."* `[00:20:33]`
- They **do not scrub DNC.** If someone asks to be removed, they remove them.
- They **do suppress litigation lists** — people linked to lawsuits — via Trestle inside the Phone
  Validator skill. **Ty recommends turning this on.**
- **~60% of all numbers are on the DNC minimum.**
- *"Businesses cost money, they all have risks. We're willing to deal with it if it comes to that."*

**Spam remediation isn't worth it.** `[01:13:01]`
There are three places to dispute a spam flag (it's in the Caller Reputation skill), but:
> *"It usually takes 2 to 4 weeks to remediate a number completely, and the odds it comes back spam
> are pretty high. **We just kill the number and move on.**"*

---

## 8. Infrastructure odds and ends

- **Apify** for running SiftStack automations off your own machine — Ty's daily foreclosure pull runs
  there. Cheaper/simpler than a raw VPS, and the SiftStack repo is built to accommodate it. Start on
  your own computer first. `[00:31:07]`
- **Websites:** don't pay for Carrot. Have Claude Code build one from scratch and host on **Netlify**
  (free). *"It's actually easier for Claude to build a website from scratch than to use editors like
  Carrot."* You still need **Zapier (~$19/mo)** to fire inbound leads into Sift. `[01:54:10]`
- **Lead source attribution** is done with tags + Zapier; inbound addresses get enriched on arrival
  the same as any other record. `[01:48:01]`
- **Firecrawl** — a fancier scraping infrastructure Ty uses but doesn't teach, because the free tier
  runs out fast. `[02:04:47]`
- **Migrating Claude accounts** (personal → Teams/Enterprise): ask Claude to *"create a handover doc
  that pulls in all the relevant information from all the memory files for my entire account"* before
  you move. Works for migrating off ChatGPT/Gemini too. `[00:29:00]`
- **Careful how you phrase scraping requests.** *"If you say 'find a way around this,' that probably
  goes against Claude's terms. Just ask 'using these tools, can you pull out this data.'"* `[02:04:17]`

---

## 9. New model teased: D4D (driving for dollars) `[02:08:02]`

Scores the **Google Street View image** of a property. Built by scoring the image at time of sale
for every investor transaction and back-testing which visual factors predicted it.

> **Across 10 factors, the two biggest indicators are a bad roof and bad windows.**

A **D4D score of 90+ is roughly 10x the baseline** — about **23 doors per deal** in Ty's market,
comparable to AI 90–100. Shipping "this quarter" as of 2026-07-17.

On window materials: wood is the most distressed signal (older, and they rot); aluminum is a weaker
but real factor. Windows are expensive to replace, which is why they carry signal.

Also promised that week: **vacant historical data** backfilled into the county list framework, and
**three-distressor combinations** added by popular request (reversing his Day 1 position).

---

## 10. Scattered answers worth keeping

- **Probate Finder skill has only a 25–50% hit rate.** *"Pretty unreliable."* If a decedent's
  decision-maker lives out of state, Claude struggles. **Use obituary data instead** — every parcel
  is already linked to a deceased record. `[00:10:24]`
- **Estate sales are too late.** *"The more hands in the cookie jar, the harder it is to get done.
  By the time it's through probate and at estate sale, there are too many people influencing the
  decision makers. That's why obituary data is powerful — you're very early, you can establish
  credibility and walk them through the probate process."* `[00:13:09]`
- **Relationship strategies do work but need credibility.** Two DataSift board members run entirely
  free strategies — nursing homes, lunch-and-learns, probate attorneys — but they've done ~2,000
  flips and buy with their own cash. `[00:14:42]`
- **Notice of default = lis pendens.** Notice of foreclosure comes *after* the default and is the
  public/legal notification. `[02:06:49]`
- **Red circle on a phone number = disconnected**, not DNC. Mark it dead, don't delete it. `[00:09:11]`
- **Making a skill from scratch:** do the work in one long session, then *"can you please make this a
  skill and a repeatable process."* It reviews the whole thread including your corrections — which
  is why it works. Ty's favourite variant: record a Loom of yourself doing the process, hand Claude
  the video plus transcript. **Edit an existing skill rather than starting fresh** where one exists. `[01:28:41]`
- Ty updates the published skills roughly **every 2 months**. `[01:21:10]`
