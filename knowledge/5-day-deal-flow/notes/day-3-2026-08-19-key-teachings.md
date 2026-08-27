# Day 3 — Deep Prospecting (2026-08-19, August cohort)

Distilled from [day-3-2026-08-19.md](../transcripts/day-3-2026-08-19.md) (2h 37m, 558 turns).
Compare against the July cohort: [day-3-key-teachings.md](day-3-key-teachings.md).
Speakers are real names, so attribution is reliable.

Ty's framing up front: this Day 3 is *"a little bit different in terms of how I've done Day 3 in the
past, because there's a lot of new workflows, and I'm kind of in the middle of transitioning a lot of
how I'm handling deep prospecting."* He is showing work-in-progress and says the dialed-in version
lands next cohort. `[00:05:04]` `[01:38:55]`

Cohort count: **11**. Deep Prospecting skill is at **version 5**. `[01:34:13]`

---

## 0. What changed since the July cohort

| Area | July (cohort ~10) | August (cohort 11) |
|---|---|---|
| **Skip-trace stack** | Enformion + Tracerfy + DataSift, ~$0.50–0.75/record | **DataSift + SmartSkip + DirectSkip**, **$0.25–0.45/record**. Enformion no longer named; Tracerfy being retired in favor of DirectSkip |
| **The big unlock** | Enformion person search (name+DOB → parents → siblings) | **SmartSkip at $0.15/hit returns the whole relative cluster in ONE call** — 41 associated people from a single hit |
| **Contact rate claim** | 5–7% → 50–70% | 5% → **60–70%** (same order of magnitude, tightened) |
| **Where it runs** | Local, Cowork or VS Code | **fly.io VPS at $5/mo**, 24-7 scheduled tasks, no computer on. Requires the API to be stable |
| **Gate** | none | **Most of the day's flagship workflows require the DataSift API** — Deal Room now, or public rollout end of September |
| **Model advice** | Fable 5 / Opus 4.8, effort max | **Opus 4.8 is sunset**; Fable for heavy work; **plan mode is the headline recommendation** |
| **New workflow** | — | **"Find the top 100 opportunities in the entire account"** — whole-account ranking |
| **New workflow** | — | **One-shot account build** — barren account → full preset/list/sequence infrastructure in ~1–2 hrs |
| **Mail to heirs** | Handwritten mail "about to start" | **Live this week** — 3–6 heirs mailed per record via OpenLetter, outside DataSift |
| **Probate approach** | Reach the PR | **Tyler's flip: deep prospect ALL heirs even when a PR exists** |
| **Curative** | Level 4 of the 4-level framework | Ty **doesn't do curative**; automating title research is a next-cohort project |

---

## 1. The API is the gate on most of today `[00:09:36]` `[02:30:36]`

Asked directly by Assaf Barak whether the texting agent needs the API:

> **Assaf:** *"No way to do it without the API?"*
> **Ty:** *"No. You have to think of how much — it's doing hundreds of queries. I mean, you can try
> it, but you will obliterate your usage on Claude if you try to get around it. So you can either
> join DealRoom, or you can wait until the end of September, when hopefully it's released to
> everyone."* `[00:09:53]`

Repeated four more times across the call `[01:30:04]` `[02:20:10]` `[02:14:46]` `[02:35:03]`.

**Access paths:** Business Annual, Expert Annual, or AI Monthly → message support → Deal Room Slack →
API link, access granted in ~1 hour. `[01:29:57]` `[02:17:08]`

**Why the staged rollout** (Ty, unprompted): there are **110 people in the Deal Room**. They're
measuring usage at 110, then 500, then 1,000, to size infrastructure. *"Imagine if 500 people did
that at the same time and we hadn't slowly scaled it up."* End of September is when they expect to
have the usage picture. `[02:30:49]` `[02:14:46]`

**His stated reason it can't be worked around is Claude token burn, not authentication** — he
estimates the one-shot account build would take Claude **1,000–2,000 UI clicks** to do manually
`[02:35:08]`. The documented escape hatch is export-and-hand-to-Claude: *"say we wanted to deep
prospect this 149 records, you can just go to manage and export that, and give that Excel file to
Claude."* `[02:30:23]` `[01:01:59]`

