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

## August 2026 cohort — Day 3 (2026-08-19)

Links Ty posted in chat:

| Link | What it is |
|---|---|
| https://smartskip.io/ | **SmartSkip** — the day's "big unlock" second skip-trace source, $0.15/hit. One hit returned 41 associated relatives with phones. Non-affiliate |
| https://get.directskip.com/easylists/ | **DirectSkip** — the third source; Ty is migrating off Tracerfy to this for teaching simplicity. Non-affiliate |
| https://learn.datasift.ai/agent-org-chart | Agent org chart again — 9 divisions / 74 agents / 22 skills |
| https://learn.datasift.ai/deal-room | Deal Room — the only way to get API access before the end-of-September public rollout (110 members at the time of the call) |
| https://learn.datasift.ai/county-list-playbook#39049I | County list playbook, deep-linked to a specific FIPS |

Day 3's downloadable assets are archived locally in [guides/day-3/downloads/](guides/day-3/downloads/):
the Deep Prospecting skill file (byte-identical to our installed copy), Ty's example research pack for
5100 Stokely Ln, the Deal Flow Tech Stack SOP spreadsheet, and the 83-resource hub sheet — whose
**Day 4 and Day 5 tabs are already populated**. Two items listed on the Day 3 sheet have no URL
anywhere on the hub: the Day 3 Workbook PDF (email/Zoom-chat attachment) and
`probate-property-finder.skill` (already installed).

Student/community links: https://tactiq.io/r/transcribing (Tactiq again). Notable chat intel: Nick
Redmond posted full door-knocking metrics for 6/3–8/17/26 — 95 hrs, 188 doors, 59 contacts, 11 leads,
4 contracts, $52,500 gross profit logged.

## August 2026 cohort — Day 4 (2026-08-20)

Links Ty posted in chat:

| Link | What it is |
|---|---|
| https://learn.datasift.ai/county-list-playbook#47093 | County list playbook deep-linked to Knox County TN |
| https://intercom.help/reisift/en/articles/14646968-how-to-the-lead-manager-playbook-turning-marketing-dollars-into-closed-deals | **Lead Manager Playbook article** — the day's lead-management segment follows it |
| https://intercom.help/reisift/en/articles/7156704-managing-sold-properties | Managing Sold Properties article (posted twice; our sold sweep implements this) |
| https://drive.google.com/drive/folders/1yDo99yx34scB_EpUuM02_3pneCQwhkDn | **3014 Sandland walkthrough videos** — folder of phone videos Ty fed to Claude for the rehab-from-video demo (not archived locally, large media) |
| https://docs.google.com/spreadsheets/d/1imTEnS7UbuM15LEJR0Qqu3fby1KWOfAm/edit | **Private Lender Package** for 3014 Sanland Ave Knoxville — archived as `guides/day-4/downloads/private-lender-package-3014-sanland.xlsx` |
| https://docs.google.com/spreadsheets/d/100BqEVosr2Ngn4YWvUQo09zquWTvnJN5/edit | **Knox top-25 buyers output** from the buyer-prospector live demo — archived as `guides/day-4/downloads/knox-top-25-buyers-example.xlsx` |
| https://drive.google.com/file/d/17sHGwdaLH2VQJqSnaIbHv-S0C659uS0d/view | 20-page homeowner-facing foreclosure guide (lead-magnet example) — archived as `guides/day-4/downloads/foreclosure-homeowner-guide-knox-example.pdf` |
| https://www.facebook.com/groups/KnoxRealEstateInvestors | Knox REI Facebook group — target of the vendor-directory and every-3-hours deal-scrape prompts |
| https://learn.datasift.ai/agent-org-chart | Agent org chart again (posted at close) |

**Prompts Ty pasted in chat** (he types the prompt into chat, then runs it live): rehab-from-video
(3014 Sandland ZIP + comp package, "closely mirror the finishes that are on the comps... do not
overrenovate"); fix the phone-validator skill with skill-creator (Trestle API errors + support
screenshots); "top 25 buyers in Knox County" via buyer-prospector (remove government agencies +
iBuyers, local cash buyers only); clone the SiftStack repo into a private team GitHub repo; vendor
directory from the Knox REI Facebook group ("every single trade... to flip a house"); scheduled task
scraping that group every 3 hours 9am–9pm via the Chrome Extension.

Day 4's hub downloads (4 skills/plugins, drip SOP PDF, 5532 Joyce Ann comp + rehab workbooks,
Investor Bootz sample inspection report, fresh tech-stack SOP + 83-resource hub sheet) are archived
in [guides/day-4/downloads/](guides/day-4/downloads/) — see that folder's `README.md`, including the
Day-4-sheet items with no public URL (`deal-analyzer.plugin`, `sift-operations.plugin`, the 3
interactive HTML guides, Default Account Setup guide).

Student/community links: https://tactiq.io/r/transcribing (Tactiq again),
https://www.ninjaassistants.com/discovery-call + https://vainusa.com/apply/ (DataSift-trained VA
hiring). Notable chat intel: kev hernandez's "Ty's Enemies: Bulk, Drip Campaigns, PPL"; duyn paid
$125–150/address on PPL; Eddie Briant scrapes probates in 7 of 21 NJ counties; Christian Hernandez
distills the day's list reveal as "obituary + 2 years tax del"; replays sunset when next month's
challenge replaces them (download the week of).

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
