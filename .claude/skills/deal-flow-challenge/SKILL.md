---
name: deal-flow-challenge
description: Answer questions from Ty Garrett's 5 Day Deal Flow Challenge — the training the FTM (first-to-market) strategy comes from. Use whenever the user asks what Ty taught, what the challenge said about something, or asks about pendulum theory, doors per deal, the county list framework, lift vs baseline, the marketing funnel and sales cycles, obituary vs probate data, curative title, niche sequential marketing, call attempt cadence, cold call or foreclosure scripts, the 4 pillars of motivation, STABM, lead statuses and follow-up cadences, rehash / not-interested campaigns, Trestle phone scoring and dial tiers, caller reputation and number rotation, text touch builder, deep prospecting on heirs, multi-source skip tracing, Enformion / Tracerfy / Scrapfly, SiftStack and Claude Code setup, AI call scoring, comping or rehab estimating workflows, the replacement ladder or team structure, prospector KPIs and dial targets, hiring workflows, SOPs, door knocking routes, or recently-sold loss audits. Also use when the user says "what did Ty say about X", "how does the challenge handle X", "look this up in the challenge", or wants to check current SiftStack work against how the challenge teaches it.
---

# 5 Day Deal Flow Challenge

A local, searchable copy of Ty Garrett's (DataSift) 5 Day Deal Flow Challenge. The challenge
re-runs monthly; this library holds the **July 2026 cohort (complete, 2026-07-13 → 17)** and the
**August 2026 cohort (in progress, from 2026-08-17)**. It is the source of the FTM strategy behind
the NC probate pipeline. When cohorts disagree, the newer cohort reflects current DataSift features
— cite the newer one but mention what changed.

## Where things are

Everything lives under `knowledge/5-day-deal-flow/`:

- `INDEX.md` — status table per cohort: which days have transcripts, how good each one is, cross-references
- `notes/day-N-key-teachings.md` (July cohort) and `notes/day-N-YYYY-MM-DD-key-teachings.md` (later
  cohorts) — **start here.** Distilled teachings with `[HH:MM:SS]` timestamps pointing back into the
  raw transcript. August notes carry a "what changed since July" section
- `transcripts/day-N-YYYY-MM-DD.md` — full transcripts, ~170–240K characters each
- `RESOURCES.md` — every link Ty shared in chat (Challenge Hub, county list framework, tool signups)
- `chat/` — raw Zoom chat logs, which also carry student questions Ty answered out loud

## How to answer a question

1. **Read `INDEX.md`** to see which days are actually transcribed. Only transcribed days can be
   quoted; do not answer for a day that has no transcript — say it isn't transcribed yet.
2. **Read the relevant `notes/day-N-key-teachings.md`.** Most questions are fully answered there,
   and the notes carry the exact numbers, tiers, and scripts.
3. **Grep the transcript** (never read it whole — they're huge) when the user wants Ty's exact
   words, more context around a claim, or something the notes don't cover. Search for a distinctive
   phrase, or jump to a timestamp cited in the notes.

## Rules

- **Quote accurately or not at all.** These are real numbers Ty tested against real spend. Don't
  round, don't smooth, don't invent a figure that "sounds right." If the notes say 62.4% answer
  rate or 22.6 doors per deal, use those.
- **Attribute correctly, and know how good the labels are.** Transcript quality varies per day and is
  stated in each file's header and in `INDEX.md`:
  - *Zoom transcript* — real names (`Ty Garrett:`, `Tyler Austin:`, `Phil Loesch:`). Trustworthy.
  - *AssemblyAI* — `Student 1/2/3` by voice, not name; a long Ty monologue sometimes gets split onto
    a student label. Check surrounding turns before attributing.
  - *Closed captions* — **no speaker labels at all.** Never attribute a quote from these to anyone;
    say the transcript doesn't identify the speaker.

  Ty taught most of the material. Tyler Austin (co-founder) owns the obituary/deceased-data and
  recently-sold-audit segments; Phil Loesch (power user) contributed the phone-warming and pre-call
  texting ideas.
- **Flag staleness, and prefer the newest cohort.** Each answer should say which cohort it came
  from. The July run discussed features that were unreleased at the time (the DataSift API,
  records-page auto-update); the August run is the current teaching. If a question depends on a
  feature's status, say when the session was recorded and that it may have shipped since.
- **Prefer the challenge's own vocabulary** — doors per deal, lift vs baseline, niche vs bulk
  sequential, call attempt 1/2/3, rehash, not-interested campaign, dial first/second, the four
  pillars of motivation. The user thinks in these terms.

## When the user asks to add a day

New transcripts go through the importer, which normalizes them and files them by day:

```
python scripts/import_challenge_transcript.py "C:/Users/omark/Downloads/DAY 3 ...docx"
```

It accepts `.docx`, `.md`, and `.txt`, infers day number and date from the filename (override with
`--day` / `--date`), and writes to `knowledge/5-day-deal-flow/transcripts/`. After importing, read
the new transcript and write the matching `notes/day-N-key-teachings.md`, then update the status
table in `INDEX.md`.