> ⚠️ **SiftStack note:** this framing assumes browser automation. Our `src/sms_agent` port makes
> direct HTTP calls to `apiv2.reisift.io/api/internal/` from Python — zero Claude tokens per CRM
> query — so the specific failure mode Ty describes doesn't apply. See the
> `two-way-sms-agent` memory.

---

## 2. What skip tracing actually is (the tiers) `[00:24:23]`

Ty's setup for the whole day, and he says most people don't understand it:

- **Unrestricted / governmental tier** — a warrant-level search goes to AT&T/Verizon/T-Mobile and
  gets *the* number. Not available to marketers.
- **Manual-lookup tier** — BeenVerified, Spokeo. Better than marketing-grade because you're looking
  up one person at a time. **Forewarn is by far the best in this category** but requires a licensed
  agent.
- **Marketing tier (DataSift et al.)** — ~**6,000 sources**. You feed first/last/DOB/mailing/property
  address; it returns everything ever associated with that person and **guesses the top ~5** to hand
  you. *"That guessing system is the big difference."*

Heavy regulatory stipulations are why the marketing tier is a guess and not an answer.

---

## 3. The skip-trace stack — and what it costs `[00:28:00]` `[00:33:23]`

**Three sources is still the sweet spot; past that is diminishing returns.**

| Provider | Role | Cost |
|---|---|---|
| **DataSift** | Source 1, on-plan | included |
| **SmartSkip** | **Source 2 — "the big unlock"** | **$0.15/hit** |
| **DirectSkip** | Source 3 | ~$0.10–0.15 (Ty unsure) |
| **Tracerfy** | being replaced by DirectSkip | ~$0.02/hit |
| **Trestle** | scores every resulting number | ~1.5¢ |

Links given as non-affiliate: `smartskip.io`, `get.directskip.com/easylists/`

**Full flow cost: $0.25–0.45 per record.** He repeats the number deliberately. `[00:34:11]`

**Where it's worth it — Ty's explicit ROI ruling** `[00:33:23]`:

| Data | 3x skip trace? |
|---|---|
| **First-to-market raw county data** | **Yes** — near-zero saturation, you're calling the day it hits the county |
| **Deep prospecting** | **Yes — a must-have** |
| **Priority 1 / SiftMap bulk (incl. AI score)** | **No** — DataSift + Trestle only. *"You'll spend a lot of money really fast"* |

On Tracerfy specifically: *"if you're on it, you can keep it… them and DirectSkip are kind of in that
same universe of quality. SmartSkip is the big unlock."* `[00:40:41]`

Phil pushed on justifying the cost; Ty's answer is that he and Tyler measure success as **getting a
correct number for an individual record**, and that DataSift + SmartSkip + Trestle already reaches
*"probably 90% of what you could feasibly reach."* `[00:37:54]`

On SmartSkip's price: *"I'm telling you, it's worth it. I think they could charge more."* `[00:38:15]`

---

## 4. The SmartSkip unlock, concretely `[01:23:41]` `[01:32:24]`

One 15-cent SmartSkip hit on decedent **Tomas** returned **41 associated individuals with their phone
numbers**. The deep prospecting flow then whittled those 41 down to **the 3 people who actually need
to be reached**.

That collapse — 41 → 3 — is what Ty calls *"what makes this crazy."* It's also the answer to
verifying heir ownership before mailing: the deed-chain research inside the flow does it.

**Re-skipping heirs is a real second pass** `[01:34:58]`: for decedent David Graham, the flow skip
traces the children + spouse **using the newly found mailing addresses** in DirectSkip, and you can
optionally run SmartSkip individually on each heir for numbers SmartSkip didn't surface on the
household hit. Nick confirmed from experience that this surfaces new numbers.

**Phone shortlisting solves the 30-number cap** `[01:27:38]`: the automation only writes back numbers
tagged **Dial First or Dial Second** and cleans the rest before upload. That's how a 41-person hit
doesn't blow past DataSift's per-record phone limit.

---

## 5. Three entry points into deep prospecting `[00:24:23]` `[00:30:00]`

