# Day 4 — Sales, Lead Management, Comping, Rehab & Dispo (2026-08-20, August cohort)

Distilled from [day-4-2026-08-20.md](../transcripts/day-4-2026-08-20.md) (3h 13m, 535 turns).
Compare against the July cohort: [day-4-key-teachings.md](day-4-key-teachings.md).
Speakers are real names, so attribution is reliable (unlike July's unlabeled captions).

Ty's framing: Day 4 is *"probably the second densest day to day 2"*: CRM/lead-management side, the
full-cycle sales process, comping workflow, rehab workflow, **private lending (new — "I've gotten a
lot of DMs about it")**, real deals shown end-to-end, and the dispo process — plus two Claude Cowork
Chrome-extension use cases (scraping Facebook groups). `[00:00:52]` `[00:01:20]`

> ⚠️ **Hub-page note:** the hub's Day 4 topic list (5532 Joyce Ann Dr Dayton OH, $63,379/$11,358
> rehab-vs-wholetail, Investor Bootz inspections) is JULY-cohort material. None of it appears in this
> transcript. The August worked examples are **3014 Sanland Ave, Knoxville** (acquisition + comp +
> rehab + lender package) and **158 Old State Rd** (dispo + wholetail). Investor Bootz was not
> mentioned — Ty's own closers shoot the walkthrough videos this cohort.

---

## 0. What changed since the July cohort

| Area | July (Day 4) | August (cohort 11) |
|---|---|---|
| **Worked example** | Dayton OH comp example; two-scenario teardown analysis | **3014 Sanland Ave, Knoxville: full lead lifecycle** — $240K ask → walked → **$92K contract**; plus 158 Old State wholetail/dispo |
| **Lead grading** | "Price is king — below 80% of Zestimate = hot, else 2 of 4 pillars" | **Asking price effectively ignored**: walk + offer if 1–2 pillars present; list membership (doors-per-deal) auto-checks the "reason" pillar. The 80% rule was not restated |
| **STABM** | All five done by hand; status change fires the automation | **Product change (Tyler): status → New Lead now auto-adds the board AND the task** — B and T are automated; even Ty was surprised live |
| **Hot lead cadence** | Every 1–2 days | **Every day until closed** |
| **Rehab input** | Photos (Investor Bootz $75–100/report for virtual) | **Videos** — closer shoots ~4.5 min walkthrough, zip → Claude *watches* the videos. Investor Bootz not mentioned |
| **NEW: private lender package** | not taught | Comp → rehab → **lender package with term sheet** in one chain (first time taught, as promised Day 3) |
| **NEW: dispo / buyer side** | not taught | **buyer-prospector skill** ("top 25 buyers in Knox County"), VIP buyers list, dispo SMS via NSM presets — *"replaces InvestorLift/InvestorBase"* |
| **NEW: vendor directory skill** | — | Pushed the morning of Day 4 — scrapes a local REI Facebook group via Cowork Chrome extension; 68 contractors on the live run. Sister **buyer finder skill** for buyer posts |
| **NEW: obituary-vs-probate stat** | — | **Only ~30% of deaths ever get a probate filed** — probate-only marketing misses 70% of the death-distress TAM |
| **NEW: liquidation hack** | — | Assign $5K to your own entity on every flip/wholetail take-down to repay the month's marketing inside one credit-card cycle |
| **AI call scoring** | Big Day 4 section (3 coach skills, Gemini tip) | **Deferred to Day 5** ("I'll show you that with training tomorrow", OpenRouter key) |
| **Plugins-are-dead / SiftStack build tips** | Covered | Not revisited; replaced by **private-GitHub-clone team distribution** pattern |
| **Enformion** | (Day 3 July: heir path) | Back as **"Enformion Go" for ENTITY skip tracing** — $0.15/lookup, finds an LLC's signing member. Heir role stays retired |
| **Model advice** | Fable/Opus, effort max | Comping: Fable best, Opus minimum. **Facebook scraping: use Opus, NOT Fable** — "Fable is designed primarily for cybersecurity things" and refuses scrape-shaped work |
| **Coming features** | — | **Auto-updating of records + QA agent + underwriter agent ship with the OpenAPI, end of September** |

---

## 1. Sales-process economics (opening Q&A) `[00:03:24]`

- Callers get assigned **500–1,000 new records per week** each; Ty is scaling **mail + texting**
  instead of hiring more callers (mail scales without operational drag).
- Calling is the **heaviest cost-per-acquisition channel**: salary + SmrtPhone + minutes + Number
  Verifier + Trestle. Optimize **return on ad spend** — *"this is a sales and marketing business,
  not a real estate business."* Target at least **2–3X back** on marketing spend.
- **Hedge across channels** so one carrier "shitting the bed" on spam doesn't kill the month —
  go deep on your top doors-per-deal lists across several channels rather than all-in on calling.

**The liquidation hack** `[00:05:08]` — *"a super advanced tactic"*: when taking a property down
(wholetail/flip), **assign it for ~$5,000 to your own second entity**. The lender funds it, the $5K
assignment fee repays that month's entire marketing spend inside the same 30-day credit-card cycle.
*"We pull forward that revenue… that's how we can endlessly scale."*

**Skip-trace policy confirmed** (Faiz follow-up from Day 3) `[00:13:50]`:
- Triple skip trace: **FTM county data + obituary data only** ("that's how I've always done it").
- Hottest bulk/Priority-1: **DataSift skip trace only**.
- DirectSkip has **no API** — the skill logs in via browser automation, same as SmrtPhone.
- **SmartSkip's actual unlock is the output format** — every associated person for the property
  owner in one hit. If your current vendor (e.g. IDI) already returns the relative cluster, *"you
  don't need SmartSkip."* `[00:16:33]`

**Mail rotation** `[00:10:02]`: rotate the mailer **every month** — handwritten → family postcard →
soft offer check. Same mailer repeated falls off a cliff; response degrades massively after
**6 months** regardless. Death-related lists (obituary, deep prospecting) start **handwritten**
(more emotional weight, older demographic); vacant/absentee can go straight to soft offer check.
Mailers are **pattern-interrupt marketing** — the packaging matters more than the contents.
Bulk cold-calling is only condoned on the **exhausted rehash list**.

---

## 2. The 4 pillars in practice — the Sanland deal `[00:29:40]`

KPI floors, universal for prospector and lead manager:
- **150 dials/day minimum** (*"if you have to put in stupid rules to make sure they hit it, you've
  hired wrong"*)
- → **20–25 conversations/day** (text + inbound + outbound combined)
- → **1–5 opportunities/day per person**
- **Appointments set: 1–5/day per caller** (best ever: 6) `[02:43:38]`

**The worked lead — 3014 Sanland Ave** (came in via texting flow → call):
- Notes verbatim from the caller (trained format, all four pillars): wants to sell ASAP, property
  "needs work," asking **$240,000**, rude/rushed, callback at 3:30.
- ARV realistically **$225–250K**, so the ask looked like a dead lead — but **AI score 97 + vacant**
  (top-4 doors-per-deal list) plus "needs work" plus ASAP timeline = walk it regardless.
  *"Anytime sellers say the property needs work, it's probably a shithole."*
- **Rule: if 1–2 pillars are present (especially 2–3), walk it and offer — ignore the asking
  price.** List membership itself checks the "reason" pillar: *"they're on a list that we know
  empirically is proven."*
- Called at 3:30, **met them the same night**. Two brothers had inherited from their deceased
  father; house vacant 2 years; one brother reasonable. Under contract at **$92,000** vs the $240K
  ask — *"there were a ton of other people trying to get it."* No sales wizardry: *"just being a
  real person that has empathy."*
- Pre-foreclosure corollary: auction inside 3 weeks = walk regardless of ask. **A timeline under
  30 days is a massive leading indicator of selling to an investor.** `[00:40:10]`

**Golden rules** `[00:41:49]`:
- **Never give a number over the phone, not even a ballpark** — a ballpark you must later cut (160
  → 92) kills the deal and the trust. Virtual substitute: walk them through mechanicals, roof,
  HVAC, kitchen/bath age over the phone.
- **Never send the contract without being on the phone walking them through it**; in person,
  bring the contract and sign on the spot (experienced teams — new investors can offer first,
  contract after).
- **Walk-to-contract close rate: 50–60%.** Whole acquisition team ~7 people, high EBITDA by design.
- Memorandum/affidavit only if ghosted after contract (has happened ~once ever).
- Local trust play: *"we're at 145"* vs competitors' pressure offers of $180–190 — seller still
  chose them. *"Throwing rocks at common enemies"*: 'those guys will wholesale it; we close.'
- Fortune Builders lineage: in-person, relationship-driven, listing-presentation style. Virtual
  works only with a dialed-in process (Brian Manley: 120+ cities virtual since 2018, but he flipped
  for 3 years first and runs ~50 SOPs).

**PPL/PPC** `[00:53:08]`: Ty (DataSift's CMO by trade) doesn't buy PPL — *"they do PPC and Meta and
charge you a 50-plus-percent markup."* Learn PPC yourself (~20 hours of study, per Ty/Brian) and
budget to lose a little while the algorithm trains. An **inbound version of the challenge** is
planned within ~6 months. Chat data point (duyn): PPL was costing him **$125–150 per address**.

---

## 3. STABM and the SifLine board — the automation got simpler `[01:01:06]`

**STABM** = **S**tatus · **T**ask · **A**ssignee · **B**oard · **M**essages — still *"the backbone
of how we organize the CRM side."*

**The product change (Tyler, live):** `[01:04:41]`
> *"When you change the status to New Lead on the default build now, it automatically adds it to
> the board and adds the tasks to it."*
Ty, surprised: *"Oh — so you don't even have to do this portion?"* You now change **status →
New Lead**, pin the notes, set the **assignee** — board placement and task creation fire
automatically. (July's notes already described status-as-trigger; what's new is B and T are fully
hands-off in the default build.)

- Prospecting hygiene: work marketing phases **from the last attempt backwards** so you never
  double-call; records being prospected carry status **Prospecting** + an assignee.
- **Whisper voice-dictation** for notes again stressed — callers dictate the four-pillar note right
  after the call, in any language. Pin it so it stays on top all the way to close.

**Lead lifecycle cadence** (defaults in every account, distilled from interviews with **~200 power
users** plus Ty/Tyler's own metrics) `[01:06:30]`:

| Status | Cadence |
|---|---|
| **New Lead** | call **same day** (day one task) |
| **No Contact New Lead** | **daily for 3–5 days** (default 3) — call + voicemail + text each day |
| **Nurture New Lead** | **weekly for 3 months** |
| **Cold Lead** | every **45 days** |
| **Warm Lead** | every **15 days** |
| **Hot Lead** | **every day until closed** (July: "1–2 days") |

Movement is **board-driven**: drag the card, the sequence does the status + next task. Phase
transitions after the cadence expires are **manual by design** — you drag it to Nurture when the
3-day dailies run out. `[01:33:07]`

**Task presets** live under Events → Presets (Lead Management: call new lead, call follow-up, hot
follow-up…). Everything ships on, **except you must assign a role or person** (e.g. role "Sensei" =
lead manager) before tasks start generating. Cadences (45-day cold etc.) are editable. `[01:22:12]`
Default builds 15/16/17 (lead management, acquisitions, transactions) are in every account; there's
a **2–3 hour Help Center training** on the default build. Older accounts: ask support to add it.

**No automation after the hand-raise** `[01:10:14]`:
> *"I loathe drip campaigns."*
Automated SMS/email flows are fine on the **prospecting** side (casting a net), but once a real
person raises their hand, every call, voicemail, and text is **manual and personalized** — detected
automation *"crushes trust."* Tyler: wait for the platform-integrated AI responders rather than
wiring your own onto lead management; custom texts win anyway.

**Lead-manager capacity rule (Tyler):** one lead manager saturates at **30–50 tasks per day,
sustained** — not one 100-task spike. That's the hire trigger. `[01:15:15]`

**Tyler's QA agent** (releases with the OpenAPI): scans the whole lead-management pipeline **every
Friday evening**, report ready **Monday morning**. Checks STABM alignment on every record, catches
the classic error (status edited instead of card moved → automation never fires → phantom record
with no task), and re-grades temperature: a **95-AI-score foreclosure marked cold gets auto-promoted
to hot** — *"it's gonna be like, you're stupid."* Same agent pattern for the acquisitions board,
plus an **underwriter agent** — all shipping with the OpenAPI. `[01:16:49]`

**Auto-updating of records** — end-of-September OpenAPI feature: system updates (e.g. Aug 16 update
that lowered realtor score / raised off-market score) will be able to trigger rules that reset a
worked record back into the queue when its distress changes (new NOD, probate filed, etc.). Until
then: a sequence can do it, but *"you're probably overthinking it — maybe a couple percent missed."*
`[00:25:04]` `[01:21:41]`

---

## 4. Recently-sold suppression — the one sequence everyone must build `[01:28:11]`

Ty rebuilt it live (it is NOT in the default account; Help Center article:
`intercom.help/reisift/en/articles/7156704-managing-sold-properties`, dropped twice in chat):

1. **SiftMap preset** per county pulling recently-sold: **Last Sale Price ≥ $1,000** (kills
   interfamily transfers) + **Last Sold Date back to Jan 1, 2023** — Ty goes back **3 years**;
   *"a year is probably not enough, 2 years is a good starting point."* Rationale: a 2023
   full-price buyer has no equity to deal on, and recent-buyer "failed investors" are delusional
   about sunk costs.
2. **Sequence**: trigger = property tag added → condition = the recently-sold tag → action =
   **status → Sold**. Every sold property auto-suppresses from all marketing.
3. Protect closed deals when back-filling: **exclude statuses like Under Contract / Closed** so the
   sweep doesn't overwrite them (Dave's question). Un-suppressing later = reset the individual
   record (Help article; don't reset blindly, it clears a lot).

His build philosophy: **do everything once by hand before letting Claude/API do it in bulk** —
*"when you understand the system, you can manipulate it… that's why we get these crazy workflows."*
`[01:31:18]`

---

## 5. Custom fields — the 75-field sales intake `[01:38:17]`

- Settings → Custom Fields: **groups** contain **fields** (numeric, dollar, date…). Ty's own
  SiftStack group is "TN Public Notice."
- **Tyler's 75 custom fields cover every element of the sales process** — roof age, HVAC age,
  furnace, kitchen/bath age, etc. Deployable via the **agent org chart** workflow ("deploy all the
  custom fields for the sales process") and listed field-by-field in the Day 4 training guide under
  **lead intake**. *"The perfect custom-field setup for people who do everything virtually."*
  Ty admits he doesn't fill them (they go in person + notes) — *"I should. It's best practice."*
- Marketing-side fields: **Text 1–4** (the text-touch flow from Day 2; also the baseline for the
  SMS automations), and for foreclosures: **notice URL, outstanding lien/delinquency amounts,
  auction date** — auto-populated by SiftStack.
- **Custom field + sequence combo:** a sequence **unenrolls a foreclosure from all marketing flows
  once the auction date passes.** That pattern (field feeds sequence) is the point of custom fields.

---

## 6. Comping workflow `[01:44:15]`

Run comps **before** ever talking to or visiting the seller.

**Boundary discipline (unchanged from July, still the #1 rule):** Google Maps → `Win+Shift+S`
screenshot → hand-draw the boundary → upload with the address. Never cross the interstate or a
bigger road (his example: Martin Luther King Dr is *"a pretty rough pocket"* — different ARV world
across it). *"The tighter you make this, the higher quality the output."* The skill's failure mode
is pulling look-alike properties across a boundary.

Prompt pattern: address + boundary screenshot + CRM notes/context ("seller says it's in rough
shape, give me a range"). **Model: Fable strongest, Opus the minimum.**

**Output** (comping tab): per-comp **similarity grade (numeric)**, sale date, sold price,
**adjusted price**, bed/bath, distance, Zestimate, scoring detail, **renovated-or-not flag** — and
with the API it also identifies **who bought each comp and whether they were an investor**.

**The distressed-cash-comp anchor:** a 2/1, 672 sqft nearby sold **$82,000 cash** to an investor →
Sanland (3/1, ~1,000 sqft) is worth ~**$80–100K as-is** before anyone walks it. A nearly identical
distressed comp went for **$92,000** — which is exactly what they contracted Sanland at.
`[02:12:11]`

**Non-disclosure states:** the skill switches formulas automatically; **no MLS login needed**
("it's pretty stable without it"). If you do want MLS data: find an **IDX feed** (first-party, tie
into the DataSift API) rather than browser-automating the MLS; if you must browser it, Apify +
Scrapfly + 2Captcha, and JD's chat warning — MLSs track IP/location, don't log in from two places
at once. *"I wouldn't give Claude access to our banking"* — keep it away from sensitive logins.
`[02:05:52]`

---

## 7. Rehab workflow — videos, not photos `[01:56:53]`

- Closer walks the property shooting **videos in chunks** (front, exterior, crawl space, interior —
  ~4.5 minutes total on Sanland). Uploaded to the shared **Google Drive**, downloaded as a zip.
- Drop the zip into Claude (VS Code + SiftStack gives better results than Cowork here; **plan
  mode** on) with the Day-4 prompt: combine the videos with the existing comp package, estimate
  rehab, **"closely mirror the finishes that are on the comps… so we do not over-renovate."** That
  finish-mirroring line is the critical addition — sometimes rental grade is right, sometimes
  builder grade.
- Trained on **Ty's own rehab cost data**; output splits **labor vs materials** and ships a full
  **material list with real Home Depot + Amazon SKUs**.
- **Finish tiers are hard-coded: Tier 3 = builder grade, Tier 1 = rental grade** — big cost spread
  between them.
- SKU pricing comes from **SERP API's Home Depot Product API** (+ Amazon equivalent) — Ty's
  subscription tier was **free**; his Knoxville-calibrated numbers are already baked in, so most
  markets don't need their own key. **Labor costs auto-pull for the city you're comping in**; ask
  it to adjust materials for a high-cost MSA (LA County). `[02:10:01]`
- Sanland result: conservative rehab **$87K**, real quotes landed **~$70K** (roof was the big
  line).

---

## 8. Private lender package (first time taught) `[01:57:30]`

The chain continues from comp → rehab → **"can you now package this for lenders?"** Output: ARV,
current as-is value, purchase price ($92,000), total purchase + repair cost, investor's total
investment, and a **term sheet** — the document you raise private money with. Next cohort: scraping
**private-money-lender Facebook groups** with the same vendor-directory infrastructure to prospect
lenders. `[02:58:12]`

> *"This chain used to take probably 3 or 4 hours for one setup, and now it's fully automated."*

The full query chain: comps → rehab → lender package → dispo package. Each step is one sentence.

---

## 9. Dispo — the buyer side of niche sequential `[02:13:55]`

**Manual version (no API), inside SiftMap:** search the subject address → clear the filter (map
stays centered) → More → Investor Transaction Type = **Flip** → Last Sold within 1 year → Apply.
Every flip sale in view is a proven nearby buyer — Sanland surfaced 4 (GDP Properties, Four
Horsemen LLC bought $120K/sold $231K, 25 Ventures LLC…). Call them: *"I've got a property at
$98,000 on Sanland, I'll send you the videos."*

**Entity skip trace:** **Enformion Go** ("Informium" in the transcript) — *"a huge pain in the ass
to work with, but the best entity skip tracing I've found"* — **~$0.15/lookup**, resolves the LLC's
**signing member** and skip traces them individually. Often unnecessary: Google the LLC name first.
`[02:16:30]`

**Automated version — the buyer-prospector skill** (run that morning; needs the API for the SiftMap
investor-transaction pull):
> *"Find the top 25 buyers in Knox County, Tennessee using the buyer prospecting skill inside of
> SiftStack. Remove all governmental agencies and all the iBuyers. I'm looking for legitimate cash
> buyers, ideally local inside of my market."*

Output per entity: last 6 months of purchases, mailing city, **signing member/principal**, source +
confidence, business type, notes, **verified emails** — then **SmartSkip skip trace + Trestle
scoring** on the people, upload to Sift as a tagged **"Dispo VIP buyers list."** Exclusions it
reasoned out itself: Opendoor (iBuyer), Amherst (hedge fund), Rebuilt (iBuyer-like), D.R. Horton +
Clayton (builders). GDP Properties ranked #2 — matching the manual SiftMap pull.

**Buyers get prospected exactly like sellers:** dedicated dispo numbers, the Day-2 texting flow via
a **dispo NSM preset**, four drafted SMS messages (*"contract price $92,000, sending it out at
$97,000"*), and send the comp package link for credibility. Zach: does this replace
InvestorLift/InvestorBase? Ty: *"Yeah — we have pretty big businesses and this is all we use."*
Facebook-group buyers remain worth scraping for one reason: the *"handful-of-deals-a-year"* buyers
who overpay because they self-manage — they exist nowhere else. `[03:10:37]`

---

## 10. Obituary vs probate — the 30% stat `[02:44:22]`

- DataSift has scraped obituary data **nationally since January 1, 2026**, matched to homeowners.
- **Of 100 deaths with obituaries, only ~30% ever get a probate filed.** Probate-only marketing
  forfeits **70% of the death-distress market**.
- **Probate filed = intense signal** (PR uncovered, family has decided) → go straight at the PR
  (Tyler pulls the PR's phones). **Death + NO probate after 6 months = a problem signal** — house
  sitting, bills stacking, foreclosure/vacancy risk starts at 1–3 months.
- Records filter demo: List = Obituary + List = Tax Delinquent + **Do not include: Probate** = the
  limbo estates. His sample record stacked obituary, low credit, tax delinquent, senior homeowner,
  owner occupied, low income, high equity.
- **The curative-title stack: obituary filing 6+ months old AND 2+ years tax delinquent** —
  *"this is where you hear these absurd $100–500K transactions."* Chat (Christian): *"Damn, he just
  gave us the list."* Requires SiftStack custom fields for delinquency years (DataSift's stock tax
  list has no year — Ty gets it from the county via his SiftStack API). `[03:02:49]` `[03:04:41]`
- Probate flip re-confirmed (Shaddy): even with a PR named, reach the non-PR relatives — *"a lot of
  their deal success has come from reaching people who weren't the PR"* who then push the PR.
  `[00:17:37]`

---

## 11. Wholetail — multiple exits = bigger deals `[02:48:33]`

**158 Old State Rd:** contract **$62,000**, relist as-is at **$85,000** with their own cash →
**~$18K** vs an assignment worth **$5–10K**. *"A lot of buyers exclusively buy off the MLS and only
do 5 deals a year."* The ability to close on anything = leverage for bigger deal sizes = the high
EBITDA margins. Dispo bonus from the same address: the neighboring new-build's builder said "we
only do new builds" — and became a **vacant-land buyer** for the list.

---

## 12. Facebook group scraping — vendor directory + buyer finder skills `[02:50:00]`

Two skills **pushed to the SiftStack repo the morning of Day 4** (re-pull with: *"pull down the
latest updates from SiftStack using this URL"*):

- **Vendor directory skill**: point it at your local REI Facebook group (e.g. Knoxville Real Estate
  Investors) → scrapes every vendor mentioned/posting. Live output: **68 contractors** — GCs,
  handymen, plumbing, electrical, HVAC, roofing, foundation, flooring, painting, drywall — each
  with contact, verified-phone flag, email, website/FB, service area, public ratings, BBB, license,
  what investors in the group said, cautions, confidence (high/med/low), top-pick flag. Use it to
  competitively bid: *"get quotes from every single one… people are biased toward the first person
  they talk to."* Subbing trades beats one GC managing everything.
- **Buyer finder skill**: same infrastructure for "add me to your buyers list" posts — returns the
  poster's profile URL.
- **Run these in Claude Cowork with the Chrome extension** — it uses *your* IP, domain, logged-in
  Chrome session, so ban risk is *"near zero."* The **only** workflows he prefers Cowork for.
- ⚠️ **Model quirk: use Opus, NOT Fable, for the scraping skills** — *"Fable is designed primarily
  for cybersecurity things and it does not like it when you're trying to scrape stuff."* Fine on
  the **$20 plan**. `[02:57:23]`
- **Scheduled monitoring** (Nara's ask): Cowork scheduled task scraping the group **every 3 hours,
  9 AM–9 PM**, to catch off-market deal posts — *"once you have proven this process… create skills
  that improve the stability of this."* `[02:59:40]`

---

## 13. Teams, accounts, and distribution `[02:30:02]`

- **Distribution pattern:** clone the public SiftStack repo into **your own private GitHub repo**
  shared with the team — *"personalize it, put your own twist on it, hyper-contextualize it."* Ty's
  exact prompt is in the chat (the `curl … install.py` line + private-repo instruction).
- **Claude Teams account** is what DataSift uses; individuals can be raised to the **$200 plan**
  inside Teams (the 20x tier — sign up, then upsell). Who needs a seat: anyone touching workflows
  (admin, you, optionally sales for offers) — **raw prospectors don't**. `[02:35:31]` `[02:42:37]`
- Usage limits reset at **6 AM Eastern**; after the cap it silently rolls to dollar usage —
  *"just be careful."* `[03:06:12]`
- **Train the whole org on the whole challenge** — holistic understanding breeds ideas + career
  development (cold caller → lead manager → closer path fights churn). Worried A-players will steal
  the playbook? *"Good luck."* `[02:26:31]` `[02:35:13]`
- Advice to a working 50-deal/yr probate team (John Scipione, NJ, Mojo + Follow Up Boss): don't
  rip anything out. **Bolt on a not-interested campaign (≈ +20% deal volume, "50 to probably 60")
  + the deep-prospecting flow** (he reaches 20–30% of probate records; the missing 70% is the
  SmartSkip/heir flow), then more FTM lists. Offline NJ courthouses are an **advantage** — runner
  photos → Dropbox → **the Dropbox watcher workflow is exactly this**. *"Simple scales."*
  `[02:37:23]`
- Meta-notes: ~**600 questions asked per challenge**; **80-module roadmap** with walkthrough videos
  pairing with every framework is the next evolution; old cohort recordings are being **deleted**
  (Basem in chat: this cohort is *"at least 60% different"* from January's). Support response time
  ~4 minutes. Day-5 preview: hiring skill (*"one of the biggest unlocks I've had"*), 30/60/90-day
  goals, call-grading + training, open Q&A. Foreclosure door-knock package shared in chat at the
  end. `[00:18:59]` `[00:20:07]` `[03:07:02]`

---

## Links dropped in chat

- `learn.datasift.ai/county-list-playbook#47093`
- `intercom.help/reisift/en/articles/14646968` — Lead Manager Playbook
- `intercom.help/reisift/en/articles/7156704` — Managing Sold Properties (posted twice)
- `learn.datasift.ai/agent-org-chart` (posted 3×)
- Google Drive: walkthrough-videos folder, comp-package XLSX, buyer-list XLSX, foreclosure packet
- Ty's verbatim prompts (rehab-from-videos, phone-validator repair, top-25 buyers, private-repo
  clone with `install.py` curl, vendor directory, 3-hour Facebook scheduled task) — all pasted in
  chat and quoted in the sections above
- `ninjaassistants.com/discovery-call` / `vainusa.com/apply` — DataSift-trained VA vendor (Matix)
