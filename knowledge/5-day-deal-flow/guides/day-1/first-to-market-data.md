# Guide: first-to-market-data

> Source: https://learn.datasift.ai/first-to-market-data (Day 1, August 2026 cohort — fetched 2026-08-18)
> Part of the Challenge Hub Day 1 module list. Hub pages are sunset each cohort.

---

On this page

      On this page
      ×

      Market Analysis

# First-to-Market Data

      The data nobody else has. Pulled directly from county offices before it hits any platform.

         25 min read

## The Harder a List Is to Reach, the Less You Compete

        Most investors buy pre-packaged lists and wonder why cost per deal keeps climbing. The operators making $500 per contract are pulling data nobody else has.

          First-to-market data means sourcing distress records directly from county offices the day or week they become public. Before any aggregator scrapes them. Before any platform packages them. Before your competition even knows they exist.

          This is the consistency tier of the Data Priority Pyramid, not where you start. Lead with same-day SiftMap precision: the Investor Score and acute distressor lists. Build First-to-Market once those precision pulls are producing.

        **"The harder a list is to reach, the less you compete for it."** Saturation, not build-difficulty, is the moat. A record you pull first has the lowest saturation: highest connect rate, least competition. You are one caller, not 30 investors mailing the same list.

#### FTM, pulled same-day

            $500 - $2,000

            Cost per contract once the pull is built. Lowest saturation: you are the first, often the only, call.

#### The same list, resold

            Saturated

            Once an aggregator scrapes and repackages it, you compete with everyone mailing the identical list. Higher saturation, harder to reach, thinner margins.

        Saturation, not data quality. Pre-packaged lists compete on speed and script. Pull probate records from the county clerk before they hit any platform and you are the only call that homeowner gets. That is the arbitrage.

        **The trade-off:** freshest, lowest-saturation data, cheapest per contract once running. But the build takes 25-35 days (two county auth systems, Apify, Dropbox, Trestle, captcha, courthouse runners) and the sales cycle runs 4 to 7 months, our pulled probate average. So precision leads, this layer follows.

        **Funnel position: the top.** The source aggregate runs about 66 doors per deal, typical range 50 to 75, with connect rates the saturated market never sees. It builds the pipeline you close next quarter while your SiftMap pulls close this month. Full picture: the funnel read on Doors Per Deal.

        The Six Sources

## Six Lists That Print Money Before Anyone Else Knows

        Every county generates these records. Most investors never pull them directly. Each one represents a property owner in a situation where they need to sell.

#### Probate

            Estate and inherited property cases. The most complex and most rewarding FTM source.

            Hard

#### Tax Sale / Tax-Delinquent

            Properties going to auction for unpaid taxes. Often published as PDF schedules.

            Medium

#### Foreclosure

            Lis pendens and notice-to-sale records. Speed wins this race.

            Medium

#### Pre-Foreclosure

            Default notices before formal foreclosure proceedings begin.

            Medium

#### Code Violations

            Municipality enforcement actions. Fines, liens, and condemned structures.

            Easy

#### Eviction Records

            Formal eviction filings signal landlords ready to sell problem properties.

            Medium

### Probate Records

            When someone dies owning property, the estate goes through probate court. The executor (or administrator) often needs to sell the property to settle debts, distribute assets, or avoid foreclosure. These owners are motivated but hard to reach because the original owner is deceased.

              Where to FindProbate Court Clerk, Surrogate's Court (NY/NJ), Register of Wills (PA/MD), County Clerk Probate Section

              FormatCase filings with PR number, decedent name, executor info. Often no property address included.

              DifficultyHard. Many counties require in-person visits. Online portals often lack export. 22-38% of records have deceased owners needing deep prospecting.

              CostFree to pull. Skip tracing $0.10-0.15/record. Deep prospecting ~$1-4/record with Claude.

            Deep Prospecting Guide for Probate Leads

### Tax Sale / Tax-Delinquent Records

            Property owners who have not paid property taxes. The county publishes these for auction. Two flavors: the delinquency list (all unpaid) and the auction schedule (going to sale on a specific date). Both are goldmines.

              Where to FindCounty Treasurer, Tax Collector's Office, Trustee's Office (TN), Commissioner of Revenue

              FormatPDF schedules, Excel downloads, or online searchable portals. Varies wildly by county.

              DifficultyMedium. Many counties post delinquency lists online. Auction schedules often require checking periodically.

              CostFree. Some counties charge a nominal fee for bulk downloads.