1. **Obituary data** — the flagship. Skip tracing a deceased owner reaches nobody.
2. **No / bad phone numbers** — records where DataSift returned nothing. Ty's reasoning is sharp:
   *"if no numbers are coming back for them on the DataSift side, that means a lot of other people
   have skip-traced these individual records and also not reached them."* `[02:26:58]`
3. **Return mail** — *"such a good process."* A student got **6 deals from return mail in the first
   3 months** of implementing it.

**The return-mail mechanic:** take the physical stack to Office Depot or Staples, scan the whole pile
into one PDF (front and back), then have a VA or Claude set each record's status to **Return Mail**,
which feeds the deep prospecting pipeline. `[00:30:00]`

**The headline stat, restated:** raw outbound to an obituary record ≈ **5%** chance of reaching a
decision maker. Through the deep prospecting pipeline: **60–70%**. `[00:31:00]`

**Trigger mechanism: status, not tag.** *"We don't do a tag, we just change the status to deep
prospecting."* `[00:48:57]`

**Board columns Ty runs:** Call New Numbers → Call the Relatives → Check for Relatives → Research on
Socials. He is split-testing board-based vs. straight-in-records. `[00:49:12]`

---

## 6. NEW: "Find the top 100 opportunities in the entire account" `[00:54:51]`

The day's genuinely new workflow. Ty voice-commanded it live:

> *"I want you to take all of the lists that are in Priority 1, and also the obituary data, and you
> can also do a full scan of our account. And I want you to find the top 100 opportunities in the
> entire account using the system that's inside of SiftStack."*

Trigger phrase is just **"find the top X"** — it routes itself. `[01:05:01]`

It ranks every property address top-to-bottom, folding in SiftMap data, first-to-market data, the AI
models, and — critically — **months since date of death against the probate sales cycle**. DataSift
did a study on time-from-death to start-of-sale and **SiftStack is trained on it**. `[01:00:10]`

His #1 ranked property: vacant, absentee, not owner-occupied, built 1935, owner passed **4.9 months
ago**. `[00:57:00]`

Works with the API (writes tags back) or without (export 42K records → hand the file to Claude).
`[01:01:59]`

**Stacking advice for a foreclosure-only operator** (Nick): tell it *"these are all foreclosures,
don't even factor that in"* so it ranks on everything else. Ty: *"one of the biggest deals I've ever
done was a foreclosure obituary"* — if the owner is dead, reaching the heir beats knocking the house.
`[01:08:43]`

---

## 7. NEW: the one-shot account build `[01:38:55]`–`[01:56:33]`

Ty took a barren test account (he has ~8–9 SIFT accounts) and rebuilt it end to end — SiftMap presets,
lists from the Doors Per Deal framework, records filter presets, sequences — in **about 1–2 hours**
that morning, mostly unattended while he did other work. Recorded a 40-second Loom of before/after.

**The two settings he says make it work** `[01:40:34]`:
1. **Switch to Fable** (`/` → Switch Model). *"When you're doing tasks that are this advanced, I would
   always recommend to use Fable."*
2. **Plan mode** — Claude explores and presents a plan before editing anything. This is the single
   most-repeated tactical tip of the day.

> *"I will use plan mode on anything that I think will make me sad if it fucks it up."* `[01:58:18]`

Phil, unprompted: *"that plan mode hack is legit"* — he rebuilt in half the time and got twice the
product after learning it. `[01:56:09]`

**Chunk the work like an SOP** `[02:05:20]`: SiftMap presets → records filter presets → sold property
analysis → sequences → Trestle-score the hottest preset. *"How you would teach a person, or a VA, to
do something in the correct order from an SOP perspective is how I would think about having Claude
execute on your behalf."*

**Close every session the same way** `[01:52:07]`:

> *"Everything looks awesome, let's go ahead and update the CLAUDE.md memory files, that way we have
> note of all this, and if there are any gotchas throughout this entire process, please make sure to
> update all the necessary memory files so that we get better each time, and I'm going to start a new
> session."*

Reason: at 81% context used, *"the more context it has to read through and digest, that's what causes
higher usage and more hallucinations."* Update memory → close → new session. `[02:06:52]`

