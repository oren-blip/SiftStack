# Guide: claude-skills-rei

> Source: https://learn.datasift.ai/claude-skills-rei (Day 1, August 2026 cohort — fetched 2026-08-18)
> Part of the Challenge Hub Day 1 module list. Hub pages are sunset each cohort.

---

On this page

      On this page
      ×

      AI Toolkit

# Claude Co-Work & Skills for REI

      Your entire research, analysis, and operations team. Running on a $20/mo subscription.

         12 min read
         Phase 6 Guide
19 Skills

## Claude Co-Work Mode

    Co-Work turns Claude from a chatbot into an agent: it reads files, browses the web, spawns sub-agents, and produces documents. A virtual back office.

#### File Access

        Upload spreadsheets, PDFs, and images directly. Claude reads the data and works with it in real time. No copy-pasting.

#### Sub-Agents

        Co-Work spawns parallel sub-agents for research tasks. One agent pulls comps while another estimates rehab costs. Results merge into a single output.

#### Chrome Connector

        The Chrome Extension lets Claude see what you see in the browser. It can read county clerk websites, Zillow listings, and MLS data in real time.

### Getting Started with Co-Work

        1

#### Open Claude Desktop or claude.ai

          Co-Work is available on both the desktop app and the web version. Make sure you have a Pro plan ($20/mo) or higher.

        2

#### Select Co-Work Mode

          Toggle into Co-Work mode from the conversation selector. This enables file access, sub-agents, and extended context.

            Select Co-Work from the mode dropdown.

        3

#### Set Global Instructions

          Add instructions that apply to every Co-Work conversation. Tell Claude your market, your current phase on the Deal Flow Ladder, your team size, and your CRM setup.

            Global instructions persist across all your Co-Work sessions.

        4

#### Upload Your First Skill

          Download a .skill or .plugin file from the library below. Upload it to your Co-Work project. Claude reads the skill file and gains specialized abilities.

    Start with the Deal Analyzer plugin. It combines comping and rehab estimation into one workflow. Upload a property address and get a full deal package: ARV, rehab estimate, MAO, and profit projection.

## Skills, Plugins & Built-in Tools

    Three types of AI tools, each with different capabilities. Skills are the most common. Plugins combine multiple skills into a single workflow.

        📝

        .skill

#### Skill

        A single-purpose instruction file. Teaches Claude one specific workflow like comping, rehab estimation, or phone scoring.

        🔌

        .plugin

#### Plugin

        Combines multiple skills into one file. The Deal Analyzer plugin runs comping and rehab estimation together in a single conversation.

        ⚙

        built-in

#### Built-in

        Claude's native abilities: code execution, web search, file creation, and data analysis. Available without uploading anything.

    Skills now live on the Customize page in Claude's settings. Previously managed them elsewhere? Check Settings > Customize.

## Capabilities & Permissions

    Some skills call external APIs. The Phone Validator calls the Trestle API to score phone numbers; without the right permissions, it fails silently.

      Same skill, same call. With the capability off, the pulse dies at the valve and the result stays empty. Switched on, it reaches Trestle and comes back scored.

        1

#### Open Settings

          Click your name in the lower left corner of Claude Desktop or claude.ai. Select Settings.

        2

#### Go to Capabilities

          Find the Capabilities section in Settings. This controls what Claude can do during conversations.

            Navigate to Settings and find the Capabilities section.

        3

#### Enable Required Toggles

          Turn on: Artifacts, Inline visualizations, Code execution, and Allow network egress. Network egress is the critical one for API-calling skills.

            Enable Tool access, Artifacts, and other capabilities your skills need.

        4

#### Add API Domains to Allowlist

          Under network egress, add the specific domains your skills need. For the Phone Validator, add **api.trestleiq.com** to the domain allowlist.

            Enable network egress and add api.trestleiq.com to the domain allowlist for phone validation.

            General desktop settings and Browser Use toggles for Claude's system-level permissions.

    Skills that call external APIs need the domain on your allowlist. The Phone Validator needs api.trestleiq.com to score numbers via Trestle; without it, the skill runs but returns no scores.

    Skill Library

## The REI Skill Library

    19 skills organized by business division. Each skill teaches Claude a specific real estate workflow. Download individually and upload to your Co-Work session or Project.

### Market Research & Data

#### Sift Market Research

            .skill (11MB)

          Full market analysis automation. Generates Market Finder reports, analyzes county data, identifies target zip codes, and builds acquisition strategies.

- County-level market analysis

- Zip code scoring and ranking

- Competition assessment

