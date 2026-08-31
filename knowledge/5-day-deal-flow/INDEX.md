# 5 Day Deal Flow Challenge — Reference Library

Ty Garrett's (DataSift) 5 Day Deal Flow Challenge. The challenge re-runs monthly; this library
holds the **July 2026 cohort** (complete, 2026-07-13 → 17) and the **August 2026 cohort**
(in progress, started 2026-08-17). This is where the **FTM (first-to-market) strategy** behind
the NC probate pipeline comes from. When cohorts disagree, the August run is the current teaching.

## How to use this

- **Looking for a specific teaching?** Read the `notes/day-N-key-teachings.md` file first — it's the
  distilled version with timestamps pointing back into the raw transcript.
- **Need Ty's exact words?** Grep the transcript in `transcripts/` for the timestamp or a phrase.
  Transcripts are diarized (`[HH:MM:SS] Speaker:`) and are ~230K characters each — grep, don't read whole.
- **Adding a new day?** `python scripts/import_challenge_transcript.py "<path to transcript>"` —
  handles `.docx`, `.md`, `.txt`; infers the day number and date from the filename.

## Status

### August 2026 cohort (in progress)

| Day | Date | Topic | Speakers named? |
|-----|------|-------|---|
| [1](notes/day-1-2026-08-17-key-teachings.md) | 2026-08-17 (Mon) | **Market & data strategy** — Doors Per Deal v2 web tool (market-share stacking, per-county FTM Excel roadmap), first cohort with the DataSift API live, obituary timing split-tests, one-command install of the 74-agent/22-skill library | ✅ real names |
| [2](notes/day-2-2026-08-18-key-teachings.md) | 2026-08-18 (Tue) | **Niche sequential marketing** — tags/presets conveyor, sold suppression ("most important workflow"), Trestle 2,000-number experiment, Number Verifier spam playbook, autonomous two-way SMS agent, not-interested campaigns (20–30% of deals), team ladder. 4h17m, longest session; Tyler co-teaches | ✅ real names |
| [3](notes/day-3-2026-08-19-key-teachings.md) | 2026-08-19 (Wed) | **Deep prospecting** — skip-trace tiers explained, DataSift+SmartSkip+DirectSkip at $0.25–0.45/record (SmartSkip $0.15/hit returns 41 relatives in one call), "find the top 100 opportunities" account-wide ranking, one-shot account build via plan mode + Fable, handwritten mail to 3–6 heirs per record. 2h37m, lightest day; API-gated throughout | ✅ real names |
| [4](notes/day-4-2026-08-20-key-teachings.md) | 2026-08-20 (Thu) | **Sales & deal analysis** — lead grading flipped (walk + offer on 1–2 pillars; July's 80%-of-Zestimate rule is gone), STABM auto board+task on New Lead, private lender package w/ term sheet (first time taught), buyer-prospector dispo flow ("top 25 Knox buyers", "replaces InvestorLift"), rehab estimate from walkthrough VIDEOS (3014 Sanland: $240K ask → $92K contract), ~30% of obituary deaths ever get probate + the obit+2yr-tax-delinquent curative stack, Facebook vendor/buyer scraping skills (use Opus, NOT Fable — Fable refuses scrape-shaped work), Enformion partially back as "Enformion Go" for entity skip tracing ($0.15/lookup). ~3h16m | ✅ real names |
| 5 | 2026-08-21 | *not yet imported* — AI call-scoring, Gemini transcription tip, two-scenario teardown all deferred here from Day 4 | — |

Each August notes file opens with a **"What changed since the July cohort"** section — read that
before quoting July numbers. Headline Day 1 deltas: DataSift API shipped (Deal Room beta), Ty
resumed FTM probate (July's "paused entirely" is stale), Claude model advice now Opus 5 default,
AI plan threshold lowered to $3–5K/mo spend.

**Written guides:** the August Challenge Hub links written modules per day (13 on Day 1, 6 on
Day 2, 2 on Day 3, 9 on Day 4). Local copies live in [guides/day-1/](guides/day-1/), [guides/day-2/](guides/day-2/), [guides/day-3/](guides/day-3/) and [guides/day-4/](guides/day-4/)
(start at each folder's `README.md` digest — it says which guide holds which table so you don't
have to open them all). Fetch future days with `python scripts/fetch_challenge_guides.py <day>`
the week they air — **hub pages are sunset each cohort**, so the local copy is the durable one.

The remaining August days import with
`python scripts/import_challenge_transcript.py "<downloaded .transcript.vtt>"` — the 8/18–8/21
dates auto-map to Days 2–5.

Day 3's downloadable assets (skill file, example research pack, tech-stack SOP, and the 83-resource
hub sheet whose Day 4–5 tabs are already populated) are in
[guides/day-3/downloads/](guides/day-3/downloads/) — see that folder's `README.md`.
Day 4's 15 archived assets (buyer-prospector / comping / rehab-estimator / lead-manager-coach
skills, the datasift-lead-management plugin, drip SOP PDF, the 5532 Joyce Ann comp + rehab
workbooks, the Investor Bootz sample inspection report, and three chat-only files incl. the Knox
top-25-buyers output) are in [guides/day-4/downloads/](guides/day-4/downloads/).