**What to build by hand FIRST** (asked by Dino, starting from scratch) `[02:22:48]`: one SiftMap
preset, one list, one records marketing preset, and **one sequence — specifically the sold property
sequence** — manually. *"Those are the hardest elements, probably, in the entire app."* Then hand the
rest to Claude, because now you can read the guides and tell whether Claude did it right.

---

## 8. Mailing the heirs `[01:23:41]` `[01:25:14]` `[01:28:08]`

Live as of this week. **Handwritten letters to every heir**, not just the PR.

- **3–6 heirs mailed per record** ("I haven't seen one that's even over 6")
- Sent through **OpenLetter directly**, NOT through DataSift — *"our system does not currently support
  mailing that many people from the same record."* DataSift's in-app mail is OpenLetter on the back
  end; they make no money on it.
- Cost: transcript reads *"about $175 a mailer"* — almost certainly **$1.75**, given handwritten
  OpenLetter pricing. Treat the exact figure as unverified.
- Suppression still applies: buy box, recently sold, low equity all stripped first. **"Buy box plus
  obituary, we do this."** `[01:29:12]`
- Coming feature, ~end of 2026: **multiple decision-maker owners inside a single record**, which kills
  the export-and-mail-outside workaround. `[01:31:28]`

**Timing rule change** `[01:26:40]`: *"All marketing goes out at the same time, ideally. Whether that's
email, mail, call, whatever — the soonest you can introduce it, the better it'll perform."* Ty flags
this as **a newer concept, last 3 months**. Note this is the deep-prospecting-only policy; he's not
applying it to the whole book.

**Personalization is the point:** addressing the heir by name *"does much, much better than reaching
out to the heir and saying the deceased person's name instead."* `[01:23:41]`

---

## 9. Probate: Tyler's flip `[00:33:23]`

Instead of contacting the Personal Representative, **run the full deep prospecting flow to find all
potential heirs even when a PR is already named.**

Why it wins: you end up with **3 correct numbers on one property** — one is the PR, the other two are
in the decision-making process but not listed at the county. And if you reach a non-PR heir, they know
who the PR is and *"have way more leniency in trying to get them and convince them to also sell."*

---

## 10. Marketing philosophy — the core commandment `[00:43:21]`

Omar asked whether deep prospecting is about finding unfindable records or about raising contact rate.
Ty's answer is the day's thesis:

> *"If there were the Ten Commandments of what I believe in… this entire strategy is based on we want
> to connect with as many people as we possibly can at the individual property level. When we know
> that every 10 to 20 records is going to be a transaction, the game shifts from how do we reach as
> many people on that list as humanly possible."*

**Channel ladder, cheapest first:** Call → Voicemail → Text → Mail → Email → Door knocking.
Door knocking is the most expensive fully-loaded. `[00:49:57]`

**The pizza story** `[00:49:57]`: a community member couldn't reach a required signer, so they had a
pizza delivered to the house with a note attached asking them to call. Got the deal.

> *"If you did all of those marketing touches and no one responded, you know it's a good opportunity,
> because no one else wants to do it, because they're lazy."*

**Recursive search** `[01:33:16]`: when the standard flow still can't find someone, tell Claude *"I
still can't find these people"* and it loops until it resolves. Ty doesn't run it by default —
*"it uses a lot of credits"* — but calls it *"really, really good"* for hard signers.

---

## 11. Student results quoted on the call

| Who | Result |
|---|---|
| **Faiz Abrar** | **119 records** (obituary + trusts, skipping probate), niche sequential, one caller → **~3 contracts**, each min $40–50K. *"She's murdering with that."* `[01:03:50]` |
| **Nick Redmond** | Door knocking, 6/3–8/17/26, 22 knock days (incl. a 12-day vacation): **95 hrs, 188 doors, 59 contacts, 11 leads, 2 appointments, 6 offers, 4 contracts, $52,500 gross profit logged** (chat `[01:42:15]`). Separately: 7–8 deals in 6 months full-time, avg assignment $25K+ |
| **Moe Galal** | 5 under contract — 4 from direct mail, 1 from cold call, ~$30K avg assignment. Ty attributed the call-side weakness to the current carrier turmoil and sent him to Day 2 `[00:53:38]` |
| **Anonymous** | **6 deals from return mail** in first 3 months `[00:30:00]` |