### Foreclosure Records

            Lis pendens filings at the Register of Deeds or newspaper legal notices. The clock starts ticking the moment a foreclosure notice is filed. Median time from notice to auction: 34 days in Knox County. Your marketing window is Day 1-30.

              Where to FindCounty Clerk Civil Division, Register of Deeds, local newspaper legal notices

              FormatOnline docket searches, newspaper publication lists, or county-posted auction schedules

              DifficultyMedium. Online in many counties. Newspaper notices require manual extraction.

              CostFree. 38% deceased owner rate means deep prospecting is often needed.

### Pre-Foreclosure Records

            Default notices filed before the formal foreclosure process begins. The homeowner is behind on payments but the property has not yet been scheduled for auction. This is the earliest warning signal and the longest marketing window.

              Where to FindCounty Recorder, Register of Deeds, or court docket (varies by judicial vs non-judicial state)

              FormatNotice of default filings, recorded documents, or court case filings

              DifficultyMedium. Available online in many counties. Some require subscription access to the recorder's portal.

              CostFree to pull from county recorder. Some subscription portals charge $25-50/mo.

### Code Violations

            Municipality code enforcement actions. Fines, condemnation orders, and abatement liens. Property owners facing mounting fines and mandatory repairs are often motivated to sell. This data is usually city-level, not county-level.

              Where to FindCity Code Enforcement Division, Building & Zoning Department, Community Development, Housing Inspection Services

              FormatOnline searchable portals, FOIA request exports, or published violation lists

              DifficultyEasy. Most cities have online portals. FOIA requests typically fulfilled within 10 business days.

              CostFree. FOIA requests may have nominal processing fees ($5-25).

### Eviction Records

            Formal eviction filings signal a landlord dealing with problem tenants. These owners are already frustrated with property management. Many are ready to sell, especially if the eviction is their second or third. Target the landlord, not the tenant.

              Where to FindGeneral Sessions Court, Civil Court Clerk, Small Claims Division

              FormatCourt docket searches, case filing lists. Some counties publish weekly or monthly.

              DifficultyMedium. Online in many jurisdictions. Some require courthouse visits for complete records.

              CostFree. Skip tracing needed to reach the landlord (owner), not the tenant.

## Where the Data Actually Lives

        Three ways to get first-to-market data out of county systems and into your CRM. The method depends on what the county makes available.

            Online Portals
            In-Person Courthouse
            Publication Notices

### Online County Portals

            The easiest path. Many counties have searchable online databases for property records, court filings, and tax information. The quality varies from fully exportable CSV downloads to clunky CAPTCHA-protected search-one-at-a-time interfaces.

              Knox County Register of Deeds online portal. Search by name, address, or document type.

#### What to look for:

- County Recorder / Register of Deeds website (deed transfers, lis pendens)

- County Treasurer / Tax Collector website (delinquency lists, auction schedules)

- Probate Court Clerk portal (estate filings, case searches)

- City Code Enforcement portal (violation searches)

            Start by searching "[County Name] + [record type] + search" or "[County Name] + recorder online." The FTM County Data Skill automates this research for you.

### In-Person Courthouse Pulls

            When data is not online, someone goes to the courthouse. The harder the data is to get, the fewer competitors pull it. Some of the best markets keep probate records on a terminal inside the clerk's office.

              County clerk data terminal. Records that are not available online can often be searched and photographed on-site.

                Pulling records directly from a county terminal. Some of the best FTM data is only available in person.

                County clerk recorder office. Walk in, search, photograph the results.

#### What to bring:

- Photo ID (some offices require it to access terminals)

- Phone or camera to photograph screen results

- USB drive if the office allows data export

- List of specific record types you need (probate, tax sale, foreclosure)

            If you cannot go yourself, hire a TaskRabbit or use Investor Bootz. One trip typically covers 2-3 list types.

### Publication Notices

            In many states, foreclosure notices must be published in a local newspaper before the auction. Tax sales often have similar publication requirements. These notices contain property addresses, case numbers, and auction dates.

              Foreclosure notices published in the Knoxville Focus. These contain property address, case number, and auction date.

