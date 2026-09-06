# Day 5 — Scaling & Operations (2026-08-21, August cohort)

Distilled from [day-5-2026-08-21.md](../transcripts/day-5-2026-08-21.md) (2h 46m, 606 turns).
Compare against the July cohort: [day-5-key-teachings.md](day-5-key-teachings.md).
Named speakers, so attribution is reliable. Ty Garrett hosts alone; no Tyler on this one.

**The format changed.** `[00:04:28]` Ty opened by saying he was deliberately *not* running the
company-audit walkthrough this time:

> *"Historically, Day 5 is all about scaling and operations, and I like to cover the company audit…
> So we'll try something new today, where I've done a lot of coaching calls… people give me an idea
> of their biggest bottleneck… and I kind of give them a rough idea of what I think they should do
> from a 30, 60, 90-day goal perspective."*

What actually got taught: a live KPI teardown of one caller's first month, the hiring machine end to
end, the call-review/training engine that Day 4 promised, and a large new block on **OpenRouter and
model economics**. He also promised, "probably this weekend," a **massive checklist by division**
listing every workflow — the audit tool's replacement.

---

## 1. Opening Q&A — rulings before the main content

**Skip trace / heir phones (Dave Marsh)** `[00:07:14]`
> *"I basically pull in SmartSkip, and then **I'm moving over to DirectSkip**."*
Tyler posted a **DirectSkip-integration agent** in Deal Room that morning. Output convention:
everything goes in the **message board** as a quick family tree, and the API tags the phone numbers
with **both** the Trestle tier *and* the relationship — *"sister-in-law dial 1, or sibling dial 2."*
A product feature to attach many owners to one record (so you can mail all of them from the system)
is coming: *"we're just not there yet. That's like a two-week-old process."* `[00:08:04]`

**Forewarn — do not automate it** `[00:10:24]`
> *"With Forewarn, obviously there's no API, and you have to be really careful in using Claude to do
> automations, because **Forewarn could detect that and then ban you forever**. That's why I said
> SmartSkip's better."*
Chat corroborates: Robin Adair has already been "slapped" — Forewarn's cap is **200/week** and they
don't want it used for cold calling. Dave Marsh notes Chris Aleman (DataSift FB group) sells a
Python Forewarn skip-trace script and got his own cap raised.

**Tier 1 vs Tier 2 ZIPs** `[00:08:37]` — Ty doesn't exclude ZIPs. He excludes **neighborhoods** from
the Market Finder pull (zero-transaction or very-low-margin ones), then ranks everything else by
doors per deal + best first-to-market.

**Tax sale is the #1 list** `[00:26:41]`
> *"Tax sale is probably the number one list universally in every market. It just depends on how
> accessible it is."*
Knox mechanics: auction every **6–12 months**; Ty's team calls the clerk and pulls the list **every
2 months** leading up to it; it arrives as a **~700-property PDF** that is a printed copy of an
internal Excel file the county won't release. Right of redemption ≈ **1 year** post-auction.
Chat (Sonya Johnson, Atlanta): list posted monthly, auction first Tuesday of every month.

**How Ty filters the tax list** `[00:27:02]` — not cherry-picking. Take DataSift's property value,
estimate mortgage debt, add total delinquency, and keep only what clears a fully-loaded equity
threshold. Worked example: $100K value − ~$30–40K mortgage − ~$60K back taxes = skip it.
He does **no sub-2 or creative** — *"I kind of think it's pretty sketchy. There's a lot of stuff
going on right now with mortgages being called by banks through sub-2s."*

**Buy box** `[01:21:18]` — internally he'd like a **$500K ceiling** but they took deals in the
**$600–700K ARV** range so the box went to $700K. **Put a floor in too:**
> *"One of the fastest ways to clog up your pipeline is to have a bunch of shitty houses that are
> worth like 25 grand."*
Worst offenders: Ohio, Indiana. Knox has sub-$100K pockets that *"suck to deal with"* — Old State Rd
sits in one, which is why they **wholetailed** it ($65K in, $85K out). Pretty houses that would
normally go to a realtor: **novation**, and only really worth it on obituary records. `[00:23:02]`

**Phil Loesch's testimonial — a contract with zero phone calls** `[00:10:57]`
> *"It was a doors-to-deal. We started off with the text, got text engagement, got an appointment,
> got a signed contract this morning. …It turns out it was a 75-year-old guy looking like ZZ Top
> that I wasn't expecting to only want to deal with text messages. For the OGs in here that are
> trained on 'you gotta get them on the phone' — we didn't get him on the phone, but we got the
> contract."*

**Say the words** (Phil) `[00:14:18]`
> *"We're saying the word foreclosure now. We're not afraid to do it, because people like the honesty
> and know it's not a bot or a script anymore… We're saying foreclosure, we're saying probates,
> death in the family — **not** 'sensitive situations,' because that sounds like a bill collector."*

**The SMS auto-responder is a "synthetic audience"** `[00:17:09]` — trained on every text they've
ever sent plus best-practice sales calls: *"here were a thousand real seller calls, and here's how
they all responded."* It **stops itself and hands off to a human the moment it detects an interested
party**, because *"the death sensitivity is real."*

---

## 2. The KPI workbook — one caller's first month, every number `[00:29:08]`

Ty pulled the whole thing that morning: *"this was all built in like 10 minutes, and I just kind of
walked away. All in one shot."* DataSift **killed its internal KPI-dashboard roadmap** because the
API + Claude does it better and custom each time.

The caller (Adriana), one month:

| Metric | Value |
|---|---|
| Working days | **19** |
| Leads generated | **~28** |
| Contracts | **3** |
| "Not interested" records generated | **193** |
| Unique right-party contacts | **261** |
| Correct numbers from calling alone | **21** |
| Confirmed on **both** channels (call + text) | **39** |
| Dial-confirmed of the 261 | **163** |
| **Blended dials per correct number** | **13.5** |
| Source list size (top doors per deal) | **1,457** |
| **Contact rate against that list** | **17%** (261 ÷ 1,457) |
| Per-channel split | *"about 8 or 9% from each"* — ~8% text, ~9% call |

> *"She generated 193 [not-interested] properties… remember, **20% of those end up becoming all of
> our deal volume down the road**."*

