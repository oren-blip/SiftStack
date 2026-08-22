# Day 2 — Niche Sequential Marketing (2026-08-18, August cohort)

Distilled from [day-2-2026-08-18.md](../transcripts/day-2-2026-08-18.md) (4h 17m — Ty's own count
at close; Assaf in chat calls it the record-longest 5DDFC session). ~134 people on the call, "100
plus pretty much the whole time."
**Named speakers** — attribution is reliable. Ty Garrett hosts; **Tyler Austin DOES appear and
teach this time** (unlike Day 1), jumping in on buy-box floors, AI-score philosophy, and the AI-plan
concierge. Phil Loesch is everywhere — he **signed a deal 20 minutes before the call** (20-acre
rural property with a house, ~$200K projected net on the flip).

Ty's framing: records-page filter presets are the backbone — *"The tags tell me where this property
is in all of my marketing flows."* `[00:52:17]` Day 2 = the entire conveyor from raw records to
call/text/mail, plus the phone-infrastructure deep dive.

---

## 1. What changed since the July cohort

Compared against [day-2-key-teachings.md](day-2-key-teachings.md) (July 14 session):

1. **The Text Touch Builder was replaced by a fully autonomous two-way SMS agent.** July: Claude
   writes 4 unique touches per record, the caller copy-pastes them and dials 10–20 min later.
   August: a SifStack agent (via the API + SmrtPhone) sends every text itself on a **9am cron**,
   spreads them through the day (137 messages across 427 minutes in the live example), rotates
   numbers, **auto-replies with AI until someone says they're interested**, then stops the drip,
   pings the assigned prospector in Slack, and fires dispositions (wrong number, STOP → DNC +
   `Mail Only` tag) back into Sift automatically. Live 1-week test: **766 texts → 4 leads**;
   capacity ~400 texts/day. Implemented "like 7 days ago." `[03:07:00]` `[03:12:24]` `[03:13:42]`
2. **Number Verifier is the new spam weapon; July's playbook is mostly dead.** July taught the free
   Caller Reputation Monitor (IPQS) + rotate every 25 dials + Phil's "priming" trick. August: Ty
   **stopped priming — "it seems like it's not working"** `[02:57:45]`; the answer is
   **numberverifier.com** (~$10/number/mo, **$150/mo minimum = 10 numbers**, 90-day out on the annual
   contract, owned by Blacklist Alliance). It dials your numbers from real AT&T/T-Mobile/Verizon
   lines to read the actual spam label per carrier and runs automated remediation (~5 days).
   Caller ID Reputation is still dismissed — they quoted Ty **$6,000/yr up front**. `[02:34:33]` `[02:52:08]`
3. **Attempt count went up.** July: "4 full attempts — it has to be this, trust me." August: Ty now
   says **"somewhere between 4 and 6 full marketing attempts"**, and Phil is running **10 attempts —
   5 in a row, then 5 more over 2 weeks with texts and emails only**. A full attempt now explicitly
   stacks **call + voicemail + text + email + direct mail + door knock**. `[01:47:xx]` `[00:06:12]`
4. **The API automated the whole conveyor.** July's Trestle flow was export CSV → Claude → re-upload.
   That manual path is still taught, but Ty's own pipeline — skip trace ×3, Trestle scoring, record
   assignment, status changes, texting — **runs automatically every morning as cron jobs**. "It took
   me a month and a half to get it all correct." `[02:15:25]` `[02:29:47]` `[02:30:15]`
5. **Team structure: full-cycle sales is the new test.** July was "collapse prospector → lead manager
   → closer over time." August: a hire from ~5–6 weeks ago at **$1,100/mo base** does prospecting +
   lead management + appointment setting in one seat; closers go out in person (**90/10
   in-person vs virtual** — "we're in a lack-of-trust economy"). Result: **Adriana got 3 contracts on
   ~30 leads in 4 weeks.** `[01:39:41]` `[03:18:23]`
