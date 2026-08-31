# Guide: comping-workflow

> Source: https://learn.datasift.ai/comping-workflow (Day 4 module, fetched 2026-08-28)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

    Deal Analysis

# AI-Powered Comping Workflow

    One 9-step Claude skill. Appraiser-grade valuations in minutes, not hours.

        15 min read

## Comping Takes Too Long

    Traditional comping eats 45-90 minutes per property. Most operators either rush it and miss adjustments, or skip it entirely and guess.

      The Claude comping skill compresses that into a single conversation. Give it an address. It pulls public records, finds comparable sales, sorts them into two buckets, applies feature adjustments, checks market conditions, and delivers a complete analysis with a confidence-banded ARV range.

      The output is a 7-tab Excel workbook you can hand to a partner, lender, or contractor. Not a screenshot of a Zillow page. A structured report with the math trail visible at every step.

#### What It Produces

        7-tab Excel workbook: Executive Summary, Subject Property, Comparable Sales, Adjustments Detail, Market Analysis, ARV Calculation, Sources and Notes. Plus a full in-context breakdown.

#### What You Need

        Claude Pro ($20/mo), a property address, and optionally your own closed deal data for market calibration. That is it.

    This skill took roughly 25 iterations to build and was peer-reviewed against real closed deals. It is intentionally conservative: your ARV estimate should be the floor, not the ceiling. A high ARV that does not hold up kills deals.

        Download the Claude Comping Skill

        Upload this .skill file to Claude Co-Work or Claude Projects to start comping properties instantly. [Download from Google Drive](https://drive.google.com/file/d/1xfsQXSNZddwqAmHpVWvD6su0FcLzMYKK/view?usp=sharing)

        See all available skills → Claude Skills for REI

      Turning on the comping skill in Claude. Click to zoom.

    Core Framework

## The Two-Bucket Method

    Every comp goes into one of two buckets based on condition. The gap between them tells you what the market pays for renovation.

#### Bucket A: Unrenovated

        Dated finishes, original condition, deferred maintenance. Similar age, size, and layout to subject property.

#### Bucket B: Renovated

        Fully updated, flipped, or clearly modernized to current market standard. Verified via photos, remarks, or permits.

      Both buckets fill with comps. Renovated sells heavier per square foot, so bucket B sinks. The gap between levels is the market premium: 20.4% on Joyce Ann.

#### Bucket A Details

      Select comps with similar size/plan, average or below-average condition, sold within 90 days (6 months max), arm's-length sales only. Calculate the **Median PPSF_A** (price per square foot for unrenovated properties).

#### Bucket B Details

      Select comps that are flips or clearly modernized, verified via photos, remarks, and permits. Quality-adjust ultra-lux outliers, then calculate the **Median PPSF_B** (price per square foot for renovated properties).

      MARKET PREMIUM FORMULA

      Market Premium (%) = (PPSF_B - PPSF_A) / PPSF_A x 100%

    **This is not a rehab cost estimate.** The Market Premium is a market-derived metric. It tells you what buyers in this micro-market are willing to pay for updated finishes. Typical spread is 10-30%. Below 5% or above 30%, re-examine your comp selection. Something is off.

    The Joyce Ann renovation premium was 20.4%: renovated homes in Harrison Township sell for roughly 20% more per square foot than dated ones. A healthy spread. At 5% or less, flipping does not pay. At 35%+, recheck your comp buckets.

## Disclosure vs Non-Disclosure

    The skill auto-detects which framework to use based on property address. Disclosure states have visible sold prices. Non-disclosure states hide them, requiring a triangulation method.

        Disclosure (38 States)
        Non-Disclosure (12 States)

### Two-Bucket Method (Standard)

        Sold prices are publicly recorded. The skill pulls actual sale prices from MLS, county records, and aggregators (Zillow, Redfin). Comps are sorted into Bucket A and Bucket B using real sold data.

#### Confidence Band

          ±2-5% on final ARV. Tighter range because you are working with actual sold prices.

        This is the framework used in the 5532 Joyce Ann example. Ohio is a full disclosure state.

### Triangulation Method

        Sold prices are not publicly recorded. The skill must derive estimated sold prices (ESP) using multiple methods before it can apply the Two-Bucket analysis.

#### Method A: Last List Price + DOM

            Find the last list price before "Pending." Under 7 DOM = list price or 101%. 7-30 DOM = 97-100%. Over 30 DOM = 90-95%.

#### Method B: Deed of Trust Calculation

            Find the loan amount from public records. Conventional: Loan / 0.80. FHA: Loan / 0.965. VA: Loan / 1.00.

#### Method C: Tax Value Ratio (Sanity Check)

            Compare assessed value to list price ratios for active homes. Apply multiplier. Use only as confirmation, never as primary method.

#### Confidence Band

          ±5-7% on final ARV. Wider range because you are working with derived prices, not actual sold data.

        Non-Disclosure States:

          TXUTWYNMIDMTNDAKKSMSLAMO

## The 5532 Joyce Ann Comp Report

    A 1961 brick ranch in Dayton, OH. 3 bed, 2 bath, 1,892 sqft, dated condition. The skill produced a 7-tab report. Here is every tab.

      Executive Summary
      Subject Property
      Comparable Sales
      Adjustments
      Market Analysis
      ARV Calculation
      Sources

        Executive Summary tab. Click to zoom.

### What This Tab Shows

      The executive summary is your one-page overview. Three sections at a glance:

      **Subject Property:** Address, property type (Single Family, Brick Ranch), 1,892 sqft, 3/2, built 1961. Confirms the skill pulled the right property.

      **ARV Analysis Results:** Final ARV of $265,000 with a range of $252,000 to $278,000. Moderate confidence. Post-renovation price per square foot of $150.53.

      **Market Snapshot:** Balanced market. Median sale price $225,000, median PPSF $131. Average 34 days on market. 98% sale-to-list ratio. This tells you the market is not distressed and not overheated.

        Subject Property tab. Click to zoom.

### What This Tab Shows

      Every data point the skill gathered about the subject property, organized into four sections:

      **Basic Information:** Full address, city (Dayton), state (OH), ZIP (45415), county (Montgomery), subdivision (Harrison Township).

      **Property Characteristics:** 1,892 sqft living area, 13,068 sqft lot, 3 bed / 2 bath, 1961 build, 1 story, 2-car attached garage, no pool, unfinished basement (mechanical/storage).

      **Current Condition:** Dated. Cosmetic rehab needed. Renovation scope to be determined in a separate workflow.

      **Ownership and Legal:** Individual owner, residential zoning, no HOA. Clean.

      **Cross-check your GLA.** The Sources tab flagged a discrepancy: some public records show 1,652 sqft vs the 1,892 sqft used here. If actual GLA is closer to 1,652, the ARV drops to roughly $240,000 and the wholesale price falls to around $195,000. Always verify GLA with the county assessor before making an offer.

        Comparable Sales tab. Click to zoom.

### 6 Comps, Two Buckets

      The skill found 6 comparable sales within 2 miles, all sold in the last 90 days, all 3/2 brick ranches built between 1955-1975. Here is the full breakdown:

           |

               | # | Address | Date | Price | GLA | PPSF | Condition | Dist. | Adj. | Adj. Value | Bucket

             | 1 | 5802 Sparkhill Dr | Dec 12 | $190,000 | 1,520 | $125.00 | Partial Update | 1.2 mi | +$22,000 | $212,000 | A

             | 2 | 6407 Woodville Dr | Nov 15 | $210,000 | 1,686 | $124.56 | Average | 1.5 mi | +$8,000 | $218,000 | A

             | 3 | 6012 Imperial Hills Dr | Jan 12 | $208,750 | 1,669 | $125.07 | Good/Maintained | 1.8 mi | +$9,000 | $217,750 | A

             | 4 | 6430 Oakhurst Pl | Dec 19 | $240,000 | 1,657 | $144.84 | Dated | 1.6 mi | +$10,000 | $250,000 | A

             | 5 | 701 Fredericksburg Dr | Dec 29 | $239,900 | 1,464 | $163.87 | Updated | 0.8 mi | +$17,000 | $256,900 | B

             | 6 | 6029 Imperial Hills Dr | Dec 29 | $210,000 | 1,411 | $148.83 | Good | 1.8 mi | +$19,000 | $229,000 | B

####

        TWO-BUCKET RESULTS

        **Bucket A (4 comps):** Median PPSF $125.03 | Avg $129.87

        **Bucket B (2 comps):** Median PPSF $156.35 | Avg $156.35

        Renovation Premium: 20.4%

        Adjustments Detail tab. Click to zoom.

### Line-by-Line Adjustments

      Every comp gets adjusted to make it comparable to the subject property. The skill applied three types of adjustments across the 6 comps:

#### GLA Adjustments

          +$78,000 total. The subject (1,892 sqft) was larger than every comp. Comp 6 was 481 sqft smaller, earning the biggest adjustment (+$19,000).

#### Condition Adjustments

          -$3,000 total. One comp (5802 Sparkhill) had newer roof and windows than the subject. The adjustment accounts for that advantage.

#### Basement Adjustments

          +$10,000 total. The subject has an unfinished basement. Comp 1 (5802 Sparkhill) only had a crawl space. Adjustment reflects the storage and expansion value.

        TOTAL ADJUSTMENTS ACROSS ALL COMPS

        GLA +$78,000 | Condition -$3,000 | Basement +$10,000 = Net +$85,000

        Market Analysis tab. Click to zoom.

### Market Health Check

      Before the skill calculates ARV, it reads the market. The Market Analysis tab has three sections:

#### Market Metrics

          Balanced market. Median price $225,000, PPSF $131. 34 avg DOM. 98% sale-to-list ratio. 45 active listings, 22 pending, 3.5 months of inventory.

#### Market Trends

          3-month: Stable (+1.2%). 6-month: Slight appreciation (+3.8%). DOM stable at 30-40 days. Inventory balanced.

      **Local color matters.** The market notes section captured that Huber Heights / Harrison Township is known as the world's largest community of brick homes. Average home value around $204K, up 3.8% year-over-year. It also flagged that the subject has an R-22 A/C condenser that will need full replacement (R-22 refrigerant is phased out), and the new furnace (2024) is a strong selling point. These details affect both your rehab budget and your marketing strategy post-renovation.

        ARV Calculation tab. Click to zoom.

### The 9-Step ARV Math

      This is where the skill shows its work. Every number traces back to a specific data point. No black boxes.

Base PPSF (Unrenovated)
$125.03

Renovation Premium
20.4%

Post-Reno PPSF
$150.53

Market Sentiment Adjustment
-2.0%

Adjusted PPSF
$147.52

Subject GLA
1,892 sqft

Base ARV (PPSF x GLA)
$279,108

Feature Adjustments
-$14,000

FINAL ARV
$265,000

#### Confidence Analysis

          Moderate confidence. ±5.0% band. ARV Low: $252,000. ARV High: $278,000.

#### Why -2% Sentiment?

          Balanced market with 98% sale-to-list ratio. Not hot enough for a positive bump, but the slight positive trend (+1.2% 3mo) prevents a deeper cut.

        Sources and Notes tab. Click to zoom.

### The Paper Trail

      Every good comp report is auditable. This tab documents where the data came from and what constraints were applied.

#### Data Sources

          Zillow, Sibcy Cline MLS, Coldwell Banker MLS, ATTOM Data, Montgomery County Auditor, Homes.com, and subject property due diligence photos.

#### Search Parameters

          90-day window (Dec 2025 - Feb 2026). 2-mile radius. GLA range 1,400-2,150 sqft. Year built 1955-1975. Harrison Twp / Butler Twp / North Dayton.

### Key Recommendations

      The skill flagged several items for verification before making an offer:

- Verify GLA with county assessor. Records show 1,652 vs 1,892 sqft discrepancy.

- Get actual basement square footage and finish level. Unfinished adds $5-10K, finished could add $15-25K.

- R-22 A/C condenser needs full replacement (refrigerant phased out).

- Electrical panel should be evaluated (original 1959 panel).

- Run title search. Check permit history for unpermitted additions.

- Wholesale price target: $205,000-$215,000. Selling points: new furnace, 1,892 sqft, sunroom, fenced yard.

      Next 5-Day Deal Flow Challenge: Monday, September 21 to September 25. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Adjustment Cheatsheet

    The skill uses these ranges when adjusting comps. Values shift by price tier and climate. Expand each category to see the full table.

        Bedrooms and Bathrooms

           |  | Feature | Under $500K | Over $500K

             | Bedroom | +$10,000 | +$25,000

             | Full Bath | ±$10,000 | ±$10,000

             | Half Bath | ±$5,000 | ±$5,000

        Garage and Parking

           |  | Feature | Standard | Hot/Cold Climate

             | Garage | $10,000-$15,000 | $20,000-$25,000

             | Carport | $5,000-$7,500 | $10,000

          **Climate note:** Use high end in very hot (AZ, NV, TX) or very cold (IL, MN, WI) markets. Hail-prone areas (TX, OK, CO) make garage vs carport a major differentiator.

        Traffic and Location

           |  | Issue | Under $500K | Over $500K

             | Backing busy road | -$10,000 | -10% to -15%

             | Fronting busy road | -$20,000 | -20%

             | Commercial adjacency | -$10K to -$20K | -10% to -15%

        Pool, Lot Size, and Views

           |  | Feature | Under $500K | Over $500K

             | Pool (hot climate) | +$20K to +$40K | +$20K to +$40K

             | Pool (cold climate) | +$5K to +$15K | Negative possible

             | Extra 5,000 sqft lot | $5K-$10K | $30K-$50K

             | Water view | +$20K-$50K | +$50K-$150K

        Basement and ADU

          **Basements** are not counted as GLA by appraisers. Value depends on finish level:

           |  | Finish Level | Value (% of Above-Grade PPSF)

             | Finished to same quality | ~50%

             | Finished with drop ceilings | ~35-40%

             | Partially finished | ~25-35%

             | Unfinished | ~10-15%

          **ADUs:** Not separately deeded = ~50% of equivalent value. Separately deeded/titled = 100% at local PPSF.

        Foundation (Critical for TX/OK)

           |  | Issue | Adjustment

             | Minor cracks (cosmetic) | -$5,000 to -$10,000

             | Moderate issues | -$15,000 to -$25,000

             | Major repair needed | -$25,000 to -$40,000+

             | Previous repair (documented) | -$5,000 to -$10,000

## Draw Your Polygon in SiftMap

    The comping skill works with any address. But if you want to constrain where it looks for comps, draw a polygon in SiftMap first.

      SiftMap polygon with investor transaction filter. Click to zoom.

### Why Draw a Polygon?

      The skill's default search uses a radius from the subject property. That works in most markets. But in block-by-block markets where values shift street to street, a polygon gives you precision. You are telling the skill: "Only look inside these boundaries."

      The golden rule of comping: **do not cross major roads.** Thick yellow lines on the map are value boundaries. The polygon lets you enforce that.

#### Investor Transaction Filter

        Toggle the investor transaction filter in SiftMap to see what investors are paying in the area. These are real acquisition prices, not retail sales. Gives you ground truth for your wholesale price target.

#### Edit to Refine

        The default polygon is accurate enough for most markets universally. But you can edit it to focus on a specific sub-area for more refined results. Narrow the polygon to 3-4 blocks around your subject for hyper-local comps.

    Most operators never need to edit the polygon. The default radius-based search pulls solid comps in any market. But where values change block by block (older urban areas, waterfront transitions), tightening the polygon is worth the 30 seconds.

## Customize with Your Own Deals

    The default adjustment tables are national averages. Your closed deals are ground truth. Feed them to the skill and it calibrates automatically.

      Editing the comping skill in Claude Co-Work. Click to zoom.

### How It Works

      Open the comping skill in Claude Co-Work (or Claude Projects). Add 3-5 properties you have closed in your target market. For each property, include:

- Property address and basic specs (beds, baths, sqft, year built)

- Your purchase price (what you paid)

- Rehab cost (actual spend, not estimate)

- Final sold price or appraised ARV (what it sold for or appraised at)

- Any notable adjustments (pool added, garage converted, foundation repaired)

      The skill uses your closed deals to recalibrate its adjustment ranges, market sentiment assumptions, and confidence bands for your area. Instead of using national averages for "garage adds $10-15K," it learns that in your market, a 2-car garage adds $18K based on your actual data.

### Draft Your Calibration Prompt

    Use the field below to draft your calibration data. Include 3-5 closed deals with the details listed above.

#### Do This

        Feed real closed deals with exact numbers: purchase price, rehab spend, final sold price.

        Include 3-5 properties from the same market or sub-market.

        Note any unusual features (pool added, foundation repair, lot split).

#### Not This

        Do not tell Claude "my market is hot" without data to back it up.

        Do not use deals from different cities or states as calibration data.

        Do not mix flips with buy-and-hold rentals. Different exit strategies, different comps.

    Do not re-enter calibration data every time you comp. Save it inside the skill's project or Co-Work space; Claude remembers it across conversations. Three solid closed deals from your market improve accuracy for every future comp.

## Resources

    Tools, references, and related guides.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, September 21 to September 25

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

      [#### Download the Comping Skill

The .skill file for Claude. Upload to Co-Work or Projects to start comping.](https://drive.google.com/file/d/1xfsQXSNZddwqAmHpVWvD6su0FcLzMYKK/view?usp=sharing)
      [#### Claude Pro

$20/mo. All you need to run the comping skill. No Max plan required.](https://claude.ai)

#### Rehab Estimator Workflow

Companion guide: rehab estimation, finish tiers, scoping, deal economics.

      [#### Deal Flow Tech Stack SOP

Complete tool stack with pricing for every phase.](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)
      [#### Case Studies

Real operator results across all four phases.](https://go.dataflik.com/case-studies-intermediate)
      [#### Critical Resource Hub

83 tools and resources across all 5 days of the Deal Flow Challenge.](https://docs.google.com/spreadsheets/d/1bQBHLsxVwXbsbz9SBcfpatPaFgAIsICo/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

#### Rehab Estimator Workflow

Turn inspection photos into contractor-grade rehab estimates with the Claude Rehab Estimator skill.

          Reset

  ×
