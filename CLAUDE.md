# CLAUDE.md — SiftStack

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SiftStack** — Full-stack real estate investing operations platform built around DataSift.ai CRM. Covers the entire REI business lifecycle:

1. **Data Acquisition:** Web scraping tnpublicnotice.com (foreclosures, tax sales, probates), scanned PDF import, courthouse terminal photo import (probate, eviction, code violations, divorce), Dropbox auto-polling
2. **Enrichment Pipeline:** 10+ steps — Smarty address standardization, Zillow property data, Knox County Tax API, obituary/heir research, Ancestry.com SSDI, Tracerfy skip trace, Trestle phone scoring, entity research
3. **Deal Analysis:** Comparable sales (Two-Bucket ARV), rehab estimation (4-tier room-by-room), deal analyzer (MAO/ROI/financing scenarios)
4. **Market Intelligence:** Zip code scoring, Market Finder reports, cash buyer list building, investor portfolio analysis
5. **CRM Automation:** DataSift upload, 26 TCA sequence templates, 12 niche sequential marketing presets, filter preset management, SiftMap sold property tagging
6. **Lead Management:** 4 Pillars of Motivation auto-qualification, STABM daily routine, pipeline reporting, deep prospecting (4-level framework)
7. **Operations:** Acquisition playbook generator (SOPs, scripts, checklists), Slack/Discord notifications, Google Drive upload, Apify Actor deployment

Currently focused on Knox and Blount counties, Tennessee.