#### Sources for publication notices:

- Local newspaper legal notice sections (online archives)

- County-designated legal publication websites

- State legal notice aggregator sites

- County website "Public Notices" or "Legal Notices" section

            The challenge is extraction. These are formatted for reading, not importing. Use Claude to convert newspaper notice text into structured CSV for CRM upload.

      Next 5-Day Deal Flow Challenge: Monday, August 17 to August 21. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Not All Counties Are Created Equal

        The same record type can be easy to pull in one county and nearly impossible in the next. Assess before you commit.

            ✅

#### Easy

            Online, exportable, free

            ⚠️

#### Medium

            Online but limited access

            🔒

#### Hard

            In-person only

            🤝

#### Needs Help

            Hire a courthouse runner

### Easy: Online, Exportable, Free

            The county posts records online with search and export capabilities. Tax delinquency lists published as downloadable Excel files. Code violation portals with CSV export. These are your quick wins.

            **Strategy:** Set a recurring calendar reminder to check these sources weekly or monthly. Automate where possible. These lists update on predictable schedules (monthly for tax delinquency, weekly for code violations).

            **Common examples:** Tax delinquency Excel downloads, code violation portals, some foreclosure docket searches with bulk export.

### Medium: Online but Limited

            The county has an online portal, but it requires a subscription, has CAPTCHA protection, or only allows searching one record at a time. No bulk export. You can access the data, but extracting it at scale takes work.

            **Strategy:** Use the portal for targeted searches. For bulk extraction, consider FOIA requests or check if the county offers bulk data subscriptions. Some counties sell bulk data access for $50-200/year.

            **Common examples:** Probate case search portals, Register of Deeds with per-search CAPTCHA, court dockets without export.

### Hard: In-Person Only

            No online access. Records are on terminals inside the courthouse. You have to show up, search on their system, and photograph or hand-copy what you find. This is where the competitive advantage is strongest.

            **Strategy:** Go yourself if local. If not, hire through TaskRabbit ($20/hr) or Investor Bootz. One visit typically yields 2-3 list types. Take photos of every screen. Process the data into your spreadsheet after.

            **Common examples:** Small county probate courts, older courthouse systems, counties that have not digitized older records.

### Needs Help: Hire a Courthouse Runner

            The county requires special access (signed affidavits, license verification), has severely limited hours, or the data is so disorganized that you need a local contact who knows the system. This is where TaskRabbit and local networks shine.

            **Strategy:** Post a TaskRabbit task under "Personal Assistant" specifying the courthouse, record types needed, and format instructions. Provide clear written instructions with example screenshots of what the data should look like. Consider building an ongoing relationship with a reliable runner for monthly pulls.

            **Common examples:** Counties requiring affidavits for probate access, offices with 2-hour weekly public access windows, disorganized record systems requiring county clerk guidance.

## From Courthouse to First Contact in 48 Hours

        Every FTM record follows this path: six steps from raw county data to first marketing touch. Move faster, close more.

        The pipeline draws on scroll. Each step feeds directly into the next.

## Probate: The Most Complex, Most Rewarding FTM Source

        Probate has the highest margins because it has the highest barrier to entry. Messy data and hard research scare investors off. Exactly why it works.

            Finding Cases
            The Missing Address Problem
            Processing for CRM

### Finding Probate Cases

            Probate cases are filed at the county probate court (or Surrogate's Court in NY/NJ, Orphans' Court in PA/MD). You are looking for new estate filings where the decedent owned real property.

              County computer system showing probate case types. Not available online in many counties, requiring in-person access.

#### What to search for:

- **Case type:** Estate, Probate, Administration, Heirship Determination

- **Date range:** Last 30-90 days for fresh cases

- **Key data:** Decedent name, case/PR number, executor name and address, date of death

            Filter for residential property. Skip estates with only personal property (vehicles, bank accounts). Focus on cases where the executor has been appointed and is actively settling the estate.