---

## 12. Costs, plans, and infrastructure

- **Ty's marketing spend: $10,000–15,000/month**, depending on mail campaigns. `[01:34:34]`
- **Claude: $200 max plan**, on his desktop, no special rig. Biggest overage month ~**$600** while
  building heavily. Expects the **$100 plan suits most people** if you run RTK + best practices.
  `[01:50:18]` `[01:59:33]`
- **fly.io VPS at $5/month** runs the SMS workflow and all first-to-market data on scheduled tasks,
  24-7, no local machine. *"The 501 advanced stuff."* `[00:16:46]`
- **No Mac Mini / dedicated rig needed.** *"99.9% of you do not need any of the rig stuff… mostly hype
  trash."* The $500K mini-server stories are for companies doing county-scale data standardization.
  `[01:50:18]`
- **Opus 4.8 is sunset** — it's Opus 5 now; update VS Code if you still see 4.8. `[02:09:19]`
- **Fable is on the paid plan, not separate prepaid credits.** `[01:56:33]`
- **3–5 Claude sessions in parallel** is Ty's normal working pattern. `[02:11:38]`
- **Equity threshold: low equity = 20%**, derived from their models — *"it seems like people like to
  sell when it's above this threshold."* Nick runs 45% for knocking, 35% for calling. `[01:36:27]`
- **Incomplete records: ~20%** of an account (11K of 42K in Ty's). Missing first/last name. *"If
  you're just starting out, focus just on the clean stuff."* `[02:33:12]`

---

## 13. Practical gotchas

- **Don't tell Claude you're bypassing a CAPTCHA.** Maryam burned an hour on a hard refusal installing
  2Captcha. Ty: say *"I want you to install this tool"*, not *"help me get around this CAPTCHA"* —
  and *"it may cache that and save it, where you won't be able to install it."* Try Fable if Opus
  refuses. `[00:14:07]`
- **Ty got an IP banned** from a county source by scraping without rotating residential IPs. He now
  has to switch his desktop IP just to view it for trainings. Fixed inside SiftStack for everyone
  else. `[01:58:33]`
- **Support philosophy:** they won't build it for you. Get it close, then ask support what you're
  missing. *"Teach you how to fish."* `[00:15:42]`
- **The transcript hack** (Ty endorsing a student idea): feed the Challenge Hub guides + day
  transcripts to Claude and ask *"what would Ty do"* / *"what are the steps"* to generate your own
  checklist. `[02:13:04]`
- **74 agents / 22 skills / 9 divisions** in the Agent Org Chart, all QA'd by Ty. *"They're not
  perfect, but they're much better than if you try to build them yourself."* `[01:53:29]` `[00:19:45]`
- **Install order** (Joshua): Claude Code → RTK + Get Shit Done → SiftStack → API → skills. RTK and
  GSD first *"because you'll just save a lot of your usage on Claude."* `[00:11:57]`

---

## 14. The deep prospecting skill stack (Ty's own answer) `[01:37:51]`

Asked which specific skill runs the flow, Ty named a combination, not one skill:

- Obituary Mail Campaign
- Obituary Mail Export
- **Deep Prospecting v5**
- Obituary Enricher
- Entity Researcher

*"It's using quite a few of these combinations."* His advice for an already-customized install: ask
Claude to find the differences and methodically update, **explicitly telling it what not to touch.**

---

## 15. Day 4 preview `[02:35:44]`

Sales day: comping automation, rehab scope building, **private lending / private money packages
(first time taught)**, dispo processes, lead management flows, SiftLine boards, general sales process.
Ty: *"tomorrow is probably the craziest day aside from today."*

---

## Links dropped in chat

- `learn.datasift.ai/agent-org-chart` — the 9-division / 74-agent chart
- `learn.datasift.ai/deal-room` — API access today
- `learn.datasift.ai/county-list-playbook`
- `smartskip.io` · `get.directskip.com/easylists/` — non-affiliate
