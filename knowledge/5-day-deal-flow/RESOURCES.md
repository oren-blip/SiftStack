# Links Ty shared during the challenge

Pulled from the Zoom chat logs in `chat/`. Ty constantly says *"I put it in the chat"* during the
sessions — this is that chat. Raw logs are kept alongside because they also contain student questions
Ty answered verbally.

## August 2026 cohort — new since July (Day 1, 2026-08-17)

| Link | What it is |
|---|---|
| https://learn.datasift.ai/agent-org-chart | **Agent org chart** — posted 8+ times on Day 1; the new centerpiece page for the Claude/agent setup |
| `curl -fsSL https://raw.githubusercontent.com/DataSift-Ty-Personal/SiftStack/main/install.py \| python3 -` | **One-line SiftStack installer** — Ty now distributes his SiftStack repo (skills + workflows) via install script; he tells attendees to paste this into Claude and "download all of the skills and workflow that's inside of this repo" |
| https://learn.datasift.ai/county-list-playbook | **County list playbook** — appears to supersede the July `county-list-framework` link; same FIPS deep-link anchors (`#47093` = Knox TN, `#01073` = Jefferson AL) |
| https://learn.datasift.ai/deal-room | Deal room page |
| https://learn.datasift.ai/challenge-day-1 … /challenge-day-5 | Day hub pages — each links 13 written guide modules. **Sunset each cohort**; Day 1's guides are copied locally to `guides/day-1/` (fetch other days with `scripts/fetch_challenge_guides.py`) |
| https://github.com/rtk-ai/rtk | RTK — *"install this repo, will help token usage alot"* (moved up from a Day 3 mention in July to Day 1) |
| https://docs.google.com/spreadsheets/d/1cPMpqRckv-Z6dt3mz3YXh5c-KiFEi7Od/edit | Day 1 sheet (Ty's share, may be permissioned) |
| https://www.remotelatinos.com/ | Remote Latinos — VA/prospector hiring |
| https://www.macwhisper.com/ | MacWhisper — voice dictation (Mac alternative to WhisperFlow) |
| https://www.facebook.com/groups/1831529317509932 | Second Facebook group posted at close of Day 1 |

## August 2026 cohort — Day 2 (2026-08-18)

Links Ty posted in chat:

| Link | What it is |
|---|---|
| https://intercom.help/reisift/en/articles/15282418-how-to-update-and-manage-your-recently-sold-records | **Recently-sold records article** — the managing-sold-properties workflow (our monthly sold sweep implements this) |
| https://intercom.help/reisift/en/?q=tags | DataSift help center search for tag articles |
| https://www.forewarn.com/ | **Forewarn** — identity/phone lookup app; students report best direct-to-market accuracy; free through some MLS boards |
| https://numberverifier.com/ | **NumberVerifier** — spam-label checking for outbound caller IDs ($150/mo minimum per Phil). Carrier registration trio named in chat: **First Orion, Hiya, TNS** |
| https://github.com/rtk-ai/rtk | RTK again — Day 2 prompt: implement as global CLAUDE.md settings |
| http://scrapfly.io/ + https://2captcha.com/ + https://apify.com/ | Scraping stack (moved up from Day 3 in July; Apify newly added) |
| https://learn.datasift.ai/agent-org-chart | Agent org chart again (posted at open + close) |

Student/community links: https://tactiq.io/r/transcribing (Tactiq transcription), https://addleverage.com/ + https://realva.services/ + https://www.ninjaassistants.com/#hero + https://vainusa.com/apply/ (VA hiring services), https://code.visualstudio.com/ (VS Code for newcomers). Notable chat intel: "scrapling gets past cloudflare" (John Sterling); Ty hinted he's building his own caller-reputation site (per Ryan Hawker's read); Quo dialer mentioned as a smrtphone alternative.

## Challenge material

| Link | What it is |
|---|---|
| https://learn.datasift.ai/challenge-hub | Challenge Hub — the day-by-day landing page Ty screen-shares throughout |
| https://learn.datasift.ai/county-list-framework | **Doors Per Deal / county list framework.** The tool behind all the Priority 1/2/3 and lift-vs-baseline talk on Day 2 |
| https://learn.datasift.ai/niche-sequential-marketing | Niche sequential marketing guide — the click-by-click preset build |
| https://learn.datasift.ai/siftstack-setup | SiftStack setup guide |
| https://github.com/DataSift-Ty-Personal/SiftStack | Ty's own SiftStack repo |
| https://www.facebook.com/groups/reisift | DataSift/REISift community group (recordings posted here) |
| https://www.loom.com/share/a5e3fccd338945dea5af9f65811bfa16 | Loom shared on Days 3 and 4 |

County-list-framework deep links use FIPS anchors, e.g. `#47093` = Knox County TN, `#37119` = Mecklenburg NC.

## Tools referenced

| Link | Role |
|---|---|
| https://www.ipqualityscore.com/ | IPQS — **free plan only.** Powers the Caller Reputation Monitor skill (Day 2) |
| https://www.tracerfy.com/ | Tracerfy — one of the three skip-trace sources for FTM data |
| https://accounts.enformion.com/Join | Enformion / "Informium" — third skip-trace source (referral link Ty posted) |
| https://scrapfly.io/login | Scrapfly — scraping infrastructure (Day 3) |
| https://2captcha.com/ | 2Captcha — CAPTCHA solving (Day 3) |
| https://github.com/rtk-ai/rtk | RTK (Day 3) |
| https://github.com/lfiaschi/audiencekit | AudienceKit (Day 4) |

Trestle is discussed at length on Day 2 but its signup link wasn't posted in chat — see
`notes/day-2-key-teachings.md` §9 and the `phone-validator` skill.

## Spreadsheets / drives

These are Ty's shares and may be permissioned to challenge attendees:

- Day 2 sheet — https://docs.google.com/spreadsheets/d/1hdQxEIZ6D3aa730QeltCelvD1R7rZCvQ/edit
- Day 4 sheet — https://docs.google.com/spreadsheets/d/18TdhghJw5yE-BVJyrBDmto5oj4AjSkBJ/edit
- Drive folder — https://drive.google.com/drive/folders/1DWZSnXoOb690WIufayw7XmA4FfQsA0Xa
- Ty's own buying site (referenced as an example) — https://volunteerhomebuyers.com/