### The Missing Address Problem

            Probate filings give you a case number, decedent name, and executor contact info. Not the property address. No address means no mail, no skip trace, no way to comp the deal.

            This is the exact problem the **Probate Property Finder** Claude skill solves. It takes the decedent name and county, browses the county assessor and deed records, and finds every parcel the decedent owned.

            **Manual process:** Search the county assessor website by decedent name. Cross-reference with deed records. Check for trust-held properties. This takes 20-45 minutes per record manually.

            **With the skill:** Paste the PR number, decedent name, and county. The skill browses the assessor and recorder sites, finds matching properties, and outputs a Sift-ready CSV. Works on single records or bulk CSV uploads.

### Processing Probate Records for CRM

            Once you have the property address, the probate record goes through the standard pipeline: skip trace, upload to CRM, assign filter preset, trigger niche sequential marketing.

#### Critical processing steps:

- **Owner swap:** Change the CRM record owner from the deceased to the executor/heir. Update mailing address to executor's address.

- **Tag by situation:** "Probate" tag plus specific sub-tags (multiple heirs, vacant, occupied by family).

- **Deep prospecting queue:** 22-38% of probate records need L3-L4 research to find the right decision maker.

- **Not-interested cadence:** Probate leads use a 45-day follow-up cycle (longer than the 15-day foreclosure or 90-day general cadence).

        22-38% of all distressed property lists have deceased owners, higher still for probate and foreclosure. If you skip deep prospecting your FTM leads, you leave deals on the table where most investors cannot find the decision maker.