8. **REI Skill Library:** 13 Claude Co-Work skill files (`.skill`/`.plugin` ZIPs) for distribution to DataSift community via [learn.datasift.ai/claude-skills-rei](https://learn.datasift.ai/claude-skills-rei). Skills teach Claude specific REI workflows when uploaded to Co-Work sessions or Projects.

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # then fill in credentials

# Run
python src/main.py daily                          # new notices since last run
python src/main.py historical                     # last 12 months of data
python src/main.py daily --split                  # separate CSV per county+type
python src/main.py daily --counties Knox          # only Knox county
python src/main.py daily --types foreclosure,probate  # only specific types
python src/main.py daily -v                       # verbose/debug logging

# NC probate weekly scrape (use scripts/nc_weekly_scrape.bat for defaults)
scripts\nc_weekly_scrape.bat                      # last 7 days, all 7 NC counties
scripts\nc_weekly_scrape.bat 2026-05-18           # from a specific date

# DataSift preset/sequence management
python src/main.py manage-presets --discover                      # list all presets and sequences
python src/main.py manage-presets --add-sold-exclusion            # add Sold exclusion to all presets
python src/main.py manage-presets --create-sold-sequence          # create Sold cleanup sequence
python src/main.py manage-presets --all                           # discovery + update + sequence

# SiftMap sold property tagging (monthly sold sweep — build 1.0.34+)
python src/main.py manage-sold --counties Cabarrus,Catawba,Gaston,Iredell,Lincoln,Mecklenburg,Rowan --months-back 1 --headless
python src/main.py manage-sold --counties Mecklenburg --dry-run --headless   # count-only, adds nothing
python src/main.py manage-sold --keep-strangers ...               # pull + tag but skip the stranger delete
python src/main.py manage-sold --delete-strangers-only --sold-tag-date 2026-06 --dry-run   # preview the delete filter
scripts\manage_sold_monthly.bat --watch                           # supervised run, visible browser
# Scheduled: Task Scheduler "SiftStack Sold Sweep", 1st of month 12:00 (from Sep 2026)

# Courthouse photo import (build 1.0.28+)
python src/main.py photo-import --folder ./photos --photo-county Knox --photo-type probate
python src/main.py photo-import --folder ./photos --photo-county Knox --photo-type eviction --skip-obituary
python src/main.py dropbox-watch                                  # auto-poll Dropbox for new photos
python src/main.py dropbox-watch --poll-interval 300 --max-polls 5  # 5-min interval, 5 cycles
python src/main.py dropbox-watch --no-delete                      # keep photos in Dropbox after processing
```

All source files are in `src/` and imports assume `src/` is the working directory. Run from project root with `python src/main.py` or set `PYTHONPATH=src`.

## Architecture

**Data flows:**
- **Web scrape:** `main.py` → `scraper.py` → `captcha_solver.py` → `notice_parser.py` + `foreclosure_filter.py` → enrichment → CSV
- **PDF import:** `main.py` → `pdf_importer.py` (pypdfium2 → `image_utils.py` OCR) → enrichment → CSV
- **Photo import:** `main.py` → `photo_importer.py` (OpenCV → `image_utils.py` OCR → `llm_parser.py`) → enrichment → CSV
- **Dropbox watch:** `dropbox_watcher.py` → `photo_importer.py` → enrichment → CSV (auto-polling loop)
- **Market Finder:** `extract_market_finder.py` → DataSift Market Finder (Playwright) → paginate all ZIP + neighborhood data → JSON → `generate_knox_report.py` → 7-sheet Excel

- **main.py** — CLI entry point. Parses args (`daily`/`historical`, `--split`, `--counties`, `--types`, `-v`). Filters saved searches by county/type, orchestrates scrape → dedup → export, logs run summary stats.
- **scraper.py** — Playwright browser automation. Reuses saved session cookies when possible, falls back to fresh login. Selects each saved search from the Smart Search dropdown (triggers ASP.NET postback), paginates results (50/page max), clicks each View button to open notice detail pages. Uses `last_run.json` for daily mode state, `cookies.json` for session persistence.
- **captcha_solver.py** — Solves reCAPTCHA v2 via **2Captcha API** on every notice detail page. Sends websiteURL + sitekey, gets back a `g-recaptcha-response` token, injects it, clicks "View Notice". Retries up to 3 times. This is the primary bottleneck (~10-30s per notice).
- **notice_parser.py** — Extracts structured fields from raw notice text using regex. There are NO structured HTML fields on the site — address, owner, dates are all embedded in free-text notice bodies. Defines the `NoticeData` dataclass used throughout.
- **foreclosure_filter.py** — Filters foreclosure search results to only keep real first-to-market trustee sales. Matches against observed title variations (substitute/successor trustee sales). Non-foreclosure notice types pass through unfiltered.
- **data_formatter.py** — Deduplicates by address (keeps most recent), then converts `NoticeData` list to Sift upload CSV. Split mode produces `{county}_{type}_{timestamp}.csv` files.
- **config.py** — Credentials (from `.env`), ASP.NET element selectors, saved search definitions, rate limiting constants, paths, image processing thresholds.
- **image_utils.py** — Shared OCR utilities used by both `pdf_importer.py` and `photo_importer.py`. Exports `fix_rotation()` (Tesseract OSD) and `ocr_page(image, psm)` with configurable page segmentation mode. Handles Tesseract binary detection.
- **photo_importer.py** — Courthouse phone photo import. OpenCV preprocessing chain (EXIF transpose → blur check → bilateral filter → perspective correction → Otsu threshold) → Tesseract OCR (PSM 4) → LLM parsing → NoticeData. Supports all 7 notice types.
- **dropbox_watcher.py** — Cursor-based Dropbox folder polling. Downloads new photos, resolves county + notice_type from folder path (`/Knox/eviction/photo.jpg`), processes through photo_importer, deletes from Dropbox after success. State persisted to `dropbox_state.json` + `photo_state.json`.
- **report_generator.py** — Generates per-record PDF deep prospecting reports using reportlab. Includes property summary, signing chain with phone tiers, valuation, deceased owner detection. Output to `output/reports/`.
- **extract_market_finder.py** — Playwright automation to extract ALL ZIP code + neighborhood data from DataSift Market Finder. Handles styled-component dropdowns, pagination (20 rows/page), Beamer popup dismissal. Outputs JSON. See "Market Finder Extraction Patterns" below.
- **market_analyzer.py** — ZIP code scoring engine. 6-factor weighted composite (Distress 30%, Value 20%, Equity 15%, Tax Delinquency 15%, Competition 10%, DOM 10%). Grades A/B/C/D, budget allocation across top ZIPs. Reads from scraped notice CSVs in `output/`.
- **drive_uploader.py** — Google Drive upload via service account. `upload_file()` (generic, returns webViewLink) and `upload_csv()` (CSV-specific, returns file ID).

## Site-Specific Details

The site is **ASP.NET WebForms** — all navigation uses `__doPostBack()` with ViewState. Session IDs are embedded in URL paths (`/(S({guid}))/`). Playwright is required because direct HTTP requests would need to manage ViewState/EventValidation manually.

**reCAPTCHA v2 is required on every single notice detail page**, even when logged in. There is no CAPTCHA on login, search, or results pages. The sitekey is hardcoded in `config.py`.

## Saved Searches

8 searches defined in `config.py` as `SAVED_SEARCHES`. Each maps to an exact dropdown option name on the Smart Search dashboard:
- Knox & Blount × (Foreclosure V2, Tax Sale V2, Tax Delinquent V2, Probate V2)

Filterable via `--counties` and `--types` CLI args (comma-separated, or omit for all).

## Key Domain Rules

- **Foreclosure filtering is critical.** Not all notices from "Foreclosure" saved searches are actual foreclosures. The scraper parses each notice's full text and only includes ones with trustee sale language. See `INCLUDE_PHRASES` / `EXCLUDE_PHRASES` in `foreclosure_filter.py`.
- **Probate owner_name** should be the Personal Representative/Executor/Administrator — not the deceased.
- **Owner names** in foreclosure notices typically appear after "executed by" in the deed of trust language.
- **Rate limiting:** 2-3 second random delays between requests, 3 retries per page.
- **Address dedup:** Same property can appear in multiple notices; `data_formatter.deduplicate()` keeps the most recent.

## Output

CSV files land in `output/` (gitignored). Logs go to `logs/` with timestamped filenames. Sift columns: `date_added, address, city, state, zip, owner_name, notice_type, county, source_url`.

## Apify Deployment

The project runs as an **Apify Actor** in the cloud. When `APIFY_IS_AT_HOME` or `APIFY_TOKEN` is set, `main.py` uses the Actor SDK instead of CLI args.

```bash
# Install Apify CLI
npm install -g apify-cli

# Local test (reads input.json, simulates Actor environment)
apify run --purge

# Deploy to Apify platform
apify login
apify push

# On Apify Console: set up daily schedule and configure secrets in Actor input
```

### Actor Input (configured in Apify Console or `input.json`)
- `mode`: "daily" or "historical"
- `counties` / `types`: arrays to filter saved searches (empty = all)
- `tn_username`, `tn_password`, `captcha_api_key`: secrets (required)
- `google_drive_folder_id`, `google_service_account_key`: optional Google Drive upload

### Actor Output
- **Dataset**: structured records pushed via `Actor.push_data()`
- **Key-value store**: `output.csv` backup
- **Google Drive** (optional): CSV + summary text file uploaded via service account

### Key Files
- `.actor/actor.json` — Actor manifest (name, version, Dockerfile path)
- `.actor/input_schema.json` — Input fields + validation for Apify Console UI
- `Dockerfile` — Based on `apify/actor-python-playwright:3.12`
- `src/drive_uploader.py` — Google Drive upload via base64-encoded service account key
- `input.json` — Local test input (gitignored, contains credentials)

## Courthouse Photo Pipeline (build 1.0.28+)

Courthouse terminal photos → OCR → LLM parse → enrichment → DataSift. Runner takes phone photos at Knox/Blount county terminals, uploads to Dropbox organized as `{county}/{notice_type}/`, system auto-processes.

### Notice Types (7 total)
- `foreclosure`, `tax_sale`, `tax_delinquent`, `probate` — existing from web scraper
- `eviction` — plaintiff = landlord (target contact), defendant = tenant
- `code_violation` — owner of record, violation type, compliance deadline
- `divorce` — petitioner + respondent, property from schedule page

### Critical OCR Patterns (hard-won from live testing)

**Moire pattern from terminal screens is the #1 OCR killer.** Standard Tesseract preprocessing (adaptive threshold, CLAHE) produces garbage on courthouse terminal photos. The fix:
- **Bilateral filter** (`cv2.bilateralFilter(gray, 15, 75, 75)`) removes moire while preserving text edges
- **Otsu threshold** (`cv2.THRESH_BINARY + cv2.THRESH_OTSU`) after bilateral — auto-determines optimal binary threshold
- **PSM 4** (single column variable text) for terminal screens — NOT PSM 6 (single uniform block) which was the research recommendation but fails in practice
- **Do NOT use `fix_rotation()` (Tesseract OSD) on phone photos** — EXIF transpose handles rotation. OSD on raw phone images often fails and the 270° fallback rotates correct images sideways

### Probate Deep Prospecting (from courthouse terminals)

Courthouse probate records have decedent name + PR/executor name but NO property address. Multi-tier lookup fills the gap:

**Property Address Lookup** (Step 3c in enrichment pipeline):
1. **Tier 1: Knox Tax API name search** — search `/parcels/{decedent_name}`, score by token overlap (FIRST MIDDLE LAST → LAST FIRST MIDDLE), accept >= 0.4 match. Tries multiple name variations (with/without suffix, LAST FIRST format, first+last only).
2. **Tier 2: Executor family search** — search Knox Tax API by executor name, look for properties where decedent's last name appears in owner field (family property transferred to executor).
3. **Tier 3: People search** — search TruePeopleSearch/FastPeopleSearch for decedent's last known Knox County address.

**Probate Preset** (obituary enricher):
- Triggers when court record has PR name + decedent name (no address required) — prevents wrong obituary from overriding court-named executor
- Sets DM = the named PR/executor directly, skips obituary search entirely
- Then runs DM address lookup (Knox Tax API → People Search → Tracerfy)

**DOD Sanity Check** (obituary enricher):
- Rejects obituary matches where DOD is > 3 years before the notice filing date (`MAX_DOD_GAP_YEARS = 3`)
- Prevents matching a 2014 obituary to a 2025 court filing (wrong person with same name)
- Applied to both full-page and snippet matches

### Dropbox Folder Structure
```
{DROPBOX_ROOT_FOLDER}/
├── Knox/
│   ├── eviction/
│   ├── code_violation/
│   ├── divorce/
│   ├── foreclosure/
│   ├── tax_sale/
│   └── probate/
└── Blount/
    └── (same subfolders)
```

### Environment Variables
- `DROPBOX_APP_KEY` — Dropbox OAuth2 app key
- `DROPBOX_APP_SECRET` — Dropbox OAuth2 app secret
- `DROPBOX_REFRESH_TOKEN` — Dropbox offline refresh token (auto-rotates access tokens)
- `DROPBOX_POLL_INTERVAL` — seconds between polls (default 900 = 15 min)
- `DROPBOX_ROOT_FOLDER` — root folder path in Dropbox (e.g., "TN Public Notice")

### Dependencies (added to requirements.txt)
- `opencv-python-headless>=4.13.0` — image preprocessing (headless = no GUI, saves 26MB in Docker)
- `numpy>=1.26.0` — required by OpenCV
- `dropbox>=12.0.2` — Dropbox SDK (minimum for post-Jan-2026 API compatibility)

## NC Probate Pipeline (Phase 2 — 7-county expansion)

Built on top of the TN pipeline but with distinct conventions:

**One-command weekly run** (`scripts/nc_weekly_run.bat`) — wraps the entire 6-step pipeline:
```
scripts\nc_weekly_run.bat                  # last 7 days
scripts\nc_weekly_run.bat 2026-05-18       # from a specific date
```
Steps it runs in sequence: scrape → merge by ISO week → manual archive index refresh → polish pipeline → eCourts name-search backfill → consolidate workbook. All output appends to `logs/nc_weekly_run.log`. Final workbook: `output/FTM_YYYY_NC_Estates_throughWeekN.xlsx`.

**Scheduling model — daily workbook (build 1.0.33+).** One Windows Task Scheduler job:
- **`SiftStack NC Daily Build`** → `scripts/nc_daily_run.bat`, daily 5 PM. Full pipeline: scrape last 2 days → merge by ISO week → archive index refresh → polish → eCourts backfill → consolidate workbook. Skips weekends + NC court holidays (`scripts/is_workday.py`) and takes the pipeline lock. Logs to `logs/nc_daily_run.log`.
- The current (non-archived) week is re-polished each night until it's archived, so the workbook is fresh every morning. `scripts/nc_weekly_run.bat` remains as the manual full-week (7-day) catch-up build.
- `scripts/nc_daily_scrape.bat` exists as an optional scrape-ONLY helper (accumulate raw cases without rebuilding) but is **not scheduled** — the daily build covers the normal case.

**Persistent GIS cache** (build 1.0.33+) — because the daily build re-polishes the same in-progress week each night, `nc_gis_lookup.lookup_properties` now backs its per-process cache with a cross-run disk cache (`output/.nc_gis_cache.json`). Successful `(decedent, county)` lookups are remembered for 14 days so the slow county GIS (esp. Cabarrus ~1 min/call) isn't re-hit for decedents already resolved earlier in the week. Misses are NOT cached (they retry each run for late-indexed filings). Env knobs: `NC_GIS_CACHE_DISABLE=1` to bypass, `NC_GIS_CACHE_TTL_DAYS=N` to change lifetime; delete the JSON file to clear. Bump `_PERSIST_VERSION` in `nc_gis_lookup.py` when a county endpoint or the candidate schema changes (auto-invalidates old entries).

**Standard NC weekly scrape command** (`scripts/nc_weekly_scrape.bat`):
```
python src/main.py nc-daily \
  --since YYYY-MM-DD \
  --counties Cabarrus,Catawba,Gaston,Iredell,Lincoln,Mecklenburg,Rowan \
  --types probate \
  --skip-obituary \
  --no-skip-trace
```

**Required NC flags (and why):**
- `--skip-obituary` / `--nc-obituary` — **NC obituary enrichment is ON by default** as of 2026-06-13 (the A/B rollout flipped). `scripts\nc_weekly_scrape.bat` sets `NC_OBITUARY=1` and passes `--nc-obituary`, which overrides the global `--skip-obituary` for NC notices and runs the Tier 2 path (Serper + Firecrawl + LLM; Knox Tax tier gated off for non-TN states). To opt OUT for a single run, set `NC_OBITUARY=0`. Ancestry SSDI stays disabled in NC (Knox-tested only).
- `--no-skip-trace` — DataSift skip trace (post-upload, auto-tag `skip_traced_YYYY-MM`) handles phones + emails. **PAY-PER-RECORD, not unlimited** (corrected 2026-08-06): the account is on Professional $149/mo with **no skip-trace addon**, drawing down a prepaid balance (`user/` API → `balance`). The $97/mo unlimited add-on is something Oren has NOT bought yet — he wants a heads-up when monthly pay-per-record spend approaches $97 so upgrading becomes worthwhile. So skip trace ONLY the rows that need it. Tracerfy ($0.02/contact) is reserved for **Phase 2 deep prospecting** where DataSift can't help (heirs identified from obituary search who aren't in the CSV yet).

**`--nc-obituary` (ON by default since 2026-06-13; build 1.0.30+):**
- Default ON — `nc_weekly_scrape.bat` sets `NC_OBITUARY=1`. Opt OUT for a single run with `NC_OBITUARY=0`. The A/B rollout is complete; NC obituary enrichment is now standard.
- Search backend: uses **Serper (Google)** as of 2026-06-30 (commit a8257e2). It previously used DuckDuckGo, which had started returning 0 results for every decedent — silently starving the heir-finder so every case fell to "Heirs of". If obit hit-rate ever drops again, check the Serper key/quota first.
- Implementation: `obituary_enricher.py` threads `notice.state` through every lookup helper. The Knox Tax tier is gated on `state == "TN"`; non-TN states go straight to Tier 2 (Serper + Firecrawl + Claude). `_STATE_FALLBACK_CITY = {"TN": "Knoxville"}` — for NC notices with no city, the lookup runs city-less rather than guessing.

**eCourts-only by default (build 1.0.32+):**
- The NC scrape pulls **only from Odyssey eCourts** by default. Newspaper scrapers (column.us, Salisbury Post AdHunter, Gannett iPublish Marketplace) are gated behind `--include-newspapers` and stay opt-in.
- Why: newspapers publish Notice-to-Creditors 1–8 weeks AFTER the eCourts docket filing. eCourts-only catches every case faster, guarantees every row has a `Case No.`, eliminates soft-dedup overhead from cross-source dedup, and removes the truncated-name parser fragility (e.g. "Walker, Betty" vs "Walker, Betty Louise") that newspaper feeds introduced.
- Pass `--include-newspapers` if you specifically need newspaper coverage for a county that's lagging in Odyssey, or to A/B test scope.
- Tax-sale + tax-delinquent scrapers are unaffected (Mecklenburg ArcGIS, Zacchaeus, Mecklenburg/Rowan county XLSX) — those aren't newspaper sources.

**Post-scrape polish pipeline** (`python fix_addresses_and_prep.py`):
0. **Step -0.96** Reject known-wrong parcels but HOLD the case (`manual_parcel_rejects.txt`: Case No. + Parcel ID per line). Unlike `manual_drops.txt` (permanent case kill), this only blocks that parcel from that case — the row stays live as no-parcel (auto-excluded from workbook/uploads) while nightly runs keep hunting; the Step 0.64 decedent-address fallback can attach the right parcel once the court scans the Application PDF. Re-asserted at Step 3.95 against late re-attachment.
1. **Step -1** Backfill blank Case No. from user's manual archive (see `build_manual_archive_index.py` — newspapers publish Notice-to-Creditors 1-8 weeks AFTER eCourts filing, so blank-case-no rows often match cases the user already pulled manually in a prior week)
2. **Step -0.8** Drop archive duplicates — rows whose backfilled Case No. resolves to a prior ISO week's manual entry. User's rule: keep the original in the prior week and update info there; remove from current week.
3. **Step -0.5** Soft-dedup blank-case-no rows against same-decedent named rows in the current week (catches newspaper notices that ALSO appear in this week's eCourts pull)
4. **Step 0** Validate existing parcel matches with middle-name-aware matcher (catches homonyms like "Osborne, James Lee" matched to "James D Osborne")
5. **Step 0.5** Re-search with name variations for cases the audit blanked
6. **Step 1** Repair property addresses + re-classify suspect Commercial-tagged rows
7. **Step 1.5** Re-collapse multi-parcel decedents (prefer residential as main, vacant lots → Notes)
8. **Step 1.7** Backfill Property Value from GIS
9. **Step 1.8** Drop properties > $500K (user's buy-box cap)
10. **Step 1.9** Drop heir-occupied (executor mailing == property address)
11. **Step 1.95** Fill missing PR mailing from property address (so direct mail still goes to property)
12. **Step 2** Drop genuinely commercial rows
13. **Step 3** Collapse duplicate-decedent rows where Case No. is blank
14. **Step 3.5** Clean bad-city / bad-zip leftovers — when Property City contains a street suffix (Dr/St/Rd/Ln), state code (Ga/Ny), or numeric value (9-digit-no-dash ZIPs that leaked through), merge the suffix back into Property Address and clear the bad city. Also reformat `281640000` → `28164` / `28164-0000`.
15. **Step 4** Filter to has-parcel + apply "Heirs of [Decedent]" transform for no-PR rows (promotes first usable beneficiary to PR before falling back to "Heirs of")

**Per-session GIS cache** — `nc_gis_lookup.lookup_properties` caches by `(decedent, county)` so each unique decedent only hits the county GIS once per pipeline run. Critical for Cabarrus (~1 min/call API).

**Optional polish helper** (`scripts/daily_reenrich.bat`) — POLISHES the latest weekly FTM CSV (runs `reenrich_ftm_executors.py` + `recover_parcels.py` to fill blank executors/parcels from the eCourts Parties API + county GIS). Does NOT scrape. Not currently scheduled — run by hand if a workbook has stubborn blanks; the weekly run already covers the normal case. (Scheduled automation is now the daily-scrape / weekly-organize split above.)

**FTM-format output** (`src/nc_ftm_writer.py`):
- 30 columns including Beneficiaries (from eCourts Parties API), Property Value, DM columns (DM Name / Relationship / Phone / Email / DM 2/3)
- Per-county color tints (Cabarrus light blue, Catawba light green, Gaston light yellow, Iredell light pink, Lincoln lavender, Mecklenburg peach, Rowan teal)
- Sorted by County then Case No.
- Dark green header, single-line row layout, County dropdown

**Multi-week workbook consolidation** (`python consolidate_weeks.py`):
- Combines `*_weekN_datasift.csv` files into one XLSX with a tab per ISO week
- Auto-picks latest per week from `output/`
- Output: `output/FTM_YYYY_NC_Estates_throughWeekN.xlsx`

## Skip-Trace Stack (build 1.0.35+)

Three sources is the sweet spot; past that is diminishing returns (Ty, 5DDF Day 3
2026-08-19). **DataSift is source 1 and unlimited since 2026-08-23** — always trace
there first. Sources 2 and 3 are the only metered decision.

| Provider | Role | Cost | Access |
|---|---|---|---|
| DataSift | source 1 | unlimited on plan | in-app |
| **SmartSkip** | source 2 — the relative cluster | **$0.15/row** | **CSV only, NO API** |
| Enformion | PR phone fallback, nightly | $0.35/match | API (`src/enformion_client.py`) |
| Tracerfy | heir traces | $0.02/hit | API |
| Trestle | scores every resulting number | $0.015/phone | API |

**Where it's worth it:** first-to-market county data — yes. Deep prospecting — a
must-have. Bulk Priority 1 / SiftMap — **no**, DataSift + Trestle already reaches
~90% of what's reachable and 3x tracing bulk burns money fast.

### SmartSkip round-trip (`src/smartskip_io.py`)

SmartSkip has **no API and never will** — their own "API vs manual" post argues
against them. So this is a CSV round-trip with a human in the middle:

```bash
# 1. build the upload file (dedupes across weeks; writes a sidecar keymap)
python src/smartskip_io.py export output/*_dm_enriched.csv --filter heirs
python src/smartskip_io.py export <csv...> --filter no-phone --dry-run   # cost only, $0

# 2. upload that CSV at smartskip.io, download the campaign-format result

# 3. parse it back: cluster -> signer gate -> Trestle -> review CSV
python src/smartskip_io.py ingest <download> --keymap <the_keymap.csv>
python src/smartskip_io.py ingest <download> --max-people 3 --no-trestle
```

- **Subject = the DECEASED OWNER at the PROPERTY address**, not the PR. Ty:
  *"the input name is the person who is the owner on title."* Tracing the PR
  returns the PR's own numbers, which we usually already have; tracing the
  decedent returns the family cluster. `--subject pr` exists for the narrow case.
- **The signer gate is load-bearing.** One $0.15 hit returned **41 associated
  people**; the flow keeps ~3. **A DataSift record holds up to 30 phones (UI
  shows N/30), but the API owner-PATCH saves only the FIRST 15 entries of the
  phones array** — so 15 is the working ceiling for API pushes. Measured
  2026-08-27 on case 26E000919-170 (14 existing + 5 pushed = 1 accepted) and
  re-confirmed live the same day (15 existing + 4 pushed = 0 accepted, HTTP
  200 both times). The server truncates without error, so only a read-back
  after the write catches it. Slots 16-30 are reachable only via the UI /
  the "Upload phone numbers by property address" wizard
  (`upload_phone_numbers_by_address.py`, untested past 15). A raw cluster
  would blow the record up. `shortlist()` drops
  neighbours/associates/roommates outright, then ranks spouse > child >
  grandchild > sibling > parent > niece/nephew > in-law, preferring people who
  actually have a phone and a mailing address.
- **Only Dial First / Dial Second survive** Trestle scoring. Cached numbers
  (`output/.trestle_score_cache.json`, ~2,900 entries) are free; only new ones
  bill, and `--max-spend` (default $5) is a hard ceiling. A number that could
  not be scored is KEPT — unscored is unknown, not bad.
- **Rejoin** is via `SiftKey` (`surname-firstinitial-zip5`), emitted as a column
  AND a sidecar keymap, because a vendor template may strip unknown columns.
- **Confirmed export schema** (live run 2026-08-24, 79 columns, one row per
  person). Two columns carry different things and it matters:
  - `Relationship` = the ROLE — `Subject` / `Relative` / `Associate`
  - `Possible Type` = the actual TIE — Spouse, Child, Parent, Sibling, In-law,
    Other Relative, Unknown, Neighbor, Past neighbor, Friend, Tenant,
    Coworker, Landlord

  We rank on the tie and filter on the role. **The `Subject` row is the dead
  owner returned inside their own cluster** — dropped, along with the whole
  `Associate` role and anyone flagged `Deceased`. The found person's name is in
  plain `First Name`/`Last Name`; `Input Name` is the SUBJECT we searched for,
  so mixing them up would stamp the decedent's name on every heir.
  Phones ship as trios (`Phone N number` / `type` / `connected`) up to 15, plus
  16 email slots; connected numbers are ordered first (only ~10% carry the flag).
- `SiftKey` does NOT survive the round trip — SmartSkip strips unknown columns.
  Rejoin falls back to `Input Name` + `Property Zip`, which matched **82/82** on
  the live run. Keep the sidecar keymap.
- **Their spouse detection is weak** — 9 `Spouse` labels in 1,178 rows. A
  95-year-old living at the subject property came back typed `Unknown`. The
  `At Property` column in the review CSV catches these (47 of 330 on the live
  run) and doubles as the occupied-hold signal.
- The parser sniffs LONG (one row per person) vs WIDE (`Relative N Name` groups)
  and raises with the headers it saw rather than silently returning nothing.
  `UPLOAD_COLUMNS` was verified against their real mapping screen — all ten
  fields auto-mapped, no `Middle Name` (leave it blank; putting anything there
  poisons every search).
- Writes a **review CSV only**. Nothing is uploaded to DataSift, ever, without
  being asked first.

Measured 2026-08-24 on 31 weekly files: 1,350 rows → 220 "Heirs of" → **82 unique
traceable subjects = $12.30** one-time backlog (121 were cross-week duplicates,
17 had no address anchor). **Live result:** 1,178 people returned (median 15 per
estate, max 30) → **330 kept across 70 of the 82 estates** — 114 Child, 71
In-law, 55 Sibling, 53 Parent, 9 Spouse. 12 estates returned nothing usable.

### Enformion spend cap

`src/enformion_client.py` bills $0.35 per MATCH (misses free) and ran **uncapped**
until 2026-08-24 — 150 matches over 10 days, $52.50, ~$160/mo. Now every billed
match counts against `NC_ENFORMION_MAX_SPEND` (default **$10.00 per process**);
past that the client goes inert for the run and logs once. Cache hits and misses
never count. `NC_ENFORMION_MAX_SPEND=0` disables the cap. Spend is reported in the
nightly log line from `nc_deep_prospect.py`.

Note: Ty stopped naming Enformion in his taught stack on Day 3, but **his own v5
skill still ships it as the primary heir-resolution path**, and SmartSkip cannot
run unattended inside the nightly build. Keep it until the bake-off says otherwise.

## DataSift.ai (REISift) Integration

DataSift.ai (formerly REISift) is the CRM where scraped records land for niche sequential marketing campaigns. There is **no REST API** — upload is via Playwright browser automation of the web UI.

**Domain:** `app.reisift.io` (NOT `app.datasift.ai`). API at `apiv2.reisift.io`.

### Key Files
- `src/datasift_formatter.py` — Transforms `NoticeData` → DataSift CSV (41 columns)
- `src/datasift_uploader.py` — Playwright login + upload wizard + enrich + skip trace + preset management + sequence builder + SiftMap sold workflow
- `test_datasift_upload.py` — Headed browser test (upload + enrich + skip trace)
- `test_manage_presets.py` — Headed browser test (preset discovery + sold exclusion + sequence creation)
- `test_manage_sold.py` — Headed browser test (SiftMap sold property tagging)

### CSV Column Structure (41 columns)
- **Core auto-mapped (11):** Property Street/City/State/ZIP, Owner First/Last Name, Mailing Street/City/State/ZIP, Tags
- **Lists + Notes (2):** Lists (for niche sequential), Notes (contextual per notice type)
- **Built-in fields (13):** Estimated Value, MSL Status, Last Sale Date/Price, Equity Percentage, Tax Deliquent Value, Tax Delinquent Year, Tax Auction Date, Foreclosure Date, Probate Open Date, Personal Representative, Parcel ID, Structure Type, Year Built, Living SqFt, Bedrooms, Bathrooms, Lot (Acres)
- **Custom fields (15):** Notice Type, County, Date Added, Owner Deceased, Date of Death, Decedent Name, Decision Maker, DM Relationship, DM Confidence, DM 2/3 Name/Relationship, Obituary URL, Source URL

### Niche Sequential Marketing
DataSift's niche sequential system uses filter presets to guide records through SMS → Call → Mail → Deep Prospecting phases. Two preset folders: "00 Niche Sequential Marketing" (12 presets, courthouse data) and "01. Bulk Sequential Marketing" (9 presets, bulk data). All 21 presets exclude Sold status (build 1.0.23). A "Sold Property Cleanup" sequence in the Transactions folder auto-fires on "Sold" tag to change status, remove from lists, clear tasks, and clear assignee.

- **"Courthouse Data" tag:** Every record gets this tag — signals first-to-market county data (prioritized over bulk data in filter presets)
- **Lists column:** Maps `notice_type` → DataSift list name (`foreclosure` → "Foreclosure", `probate` → "Probate", `tax_sale` → "Tax Sale", `tax_delinquent` → "Tax Delinquent", `eviction` → "Eviction", `code_violation` → "Code Violation", `divorce` → "Divorce"). DataSift auto-creates lists from CSV.
- **Tags:** Courthouse Data, notice_type, county, YYYY-MM date, deceased/living, DM confidence level, has_auction, tax_delinquent, photo_import (for photo-sourced records)

### Sold Property Sweep (build 1.0.34+)

Implements DataSift's "Managing Sold Properties" article for the 7 NC counties. Monthly flow (Task Scheduler "SiftStack Sold Sweep", 1st @ 12:00, first auto-run Sep 2026; `scripts/manage_sold_monthly.bat`):

1. **SiftMap pull per county/month** — county-level URL navigation with Last Sold Date range + min sale price $1,000 (excludes deed transfers). `COUNTY_STATE_FIPS` in `datasift_uploader.py` maps county → (state, FIPS); TN (Knox/Blount) legacy + 7 NC counties. Adds ~4,400 records/month across the 7 counties (June 2026 measurement: Meck 2,092, Catawba/Iredell 485 each, Cabarrus 378, Rowan 369, Gaston 317, Lincoln 247). Tags: "Sold" + "Sold YYYY-MM" (sale month, not run month); "Do not replace owners" toggled OFF so buyer info updates.
2. **Sequences fire on matched leads** — records that merged onto existing leads get the Sold tag → **Oren's hand-built "Sold -> Reset"** (default folder, created 04/19/26, Active) removes ALL lists + campaign/week tags, deletes tasks, clears assignee, sets status → Default (article's design; the Sold tag stays as the permanent marker). NOTE: the build-1.0.23 "Sold Property Cleanup" sequence and the "00 Niche/01 Bulk" preset folders NO LONGER EXIST — the account was reorganized ~April 2026; don't trust older sections of this file about them. Companion "Sold Status Sync" (default folder) bridges the MANUAL path: status hand-changed to Sold → adds the "Sold" tag → chains into Sold -> Reset.
3. **Stranger delete** — pulled records that were never our leads are deleted the same run. Filter: month Sold tag AND "Created Date" (calendar block) = pull day. Guards: both filter chips must verify in the "Filtering by:" bar, count must be >0 and ≤ records pulled, else ABORT. **NOTE (2026-08-01 live-run finding): SiftMap adds currently create NO new records at all** — DataSift processes the jobs, consumes quota, claims "New Records" in breakdowns, but the account total doesn't change. Only address-matched EXISTING records get the tags (576 of 5,952 on the first run). So in practice there are no strangers and the delete no-ops; keep the machinery in case DataSift fixes adds.

Key flags: `--dry-run` (count-only pull, or count-only delete preview with `--delete-strangers-only`), `--keep-strangers`, `--expected-max` (ceiling for standalone real deletes), `--headless`. First live run should be supervised (`manage_sold_monthly.bat --watch`) — the Mecklenburg "Select Max" with ~2K selected and the delete-confirm modal are unverified at volume.

### Upload Wizard (5 Steps)
1. **Setup:** Click "Upload File" sidebar → "Add Data" → dropdown "Uploading a new list not in DataSift yet" → enter list name → organization questions
2. **Tags:** Skip through (tags are in CSV column)
3. **Upload File:** Set file on `input[type="file"]`
4. **Map Columns:** Core address fields auto-map; Tags, Lists, and enrichment columns may need manual mapping
5. **Review + Finish Upload:** Click "Finish Upload" — processing happens in background

### Column Mapping Notes
- Only core address fields (Property Street, City, State, ZIP) reliably auto-map
- Tags, Lists, Estimated Value, and enrichment columns often stay unmapped in step 4
- Notes and MSL Status sometimes auto-map
- Custom fields (TN Public Notice group) require drag-and-drop mapping

### Contact Logic
- **Deceased owners:** Contact = decision maker (first/last name + mailing address from DM)
- **Living owners:** Contact = property owner (owner mailing address, falls back to property address)

### Post-Upload: Enrich + Skip Trace

After CSV upload, the pipeline automatically runs two DataSift actions via Playwright:

1. **Enrich Property Information** (Manage → Enrich Data): Adds SiftMap property data (beds, baths, Zestimate, sqft, sale history) to uploaded records. "Enrich Owners" and "Swap Owners" are OFF — protects our PR/DM contact mapping.
2. **Skip Trace** (Send To → Skip Trace): Pulls phone numbers (up to 5 per owner) + emails. **Billed per record against a prepaid balance — NOT unlimited** (see the `--no-skip-trace` note above). Adds auto-tag `skip_traced_YYYY-MM`.

Both run in background — tracked in Activity tab. Both are ON by default when `--upload-datasift` is set.

### CLI Flags
```bash
python src/main.py daily --upload-datasift        # upload + enrich + skip trace
python src/main.py daily --upload-datasift --no-enrich       # upload only, skip enrichment
python src/main.py daily --upload-datasift --no-skip-trace   # upload + enrich, skip skip trace
python src/main.py daily --notify-slack            # send run summary to Slack/Discord
```

### Environment Variables
- `DATASIFT_EMAIL` — DataSift login email
- `DATASIFT_PASSWORD` — DataSift login password
- `SLACK_WEBHOOK_URL` — Slack/Discord webhook for run summaries

### Login Selectors (SPA quirks)
- Hidden checkboxes (Remember me, Terms) — click `<label>` elements, not `<input>`
- Use `wait_until="domcontentloaded"` (not `networkidle` — SPA keeps WebSocket connections open)
- Cookie validation: check for `/dashboard` or `/records` in URL (5s wait for SPA redirect)

### DataSift UI Automation Patterns

Hard-won patterns from build 1.0.22-1.0.23 (SiftMap, preset management, sequence builder). Follow these to avoid repeating past mistakes.

**Styled-Components (no native HTML controls)**
- No native `<select>` elements — all dropdowns are `[class*="Selectstyles__Select"]` containers
- `[class*="SelectValue"]` = current value display; `[class*="SelectOptionContainer"]` = dropdown options
- Multiple Select dropdowns exist per panel (Lists, Tags, Property Status) — always target the **LAST visible one**
- Use `x > 450` bounds check in all JS queries to avoid matching sidebar elements (sidebar is 0-400px)
- React state updates require native setter + event dispatch, not just `.value = ...`:
  ```js
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(input, 'new value');
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  ```

**Panel Scrolling (Playwright scroll fails)**
- Filter panel is a scrollable `<div>`, NOT the viewport — `scroll_into_view_if_needed()` does nothing
- Use JS: `el.scrollIntoView({behavior: 'instant', block: 'center'})` instead
- Filter Presets section is at the BOTTOM of the filter panel — must scroll container down to reveal
- After scrollIntoView, element y-positions may be negative — don't filter by `y > 0` for the target element

**React DnD (Sequence Builder)**
- Cards have `draggable="false"` — Playwright's native drag won't work
- Must use slow mouse drag: `mouse.move()` → `mouse.down()` → 20 incremental steps (50ms each) → `mouse.up()`
- Add 500ms pauses between down/move/up phases
- "Add new Action +" button required for 2nd+ actions; first action uses initial drop zone
- Sidebar cards can scroll out of view when main area scrolls — scroll BOTH source and target into view before drag

**Pointer Interception (common blockers)**
- Beamer NPS survey iframe (`#npsIframeContainer`) blocks ALL pointer events globally — remove from DOM via `_dismiss_popups()`
- `RecordsFiltersstyles__RecordsFiltersSection` elements intercept clicks — use `page.evaluate()` JS click or `force=True`
- When Playwright click fails with "outside of viewport" or "intercept": switch to `page.evaluate(el => el.click())`
- SiftMap PropertyDetails panel blocks sidebar checkboxes — remove from DOM before interactions

**Preset Management Workflow**
- Flow: open filter panel → scroll to bottom → expand "Filter Presets" → expand folder → click preset → modify → Save (not Save New) → confirm overwrite
- Folder names have case variations ("00 Niche" vs "00 NICHE") — use `.toUpperCase()` comparison
- Preset names follow pattern `^\d{2}\.` (e.g., "00. Needs Skipped")
- 2 folders: "00 Niche Sequential Marketing" (12 presets), "01. Bulk Sequential Marketing" (9 presets)
- All 21 presets have Property Status "Do not include" → "Sold" (build 1.0.23)

**Sequence Builder Workflow**
- Flow: `/sequences` → Create → title + folder → drag trigger → condition → actions tab → drag actions → configure → save
- Duplicate name handling: detect error toast "different sequence title", retry with " V2" suffix
- Actions tab: navigate via "Set the Following Actions" button or URL (`/sequences/new/actions`)
- Autocomplete inputs: after each selection, `fill("")` + Escape to dismiss dropdown before next entry
- "Sold Property Cleanup" sequence exists in Transactions folder (build 1.0.23): Trigger (Property Tags Added) → Condition (Sold) → Actions (Status→Sold, Remove Lists, Clear Tasks, Clear Assignee)

**SiftMap Automation**
- Search by city (NOT county): Knox → "Knoxville, TN", Blount → "Maryville, TN"
- PropertyDetails panel auto-opens on search — remove from DOM before other interactions
- "Add Records to Account" modal: toggle OFF "Do not replace owners", add tags, dismiss dropdown by clicking heading (NOT Escape — clears tags)
- Known limitation: SiftMap filters (price, date) set values visually but don't trigger React re-query. Only sidebar-visible properties (~3-5) get added per run

**Market Finder Extraction Patterns (build 1.0.29+)**

Hard-won patterns from building `extract_market_finder.py`. The Market Finder UI differs significantly from the rest of DataSift.

- **NO HTML `<table>` element** — data table is entirely div-based: `Tablestyles__TableContainer` → `TableRow` → `TableCell` (styled-components). Searching for `<table>` or `<tr>/<td>` finds nothing.
- **PAGINATION, not infinite scroll** — table shows 20 rows per page with "1-20 of N" text and `PaginationInnerContainer` with prev/next `<button>` elements. Must click through ALL pages to get complete data. Knox County has 48 ZIPs (3 pages) and 120+ neighborhoods (7 pages).
- **State/County selection uses `InputMultiSearch`** — NOT styled-component Select dropdowns. Inputs have placeholders: `"Select States"`, `"Select Counties"`, `"Select ZIP Codes"`. Click input → type name → click dropdown result item (`[class*="Item"]:has-text("...")`).
- **ZIP/Neighborhood toggle is a styled Select dropdown** — at the top bar with `Selectstyles__SelectValue` showing current view. Check the displayed text BEFORE clicking — if already on the correct view, clicking toggles AWAY from it. Only click to switch if the displayed text doesn't match the desired view.
- **Beamer push modal (`#beamerPushModal`)** — appears on fresh login, blocks ALL pointer events. Different from the NPS survey (`#npsIframeContainer`). Both must be removed from DOM before any click interactions. Always call dismiss with `force=True` as fallback.
- **Page body scrolling required** — pagination controls are at `y=1867`, below the viewport (`clientH=824`). Must scroll `AdminPage__AdminPageBody` container down before pagination buttons are accessible.
- **Summary panel on right side** — shows county-level aggregates: Median Home Value, Homes on Market, Mo. Investor Transactions, Homes Sold Last Month, Market Rent, Gross Rental Yield, Homeownership Rate. Extract via regex on page text.

```bash
# Extract all Market Finder data for a county
python src/extract_market_finder.py --state "Tennessee" --county "Knox" -v
python src/extract_market_finder.py --state "Tennessee" --county "Knox,Blount" --headless

# Output: JSON file in output/market_finder_{state}_{county}_{timestamp}.json
```

## REI Skill Library (13 Skills)

Distribution-ready Claude Co-Work skill files at `Skills for REI/improved/`. Each `.skill` is a ZIP containing `SKILL.md` + `references/` folder. Plugins (`.plugin`) also include `commands/` and `.claude-plugin/plugin.json`.

### Skill Inventory

| # | File | Division | Score | What It Does |
|---|------|----------|-------|-------------|
| 1 | `sift-market-research.skill` | Market Intel | 9.6 | Market Finder reports, zip code scoring (6 weights verified against `market_analyzer.py`), 7-sheet Excel output |
| 2 | `first-market-county-data.skill` | Market Intel | 9.7 | County clerk data extraction for all 7 notice types, FOIA templates, marketing windows |
| 3 | `buyer-prospector.skill` | Market Intel | 9.6 | Cash buyer list from 84K+ records, LLC/trust/corp research, 50-state SOS URLs |
| 4 | `real-estate-comping.skill` | Deal Analysis | 9.7 | Two-Bucket ARV, disclosure/non-disclosure routing (12 states), adjustments verified against `comp_analyzer.py` |
| 5 | `rehab-estimator.skill` | Deal Analysis | 9.8 | 912-line skill, complete Repair Cheat Sheet verified against real contractor SOW, 4-tier system |
| 6 | `deal-analyzer.plugin` | Deal Analysis | 9.6 | Combined comp+rehab pipeline, MAO (75%/70% rules), multi-loan financing, exit strategy comparison |
| 7 | `deep-prospecting.skill` | Deal Analysis | 9.6 | 4-level research depth (L1-L4), heir verification loop, DOD sanity check (3yr), 3-site skip trace waterfall |
| 8 | `probate-property-finder.skill` | Deal Analysis | 9.7 | Property lookup for probate decedents, 3-tier search (Tax API→Executor→People search), confidence scoring |
| 9 | `phone-validator.skill` | Operations | 9.8 | Trestle API scoring, 5-tier dial priority, 3 tier strategies, litigator risk check, 4.75x connect rate |
| 10 | `sequential-presets.skill` | Operations | 9.5 | 12 niche + 9 bulk filter presets, Pendulum Theory (SMS→Call→Mail→DP), DataSift UI implementation steps |
| 11 | `sift-sequences.skill` | CRM | 9.5 | 26 TCA sequence templates (verified against `sequence_templates.py`), UI walkthrough, HOT A01-A16 chains |
| 12 | `sift-operations.plugin` | CRM | 9.3 | CRM operations encyclopedia, STABM routine, lead pipeline (9 statuses), task presets, team roles |
| 13 | `playbook-creator.skill` | Operations | 9.5 | Playbook/SOP generator from transcripts, 7-node chart limit, 5th grade reading level, Word doc output |

### Cross-Skill Verified Consistency

These values are identical across all skills that reference them:
- **Phone tiers:** 81-100 (Dial First), 61-80 (Dial Second), 41-60 (Dial Third), 21-40 (Dial Fourth), 0-20 (Drop)
- **Preset folders:** "00 Niche Sequential Marketing" (12 presets), "01. Bulk Sequential Marketing" (9 presets)
- **Sequence count:** 26 TCA templates across 5 folders (Lead Management 6, Acquisitions 6, Transactions 6, Deep Prospecting 4, Default 4)
- **Comp adjustments:** Bedroom $5,000, Bathroom $7,500, $/sqft $85, Age $500/yr (from `comp_analyzer.py`)
- **Financing defaults:** HML 12%, conventional 7%, 2 points, 2.5% closing (from `deal_analyzer.py`)
- **DOD sanity:** MAX_DOD_GAP_YEARS = 3 (from `obituary_enricher.py`)
- **Notice types:** 7 total (foreclosure, tax_sale, tax_delinquent, probate, eviction, code_violation, divorce)

### Key Corrections Made During Optimization (April 2026)
- **Hardcoded credentials removed** from sift-market-research (had email/password in SKILL.md)
- **Bedroom adjustment corrected** from $10K to $5K in real-estate-comping (matched to `comp_analyzer.py`)
- **HML points corrected** from 0% to 2% in deal-analyzer (matched to `deal_analyzer.py DEFAULT_HARD_MONEY_POINTS`)
- **Linux paths fixed** in sequential-presets (was `/home/ubuntu/skills/...`, now relative)
- **Preset names aligned** across 3 skills to match `niche_sequential.py` source code
- **Transfer tax labeled** as Tennessee-specific in deal-analyzer with state reference table for top 10 states
- **"Substantial renovation" defined** in real-estate-comping: kitchen + 1 bath minimum (~$15K spend)

### Skill File Structure
```
skill-name.skill (ZIP containing):
├── SKILL.md              # Main skill instructions
├── references/            # Domain knowledge files
│   ├── *.md              # Reference documents
│   └── *.pdf             # SOPs, guides
└── scripts/              # Optional automation scripts
    └── *.py / *.js

plugin-name.plugin (ZIP containing):
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
├── commands/             # Slash commands
│   └── *.md
├── skills/
│   └── skill-name/
│       ├── SKILL.md
│       └── references/
└── README.md
```