- Target market recommendations

              [Download .skill](https://drive.google.com/file/d/1Nhjgwh0t4ssC4flTz0lR-xHqH9eF2a5D/view?usp=sharing)
              SiftMap Mastery Guide →

#### First-to-Market County Data

            .skill

          Automates county clerk data pulls for first-to-market lists. Identifies probate, tax sale, foreclosure, and code violation records from public sources.

- Probate record extraction

- Tax delinquent list building

- Foreclosure notice parsing

- Code violation sourcing

              [Download .skill](https://drive.google.com/file/d/1xQuYOgOBM0bfPIKsy4zTh8qM1BDwUKQo/view?usp=sharing)
              FTM Data Guide →

#### Buyer Prospector

            .skill (1.9MB)

          Builds verified cash buyer lists using SiftMap investor transaction data. Analyzes portfolios, identifies active investors, and scores buyer quality.

- Investor portfolio analysis

- Cash buyer identification

- Transaction history scoring

- Buyer type classification

              [Download .skill](https://drive.google.com/file/d/1IQLXyAAW0xbbRzqx6METiLymm7DjTGIY/view?usp=sharing)
              Buyer Prospecting Guide →

### Deal Analysis

#### Real Estate Comping

            .skill

          Two-Bucket comparable sales methodology. Generates full comp reports with ARV calculations, adjustment breakdowns, and confidence bands.

- Two-Bucket ARV methodology

- Comp filtering and scoring

- Adjustment cheatsheets

- Disclosure/non-disclosure handling

              [Download .skill](https://drive.google.com/file/d/1xfsQXSNZddwqAmHpVWvD6su0FcLzMYKK/view?usp=sharing)
              Comping Workflow Guide →

#### Rehab Estimator

            .skill

          Room-by-room rehab cost estimation with finish tier system. Generates full rehab budgets, wholetail comparisons, and project timelines.

- 4-tier finish system

- Room-by-room scoping

- Regional pricing adjustments

- Wholetail vs full rehab analysis

              [Download .skill](https://drive.google.com/file/d/1AhPX4u2XFE1eilxOm6TC4M3hJlvFUNQl/view?usp=sharing)
              Rehab Estimator Guide →

#### Deal Analyzer

            .plugin

          Combines comping and rehab estimation into a single deal analysis workflow. Calculates MAO, ROI, and profit projections for any property.

- Combined comp + rehab pipeline

- MAO and 75% Rule calculation

- ROI projections

- Full deal package output

              [Download .plugin](https://drive.google.com/file/d/1Zl3fABbc363pa2KqX-5WaO9WsYme8vzi/view?usp=sharing)
              Comping + Rehab Guides →

### Lead Research & Prospecting

#### Deep Prospecting

            .skill

          Four-level research depth framework. Automates enhanced skip tracing, public record searches, genealogy research, and heir identification.

- 4-level depth research

- Heir identification via genealogy

- Public record cross-referencing

- Owner swap documentation

              [Download .skill](https://drive.google.com/file/d/1s6BYWg9BXEYDYUshXWaov4mXZUc7o8W6/view?usp=sharing)
              Deep Prospecting Guide →

#### Probate Property Finder

            .skill

          Automates county-specific probate research. Identifies probate filings, deceased owner properties, and heir contact information from public records.

- County probate record search

- Deceased owner identification

- Heir contact extraction

- Property status verification

              [Download .skill](https://drive.google.com/file/d/1_PtG_bfjdUcLroaMBArxrznrctQpXy70/view?usp=sharing)
              FTM Data Guide →

#### Phone Validator

            .skill

          Scores phone numbers via Trestle API (0-100 activity score). Tags numbers by dial priority tier and line type. Requires network egress permission.

- Trestle API integration

- 5-Tier Dial Priority tagging

- Line type identification

- Dead number elimination (~50%)

              [Download .skill](https://drive.google.com/file/d/1VzNjMOj8Rf3zh0pR0DzFE2pOILyGcYoE/view?usp=sharing)
              Phone Scoring & Spam Guide →

#### Caller Reputation Monitor

            .skill

          Keeps your outbound numbers out of "Spam Likely" labels. Monitors every SmrtPhone caller ID daily using your own answer rates, then manages warm-up, rest, and rotation. Pairs with the Phone Validator: Trestle scores the numbers you dial, this protects the numbers you dial from.

- Daily number health scans from your call log

- Warm-up and rotation lifecycle with dial caps

- HTML dashboard plus recommended dial pool

- Free registration and spam flag remediation runbook

              [Download .skill](https://drive.google.com/file/d/1K9bB9u2ZmVlQKFJ3XLaLfLvSoGZLYoYI/view?usp=sharing)
              Phone Scoring & Spam Guide →

#### Text Touch Builder

            .skill

          Writes a four-text SMS sequence for every record in your ready-to-call queue. Messages vary per record like cold email, so nothing reads mass-blasted. Callers copy the next touch into their dialer right before the call, and answer rates climb because the number is no longer a stranger.

- Four-touch recipe from identity check to breakup text

- Seeded variants, no two records send identical sequences

- CSV import into Text Touch 1-4 custom fields

- Every text signed by the assigned caller

              [Download .skill](https://drive.google.com/file/d/1eu5qg1COA2mYl8s2rDj9zFBjwUAT4fCq/view?usp=sharing)
              Text Touch Guide →

### CRM & Operations

#### Sequential Presets

            .skill

          Builds niche sequential marketing filter presets for your DataSift CRM. Configures the 12-filter system for skip tracing, calling, mailing, and deep prospecting.

- 12 niche filter presets

- Skip trace queue setup

- Call/mail/DP cycle filters

- Not-interested recycling

              [Download .skill](https://drive.google.com/file/d/1dORx4amPLslkqiM3RVcdu_FxPkfYv1Pu/view?usp=sharing)
              Niche Sequential Guide →

#### Sift Sequences

            .skill

          Creates and configures CRM automation sequences using the TCA model (Trigger, Condition, Action). Builds lead management, acquisition, and transaction workflows.

- TCA model automation

- 26 pre-built sequence templates

- SMS/email integration

- Folder organization system

              [Download .skill](https://drive.google.com/file/d/1IcXHZ7WT3eQtvg-oRdJ_6RxYYAIBH1py/view?usp=sharing)
              CRM Sequences Guide →

#### Sift Operations

            .plugin

          Full CRM operations management. Handles lead pipeline setup, status configuration, task presets, event scheduling, and team workflow automation.

- Lead pipeline configuration

- Task preset building

- Team role assignment

- Daily execution workflows

              [Download .plugin](https://drive.google.com/file/d/1kAvtrPfUfl0lEfNsO9IDmRGeifuEL2fO/view?usp=sharing)
              Lead Management Guide →

#### DataSift Lead Management

            .plugin

          Sets up your DataSift account for lead management in minutes. Auto-builds the full 7-folder, 75-field intake structure, generates a branded Lead Manager training manual, and installs a daily KPI bot that posts to Slack.

- 75 custom fields auto-built via the DataSift API

- Branded Lead Manager training manual

- Daily KPI Slack bot

- Round-robin task preset setup

              [Download .plugin](https://drive.google.com/file/d/1yseQnt6aGOc_WOL0kWVGqOZICT9eEGpc/view?usp=sharing)
              Lead Intake Guide →

#### Playbook Creator

            .skill

          Generates custom acquisition playbooks based on your market, exit strategy, and team structure. Produces SOPs, scripts, and daily checklists.

- Custom SOP generation

- Script templates

- Daily checklist building

- Strategy-specific workflows

              [Download .skill](https://drive.google.com/file/d/1Thbp5MXH6oZRAPMB4gQNChLbXlxxU9VA/view?usp=sharing)

### Call Coaching

#### Cold Call Coach

            .skill

          Pulls real cold call recordings from your SmrtPhone account and transcribes them with an audio model that hears tonality. Grades every conversation against the DataSift cold calling rubric and rolls results into per-caller scorecards.

- Opener, 4-pillar probing, objections, and close quality scored

- Real tonality notes heard from the audio

- Per-call reports plus a styled Excel workbook

- Transcription costs about $0.002 per audio minute

              [Download .skill](https://drive.google.com/file/d/1BBVq7CiJl-_W0PsMZt9Kj3dl0vS7ASTJ/view?usp=sharing)
              Hiring Guide →

#### Lead Manager Coach

            .skill

          Grades follow-up and qualification calls against the DataSift lead manager rubric. Same pipeline as the Cold Call Coach, pointed at the calls where leads become appointments.

- Four qualifying questions scored: condition, timeline, motivation, price

- 4-pillar depth and roadblock discovery checks

- Next-action discipline graded on every call

- Lead manager scorecards and Excel export

              [Download .skill](https://drive.google.com/file/d/1YW2qKuvugXIkPFmKfinBxk4I7_GpMlQe/view?usp=sharing)
              Lead Management Guide →

#### Closer Coach

            .skill

          Grades offer and negotiation calls against the DataSift closer rubric, from discovery deepening through the money conversation to commitment locking. Works on in-person appointment recordings too.

- Multi-option offer presentation scoring

- Negotiation timeline: every price move and its trigger

- "The moment it was won or lost" quoted per call

- Closer scorecards and Excel export

              [Download .skill](https://drive.google.com/file/d/1ZSXs0AmEiMKaVfMEL4uoAcU85n0W6x8A/view?usp=sharing)

      Next 5-Day Deal Flow Challenge: Monday, August 17 to August 21. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Install Your First Skill

    Pick a skill from the library above. The whole process takes under two minutes.

        1

#### Download the .skill file

          Click the download button on any skill card above. The file saves to your Downloads folder.

            Click the download button on Google Drive to save the .skill file.

        2

#### Open Claude Desktop or claude.ai

          Log in with your Pro account ($20/mo). Open Co-Work mode or create a new Project.

        3

#### Upload the skill file

          Click the + button in your conversation. Select the .skill or .plugin file from your Downloads folder. Claude reads it instantly.

            Upload the .skill or .plugin file to your conversation.

        Uploading your first skill. Select the .skill file and Claude handles the rest.

        4

#### Start using the skill

          Type a prompt that triggers the skill. For the Comping skill: "Run a comp analysis on [address]." Claude follows the skill's complete workflow.

            The Comping skill loaded in Co-Work mode, ready to run a property analysis.

        5

#### Check Capabilities if needed

          If the skill needs API access (like the Phone Validator), configure Capabilities first. See the Capabilities & Permissions section above.

## Chrome Extension

    The Claude Chrome Extension lets Claude see what you see: it reads page content, extracts table data, and interacts with web apps in real time.

#### Read Any Web Page

        Claude reads the active tab content. County clerk databases, Zillow listings, MLS pages. Ask Claude to extract specific data points.

#### Extract Structured Data

        Point Claude at a table or list on a web page. It parses the data and converts it into a spreadsheet, CSV, or structured analysis.

#### Cross-Reference Sources

        Open multiple tabs. Claude reads them all and cross-references the data. Property details from Zillow matched against county records.

#### Do

- Use for reading public data (county records, property listings)

- Combine with skills for enriched analysis

- Use on pages with tables and structured data

- Keep the extension updated to the latest version

#### Don't

- Use on pages requiring login credentials

- Expect it to click buttons or fill forms

- Use on JavaScript-heavy single-page apps (limited rendering)

- Rely on it for real-time data that changes frequently

## WisprFlow: Voice-Powered Productivity

    WisprFlow turns your voice into text anywhere on your computer. Dictate prompts to Claude, write emails, fill CRM fields, and draft documents. All hands-free.

    WisprFlow: instead of typing a 200-word prompt, speak it in 30 seconds. Transcription is near-perfect in any text field. I use it for everything: Claude prompts, Slack messages, CRM notes, email replies.

#### Works Everywhere

        Any text field on your computer. Claude chat, browser input, Word docs, Slack, email. Press the hotkey and start talking.

#### Near-Perfect Transcription

        Trained on natural speech patterns. Handles industry jargon, property addresses, and technical terms without constant corrections.

#### Free to Start

        WisprFlow offers a free tier to test the experience. Paid plans unlock unlimited dictation and advanced features.

    [Try WisprFlow → wisprflow.ai](https://wisprflow.ai)

## Troubleshooting

    Ask Claude first. Describe the issue and Claude will walk you through the fix. For the most common problems, start here.

        Skills not visible in settings

          Skills have moved to the Customize page. Go to Settings > Customize to find your uploaded skills. If you still do not see them, try refreshing the page or restarting Claude Desktop.

        Claude not using the uploaded skill

          Make sure the skill file was uploaded to the current conversation or project (not a different one). Try explicitly asking Claude to "use the [skill name] skill" in your prompt. Some skills activate on specific trigger phrases.

        Upload errors (file too large)

          The Sift Market Research skill is 11MB, near the upload limit. On a size error, upload via Claude Desktop (higher limits than web). Or split it: skill in one message, analysis in the next.

        Skills greyed out or disabled

          This usually means your plan does not support the feature. Skills and Co-Work require a Pro plan ($20/mo) or higher. Check your subscription status under Settings > Billing.

        Chrome Extension not connecting

          Make sure the Claude Chrome Extension is installed and enabled. Check that you are logged into the same Claude account in both the extension and the web app. Try disabling and re-enabling the extension. Clear browser cache if the issue persists.

## Resources & Next Steps

    Explore the dedicated guide pages for each skill and access Claude Pro.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

      [#### Claude Pro

Sign up or upgrade to Pro ($20/mo) for Co-Work and Skills access.](https://claude.ai)
      [#### WisprFlow

Voice-to-text for all your Claude interactions.](https://wisprflow.ai)

#### Comping Workflow Guide

Full walkthrough of the Two-Bucket comp analysis methodology.

#### Rehab Estimator Guide

Room-by-room rehab estimation with finish tier system.

#### Deep Prospecting Guide

4-level research depth framework for finding decision-makers.

#### Phone Scoring & Spam Management

Trestle API phone validation, 5-Tier Dial Priority, and caller ID spam monitoring.

#### Buyer Prospecting Guide

Build verified cash buyer lists using SiftMap investor data.

#### FTM Data Sourcing Guide

Complete guide to courthouse pulls and first-to-market data.

#### SiftMap Mastery Guide

Filter layering, distressor stacking, preset strategy, and AI scoring.

      [#### Deal Flow Tech Stack SOP

Complete tool and pricing reference for your phase.](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)

 Reset

  ×