## Tax Sales: PDF Goldmines Most Investors Ignore

        Some of the most accessible FTM data: counties post auction schedules and delinquency lists online. The catch: usually PDFs, not spreadsheets.

          Real tax sale PDF from a county treasurer's office. Structured data trapped in a non-exportable format.

          [View Full PDF](https://drive.google.com/file/d/1H8WqEa9ZzVWxCR1Zb38egLnRp9A9rask/view?usp=sharing)

            Auction Schedule Lists

              Published 30-60 days before the auction date. Contains property address, owner name, amount owed, and auction date. Check your county treasurer or trustee website monthly. Some counties publish in the local newspaper as required by state law.

              **Processing tip:** Copy the PDF text and paste into Claude with the prompt: "Extract this tax sale data into a CSV with columns: Property Address, Owner Name, Amount Owed, Auction Date, Parcel ID." Claude handles messy PDF formatting far better than manual extraction.

            Tax Delinquency Lists

              The full list of properties with unpaid taxes, not just those going to auction. Often thousands of records, including owners delinquent for years. Many counties publish these annually, some as online Excel files, the easiest FTM data to process.

              **Processing tip:** Filter for residential properties with 2+ years of delinquency. High equity is a strong indicator of motivation (they own the property outright but cannot pay taxes).

            Tax Lien Certificates

              In tax lien states, the county sells the tax debt as a certificate rather than selling the property. These certificates are public record. The property owner has a redemption period, and many sell during this window to avoid losing the property entirely.

              **Processing tip:** Focus on certificates approaching the redemption deadline. These owners face the most urgency. Marketing should emphasize helping them resolve the situation before they lose the property.

#### Do

- Use Claude to extract structured data from PDF tax sale lists

- Check county treasurer sites monthly for updated auction schedules

- Filter for residential properties with high equity

- Cross-reference with DataSift for existing records before uploading

#### Don't

- Manually type 200+ records from a PDF into a spreadsheet

- Wait until the week before auction to start marketing

- Skip the data cleaning step (remove commercial, vacant land, duplicates)

- Assume every delinquent property is a deal (many have liens exceeding value)

## Foreclosures: Speed Wins the Race

        The most time-sensitive FTM source: median notice-to-auction window is 34 days, your marketing window is Day 1 through Day 30. Every day waited, odds drop.

            Lis Pendens Filing
            Newspaper Notice

### Lis Pendens (Register of Deeds)

            Filed at the county Register of Deeds or County Clerk. Searchable online in many counties. This is the legal filing that starts the foreclosure process. You get: property address, owner name, lender, case number, filing date.

              TimingDay 1
Available the day it is filed

              FormatDigital
Searchable online portal

              CompletenessFull
Address, owner, lender, case #

              CompetitionLow
Few investors monitor filings daily

              County Register of Deeds portal. Lis pendens filings are searchable by date, owner name, or case number.

### Newspaper Legal Notice

            Required publication in a local newspaper before the auction. Typically published 3-4 weeks before the sale date. Contains property description, auction details, and sometimes owner information. More accessible but later in the timeline.

              TimingDay 20+
Published weeks before auction

              FormatText
Newspaper text, needs extraction

              CompletenessPartial
Legal description, not always address

              CompetitionHigher
More investors check newspaper notices

              Newspaper legal notice for a foreclosure auction. Requires extraction and formatting before CRM upload.

          For a complete analysis of foreclosure data using 12 months of real Knox County records (537 records, 248 unique properties).

## Find Where to Pull: The FTM County Data Skill

        Every county is different. Finding WHERE to pull data takes hours of calls and website hunting. This skill does it in minutes.

          The First-to-Market County Data skill takes a county name and returns every office, portal, phone number, and difficulty rating for each FTM data type. It covers three priority tiers:

#### Priority A: Core Lists

            Probate/Heirship, Foreclosure/Auction, Tax Sale, Tax Delinquency. The highest-value FTM sources. The skill finds the exact office, address, portal URL, and difficulty rating for each.

#### Priority B: Standard Lists

            Code Violations, Condemned Structures, Mechanic's Liens, IRS/State Tax Liens. Supplementary FTM sources that add volume to your pipeline.

#### Priority C: Extended Lists

            HOA/Condo Liens, Utility Shut-offs, Building Permits (demolition/repair), Bankruptcy filings. Advanced sources for operators who have exhausted A and B.

          Real output from the FTM County Data skill. Every office, portal, and difficulty rating for one county in minutes.

            1

#### Download the Skill

              Download the .skill file from the link below. This is a Claude custom skill that loads into your Claude Pro account.

            2

#### Load into Claude

              Open Claude (claude.ai), go to Settings, and import the skill file. It will appear in your skill library.

            3

#### Enter Your County

              Tell Claude which county and state you want to research. The skill runs the research prompts and returns a structured table of every data source available.

#### First-to-Market County Data Skill

            Claude custom skill for researching county data sources. Requires Claude Pro ($20/mo).

        See all available skills → Claude Skills for REI

          [Download Skill](https://drive.google.com/file/d/1xQuYOgOBM0bfPIKsy4zTh8qM1BDwUKQo/view?usp=sharing)

          See the real research output: [**FTM County Data Research Spreadsheet**](https://docs.google.com/spreadsheets/d/1abhhsk4F_bNZYpnaTJwBKJP0GXh2a7UU3_bq2F4fgl4/edit?usp=sharing)

## Solve the Missing Address Problem: Probate Property Finder

        Probate records give you a case number and a name. Not an address. No address, no marketing. This skill bridges the gap.

            Manual Research
            Probate Finder Skill

### Manual Property Discovery

            Search the county assessor by decedent name. Cross-reference with deed records. Check trust documents. Verify property type. Format for CRM upload. Repeat for every record.

              Time per Record20-45 min
Searching, cross-referencing, verifying

              Cost$1-3
At VA rates, realistic output

              Volume10-15/day
One person, full-time

              AccuracyVariable
Depends on researcher skill

### Probate Property Finder Skill

            Paste the decedent name and county. The skill browses county assessor and deed record websites, finds every parcel the decedent owned, and outputs a clean CSV ready for DataSift upload.

              Time per Record2-5 min
Automated browsing and extraction

              Cost$20+/mo
Claude Pro subscription, starting

              Volume50-100/day
Bulk CSV processing supported

              AccuracyHigh
County assessor is source of truth

### How It Works

              1

#### Input the Case Details

                Provide decedent name, county, and state. Optionally include PR number, executor name, and date of death for better matching.

              2

#### Skill Browses County Records

                The skill navigates the county assessor website, searches by owner name, cross-references with deed records, and identifies all parcels owned by the decedent.

              3

#### Get Sift-Ready Output

                Receive a formatted CSV with property addresses, parcel IDs, property types, and assessed values. Ready to upload directly to DataSift.

#### Probate Property Finder Skill

            Claude custom skill for discovering properties owned by probate decedents. Works on single records or bulk CSV.

          [Download Skill](https://drive.google.com/file/d/1_PtG_bfjdUcLroaMBArxrznrctQpXy70/view?usp=sharing)

        Probate Property Finder skill output. Structured research results ready for your CRM.

## When Data Is Not Online: TaskRabbit and Investor Networks

        Some of the best FTM data requires a physical visit. When you cannot go yourself, hire someone who can.

#### TaskRabbit

            ~$20/hr

        A TaskRabbit posting for a courthouse data pull. Typical cost: $25-50 per trip.

            Post under "Personal Assistant." Provide courthouse address, record types needed, and format instructions. Most tasks complete in 2-4 hours.

#### Investor Bootz

            Varies

            Network of runners specifically for real estate data pulling. Familiar with courthouse systems. Can handle more complex requests.

#### One Trip ROI

            $40-80

            Covers 2-3 list types per visit. If one lead from that trip closes, the ROI is 100x or more.

            TaskRabbit Personal Assistant category. Post your courthouse data pulling task here.

            Investor Bootz specializes in real estate investor services including courthouse data pulls.

            1

#### Post the Task

              On [TaskRabbit](https://www.taskrabbit.com/services/personal-assistant) or [Investor Bootz](https://investorbootz.com/), specify the courthouse address, which records you need (probate, tax sale, foreclosure), and the date range.

            2

#### Provide Clear Instructions

              Send written instructions with example screenshots of what the data looks like. Specify: take photos of every screen, export to USB if possible, note the office name and contact for future visits.

            3

#### Process the Data

              Receive photos or files from the runner. Use Claude to extract structured data from photographs or PDFs. Clean, format, skip trace, upload to CRM.

        A TaskRabbit courthouse runner costs $20/hour. One trip covers 2-3 list types: $40-80 for data nobody else in your market has. One closed lead at a $10,000 assignment fee is over 100x ROI.

## FTM Data Meets Niche Sequential Marketing

        First-to-market data is the fuel. Niche sequential marketing is the engine. Here is how they connect.

        Cleaned, skip-traced FTM records upload to DataSift and enter the niche sequential system. Each list type gets its own filter preset, which triggers the 3-day cadence, always cold-call-led: call first, then direct mail, then text.

            Cleaned FTM List
            CSV ready for upload

          →

            DataSift Upload
            Tag by list type

          →

            Filter Preset
            Auto-assign cadence

          →

            3-Day Cadence
            Call, Mail, Text

          Cleaned FTM records ride in tagged by list type. Each preset fires the 3-day cadence: call, mail, text.

#### Do

- Tag every FTM record by list type (Probate, Tax Sale, Foreclosure, etc.)

- Create dedicated filter presets for each FTM list type

- Use the niche sequential cadence (under 1,000 records, full 3-day cycle)

- Set up not-interested follow-up cadences (Probate 45 days, Foreclosure 15 days, General 90 days)

#### Don't

- Mix FTM records with purchased list records in the same filter

- Use bulk sequential (power dialer) on small FTM lists (under 1,000 records)

- Cold-text deceased or probate records: those run cold call, voicemail, mail, then deep-prospect the heir or executor, never a cold text

- Skip the tagging step (you lose the ability to track cost per contract by source)

- Forget to set up the not-interested follow-up cadences (20-30% of deals come from these)

          For the complete 12-filter setup, 3-day cadence walkthrough, and A-Z configuration guide, see the **Niche Sequential Marketing Guide**.

          For geographic filtering, distressor layering, and preset building, see the **SiftMap Mastery Guide**.

## Resources & Next Steps

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

      [#### FTM County Data Skill

Claude skill to research county data sources for any U.S. county](https://drive.google.com/file/d/1xQuYOgOBM0bfPIKsy4zTh8qM1BDwUKQo/view?usp=sharing)
          [#### Probate Property Finder Skill

Claude skill to discover properties owned by probate decedents](https://drive.google.com/file/d/1_PtG_bfjdUcLroaMBArxrznrctQpXy70/view?usp=sharing)
          [#### FTM Research Spreadsheet

Example output from the County Data Skill showing real research results](https://docs.google.com/spreadsheets/d/1abhhsk4F_bNZYpnaTJwBKJP0GXh2a7UU3_bq2F4fgl4/edit?usp=sharing)

#### Niche Sequential Marketing Guide

Complete 12-filter setup and 3-day cadence walkthrough for small FTM lists

#### Deep Prospecting Guide

4-level research depth framework for finding decision-makers on FTM leads

 Reset Progress

    ×
