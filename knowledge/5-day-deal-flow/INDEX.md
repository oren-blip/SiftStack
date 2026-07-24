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

| Day | Date | Topic | Transcript | Speakers named? | Notes | Video | Chat |
|-----|------|-------|-----------|---|-------|-------|------|
| 1 | 2026-07-13 (Mon) | Market research, county list framework / doors per deal, Claude REI skills library | ❌ | — | ❌ | ✅ | ❌ |
| 2 | 2026-07-14 (Tue) | **Niche sequential marketing** — call cadence, scripts, Trestle, team structure, KPIs | ✅ | ⚠️ numbered only | ✅ | ✅ | ✅ |
| 3 | 2026-07-15 (Wed) | **Deep prospecting** — obituary/probate heirs, multi-source skip tracing, SiftStack | ✅ | ✅ real names | ✅ | ✅ | ✅ |
| 4 | 2026-07-16 (Thu) | Sales — lead management, sequences, drips, rehab estimating, comping, AI call scoring | ✅ | ❌ captions only | ❌ | ✅ | ✅ |
| 5 | 2026-07-17 (Fri) | KPIs, Claude-powered reporting, calling volume | ❌ | — | ❌ | ✅ | ❌ |

Recordings are in `videos/` as `day-N-YYYY-MM-DD.mp4` (~3.4 GB total, gitignored).
Zoom chat logs are in `chat/`; the links from them are indexed in [RESOURCES.md](RESOURCES.md).

### Gaps worth closing

1. **Days 1 and 5 have no transcript at all** and can't be quoted.
2. **Day 4 is closed-captions only — no speaker labels.** You can read what was said but cannot
   attribute any quote to Ty vs. a student. Treat every Day 4 quote as unattributed.
3. **Day 2 has numbered speakers** ("Student 1/2/3") from AssemblyAI, not names.

All three are fixed the same way: download Zoom's **`*.transcript.vtt`** for that recording (Day 3
proves it exists — it yields real names like `Ty Garrett:` / `Tyler Austin:` / `Phil Loesch:`), then
re-import with `--force`. Prefer `.transcript.vtt` over `.cc.vtt` and over the AssemblyAI `.docx`
every time.

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