**Leads per deal collapsed.** `[00:33:00]`
> *"I used to think it was probably somewhere between **20 and 30 leads** would be a deal. I actually
> think now it's somewhere between **5 and 15**… as opposed to getting like **50 to 100 leads per
> deal**, which is how it used to be whenever bulk was super prominent."*
The mechanism: the SMS flow adds *"an insane amount of friction on the front end,"* so anyone still
willing to talk is high quality.

**The deal-yield claim, verbatim** (two passes, slightly different framings — quoted rather than
reconciled):
> `[00:46:57]` *"When we do AI score of 95+, free and clear, senior, vacant, probate, notice of
> default — about **every 20 of that 261 of the right party contacts in the next 6 months is going
> to sell**."*
> `[00:54:09]` *"…the whole stack of outbound to these 1,457 people, because **we know that every 20
> of them is gonna be a deal**. At some point."*
The second reading (1 deal per ~20 doors) lines up with the published Knox doors-per-deal table
(AI 90+ = 25.3). Treat the first as the same ratio, loosely stated.

**Not-interested vs hard no** (Joshua Goodwin) `[00:45:51]`
> *"We will only commit a correct number if they say they're **not interested in selling**. If they
> say 'no, fuck off,' we know that could easily be just another person who's getting blasted, but
> it's not the real owner."*
Ambiguous ones get re-called — that's why 39 are confirmed on both channels.

**KPIs are worthless unless they fire an action.** `[00:36:04]` Real incident: a bad calling day →
Claude's **Slack automation flagged the anomaly** → Ty asked it to inspect the properties being
called → it found they'd pushed in records **outside the high-doors-per-deal band**. They killed
those lists same day.
> *"If we did not have these automations firing, you burned like 3 or 4 days of marketing… Most
> people hear KPIs and they're like 'oh yeah, I track my KPIs,' but you just don't do shit with it.
> That's the issue."*
Phil: the same signal shows up as volume — *"if all of a sudden you had an extra 20% more dials in a
day, then you were calling a crappy list."* Ty calls the underlying skill **entrepreneurial
agility**: *"being able to change really fast and it not rock the boat."* `[00:38:18]`

---

## 3. The blended text + call engine — capacity and cadence `[00:39:07]`

**Texting now supplies about half of all correct numbers.**
> *"That texting automation is actually pulling in about **half of our correct numbers**, meaning
> that's half the workload that now doesn't need to happen for the caller."*
Plus **Trestle removes ~70% of numbers** before anyone dials.

**Capacity per caller: 250–300 records per week.** `[00:39:07]` `[01:45:47]`
Caveat in his own words: *"I've only been doing this for 2 weeks, so I need to see it shake out for
probably 4 to 8 weeks."* Phil's counter-datapoint: **20–30 records/day before** the automated text,
30–50 records *touched* (not dials) — Ty's higher number comes from running **20 numbers at 25
calls-and-texts per number per day**.

**Numbers to buy:** **10 SmrtPhone numbers for one caller**; **25 calls + texts per number per day**
is the threshold. `[00:55:51]` SMS cost, per Phil in chat: **$0.01** each.

**How the funnel actually cleans itself** `[00:41:01]`: blast texts → wrong-number replies get
removed → *"now we only have like two numbers per record to call"* → a chunk say not-interested by
text (137 in the sample month) → the caller dials whatever is left.

**Text timing doesn't matter.** (Nelson Martinez) `[00:48:36]`
> *"She may call 6 hours later, she may call 30 minutes later, and there's seemingly no correlation
> in the answer at that time. So we just stopped caring about it."*
Texts fire **4 days in a row** whether or not the caller dials — *"we're kind of treating it as its
own siloed channel."*

**Attempts:** Ty runs **4 full attempts**, Phil runs **5**, and Phil then hands off to an automated
**attempts 6–14, every other day, text + email**. `[00:42:23]` `[00:42:30]`
Phil's warning to newcomers `[00:34:27]`:
> *"Almost everybody who's gonna start is gonna say 'this doesn't work' in your first 5 days, because
> it actually doesn't. It's the second, the third, and the fifth contacts that are making it…
> **Find out how many records you can touch in a day, and that's how big that caller's list should
> be for the week.** If you don't touch it every single day for 5 days in a row, it gets stale."*

**Where the deals actually landed** `[01:08:41]`: both August worked deals (3014 Sanland, 158 Old
State) took **3 and 4 full attempts** — and the Sanland seller took **4 messages** before engaging.
In his record presets, most deals sit on the **third full attempt**. Untested hunch: foreclosures
headed to auction may need **~10 attempts** because they're hit so hard.

**Ideal per record, per day, budget permitting** (Mak's clarifying question) `[01:04:08]`: call every
number → leave a voicemail → send a text → send an email → send a letter. All of it in parallel, all
in the same day. *"You just want to do the cheapest one that you can afford first, and then stack the
rest up."*

**List turnover: 5–15% per month.** `[01:04:43]` Visual proof from his own AI 90+ SiftMap preset:
model updates on **Aug 1 and Aug 4** dropped **263 + 677 new properties** into the account.
One person **taps out around 2,000 records total** once turnover plus not-interested recycling
stacks up. `[01:05:11]`

**Don't merge markets, and don't run all lists at once.** `[01:02:43]` `[01:07:09]` Pick one city,
work list #1 to exhaustion, then move to #2.
> *"Why would we want to expand past that when we know that it's super efficient based off doors per
> deal? We just have to get in contact with them. **This is why bulk is dumb.** When people are like
> 'I need 10,000 new records' — no, you don't. I promise."*

**Scripts** `[00:43:09]`: only two script *frames* — (a) obituary + probate together, where the caller
is primed that they're reaching **relatives, not the owner** and the sales cycle is long (walk them
through probate); (b) foreclosure, where *"we know they're probably gonna be angry"* and speed to
help wins. Everything else uses **one open-ended script**: are there any plans for the property?
*"We leave that open-ended for them."*

---

## 4. Email, mail, and paid — the rest of the stack `[00:56:56]`

- **Ty's email stack: Instantly ($49/mo)** + its built-in verification, connected to DataSift by API.
  *"Think about Instantly as the equivalent of Smarter Contact for texting, or click-to-dial for
  SmrtPhone. It's another marketing tool that sits on top of Sift."* `[01:02:08]`
