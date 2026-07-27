# 5 Day Deal Flow Challenge — Reference Library

Ty Garrett's (DataSift) 5 Day Deal Flow Challenge, recorded 2026-07-13 → 2026-07-17.
This is where the **FTM (first-to-market) strategy** behind the NC probate pipeline comes from.

## How to use this

- **Looking for a specific teaching?** Read the `notes/day-N-key-teachings.md` file first — it's the
  distilled version with timestamps pointing back into the raw transcript.
- **Need Ty's exact words?** Grep the transcript in `transcripts/` for the timestamp or a phrase.
  Transcripts are diarized (`[HH:MM:SS] Speaker:`) and are ~230K characters each — grep, don't read whole.
- **Adding a new day?** `python scripts/import_challenge_transcript.py "<path to transcript>"` —
  handles `.docx`, `.md`, `.txt`; infers the day number and date from the filename.

## Status

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