6. **Cadences were re-tuned from missed deals.** July: rehash every 30 days (10 for foreclosures);
   not-interested 30–45 FTM / 45–90 SifMap. August: reactivation presets at **45 and 90 days**;
   **probate moved from 90 → ~40–45 days** ("we missed a lot of transactions"); **foreclosure with an
   auction date = every 15 days**; pre-foreclosure ~30; other FTM 90. **Rehash is now 90 days** and
   admittedly neglected ("we don't have the bandwidth") — and it's the one place Ty now blesses bulk
   dialing. `[04:07:24]` `[04:05:44]`
7. **Bulk softened from "dead" to "a tool for specific jobs."** July: "We've scrapped bulk
   altogether." August: Phil ships all Priority 1 lists across 5 counties to bulk dialers while
   working the hottest niche-style — **connect rate up ~20% in two weeks** — and Ty concedes bulk for
   rehash lists. The challenge hub now even carries a bulk guide "for people who don't believe us." `[01:08:12]` `[01:02:48]`
8. **Skip-trace vendor stack changed.** July: DataSift + Tracerfy + Informium ("skip in three
   places"). August: **Informium is cut** ("a disaster to get people onboarded") and demoted to
   entity/signing-member skip tracing for Day 4 dispo; Ty is **moving to DirectSkip** (Tyler's pick);
   **SmartSkip (15¢/hit)** is teased as the Day 3 star. Multi-source skipping still **FTM-only** —
   Phil asked point-blank and Ty confirmed it doesn't pay anywhere else. `[02:32:19]` `[02:14:11]`
9. **Sold suppression got the full build treatment and a stronger title:** "the single most important
   workflow in the entire challenge" (July's framing was a morning loss-audit ritual; that audit isn't
   re-taught here — buyers/dispo use of solds is deferred to Day 4). New concrete numbers: **25,355 of
   42,210 records suppressed**; cutoff **Jan 1, 2023** (strict 3-year-hold rule); **last sale price
   ≥ $1,000** to exclude interfamily transfers. `[01:11:49]` `[01:13:27]`
10. **New Claude-efficiency layer: RTK + "Get Shit Done"** public repos installed as global CLAUDE.md
    settings — Ty claims **~70% less Claude usage**. Prompt given verbatim in chat. (Neither existed
    in the July session.) `[00:10:03]`
11. **New platform facts:** DataSift **webhooks shipped "last week"** (bridge to GoHighLevel / Left
    Main / other CRMs) `[01:39:32]`; **auto-updating + fully customizable records page** prototype
    shown, releasing "in like a month and a half" to **everyone**, not just API users `[01:37:22]`;
    API full public release still "end of September," Deal Room for access today `[03:25:22]`.
12. **Phone-carrier discovery (new, and the root cause of recent pain):** SmrtPhone and nearly every
    dialer buy numbers from the same pool via two upstream carriers — **Telnyx and Twilio, ~90%+ of
    the market — and Telnyx is "going through large issues,"** which is why connect rates cratered
    for SmrtPhone users in recent weeks. Ty's numbers were being migrated to Twilio the day of the
    call; community-wide carrier moves may follow. `[02:40:xx]`
13. Dropped/moved topics vs July's Day 2: doors-per-deal framework (now Day 1, v2 web tool), the
    replacement-ladder hiring order (moved to Friday/Day 5), Tyler's deceased/relatives segment and
    obituary texting rules (moved to Day 3), recently-sold loss audit + cash-buyer harvesting (Day 4),
    cold email (rolling out "next month" — Ty withheld it because there's no guide yet), door-knock
    route builder (only referenced), Instantly/Kickbox, Facebook/Meta commentary.

---

## 2. List discipline and sales cycles (Phil's opener + Ty's framework)

**Phil's texting-sequence ops** (the thing 15 people DM'd him about): create a **separate Sift line
board per prospector**, load **20–30 records each morning**, work them, return them to the main
line. A 200-record list feeds 3 callers without them stepping on each other. (He's since automated
this with an agent + the API.) `[00:06:12]`

> *"If you don't work your list in 5 to 7 days, it goes stale and your results go down."*
> One person can take **150–200 records/week through the full process, tops** — pull only what your
> team can work in a week to a week and a half. People who say "this doesn't work" usually pulled
> 1,500 records and took 3 weeks per pass. `[00:08:08]`

**Sales cycles per list** (from Ty + Tyler's combined account data) `[00:19:03]`:
| List | Sales cycle | Note |
|---|---|---|
| FTM probate | **4–7 months** | pipeline-builder; consistency play |
| Obituary | **6–12 months** | the $100K+ curative-title deals live here |
| Vacant combos | fast | "money today" — Marion County's out-of-state-vacant + tax-delinquent-vacant ≈ 1,400 properties |

One-man-band starting stack: vacant combos for cash flow + FTM probate + bolt in obituary deep
prospecting. Balance long-cycle pipeline lists against fast-cycle lists.

**Prioritize inside a big list by top zip codes** (Tyler): pull the whole list, work the best areas
first — deals exist everywhere, but top zips also **exit** fastest. Live demo: hottest ready-to-call
111 properties → include zip 37917 only → 17. `[00:21:26]` `[00:22:02]`

---

## 3. Records page = the marketing backbone

- **Buy box lives in the records filter, not SifMap:** suppress low + negative equity (**keep
  unknown** — you lose ~half of transactions otherwise, more in non-disclosure states), property
  value **$100K–$700K**, single-family, must-not recently-sold, must-not mail-only. No bed/bath or
  sqft filters — "simple scales." `[00:24:10]` `[00:26:33]`
- Tyler: **always floor estimated value** — $125–150K works most of the U.S.; FL ceilings run
  $700–900K; CA floor ~$700K / ceiling ~$2M. `[00:25:36]`
- **Estimated value = Zestimate-like as-is, not ARV.** Ty's Knox rule of thumb: $200K estimated ≈
  **$230–260K ARV**. Want $300K ARV? Filter to ~$400K max. `[00:47:28]`
- **Free & clear = 100% equity + the unknown checkbox.** And it only means *no mortgage was
  reported* — a HELOC can still be on it (he closed a deal exactly like that). `[00:46:29]` `[00:31:53]`
- **Incomplete tab** = missing owner first/last or mailing/property address — ~95% of Ty's are
  **entities**. He doesn't market to them at all (tested "want to sell the portfolio?" outreach —
  works but hard to reach; entity dispo comes Day 4). `[00:52:17]`
- **Clean** sorts by number of lists per property, top-down.
- **Tags drive everything:** `FTM` (came from county pull → prioritized over SifMap data), `Priority
  1` (doors-per-deal combo tag set in the SifMap preset — no lists there, lists auto-populate on
  pull), auto-tags from SifStack (code violation, register of deeds, liens, county list framework,
  out of state…). Folders: **Hottest = Priority 1, Strong = Priority 2**, FTM tiers separate —
  "3rd grade reading level" naming for the team. Multi-county: suffix the preset `hottest call -
  {county}`. `[01:04:34]` `[01:24:55]`
- Pull philosophy: **bring in as much as you can from SifMap/county, filter heavily in records** —
  exception: leave out what you'll never market to (vacant land for Ty). `[00:48:47]`
- His Knox Priority 1 = notice of default + probate + free & clear/senior/vacant + AI 95+ = the same
  **1,457-property cumulative stack** from Day 1 (Bryant's confusion → the cumulative count dedupes:
  1,457 − 456 = ~1,000 uniquely on AI 95+). `[02:17:32]`

**Sold suppression — "the single most important workflow in the entire challenge"** `[01:13:27]`:
1. SifMap at the **county** level (never zip) → More → **show all SifMap results**.
2. **Last sold date ≥ Jan 1, 2023** (his strict 3-year-hold rule — post-2023 buyers rarely have
   enough equity to deal) + **last sale price ≥ $1,000** (kills interfamily transfers).
3. Select 10,000 at a time → Add Records → **tag `Recently Sold`** (that tag is the whole trick).
4. A **sequence** fires on the tag: status → **Sold**, which every marketing preset excludes
   (must-not `Recently Sold`). It stays in records — suppressed, not deleted.
5. Finish with a **Recently Sold auto-add** preset per county so it feeds daily (3 unenrolled the
   morning of the call).

Result in his account: **25,355 of 42,210 properties suppressed**. Claimed effect: 10–20% lower
overhead; protects mail spend and team morale; his help-center Zoom video walks it click-by-click.
Avi's "best question of the week": obituary/deceased records DO get their own deep-prospecting
preset, but Ty deliberately did **not** suppress them from the other presets — he's split-testing
whether blind marketing ever reaches them. `[01:22:18]`

---

## 4. Team structure — the full-cycle sales experiment `[01:39:41]`

- Classic flow still described: prospector (cold dials) → lead manager (4 pillars, good-cop framing,
  set expectations) → closer (in person). But the 5–6-week-old test: **one higher-quality hire at
  $1,100/mo base doing prospecting + lead management + appointment setting** ("full cycle" minus
  closing). Rationale: the killer handoff problem (getting a seller back on the phone), career-path /
  turnover on pure cold-calling roles, cost.
- **90% of closings in person, 10% virtual** — "we're in a massive lack-of-trust economy… we are
  finding a lot of success by going in person."
- Assignment model: each preset cluster (hottest call, strong call, FTM tier 1…) is owned by one
  person; ~200 records per prospector at a time; select → Manage → **Assign to User**, then bulk
  status → **Prospecting** (that status = "actively being worked").
- **Adriana: ~3 contracts on ~30 leads in her first 4 weeks** — fewer leads than blast marketing but
  radically more motivated, "way less operational drag… very high net margin business." `[03:18:23]`
- Owner keeps making **5–10 offers a day** in the closer seat until real scale.

---

## 5. The conveyor + call process

Stages: needs skipped → skip/no numbers → ready to call → call attempt 1 → 2 → 3(+). The **call
attempts counter** is what moves a record down the belt (set every number's disposition, then
increment attempts by 1). Bulk path: select → Manage → **Update Attempts** (+1) — also how you feed
an external dialer like CallTools. `[03:19:52]` `[03:20:42]`

- **Work backwards: attempt 3 → 2 → 1 → ready to call** so you never double-dial anyone the same
  day (clearing attempt 3 first means the freshly-promoted records land in an empty bucket behind
  you). Pin the presets with the star so the order stares at the caller. `Shift + →` = next record. `[03:02:25]` `[03:48:37]`
- **Only dial the `Dial First` / `Dial Second` tags** (see Trestle below). Adriana's screen showed
  exactly that — dial-thirds and dial-fourths never touched.
- **Skip/no-numbers = the direct-mail/door-knock goldmine** (unchanged doctrine): his 164 no-number
  properties can't be reached by competitors either. Separate workflow; deep prospecting on them
  tomorrow. `[01:50:xx]`
- 30 phone-number slots per record; you'll only ever approach that in deep-prospecting flows.
  DataSift-flagged disconnected numbers (red icon) → mark dead, don't dial (Tyler would dial them;
  Ty doesn't — they nearly never pass Trestle anyway). Blue icon = correct number. `[01:21:09]` `[01:30:32]`

**Script (unchanged curiosity opener):** *"Hey Phil?"* (first name + urgency) … *"I was just calling
to see if you had any plans for 1968 Cecil Johnson"* — the more casual the better. `[03:04:xx]`

**Personalization doctrine — insinuate, never name the distress** `[03:43:06]`:
- D4D/bad-shape: *"We were walking through the neighborhood and saw 123 Main Street — just curious
  if you're open to an offer on it."*
- Foreclosure (testing for next cohort): *"I know you're probably getting absolutely blasted right
  now, but if you want someone that's actually able to help…"*
- Obituary: **address the heir by the heir's name** about the property — never the decedent's name.
- Solution route over education route: **cash offer → downsell to novation → downsell to listing**;
  if they want to save the house, genuinely tell them how (links, who to call) — the reciprocity
  brings them back. Their current walk-through deal came exactly that way.
- Sift the facts and tell the truth — "you're already better than 90% of the people in the sector."

**DNC and litigators** `[00:43:30]`: Ty does NOT scrub the DNC (removes ~60% of numbers; he removes
on request and never re-calls — "not an attorney"). He DOES scrub the **TCPA litigator list —
Blacklist Alliance is the number one** — and burns those numbers forever. On SMS-consent compliance:
*"All business has risk… if you have a low risk tolerance, I would not do this."* `[03:37:52]`

---

## 6. Trestle — restated with the 2,000-number experiment `[01:53:46]`

Phone activity score 0–100, **1.5¢/number**. Sign-up is free; usage-billed. Ty scored ~2,000 numbers
whose dispositions he already knew perfectly:

- Dial First (81–100): 881 numbers … tiers descend in bands of 20 exactly as the Phone Validator
  skill tags them (Dial First / Second / Third / Fourth / Drop).
- **"Every lead and every contract that we got was between a dial first and a dial second."**
- Net effect: **removed 60% of all phone numbers / dialed ~70% less** for the same leads and deals —
  and the callers stop dialing dead numbers, which is exactly the carrier-algorithm signal that gets
  numbers spam-flagged (nobody organically dials 5 disconnected numbers in a row).

**Use the Phone Validation API, not Real Contact:** Trestle's Real Contact / reverse-lookup products
are **not permitted for marketing use** — they'll deny the application. Phone Validation anyone can
use, it's cheaper, and the score is all this workflow needs (identity verification happens on the
phone anyway). `[02:19:41]` `[02:21:55]`