- **Phil's free alternative:** Gmail via the Sift integration, **1,000 emails/day**, unique-per-record
  because Claude writes them. *"Unless you're doing more than a thousand, use Gmail."* `[00:58:40]`
- ⚠️ **Ty's counter-warning:** *"Be careful doing that. **I have burned a couple domains** doing that…
  I have damaged domains in the past on our flagship stuff before. And it's very hard to reverse."*
  `[00:59:00]` Phil concedes: warm up, don't open at 1,000.
- **Sending is orchestrated through Claude**, not from the Sift record UI — Claude is the bridge
  between the two APIs. `[01:00:53]`
- **Custom audiences on Meta and Google** built from the same 1,457-door list. Called "super
  advanced," not demonstrated. `[00:57:13]`
- **Promised for next cohort:** a full **email module** and a **door-knocking guide** (including how
  to verify door knockers actually knocked). `[00:57:13]` `[01:37:31]`

---

## 5. Hiring — the whole machine, priced `[01:09:00]`

**The premise:** an agency charges **$3,000–$5,000 per hire** because screening is genuinely a lot of
work. Ty's route cost **~$70 per hire**.

**Channel 1 — Facebook groups (free).** Search the role ("cold caller"), click the **Groups** tab,
and post. Country-targeted groups exist ("Mexico and Latin America bilingual cold calling").
> *"I thought it was total horseshit when I first heard about it… and I actually hired two people
> from it."*
Volume: **~10 groups → ~200 applications.** Think of hiring as a marketing funnel — attention →
application → qualification → interview.

**Channel 2 — Indeed (paid), posted in the local country.** You **must** use the country-specific
employer URL (the guide has the table: `ph.indeed.com/hire`, `mx.`, `eg.`, `co.`, `ar.`, `in.`,
`za.`), and you pay a **separate daily ad spend per country**.

| Country | Premium sponsored post |
|---|---|
| Philippines | **$5–6/day** (cheapest) |
| Colombia | **$8/day** |
| Mexico | **~$10/day** |
| United States | **$15–25/day** (depends how specific the role is) |

Result: **178 applications from Colombia alone**; **$140 total Indeed ad spend for 2 hires = ~$70
each.**

**Screening questions on the post** (all three, verbatim): Can you speak fluent English? How many
years have you been cold calling, telemarketing, or in phone sales? **Are you comfortable making
150+ click-to-dial calls a day for this role?**
> *"Trying to qualify that this is a high-volume role — and if you're like 'I don't want to do
> that,' then don't even apply."*

**Channel 3 — Claude does the screening.** `[01:19:00]` A **scheduled task, twice per day**, run in
**Claude Cowork with the Chrome extension** — *"this is a case where you need to use Cowork, because
the Chrome extension is really stable and you won't get your IP address banned, because it's
actually logging in as you."* It reads Indeed **and** Facebook Messenger **and** email (all three
channels feed one pipeline) and writes a running spreadsheet: score **0–10**, accent quality,
location, real estate experience, general cold-calling experience, answers to the screening
questions, notes, and a recommendation. Ty reviews at end of day, names the ones he likes, and Claude
**sends the outreach message from his own account**.

The message, verbatim (also pasted in chat) `[01:22:12]`:
> ✅ *"Hey I love your application. Can you please send me a **loom video just to verify identity and
> your background for your resume**?"*
> *"What that is doing is **not** saying 'hey, I want to hear how your accent sounds' — it's actually
> verifying that they are who they say they are, and you can also hear how they sound on the phone."*

Then: watch the Looms → **interview the top 3**.
Scores of his actual hires: **both new hires 9.5; Adriana a 10.** `[01:23:44]`
Packaging lives in the **hiring skill** under operations in the SiftStack org chart.

**The myth Ty set out to bust** `[01:16:00]`:
> *"[Adriana] had **no sales experience in REI**, and had only been in sales for **6 months**, and she
> **closed 3 contracts in her first month**. And that's because we are really, really good at
> training."*

---

## 6. Pay, roles, and the org `[01:24:22]`

**Commission ladder — the whole sales chain adds to ~17.5–20% of a transaction:**

| Stage | Rate |
|---|---|
| Cold caller (sourcing only) | **2.5%** |
| Cold caller who carries it all the way through | **5%** |
| Closer | **10%** |
| **Blended out the door** | **~17.5%, "call it 20%"** |

> *"If we get an assignment for $10,000, all of that 20% goes straight out the door to the sales
> team. But in turn, we don't have to be on sales calls all day."*
Paid on **gross projected profit**, not net. `[01:49:28]` **No clawbacks** if the flip under-delivers:
*"That's our fault… Sales is, like, **seriously 80% morale**. If they're sad, it shows fast."*
`[01:28:25]`