### July 2026 cohort (complete)

**All five days are transcribed and distilled.**

| Day | Date | Topic | Speakers named? |
|-----|------|-------|---|
| [1](notes/day-1-key-teachings.md) | 2026-07-13 (Mon) | **Market research & data strategy** — pendulum theory, doors per deal, the marketing funnel, obituary vs probate, curative title, blueprints | ✅ real names |
| [2](notes/day-2-key-teachings.md) | 2026-07-14 (Tue) | **Niche sequential marketing** — call cadence, scripts, Trestle, team structure, KPIs, door knocking | ⚠️ numbered only |
| [3](notes/day-3-key-teachings.md) | 2026-07-15 (Wed) | **Deep prospecting** — obituary heirs, multi-source skip tracing, Deep Prospecting v4, SiftStack | ✅ real names |
| [4](notes/day-4-key-teachings.md) | 2026-07-16 (Thu) | **Sales** — 4 pillars, STABM, lead cadences, AI call scoring, comping, rehab estimating | ❌ **captions only** |
| [5](notes/day-5-key-teachings.md) | 2026-07-17 (Fri) | **Scaling & operations** — audit, budgets/runway, KPI engine, hiring workflow, SOPs, D4D model | ✅ real names |

Recordings are in `videos/` as `day-N-YYYY-MM-DD.mp4` (~3.4 GB total, gitignored).
Zoom chat logs are in `chat/`; the links from them are indexed in [RESOURCES.md](RESOURCES.md).

### Transcript quality — read before quoting

- **Days 1, 3, 5** — Zoom `.transcript.vtt` with real names (`Ty Garrett:`, `Tyler Austin:`,
  `Phil Loesch:`). Trustworthy.
- **Day 2** — AssemblyAI, speakers are `Student 1/2/3` by voice. A long Ty monologue occasionally
  gets split onto a student label; check surrounding turns before attributing.
- **Day 4** — closed captions, **no speaker labels at all**. Content is reliable, attribution is not.
  Never quote a named person from Day 4 without checking the recording.

If Zoom ever produces a `.transcript.vtt` for Days 2 or 4, re-import with `--force` — named speakers
beat both the AssemblyAI file and the captions.

## Speaker key

Transcripts are auto-diarized, so speakers are identified by voice, not by name:
- **Ty** — trainer/host, ~81% of talk time. Reliable.
- **Student 1 / 2 / 3** — distinct voices numbered by first appearance. **Consistent within a
  transcript but not tied to real identities**, and diarization sometimes splits a single long Ty
  monologue across a student label. When a quote matters, check the surrounding turns.

Named participants who recur and are worth knowing:
- **Tyler** — DataSift co-founder. Owns the obituary/deceased-data and recently-sold-audit segments.
- **Phil** — power user. Source of the phone-warming trick and the pre-call texting idea.

## Cross-references into this repo

Teachings from the challenge that are already implemented here:

- **FTM strategy** → the entire NC probate pipeline (`src/nc_*`, `fix_addresses_and_prep.py`)
- **Deep prospecting on heirs** → `nc_deep_prospect.py`, `src/obituary_enricher.py`
- **Trestle phone scoring / dial tiers** → `.claude/skills/phone-validator/`
- **Caller reputation / number rotation** → `.claude/skills/caller-reputation-monitor/` (installed at `C:\tools\caller-reputation`)
- **4-touch SMS sequence** → `.claude/skills/text-touch-builder/`
- **Niche sequential filter presets** → `.claude/skills/sequential-presets/`, `src/niche_sequential.py`