**Manual workflow (non-API users):** ready-to-call preset → Select All → Manage → **Export** with
phone numbers → Claude (Cowork or VS Code) + **Phone Validator skill** → it estimates cost first
(demo: 2 records / 5 phones = 7¢) and asks to confirm → say yes **+ add the litigation check** →
take the output CSV → records page → Upload file → **Update data → tag phones by phone number**.
Tags land as Dial First…Drop on each number. API users: this runs itself every morning. `[02:22:55]`

**Skip-trace order (multi-source only for FTM):** DataSift auto-skip (unlimited plans re-trace
daily; pay-per via Send To → Skip Trace off the wallet balance) → export → second/third source →
re-upload as *update* (new numbers append as #8, #9…) → Trestle last. Add `skip 2`/`skip 3` stages
to the conveyor if manual. Nick's shortcut: have Claude merge all the source CSVs into one upload.
Top vendors named: **DataSift, SmartSkip, Tracerfy, Skip Genie, DirectSkip**. **Forewarn** is free
for licensed agents (~250 lookups/mo, best accuracy Sam's seen) — but never automate against it or
they ban the account. `[02:10:28]` `[02:13:18]` `[02:33:28]`

---

## 7. Number Verifier + the spam war `[02:34:33]`

The segment Ty called 100% new — findings from his last ~2 weeks:

- **Every dialer buys from the same recycled number pool.** He bought 8 brand-new numbers from
  SmrtPhone: **all 8 arrived spam-flagged; 3 had existing FTC complaints** from previous owners.
  The "new numbers come clean" assumption is a myth.
- **Number Verifier** (numberverifier.com, owned by Blacklist Alliance): uploads your numbers, then
  its own real AT&T / T-Mobile / Verizon lines dial them so you see the label each carrier's
  subscribers actually see. Four reputation feeds behind the labels: two FTC complaint registries +
  Icehook + Nomorobo-style scores (~70+ = spam). When a number flags, it runs **automated
  remediation** with each carrier (~5 days). Pricing: ~$10/line, **$150/mo minimum (10 lines)**,
  annual contract with a 90-day escape. Setup requires a sales call, ~2 days to onboard.
- Reality check (Ty + Phil agree): **you will never be fully clean.** Labels flip daily — clean
  Friday, 3 carriers Sunday, 1 carrier Monday; at least a quarter of Ty's numbers are flagged on any
  given day. AT&T is the harshest. Contact rate still "went up a lot" since implementing.
- **Keep and clean numbers; stop churning them.** Old practice (drop a spammed number, buy new) is
  dead — the replacement arrives pre-flagged and remediation takes 5 days anyway. `[02:53:04]`
- **Register every number (free, mandatory): First Orion, Hiya, TNS + the Free Call Registry.**
  Ty's admin team does it; "must-haves." `[02:49:01]`
- **Priming is dead** (July's Phil trick): split-tested a week, no effect, unscalable at 10+ numbers
  per caller. `[02:57:45]`
- Cadence unchanged: **25 calls per number, 10 numbers per caller** (~250 dials capacity). `[02:57:09]`
- **Carrier root cause:** Telnyx + Twilio supply ~90%+ of dialer numbers; **Telnyx is having major
  issues** (the recent SmrtPhone connect-rate collapse). Ty's numbers were moving to Twilio that
  week; he'll report back. Don't try to switch providers yourself unless you're sophisticated —
  "just do SmrtPhone, do Number Verifier, register in the 3, and get rolling." `[02:59:46]` `[03:00:24]`
- The old **number-verifier Claude skill ≠ the platform** — the skill can't replicate the dedicated
  carrier lines; Assaf's summary "the poor man's choice" went uncontested. `[02:56:14]`
- Faiz's 5.5% connect rate diagnosed as spam labeling, not data quality. `[02:22:32]`

---

## 8. The two-way SMS agent (the day's flagship build) `[03:02:25]`–`[03:16:58]`

Fully autonomous texting on top of SmrtPhone + the API — in the SifStack repo as the **two-way text
SMS agent** (also on the agent org chart page). "You have no idea how much time it took me to build
that."

- **9am cron** pulls everything in the prospecting filter and schedules the day's sends — live
  Slack digest: 16 ready-to-call + 22 attempt-2 = 137 messages spread across **427 minutes**.
- Messages are **uniquely worded per record** (carrier fingerprint resistance — same reason as
  July's Text Touch Builder) and personalized from the record's distressors via the API — it reads
  the record, no preset-awareness needed. `[03:46:17]`
- **The AI answers replies** ("who's this?" → "Sorry for the random text, I'm with a small local
  team here in Knox County that buys a few houses a year — would you ever consider an offer?") and
  only stops + hands off to the human (Slack @mention) on an interested response. Say "small local
  team," never your real name. `[03:13:42]` `[03:33:44]`
- **STOP / wrong-number replies auto-disposition** through the API; STOP → DNC + **`Mail Only` tag**
  (they still get mail unless they refuse that too). `[03:31:03]` `[03:31:29]`
- **The killer SmrtPhone setting: outbound calls auto-use the number that texted that record** — the
  caller never manually rotates numbers again, and the callback ID matches the text thread. `[03:12:43]`
- **Text first, then call** — tested, no correlation on timing as long as the text went out first;
  texts are currently sliding past spam far better than calls, so lead flow holds up even when
  voice numbers are flagged. Fewer leads than blasting, but far more motivated. `[03:17:54]` `[03:18:23]`
- Results of the deliberately small pre-challenge test: **766 texts → 4 leads** in a week, "super
  high" reply rate; ~400 texts/day capacity on his current number count. Adriana's blended
  text+call flow: **3 contracts on ~30 leads in 4 weeks**.
- SMS attempts are tracked via the API on the record (an SMS-attempts counter field is coming to the
  UI next cohort); call attempts still gate the conveyor because he wants the human dial too. `[03:22:38]`
- Setup: download the repo, tell Claude "I'm trying to set this up" — it interviews you (company
  framing, provider, etc.). Works on other providers (Twilio, etc.) if you ask Claude to adapt it;
  SmrtPhone is the built-for baseline. Needs A2P approval through your provider. Smarter Contact is
  now redundant — its texting number can't also be your click-to-dial number, which breaks the
  continuity that makes this work. `[03:34:28]` `[03:32:08]`
- Why it wins: **full continuity** — the text, the voicemail, the call, and (coming) the email and
  mailer all come from the same real local person. "That level of connection and continuity from a
  personalization perspective at scale has not really existed, ever." Expect ~a year of arbitrage
  before the space catches up. `[03:29:11]` `[03:26:22]`
- Compliance: it's on you — "if you have a low risk tolerance, I would not do this." `[03:37:52]`

---

## 9. Not-interested + rehash (reactivation) `[03:56:40]`

Platform telemetry: ~4.5 million user actions/day. The standing stat, repeated:
**20–30% of ALL transactions on the platform come from not-interested campaigns.**

- A not-interested = **verified correct number** + status Not Interested. Most people never store
  the correct number and re-dial all five numbers next pass — the whole point is calling ONE number
  next time: *"Hey, I was just calling to see if you were still not interested in selling, or if
  anything had changed."*
- Ty's reactivation presets: **45 days** (Priority 1 / "Tier 2" data) and **90 days** (most other
  FTM). Changes driven by missed-deal autopsies: **probate 90 → ~40–45 days**; **foreclosure with an
  auction date: every 15 days**; pre-foreclosure ~30 (judicial-dependent).
- His correct-number bank: **~5,000**. The texting campaign alone banked **~135–140 correct numbers
  in a week** in hottest ready-to-call — at 20 doors per deal that's **≥7 sellers in the next 6
  months** already identified, ~8% of Knox market share from NI follow-up alone.
- **Rehash = 90 days**, callable numbers but never connected. He concedes they're behind on rehash
  (bandwidth) and it's the one place **bulk dialing is fine**; mail continues underneath regardless.
  Open question (Assaf): how to re-arm a not-interested for the next 45-day cycle without a status
  flip — Ty's interim answer is a sequence that creates a recurring follow-up task (Day 4), cleaner
  way TBD via Kylie.
- *"If I had to name the 3 biggest mistakes in all of REI, not tracking correct numbers is one of
  them."* First-day probate calls almost never sell right then — the follow-up is the deal.

---

## 10. Direct mail `[04:15:22]`

The three mailers that work (each has a challenge guide): **handwritten mailer**, **family postcard**
(literally Tyler with his wife and kids), **soft offer check** (looks like a government check — the
one of the three you can't send from inside Sift).

- "Handwritten" = **machine-handwritten with a real pen** (3D-printer-style rig) + Forever stamp —
  indistinguishable from grandma's letter. Vendor: **Open Letter Marketing** (integrates with his
  mail flow). Do NOT do the fake yellow-pad handwritten font — dead. Handwritten does especially
  well on obituaries.
- New tests: the SMS agent's personalization engine is being wired into mail (spin tokens + heavy
  per-record personalization); **soft offer check amounts now computed via the API** instead of the
  old 70–80%-of-estimated-value rule — high enough to ring phones, low enough to be safe.
- Cadence: **monthly to start** (he knows someone mailing weekly on all FTM data — "pretty wild";
  somewhere between is right). "We're moving into mailing everything."
- Obituary heirs get personalized handwritten mailers — full workflow on Day 3.

---

## 11. Claude / SifStack setup notes

- **RTK + Get Shit Done:** paste both repo links with the prompt *"I want you to take both of these
  public GitHub repos and implement them both. I want you to set them up as global CLAUDE.md settings
  that you use in every session going forward."* Claimed ~70% usage reduction. RTK link dropped in
  chat: `https://github.com/rtk-ai/rtk`. Global > per-project (per-project possible — Phil). `[00:10:03]`
- **Scraper stack for county CAPTCHAs:** **ScrapFly + 2Captcha + Apify** (rotating residential IPs) =
  "pretty much undetectable"; the code is already in SifStack — name the three tools and go. 2Captcha
  literally farms CAPTCHAs to humans. (Chat: scrapling also gets past Cloudflare — John Sterling.)
  `[00:41:53]`
- Claude **won't scrape aggregators** (auction.com, subscription sites) — invasive. Pull from the
  first-party county source (sheriff sales, recorder); the aggregators all get it there anyway. `[02:08:34]`
- Ty's daily driver: **Claude Desktop/Cowork for daily work, VS Code for building advanced
  workflows** — "using the most powerful model and VS Code is a rocket ship for driving around
  town." Skill edits (e.g. SMS templates) come out better in VS Code, where RTK/GSD apply. `[03:51:50]`
- The one-shot install (chat): `https://learn.datasift.ai/agent-org-chart` and
  `curl -fsSL https://raw.githubusercontent.com/DataSift-Ty-Personal/SiftStack/main/install.py | python3 -`.
  Yes, install all 74 agents / 9 divisions (Phil, chat). Only the SKILL.md files need to live in
  Claude — scripts/prompts folders get pulled from the internet on demand. `[03:38:38]`
- Community patterns from chat: Ryan Hawker runs SiftStack on a **Mac mini home server** so his
  data manager can use it remotely without touching his main machine; Basem triggers runs from a
  Google Sheets button; realistic setup time ~1 month+ even with SiftStack (Faiz).
- One-on-one setup isn't offered; AI-plan ($1,250/mo first county) customers get a **concierge
  onboarding** using DataSift's internal API. `[00:36:57]`

---

## 12. Odds and ends worth keeping

- **duyn / Harris County:** AI 95+ alone could run the whole business — huge turnover on that list.
  At $5K/mo spend: AI plan + a dialer + **one cold caller + mail**, total overhead under $5K; filter
  to top 5 zips (16,000 → ~1,000–1,500 records). Don't work a 15K-record list "at once" — Tyler:
  prioritize location/asset class, market to all of it over time. `[00:33:48]` `[00:37:xx]`
- **Judgment lien / estate sale (Craig, Lake County IN):** estate sales are often court-ordered
  sales chasing highest-and-best — low typical gross profit, "iffy." His winning combo: **absentee +
  low income + vacant** — Ty locked a deal on exactly that combination last week ("a banger").
  `[04:11:38]` `[04:12:16]`
- **Final judgment (FL, chat consensus):** final judgment = summary judgment issued in the
  foreclosure case, amount owed + auction date set — part of the same foreclosure pipeline; pulling
  from Sift beats going case-by-case at the county. `[00:52:34 chat]`
- **Combine counties?** (Wake + Durham) — OK for a single FTM niche when list counts are small, but
  the default is master one county first. **Depth beats breadth**: expand lists within your county
  (same two county websites cover his condemned, tax, liens, probate, foreclosure) before adding
  markets. `[04:09:28]` `[04:13:45]`
- **GoHighLevel / Left Main users:** run DataSift as the marketing arm, **webhook** hand-raises to
  your CRM (webhooks shipped last week); most eventually consolidate. CallTools can integrate but
  isn't built for click-to-dial — SmrtPhone is the path for this process. `[01:59:29]` `[03:01:29]`
- Records pulled but not yet pushed from SifMap sit "in the holding wings" — statuses (like Sold)
  stay live on them; Blount AI-90+ preset added 138 on Aug 4, one already sold before they got to it.
- Priming definition preserved for history: leave a 5–15 min connected call from a friendly phone,
  prospecting number hangs up. Now considered dead. `[02:58:24]`
- Skip-traced-disconnected numbers: Ty wants the API to auto-mark Trestle "Drop" numbers dead —
  "I've never seen a drop number from Trestle actually be the correct one." `[04:05:44]`
- Day-3 teasers: SmartSkip deep prospecting ("it is gonna shatter some minds"), obituary direct-mail
  personalization, deceased-record texting; Day-4: buyers from solds ("way better process"), the
  offer/walk process, sequences for recurring follow-up tasks.
- Challenge hub gets continuous minor updates (phone scoring guide now includes Number Verifier);
  a full overhaul with videos (~80 modules) targeted at the one-year anniversary. Recording posted
  same night; Ty answers **Facebook-group questions only during challenge week** (video replies). `[04:20:59]` `[04:04:30]`

---

## 13. Day 2 homework (implicit — Ty points at guides rather than a list)

1. Read the **Day 2 niche sequential marketing guide** and build at least ONE call flow or mail flow
   manually — even API users: *"if you do not understand it, you can't fact-check that Claude is
   correct."* `[00:59:xx]`
2. Build the **sold-property suppression** flow end-to-end (Day 1 guide, help-center video): SifMap
   pull ≥ Jan 2023 + ≥$1,000 → `Recently Sold` tag → status sequence → auto-add preset.
3. Sign up for **Trestle** (free account, 1.5¢/number) and run the Phone Validator skill on your
   ready-to-call export; upload the tags back via Update data → tag phones by phone number. Dial
   First/Second only.
4. Put every dialing number into **Number Verifier** and register all numbers with **First Orion,
   Hiya, TNS, and the Free Call Registry**.
5. Optional/advanced: install RTK + Get Shit Done as global CLAUDE.md; deploy the **two-way text SMS
   agent** from the repo ("I'm trying to set this up" and let Claude interview you).
6. Post questions in the Facebook group **this week** — that's the only window Ty answers them.