**Base pay by role (Ty's own team):** cold caller **$1,100**; lead manager **$1,500**; closer
**$2,000** (that one is **local/US**). `[01:24:22]`

**Base pay by geography (Ty's full survey):** `[01:24:58]`

| Region | Monthly base |
|---|---|
| Philippines | **$500–850** going rate (*"$1,000 is what we pay our staff, but they're really good"*) |
| Egypt | **$750–1,000** |
| Latin America | **$1,000–1,500** |
| United States | **$2,000–8,000** — $8K = overseeing all flips; **$6–7K** = sales manager with commission; **$2–4K** acquisitions depending on volume / OTE |
| Door knockers | **$2,000 base + 10–20% of contract, 1099** |

**Why Latin America for anything seller-facing:** bilingual **and** they understand American culture,
which matters for the hard conversations. Worth the premium over the Philippines.

**Classification** `[02:06:45]`: **W-2 in the US, except door knockers — 1099 for injury liability.**
All overseas staff must be **1099**.
**Payment rails:** **Wise** is the industry leader; **Deel** for larger companies that need IP/legal
protection (*"most people won't need that"*); **Gusto** for stateside. Chat adds Remitly and crypto.

**Retention:** *"In all of DataSift and the REI side, we've only had **2 people ever quit in 7
years**. That's why we overpay."* `[01:30:36]`

**Hours and management model** `[01:31:18]`: no time tracking, no screen monitoring — **open goal
management**. The only hard rule is **calling within 9 a.m.–7 p.m. Eastern** (their market's time
zone) for legal and seller-experience reasons. No weekends yet; Rami wants an evening/morning team
alternating Saturdays. KPI expectation: **150+ dials/day** (many hit 200) and **1–4 opportunities per
day**.
> *"If you set stupid rules about you have to be on from this hour to this hour, then you probably
> hired wrong in the first place."*

**Firing** `[01:33:18]`: **90-day trials.** Hire and fire against written **core values**, not tasks.
Ty's are *"will the impossible, enjoy the moments, lend a hand, show up, value in everything"* plus
*"get shit done."*
> *"It's much easier to do that than to say 'well, this person didn't do their work,' because it's a
> lot more than that. It's all the intangibles."*
His own confession: *"My biggest fault as an operator is not firing faster than I should."*
Chat (Mak): Hormozi's firing model — diagnose what they're doing wrong, check the expectation was
communicated, retrain, re-evaluate; roughly 3 cycles, then fire.

**Role consolidation is his headline prediction** `[01:37:56]`:
> *"I think the **lead manager and the prospector are gonna be the same person** going forward for
> us… I think that's where the industry's headed."*
The closer then only takes **live transfers and walkthroughs**. He also wants prospectors to get some
inbound leads mixed in to protect morale. Conversely, **going the other direction is very hard**:
> *"It's really, really, really hard to take someone from inbound and put them on prospecting."*
> (Brian Manley's 5.5-year inbound-PPC lead manager is struggling with even texting.) `[01:46:46]`

**The data manager role got renamed and merged** (Basem Sanad) `[01:42:48]`: it is now *"a full
virtual assistant admin"* — one person owning **everything administrative, everything data,
everything AI**. That's why he pays VAs above market: *"we wanted to hire really high-quality people
that we could train to use Claude, not just a lower-quality individual."* The DataSift side runs
about **four**. The work is **assigning records, quality checking, and creating new workflows** —
*"more of a QA process than a raw pulling process."* Phil's version: an **"AI champion"** dedicated to
running and extending SiftStack. Chat (Phil): a data manager should run **~$1,500** — though he no
longer has a dedicated one because *"Claude with API does most of it."*

**Give your best people your best data** `[01:38:30]` — like lead scoring, but for staff. New hires
start on lesser lists and get scaled up: *"we don't want to give a new hire PPC leads. That would be
silly, because we pay a lot of money for those."*

---

## 7. Liquidating ad spend — the money model `[01:26:32]`

Ty's mentor-at-a-distance is **Alex Hormozi**; the technique comes from his book **Money Models**.
`[02:33:47]`

The mechanic, with his numbers:
- A flip projected at **$35,000–$45,000** gross profit (Sanland's projection was *"$40,000, $45,000"*).
- They **assign it to a second entity they own for $5,000–$7,500** before the private-lender funding
  closes. *"They just see that that's going to be the purchase price, because we're assigning it to
  ourselves."*
- That $5–7.5K covers **the team's commissions on the full projected profit** plus the **~$2,000 cost
  per contract** — inside the **same 30-day credit-card cycle**.
- The team is still paid as though on the whole $35K; the operating business collects the real profit
  when the flip closes.

> *"If you can get all of your cost to acquire a deal in the same cycle of a 30-day credit card, then
> that's what allows you to **endlessly scale**. It liquidates the expenses."*

**Only pull forward the minimum.** Simon asked why not assign the whole $20K: *"you just want to pull
forward the minimum that you would need to cover the cost of the business that month."* `[01:51:21]`

**Phil's variant** `[01:53:11]`: he wholesales to his own entity at a flat **75% of ARV**, *"because
that's what we get our funding at. That way the gross profit never changes, it's just the cash flow
changes… our success rate is closer to 100%."*

**Cost-per-contract benchmark** `[01:48:43]`: Ty's is **~$2,000**; he estimates a PPC-driven shop like
Brian's at **$5,000–$10,000**.

**Deal-size reality check** `[01:54:37]`: Ty's **average flip profit is ~$50K** — *"that's a good
flip."* Sanland bought at **$92K**, Old State at **$65K**, both with **~$300K ARVs**. Ty's biggest
assignment ever: **$72K**; Brian Manley's: **$80–85K** (in Tennessee). For Brian's $75–100K-profit
flips, Ty's advice was to **cap the commission** rather than pay a flat 10%:
> *"What would be the salary that they don't want to deviate and never leave you?"*

Commission-on-leads-submitted was tried and abandoned `[01:50:05]`: *"it's super hard to track… it
gets very gray. **Business makes money, we all make money. Business makes no money, we get no
money.**"*

---

## 8. Call review and training — Day 4's deferral, delivered `[01:56:06]`

Day 4 explicitly pushed AI call scoring and call teardowns to Day 5. Here it is.

> *"I hear a lot 'my VA sucks' or 'my callers suck,' and the sad truth is **most of the time, you
> suck at training**. One of the biggest levers you can pull on the sales side is **call review**."*

**The tooling** (Simon asked directly) `[02:05:26]`: inside the SiftStack agent framework there is a
**call coaching engine**, paired with three coach skills — **cold call coach, lead manager coach,
closer coach**. Built for SmrtPhone; ask SiftStack to adapt it to another dialer.

**What it does, per run:**
1. Pulls **all the longer calls**, with recordings straight from Sift/SmrtPhone.
2. Reports caller, call length, and outcome.
3. Grades against **the four pillars**, the opener, the objections raised, **tonality**, and the
   next-step/close.
4. Emits **one fix per call** — *"we found that taking one big thing to fix from each of the calls, or
   one thing to reinforce, is the best way to do this."*
5. Writes per-person coaching detail to send to the individual.
6. Picks the **2 best and 2 worst calls of the week** for a live meeting.
7. Quotes are **transcribed verbatim from the call** in the report.

**Cadence** `[02:00:00]`: weekly is what they run now. But **every single call, every day, for the
first week** in any new role (caller, lead manager, or closer) — expandable to the first 3 days or
first 2 weeks. Absolute minimum: one hand-reviewed call meeting per week.
> *"I cannot think of a better training resource than to essentially listen to every single call and
> provide feedback on all of those every single day until they have the whole process nailed. And
> from that point, it's really just repetition."*

**Two real teaching moments it surfaced** `[01:58:00]`:
- A caller accepted "not interested" because **Zillow showed the house wasn't listed for sale** —
  *"that's not how that works at all. If you go onto Zillow, we do **not** want to see that it's for
  sale. This is off-market."*
- A caller hit an unflagged **obituary record**, was told "this is my sibling's, I inherited it, it's
  not even mine," and **didn't ask** — *"that's actually a huge opportunity."*
Then the tactical layer: how to handle the price objection, and that *"they'll sell for the right
price"* means they're **not motivated**.

**How tonality is actually detected** (Mak pushed hard on this) `[02:21:17]`:
> *"It's actually not [a transcript]. It's using an OpenRouter **audio file listening** [model], so it
> can actually detect your tonality and then transcribes that. I believe it's using an **11 Labs**
> one… they are the industry leader in **emotional voice detection**."*

**Transcription providers named:** **AssemblyAI**, and OpenRouter-routed models (below). `[02:05:50]`

**Human-in-the-loop before automating** (Shaddy) `[02:06:14]`: have the report sent to **you** first,
touch it up, then *"have Claude read your changes and update the CLAUDE.md file"* — once it's
consistent, let it send to the team automatically.

Also works solo: *"this works really well if you're doing calling yourself, because you can score
your own and actually understand the mistakes you're making from an objective perspective."*

---

## 9. OpenRouter and model economics — the big new block `[02:08:00]`

Triggered by John Scipione asking whether he needs a separate computer for Claude. Short answer:
**no**. *"My computer is $4,000 for perspective… Most, if not all of you, do not need another setup."*
A local open-source model good enough to matter needs about a **$10,000** machine — *"when people say
'I have my own setup,' they're probably running a model that is not very powerful at all."* The real
reasons to self-host are **privacy/HIPAA**, not capability.

**Published token prices he read on screen:**

| Model | Cost per million tokens |
|---|---|
| **Claude Fable 5** | **$10** — *"arguably the best model in the world… a shitload of money. I don't recommend people use Fable unless you're doing some fancy things."* |
| **Claude Opus 4.8** | **$5** — *"half the cost of Fable"* |
| **DeepSeek** | **$0.22** — *"literally like 80% cheaper than Fable. Not as good as Fable, but…"* |

**OpenRouter** routes any task to whichever of thousands of models is best-and-cheapest for it.
> *"OpenRouter just sold for **$7 billion**, so this company is probably one of the best in the AI
> space."*
Sign up, drop in **$5 at a time**, hand Claude the key.

**Measured costs from his own runs:**
- Transcribing a full Loom walkthrough with **Gemini 2.5 Flash via OpenRouter**: **$0.002 per minute**
  — *"for me to transcribe this whole video in total was **2 cents**."*
- His **daily first-to-market SiftStack pull** on fly.io: *"it uses about **40 cents** in OpenRouter
  costs to transform, transcribe, and build all of my data nice and cleanly, and then also check it.
  And then it uploads straight into Sift. **And for 50 cents, I'll do that all day, every day,
  forever.**"*
- **fly.io VPS: ~$5/month.** `[02:07:24]`

> *"If I used the Fable model to transcribe this, it would be like me going to the grocery store in a
> rocket ship. That's 10 minutes away."*

**The pattern the top builders use** (confirmed with Phil) `[02:25:48]`:
> *"They'll use **Fable to build out the guide and the plan**, and then use the **lower-level models to
> execute**, because the planning portion's the hardest part."*

**The magic phrase** (Michael Hughes asked for it) `[02:25:11]`:
> *"I'll typically say: **'feel free to use the open router models if you think it makes sense.'**"*
Or, minimal version for the overwhelmed: *"just say 'hey, I have an OpenRouter key, it's right here,'
and it will use it if it thinks it makes sense."*

**When you actually NEED OpenRouter** (Avi's challenge — "I never run out of credits") `[02:29:14]`:
> *"To run **fully autonomous** flows, you have to use OpenRouter. You can't use Claude — I mean, you
> could have it log into your desktop, but if your desktop's off, it won't work. That's why I taught
> it today."*
**The unattended-automation stack is exactly two tools: fly.io + OpenRouter.** `[02:35:15]` Apify may
still be needed depending on what data you're pulling — ask Claude and it'll tell you which you
actually need.

**Cost discipline, stated as a rule** `[02:16:00]`:
> *"The problem people run into when using these AI workflows is they try to automate things that
> cost way more than just having a person do it, and it's stupid."*

**Also mentioned, not explained:** **fusion models** on OpenRouter — stacking a Claude model, a
ChatGPT model and a Gemini model so they cross-check each other, which measurably increases
performance. OpenRouter's **benchmarks** page ranks models by quality, value and speed per task type.
`[02:23:05]` `[02:27:33]`

**And the escape hatch for anyone drowning** (Robin Adair: *"my head's exploding"*) `[02:28:22]`:
> *"OpenRouter is advanced. Just use Claude, and don't think about any of this. Don't overthink it.
> It's not as hard as you think."*

---

## 10. SOP creation for two cents `[02:13:00]`

The worked example: Ty recorded a Loom of himself walking through **how to remove sold properties
from marketing**, handed it to SiftStack, and got back a complete SOP.

The output:
- A written step-by-step process with a **flow chart**.
- **Screenshots extracted from the video and annotated automatically.**
- The **original video attached** alongside.
- Landed at `outputs/SOPs/remove_sold_properties`.

> *"We used to make all this by hand, and now it one-shot all of that, and this was **2 cents**."*

**Accuracy:** *"probably **98% accurate**, and the only time it's not is… it hallucinates a little bit
in how I said something. An example is it would spell 'DataSift' wrong."* `[02:20:33]`

**Little hack** `[02:16:40]`: if SiftStack prints a hyperlink and you can't find the file, paste the
link back in and ask where it went — *"it will tell you the exact location of the folders."*
Or just ask: *"where is the SOP for the sold properties that you just built?"*

**Why it matters for onboarding:** *"On our niche sequential internal docs, when we hire people on
for the calling side, they have SOPs with videos of me walking them through exactly like this. That's
one of the reasons they get up to speed fast, they perform better, and they feel trained."*

Ty is regenerating **all the challenge guides** with this pipeline for next cohort, so the screenshots
will finally be real. `[02:19:42]`

---

## 11. Obituary vs probate — the closing ruling `[02:42:33]`

Kyle Blake asked whether to stop pulling probates and just do obituaries. Ruling: **pull both, and
keep them separate — that separation IS the list.**

> *"Tyler and I found, from all of our probate data and all of our obituary data, **only about 30% of
> all obituaries have a probate filing actually attached to it**, meaning **70% is a huge amount of
> market that you're actually missing**."*

> *"The second layer of this is the people who have an obituary filing that's **6+ months old, who
> have not filed probate yet**. That is a killer, killer list, because oftentimes there is some type
> of problem happening amongst the family, and that property's just kind of sitting there — and
> that's usually where the foreclosures come in."*

Implementation: filter on **"last obituary date"** in the DataSift records filter. Tyler has **a
dedicated team member** working only obituary-with-no-probate deep prospecting. Ty's instruction:
*"Keep pulling probates, then bring in obituaries, and then run that full deep prospecting flow on
all of it — that way you can also get the SmartSkip heirs and reach out to them too."*

> *"One of the best lists you can ever get is derived from the marketing that is happening in your
> day-to-day business."*

---

## 12. Scattered answers worth keeping

- **Finding private money lenders** (Maritza) `[02:40:02]`: use the Day-4 Facebook-scraping workflow.
  Search **"private money real estate"** → Groups tab. He named **"Real Estate Private Money
  Lenders"** as the one with the most traction. *"You're gonna get a lot of hard money lenders and
  companies reaching out to you, but I have heard of people getting really good success finding
  individuals."* His own capital came from a DataSift seed round + the acquisition raise, so he's the
  wrong template.
- **Foreclosure pamphlet** `[00:15:06]` — Knoxville-specific, sent as a link to sellers *and* used on
  door knocks. Contains the actual foreclosure process, photos of the whole team, favorite flips,
  and resources (HUD, the state housing development agency). *"It gives a sense of, hey, we actually
  care."* Link in chat; Dave Marsh built his own from it and shared that too.
- **Updating your SiftStack fork without clobbering your own work** `[00:18:47]` — verbatim prompt
  pasted in chat, and Ty pushed an update the **morning of Day 5** (the OpenRouter/SOP tooling), so
  re-pull. You cannot push back to his public repo; his real repo is private.
- **Team collaboration = your own private GitHub repo** (repeat of Day 4) `[00:20:46]`.
- **Skills borrow Ty's Knoxville examples on purpose** `[00:19:30]` — *"how-tos and examples are why
  they're stable."* Ask it to replace/replicate for your market; not a problem.
- **Vertical integration is the endgame** `[00:27:02]` — a board member owns the title company **and**
  the construction company used on all his flips. Ty's own version: flip profits → large assets
  (DataSift, commercial).
- **Solo operator, how to split the day** (Emily, Tampa) `[02:02:04]` — three doors: (1) **Tyler's
  origin path** — full-time military job, **direct mail only**, take the inbounds, close one, use that
  money to hire a caller; (2) calling yourself, cheaper per contract but time-heavy; (3) hybrid.
  There are documented case studies of people prospecting **4–6pm after a W-2, walking properties
  6–7pm**, doing **$200–300K/year**.
- **Where to run Claude when you're overseas** (Mariam, chat) — a **paid, high-quality VPN**; Assaf
  Barak clarified that Claude uses your own browser session, so an existing VPN already covers it.
- **Overwhelm is normal** — two separate students said it out loud in chat. Ty's repeated line:
  *"Don't overthink it."*
- **Trestle's origin story** `[01:28:35]`: *"One of the reasons we created Trestle is our teams hated
  getting the disconnected numbers and the bad numbers. They perform so much higher when they talk to
  people."*
- **Next cohort: late September** (the guides say **Sept 21–25**). Ty is building **80 modules** so
  live days can be more Q&A and less lecture. He recommends **Deal Room for the API** — rollout hoped
  for end of next month. Ask at the end: leave a **Trustpilot** review.

---

## What changed since the July cohort

| Area | July Day 5 (2026-07-17) | August Day 5 (2026-08-21) |
|---|---|---|
| **The day's shape** | Company-audit walkthrough was section 2 — blueprint, monthly spend, self-score across marketing→sales→ops→KPIs | **Audit demo dropped entirely.** Replaced with live 30/60/90 coaching Q&A + a promised "massive checklist by division" |
| **The money model** | Full cost table (prospector $750–1,250, DataSift ~$300, mail ~$500, dialer ~$250, SMS $800/mo billed quarterly, **Trestle ~$200/prospector**, SmrtPhone $250–300) + **3–6 months runway**, Ty's burn ~$8K/mo | **None of that was re-taught.** Replaced by **liquidating ad spend** — assign **$5,000–$7,500** to your own entity on a $35–45K flip to repay the month's spend inside one 30-day card cycle |
| **Leads per deal** | Not stated | **20–30 → now 5–15** (and "it used to be 50–100 in the bulk era") |
| **Correct-number rate** | *"2025: 1 per 32 dials. Now: 1 per 10–15."* | **13.5 dials per correct number blended (text + call)**; **21** correct numbers from calling alone in the sample month |
| **The headline benchmark** | **Answer rate below 50% = skip-trace or spam problem**; team runs 60–70% | **Answer rate never mentioned.** New headline is **17% list contact rate** (261 right-party contacts out of 1,457 doors), split ~**9% call / ~8% text** |
| **Value of a correct number** | *"Every **50–100** correct numbers yields at least one transaction over 12 months"* | *"**every 20**… is gonna be a deal"* over **6 months** on the AI 95+ / free-and-clear / senior / vacant / probate / NOD stack |
| **Not-interested campaign** | *"Missing out on the equivalent of **30–50% of all transactions**"* | **20%** of not-interested records become deal volume later (matches the August Day 4 number) |
| **Texting's role** | Not a Day 5 topic | **Texting supplies ~half of all correct numbers**, runs as its own siloed 4-day channel, and timing relative to the call **does not matter** |
| **Caller capacity** | Not quantified | **250–300 records/week** per caller, on **20 numbers × 25 calls-and-texts/number/day**; taps out ~**2,000 records** total. Phil's pre-automation baseline: 30–50 records touched/day |
| **Agency cost to hire** | *"~$3,000 per hire"* | **$3,000–$5,000 per hire** |
| **Ty's own cost per hire** | **$135 total for two hires** | **$140 Indeed ad spend for two hires ≈ $70 each** |
| **Indeed daily spend** | "~$10/day; Ty's budget was $8/day in Colombia" | Per country: **PH $5–6 · CO $8 · MX ~$10 · US $15–25** |
| **Country-specific posting** | Ty was told one job can't span countries; **Micah Redden contradicted him live** | Restated as a **hard requirement** — you must use the country's `/hire` URL and pay separate daily spend per country. No pushback this time |
| **Applicant volume** | 5 groups ≈ 100, 10 groups ≈ 200 | **10 groups ≈ 200 applications**; **178** from Colombia Indeed alone |
| **Interview funnel** | Watch ~10 Looms → pick ~5 → interview, **use two interviewers** | Watch the Looms → **interview the top 3**. The two-interviewer rule was not restated |
| **Adriana's score** | **9.5** ("the one 10 didn't reply fast enough") | **Adriana was the 10**; the two new hires scored **9.5** |
| **Adriana's comp** | $1,100 base + **2.5%** of closed gross profit | $1,100 base + a **ladder: 2.5% (sourcing) / 5% (carries it through) / 10% (closer)** = **~17.5–20% of a transaction** to the sales team |
| **Adriana's ramp** | ~172 dials/day; taking leads to a set appointment inside ~2.5 weeks | **No REI experience, 6 months of sales total, 3 contracts in month one**; 28 leads across 19 working days |
| **Retention stat** | *"~30 employees and **one person has quit** in seven years"* | *"**2 people ever quit in 7 years**"* |
| **Door knockers** | $2–3K base + **10%** commission ($3K in California) | **$2,000 base + 10–20% of contract, 1099** (1099 specifically for injury liability) |
| **Role pay** | Prospector Egypt/PH ~$750, LatAm $1,000–1,250 | Full grid: **PH $500–850 · Egypt $750–1,000 · LatAm $1,000–1,500 · US $2,000–8,000**; internal roles caller **$1,100** / lead manager **$1,500** / closer **$2,000** |
| **Payroll rails** | Not covered | **Wise** (default), **Deel** (IP/legal, larger cos), **Gusto** (US). W-2 US / 1099 overseas |
| **Team structure** | Career path caller → closer as the retention hack | Same, **plus a prediction: prospector + lead manager consolidate into one seat**; closer takes only live transfers and walkthroughs. Data manager renamed to **"full VA admin"** owning admin + data + AI |
| **AI call scoring** | Not on Day 5 (it was July's Day 4) | **Delivered here** as Day 4 promised: **call coaching engine + cold-call / lead-manager / closer coach**, 2-best-and-2-worst weekly, **daily for a new hire's first week**, tonality from an **ElevenLabs audio model** (not the transcript) |
| **SOP creation** | playbook-creator skill + Loom/Fireflies. ⚠️ *"Transcribing video burns a lot of Claude usage"* — a student blew his $100 plan | **The fix shipped.** OpenRouter + **Gemini 2.5 Flash at $0.002/min = 2 cents per video**, and the SOP now auto-extracts and **annotates screenshots from the video** |
| **NEW: model economics** | — | Full pricing block: **Fable $10/M · Opus 4.8 $5/M · DeepSeek $0.22/M**; local models need a **$10K** machine; **OpenRouter sold for $7B** |
| **NEW: unattended automation** | Apify was the answer ("run SiftStack off your own machine") | **fly.io + OpenRouter** is now the stated stack. *"To run fully autonomous flows, you have to use OpenRouter."* **~40–50¢/day**, **$5/mo VPS**. Apify still needed for some pulls |
| **Email** | Not covered | **Instantly $49/mo** (Ty) vs **Gmail 1,000/day free via Sift** (Phil). ⚠️ Ty has **burned domains** doing the Gmail route. Full email module promised next cohort |
| **Skip-trace vendor** | Not a Day 5 topic | *"I'm **moving over to DirectSkip**"* — Tyler shipped a DirectSkip agent. **Forewarn: never automate, ban risk**, 200/week cap |
| **Obituary vs probate** | *"Estate sales are too late… obituary data is powerful, you're very early."* Probate Finder skill has a **25–50% hit rate** | Quantified: **only ~30% of obituaries get a probate filed**; **obituary 6+ months old with no probate = the killer list**, filtered on "last obituary date." Ruling: **pull both, keep them separate** |
| **Dropped without replacement** | DNC/litigator policy (~60% of numbers on DNC), spam remediation ("we just kill the number"), Netlify/Carrot websites, Zapier attribution, Firecrawl, the **D4D driving-for-dollars model** (roof + windows, 90+ ≈ 23 doors/deal), reverse-onboarding Looms, Probate Finder's hit rate | **None of these came up on August Day 5.** If you were relying on them, they're July-only material |
| **Promised next cohort** | Vacant historical data; three-distressor combos; D4D shipping "this quarter" | **80 modules**; an **email module**; a **door-knocking guide** (incl. how to verify knockers); all guides **regenerated with real annotated screenshots**; next cohort **Sept 21–25** |

---

## ⚠️ Flags for the SiftStack operator

Things taught on this day that **contradict, update, or directly bear on** what's already running in
this repo.

1. **Ty is migrating off SmartSkip to DirectSkip.** `[00:07:14]`
   The repo's decision (`project_skiptrace_stack_smartskip.md`, 8/26) locked SmartSkip as the batch
   source. Ty now says *"I basically pull in SmartSkip, and then I'm moving over to DirectSkip"* and
   Tyler shipped a **DirectSkip-integration agent** in Deal Room. Day 4 already noted DirectSkip has
   **no API** (browser automation, like SmrtPhone). **Action: watch, don't switch yet** — no cost or
   yield numbers were given for DirectSkip on either day.

2. **Phone tags are supposed to carry the relationship, not just the tier.** `[00:07:14]`
   > *"The API allows you to add tags to the phone numbers with the Trestle tag of dial 1 through 5,
   > **and the relation to the actual owner as well** — so it will say sister-in-law dial 1, or
   > sibling dial 2."*
   The repo's Trestle sweep writes tier tags only. Adding the relationship token to each phone tag
   would make the message-board family tree readable from the dial list. Also: a **multi-owner
   product feature is ~2 weeks old and incomplete** — which is the same wall the repo hit at
   **15 phones per owner-PATCH** (`project_phone_remove_via_owner_patch.md`). Don't build around the
   multi-owner path yet.

3. **Text-first is now doing half the work — and the written guide still says the opposite.**
   The Day 5 company-audit guide states *"the cold call leads live contact; **text follows the call,
   never first**."* Live, Ty runs texts as an **independent 4-day channel that fires regardless of
   dials**, timing-agnostic, pulling **~half of all correct numbers** and **~8% of the list** on its
   own. The repo's `sms_agent` is still at **PHASE=1 (cannot send)** with the only gap being
   `SMRTPHONE_API_KEY`. **This is the single highest-leverage unfinished item in the repo** by Ty's
   own numbers. (Note the repo's standing rule still applies: never automate free-text on DataSift
   record pages.)

4. **The nightly build's dependence on the home desktop has a published fix.**
   `project_chrome_remote_desktop.md` records that the nightly NC task is Interactive-only and missed
   builds must be started by hand. Ty's answer `[02:29:14]` `[02:35:15]`: **fly.io + OpenRouter**,
   because *"you can't use Claude unless your desktop is on."* His own FTM daily pull runs there for
   **~40–50 cents/day** on a **$5/mo** VPS. Apify may still be needed for specific pulls.

5. **OpenRouter is a direct answer to the repo's LLM-cost standing order.**
   `project_heir_verify_cost_blowout.md` says keep LLM cost VERY LOW, and
   `project_anthropic_monthly_cap_75.md` records two cap hits. Ty's routing rule — **Claude plans,
   cheap models execute** — plus **Gemini 2.5 Flash at $0.002/min** for transcription is exactly the
   pattern. Magic phrase: *"feel free to use the open router models if you think it makes sense."*
   Candidate targets in this repo: obituary/heir LLM verification, handwriting `vision_json()`, and
   any bulk parsing.

6. **The published KPI guide's ratios are stale.** kpi-tracking.md still prints **"Correct Numbers
   (32:1)"** as the benchmark. Live on 2026-08-21 the number is **13.5 blended / ~21 call-only**, and
   Trestle now strips **~70% of numbers** before dialing. Anything in this repo calibrated to 32:1
   (dial-volume planning, expected-yield math) is roughly **2.4x pessimistic**.

7. **Anomaly alerting on KPIs caught a real 3–4 day marketing burn.** `[00:36:04]`
   The repo already has a daily HTML report + phone-KPI ledger (`project_kpi_email_ledger.md`). The
   missing piece is the **alarm**: Claude comparing today's rates to baseline and firing a Slack
   message when they drop, then being asked to inspect *which records were called*. Ty's incident was
   records pushed outside the high-doors-per-deal band — the exact failure mode the repo's NSM preset
   gates are supposed to prevent.

8. **"Obituary 6+ months old, no probate filed" is a list this repo does not build.**
   The NC pipeline is probate-first from eCourts. Ty's number says that captures **~30%** of the
   death-distress TAM, and the highest-signal segment is the **70% that never files**. DataSift has
   national obituary data (since 2026-01-01) and a **"last obituary date"** records filter. Building
   the `obituary ≥6mo AND NOT probate` view is a pure-filter change on the CRM side — no new scraping.
   His explicit ruling to Kyle Blake: **keep pulling probates too**, because the separation is what
   creates the list.

9. **Caller-ID capacity numbers to reconcile with Dial Watch.** Ty: **25 calls *and* texts per number
   per day**, **10 numbers per caller** to start, 20 numbers at full scale. The repo's Dial Watch caps
   **25 dials/day per caller ID** — same ceiling, but Ty's 25 is the *combined* call+text budget, so
   adding SMS on the same numbers would put the repo over his threshold unless texts get their own
   pool.

10. **Litigator/DNC suppression was not re-taught this cohort.** July's Day 5 carried the DNC policy
    (they don't scrub, they do suppress litigators via Trestle, ~60% of numbers are on DNC minimum)
    and the spam-remediation verdict (*"we just kill the number"*). Neither appeared on August Day 5.
    The repo's `phone-validator` litigator suppression and `caller-reputation-monitor` are still
    running on the **July** guidance — nothing contradicted it, but nothing re-confirmed it either.

---

## Links dropped in chat

- `https://openrouter.ai/models` — posted by Ty at `02:24:43`
- `https://instantly.ai/` — posted by Ty at `01:03:04`
- Ty's foreclosure pamphlet (Google Drive) — `01:17:09`; Dave Marsh's own build of it — `01:17:28`
- The SiftStack-update prompt, verbatim — `00:20:37`
- The Loom-request message to candidates, verbatim — `01:22:12`
- `https://learn.datasift.ai/challenge-hub` — posted by Shaddy ElRamly for the private-lender replay
- `https://www.ninjaassistants.com/discovery-call` — Matix / HireTrainVA, DataSift-trained VAs
- `http://www.youtube.com/watch?v=COdaZbkqRdg` — Mak's link to Hormozi on when to fire
- Tactiq transcription extension (two attendees auto-posted it)

**Named tools this day:** DirectSkip · SmartSkip · Forewarn · Trestle · SmrtPhone · Instantly ·
OpenRouter · fly.io · Apify · AssemblyAI · ElevenLabs (emotional voice detection) · Gemini 2.5 Flash ·
DeepSeek · Wise · Deel · Gusto · Loom · Claude Cowork + Chrome extension · Trustpilot.
Chat-only additions: Remitly, crypto payouts, ExpressVPN.

**From the written hiring guide but never said on the call:** **RemoteLatinos** — marketplace
**$97/mo** (self-serve, browse pre-vetted candidates) or done-for-you Talent Hunt **$3,000/hire**;
**SparkHire** for video-screening 100+ applicants; the country-specific `indeed.com/hire` URL table
(PH, MX, EG, CO, AR, IN, ZA); and ten named hiring Facebook groups including "Egypt Cold Callers"
and "Cold Callers for Beginners - Real Estate." The guide also puts Indeed at **~$150/hire**
($8–10/day for ~5 days, shortlist 15–20, interview 5) — **higher than the ~$70/hire Ty reported
live**.
