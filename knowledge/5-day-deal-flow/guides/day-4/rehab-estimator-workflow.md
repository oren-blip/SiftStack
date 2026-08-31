# Guide: rehab-estimator-workflow

> Source: https://learn.datasift.ai/rehab-estimator-workflow (Day 4 module, fetched 2026-08-28)
> Hub pages are sunset each cohort; this is the durable copy.

---

On this page

      On this page
      ×

      Deal Analysis

# Rehab Estimator Workflow

      Turn inspection photos into contractor-grade rehab estimates in minutes. Dialed in over 4 iterations.

        ~12 min read
Cost: $20/mo (Claude Pro)
        Companion: Comping Workflow

## Everyone thinks rehab estimating is about knowing material prices.

    It's not. It's about knowing what NOT to include.

      The Claude Rehab Estimator skill builds room-by-room scopes, prices materials by region, and generates a 9-tab Excel workbook. Feed it inspection photos and a comp report, and it returns a contractor-grade estimate you can hand to your GC for verification.

      Out of the box, the skill estimates conservatively. That is by design. After calibrating with 3-5 closed deals, it tightens to within 10-15% of actual contractor SOWs.

      This page uses the same property as the Comping Workflow: 5532 Joyce Ann Dr, Dayton OH, same $265,000 ARV. The skill generated a **$63,379 full rehab estimate** and an **$11,358 wholetail estimate**. Every tab and line item is below.

        **Download the Rehab Estimator skill:** [Get the skill file](https://drive.google.com/file/d/1AhPX4u2XFE1eilxOm6TC4M3hJlvFUNQl/view?usp=sharing). Upload it to Claude and activate in your Project settings.

        See all available skills → Claude Skills for REI

      Uploading resources and turning on the Claude rehab skill. Click to zoom.

    You must do the comping first, because to estimate rehabs, we have to understand value. The comp report's renovation premium tells you what the market pays for improvements. Without that, you are guessing at finish level.

## From conservative to contractor-grade.

    Out of the box, the skill estimates high. Feed it 3-5 closed deals with real contractor SOWs, and it locks into your market's pricing.

      Conservative on purpose: a high estimate that costs you a deal saves you from a bad one. A low estimate that misses $15K kills profit. Expect estimates 20-40% above contractor bids before calibration, within 10-15% after.

        Before Calibration
        After Calibration

#### Conservative Scoping

            Includes items like staging, permits, and system replacements that may not apply. Better to flag them and remove than to miss them entirely.

#### Premium Material Pricing

            Defaults to higher finish tiers until your comp data tells it otherwise. The renovation premium from your comp report sets the correct tier.

#### Broad Methodology

            Uses category-level pricing (paint as 3 items, full demo) instead of the single-rate contractor methodology your market uses.

#### Tight Room-by-Room Scope

            Only includes what the property needs. Newer systems get skipped. Marketing costs stay separate from the contractor bid.

#### Market-Matched Tier Pricing

            Finish tier set by your comp report's renovation premium. For this property: Tier 3 (Investor-Flip Grade) at $33.50/SF.

#### Contractor Methodology

            Paint as a single $/SF rate. Selective demo, not full gut. Contingency on a tight base. The estimate reads like a real SOW.

    **What calibration fixes:** Phantom line items (staging, permits, unnecessary system work), paint methodology (single $/SF vs 3 items), scope matching (selective vs full demo), contingency sizing (10-20% on a tight base, not 15% on inflated numbers), and finish tier alignment with your comp report's renovation premium.

    The Finish Tier Framework

## Four tiers. Your comps pick the tier. Not you.

    The cardinal rule: match the comps. If renovated comps have laminate counters, you use laminate regardless of ARV. The market rewards what it rewards.

      Four finish tiers, one honest pick. The renovated comps slide across the staircase and clamp the estimate to tier 3, the standard investor flip.

        1

### Builder Grade

        $15-25/SF

        Wholetails, rentals, <$100K ARV markets

        2

### Mid Grade

        $25-40/SF

        Low-end flips, $100K-200K ARV markets

        3

        Most Common

### Investor-Flip Grade

        $35-60/SF

        Standard flips, HGTV-ready, $200K-400K ARV

        4

### Retail-Premium

        $50-80+/SF

        High-end markets, $400K+ ARV, luxury finishes

      Tier 1: Builder Grade

#### Budget Finishes for Maximum ROI

      Target buyers: investors, budget retail buyers, Section 8 tenants. Keep it simple, keep it clean, keep it cheap.

         | Category | Specification

         | Flooring | Basic LVP ($1.50-2.50/SF) or carpet in bedrooms

         | Kitchen Cabinets | Existing cleaned/painted, or cheapest RTA stock

         | Countertops | Laminate or butcher block

         | Appliances | Basic white or black, used/refurbished acceptable

         | Bathroom | Clean existing or basic replacements, fiberglass tub surround

         | Paint | 1 neutral color throughout (SW Alabaster or BM White Dove)

         | Fixtures | Chrome, basic builder-pack from big box

      Tier 2: Mid Grade

#### First-Time Buyer Appeal

      Target buyers: first-time homebuyers, retail buyers in affordable markets. One step above builder, but still disciplined.

         | Category | Specification

         | Flooring | LVP throughout ($2.50-4.00/SF), carpet in bedrooms OK

         | Kitchen Cabinets | Painted existing (spray) or stock shaker-style (white/gray)

         | Countertops | Butcher block or entry-level granite/quartz

         | Appliances | New stainless, basic models (Frigidaire, Whirlpool base)

         | Bathroom | New vanity + mirror + toilet, reglaze or basic tub surround

         | Paint | 2 colors max (Agreeable Gray walls + Extra White trim)

         | Fixtures | Brushed nickel throughout

      Tier 3: Investor-Flip Grade

#### The Sweet Spot for Most Flips

      "HGTV ready" without being luxury: the tier used on 5532 Joyce Ann Dr. Actual $/SF: **$29.19** (low end of range because no full systems replacement was needed).

         | Category | Specification

         | Flooring | Higher-end LVP ($3.50-5.00/SF), carpet OK in bedrooms

         | Kitchen | New stock shaker cabinets (soft-close) + quartz countertops + subway tile backsplash

         | Appliances | Stainless package (Samsung, LG, Whirlpool Gold)

         | Bathroom | New vanity (36"+), tile floor, tile tub surround, framed mirror

         | Paint | Professional 2-3 color scheme, spray doors for factory finish

         | Fixtures | Matte black or brushed gold (trending), coordinated

         | Extras | Recessed lights, pendant over island, barn door (1-2), open shelving

      Tier 4: Retail-Premium

#### Luxury Markets Only

      Target buyers: move-up buyers, executives. Only justified when renovated comps show premium finishes at $400K+ ARV.

         | Category | Specification

         | Flooring | Engineered hardwood or wide-plank LVP, heated tile in bathrooms

         | Kitchen | Semi-custom to custom cabinets, premium quartz/stone, waterfall island

         | Appliances | Premium stainless (KitchenAid, Bosch, Cafe), panel-ready

         | Bathroom | Freestanding tub, frameless glass shower, large-format tile, designer vanities

         | Paint | Designer color scheme, board & batten or shiplap accents

         | Fixtures | Luxury brands (Delta, Moen, Kohler premium lines)

         | Extras | Smart home, wine storage, custom mudroom, outdoor living, layered lighting

      ARV < $100K → Tier 1  |  $100-200K → Tier 2  |  $200-400K → Tier 3  |  $400K+ → Tier 3 or 4

      Always override with comp evidence. If renovated comps have laminate counters, use laminate regardless of ARV.

## Room-by-room, not category-by-category.

    Category scoping creates phantom items that exist in a spreadsheet, not the house. The skill scopes room-by-room: what you would see walking the property.

#### Do

        Scope room-by-room: kitchen, bathrooms, bedrooms, living areas, back porch, mudroom, hallways, exterior. Walk each space and note only what needs to change.

#### Don't

        Scope category-by-category: "all flooring across the house, all plumbing, all electrical." This creates phantom line items in rooms that do not need that work.

#### Do

        Use a single $/SF rate for paint covering walls, ceiling, and trim. Real contractors quote $2.90-3.00/SF flat.

#### Don't

        Break paint into 3 separate line items (walls, trim, ceiling). This tripled the paint cost from $7,763 to $16,878 in the V1 estimate.

#### Do

        Include appliances only when CRM notes, photos, or inspection confirm they are missing, broken, or dated. Always include a stainless package when comps show updated kitchens.

#### Don't

        Default to replacing all appliances on every property. And never forget them entirely. The V4 test missed appliances completely, a $2,950 error.

      $55,218 ÷ 1,892 SF = $29.19/SF

      Tier 3 range: $35-60/SF. This property came in at the low end because it did not need full systems replacement (HVAC, plumbing, electrical were functional).

### The 60-65% Rule

    Your per-SF cost, multiplied by 0.60-0.65, should approximate your materials-only cost. **If materials exceed 65% of total, labor is underpriced.** If materials are below 50%, you may be over-scoping materials. For a standard flip at $25-35/SF, materials should run $15-23/SF.

    If your estimate exceeds $40/SF on a standard cosmetic flip, you are almost certainly over-scoping.

    The skill is built conservative because people talk rehab costs down to make deals work. A low estimate that misses $15K in repairs kills your profit on the back end. Conservative is a feature, not a bug.

## 7 steps from inspection photos to Excel workbook.

    The skill follows this sequence every time. More context at the start means a tighter estimate at the end.

        1

#### Gather Intel

          Upload the inspection report, property photos, CRM notes from the homeowner conversation, and the comp report from the comping skill. The more context you give, the better the scope. Inspection reports produce the best results. Photos alone are a distant second.

            An inspection report with good photos gives the skill room-by-room condition data. Click to zoom.

            **Need an inspection?** [Investor Bootz](https://investorbootz.com/) provides investor-focused property inspections. [See an example report](https://drive.google.com/file/d/1YqwMJd8NS6sUYsY2S_3rSLdJyxDR6HU_/view?usp=sharing).

        2

#### Photo Analysis

          The skill reads room-by-room photos and builds a condition assessment for each area. It identifies what needs work (damaged drywall, dated fixtures, failed windows) and what does not. This becomes the foundation for the scope.

        3

#### Read Calibration Data

          If you have fed the skill your real-deal calibration data (actual contractor SOWs from closed deals), it adjusts every pricing assumption to match your market. Without calibration data, it uses verified national benchmarks adjusted by region.

        4

#### Build Scope (Room-by-Room)

          Each room gets its own line items based on visible condition: paint, flooring, outlets/switches ($100/room), light fixtures, doors. A second pass catches transitional spaces (hallways, mudroom, back porch, laundry, foyer) that add $3,000-4,000 to a typical scope.

        5

#### Localize Pricing

          Regional cost adjustments applied automatically. The skill sources material pricing from Amazon, Lowe's, and Home Depot by your property's region. Labor costs adjust based on market tier (0.7x for low-cost rural to 1.5x for high-cost metro).

        6

#### Cross-Reference Comps

          The renovation premium from your comp report (Bucket B minus Bucket A PPSF) sets the ceiling for finish level. Thin gap: the market is not rewarding heavy renovation. Wide gap: a higher finish tier is justified.

            The comp report's renovation premium determines your finish tier ceiling. Click to zoom.

        7

#### Generate Deliverables

          The skill outputs a 9-tab Excel workbook with: Summary, Full Rehab Estimate, Wholetail Estimate, Condition Assessment, Material Spec, Deal Analyzer, Budget Tracker, Project Checklist, and Comp Report reference. Walk through each tab in the next section.

## 9-tab Excel walkthrough: 5532 Joyce Ann Dr.

    Every tab from the real rehab estimate. Same property, same $265,000 ARV. Full rehab: $63,379. Wholetail: $11,358. All data pulled from the actual workbook.

        Summary
        Full Rehab
        Wholetail
        Condition
        Material Spec
        Deal Analyzer
        Budget Tracker
        Checklist
        Comp Report

#### Summary Dashboard

        The executive overview: purchase price, ARV, both estimates side-by-side, finish tier, and deal metrics. This is the tab you screenshot for your partner or lender.

          Property
5532 Joyce Ann Dr

          Size / Type
1,892 SF · 3/2 · 1961

          ARV
$265,000

          Purchase Price
$155,000

          Full Rehab Estimate
$63,379 ($33.50/SF)

          Wholetail Estimate
$11,358 ($6.00/SF)

          Finish Tier
Tier 3: Investor-Flip

          Local Pricing
0.82x (Dayton, OH)

          **View the full rehab estimate:** [Open in Google Sheets](https://docs.google.com/spreadsheets/d/1rLaXdrKJLtTdveaHc_lf91tnnV2buMq4/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

        Summary dashboard with key metrics. Click to zoom.

#### Full Rehab Estimate

        The complete itemized scope of work: every line item with quantity, unit cost, and installed total, organized room-by-room. Hand this to your contractor for verification.

             |  | Category | Cost

               | Demo & Cleanup | $3,560

               | Paint | $7,795

               | Flooring | $8,090

               | Kitchen | $8,008

               | Bathrooms | $8,500

               | Windows & Doors | $9,775

               | Electrical | $1,556

               | Drywall | $750

               | Trim & Millwork | $608

               | HVAC (A/C only) | $2,800

               | Appliances | $2,950

               | Exterior | $1,425

               | Landscaping & Cleanup | $1,800

               | Subtotal | $57,617

               | Contingency (10%) | $5,762

               | Total | $63,379

        Full rehab estimate with labor and materials breakdown. Click to zoom.

#### Wholetail Estimate

        The light-touch alternative. The skill generates both estimates side-by-side so you can compare exit strategies using profit-per-month.

          Wholetail Estimate
$11,358

          Cost per SF
$6.00/SF

          Contingency
5%

          ROI
29.2%

        Scope: paint, clean, landscaping, A/C replacement, minor repairs. No kitchen reno, no windows, no flooring.

        Wholetail estimate: minimal scope, faster timeline. Click to zoom.

#### Condition Assessment

        Room-by-room condition grading from inspection photos. "Poor" gets full renovation, "fair" gets targeted updates, "good" gets left alone.

             |  | Area | Grade | Key Finding

               | Roof | Poor | 10+ years, needs inspection

               | Kitchen | Poor | Original 1960s cabinets

               | Bathrooms | Poor | Pink fixtures, OSB ceiling

               | Flooring | Poor | Worn parquet throughout

               | A/C Condenser | Poor | R-22 unit, must replace

               | Furnace | Good | NEW (2024), do not scope

               | Electrical Panel | Fair | Breaker (not fuse), adequate

               | Plumbing | Good | Copper supply, no issues

               | Windows | Fair | Functional vinyl, dated

               | Brick Siding | Good | Solid, minor tuckpointing

        Room-by-room condition grades from inspection evidence. Click to zoom.

#### Material Specifications

        Brand, spec, and cost for every material. This tab turns the estimate into a shopping list your contractor can price-check at the local supply house.

             |  | Item | Spec | Price

               | Interior Paint | SW Agreeable Gray (SW 7029) | $45-55/gal

               | Trim Paint | SW Extra White (SW 7006) | $55-65/gal

               | LVP Flooring | Lifeproof, 7mm+, gray wood-look | $2.50-3.50/SF

               | Carpet | Mohawk/Shaw, 30-40oz | $1.50-2.50/SF

               | Cabinets | White shaker, soft-close | $150-250/LF

               | Countertops | Level 1 Granite (Luna Pearl) | $50/SF installed

               | Backsplash | White 3x6 subway tile | $1.50-3.00/SF

               | Light Fixtures | Matte black LED flush mount | $25-50/EA

               | Door Hardware | Matte black levers | $15-25/EA

        Material specifications with brand, model, and cost. Click to zoom.

#### Deal Analyzer

        Full deal economics for both exit strategies. Acquisition, rehab, and projected profit side-by-side.

             |  | Metric | Full Rehab | Wholetail

               | ARV | $265,000 | $265,000

               | Purchase Price | $155,000 | $155,000

               | Rehab Cost | $63,379 | $11,358

               | Total Investment | $218,379 | $166,358

               | Potential Profit | $46,621 | $48,642

               | ROI | 21.3% | 29.2%

               | 75% Rule MAO | $135,371 | N/A

        Deal analyzer: all costs included, not just ARV minus purchase minus rehab. Click to zoom.

#### Budget Tracker

        Variance tracking during the rehab: all 14 line items auto-populate from the Full Rehab tab, with invoice and paid date columns keeping your draw schedule organized. Enter actual costs as invoices arrive and the Variance column flags where you stand.

        The difference between "I think we are on budget" and "I know we are $2,300 over on windows."

        Budget tracker: estimated vs actual by category. Click to zoom.

#### Project Checklist

        5-week project timeline with checkable milestones. From pre-construction through listing prep.

- **Pre-Construction:** Utilities, inspection, bids, permits, materials, dumpster

- **Week 1:** Demo & Rough (plumbing, electrical, HVAC, framing)

- **Week 2:** Systems (inspections, insulation, drywall, windows, exterior)

- **Week 3:** Finishes (paint, flooring, cabinets, tile)

- **Week 4:** Fixtures (countertops, plumbing, electrical, appliances, hardware)

- **Week 5:** Punch List (walkthrough, inspections, carpet, deep cleaning)

- **Listing Prep:** Staging, professional photos, MLS listing, lockbox

        Project checklist: scope verification and completion tracking. Click to zoom.

#### Comp Report Reference

        The Two-Bucket comp analysis behind this estimate: Bucket A (unrenovated, $125.03 PPSF) vs Bucket B (renovated, $156.35 PPSF). The 20.4% renovation premium confirmed Tier 3 finishes and set the rehab budget ceiling.

        Two-Bucket comp analysis: the renovation premium that drives finish tier selection. Click to zoom.

      **See the full comp report for this property:** [Open in Google Sheets](https://docs.google.com/spreadsheets/d/1_YBUHRsAB2JG1zuNJ_eOsaNGqKt-7hid/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

      Next 5-Day Deal Flow Challenge: Monday, September 21 to September 25. Save your seat in the next cohort. Already enrolled? Use this as your between-session refresher.
      Save Your Seat →

## Wholetail vs Full Rehab: the profit-per-month test.

    A $25K wholetail profit in 1 month beats a $45K flip in 5 months. The comp report picks the exit; the skill builds both estimates.

        Full Rehab
        Wholetail

#### Cost Range

            $35-60/SF (Tier 3). Every visible surface, all outdated systems, full kitchen and bath remodel.

#### Timeline

            8-16 weeks for rehab + 1-2 months marketing + 1 month closing = 4-6 months total hold.

#### Exit Buyer

            Retail homebuyer via MLS at full ARV. Needs to be "show ready" with updated finishes throughout.

#### Scope Includes

            New flooring, cabinets, countertops, appliances, fixtures, paint, doors, trim, lighting, windows (if needed).

           | Category | Full Rehab

           | Kitchen cabinets | Replace or reface

           | Countertops | Quartz or granite

           | Appliances | New stainless package

           | Bathroom | Full remodel (vanity, tile, fixtures)

           | Flooring | LVP throughout + carpet in bedrooms

           | Windows | Replace if single-pane or damaged

           | HVAC | Replace if >15 years or failed

           | Interior doors | Replace all (matching style)

#### Cost Range

            $5-15/SF. Paint, clean, minor repairs, landscaping. Fix what is broken. Leave what is functional.

#### Timeline

            1-3 weeks rehab + 1 month marketing + 1 month closing = 2-3 months total hold.

#### Exit Buyer

            Investor, first-time buyer, or MLS at discount to ARV. Functional and clean, not show-ready.

#### Scope Includes

            Full interior repaint (1 neutral color), deep clean, landscaping, targeted repairs only.

           | Category | Wholetail

           | Kitchen cabinets | Clean only (paint if dated)

           | Countertops | Laminate OK if functional

           | Appliances | Clean existing, replace only if broken

           | Bathroom | Clean, reglaze tub, replace only if damaged

           | Flooring | Only in damaged/stained areas

           | Windows | Only if broken or non-functional

           | HVAC | Service only, replace if non-functional

           | Interior doors | Paint existing, replace only if damaged

      Profit Per Month = Net Profit ÷ Total Hold Time (months)

      A wholetail with $25K net in 2 months = $12,500/mo. A flip with $45K net in 5 months = $9,000/mo. The wholetail wins on velocity even with less absolute profit.

    **The cost ratio benchmark:** Wholetail costs should typically be 15-30% of full rehab costs. If the ratio is higher, too much deferred maintenance for a wholetail. If lower, the property may be a better wholetail candidate than a flip.

## The skill adjusts for your market. Here is how.

    National benchmarks are a starting point. Four factors adjust the estimate to your local reality. The skill handles them automatically; you validate the output.

        Labor Cost Multiplier

          Labor is the biggest variable between markets. Ranges from **0.7x** (low-cost rural markets like Dayton, OH) to **1.5x** (high-cost metros like San Francisco, NYC). The skill adjusts based on the property's zip code. Dayton runs approximately 0.82x the national index, which is why the real contractor costs came in at the low end of Tier 3 range.

        Material Availability

          Proximity to distribution centers affects material pricing by 5-15%. Markets within 50 miles of a major Lowe's/HD distribution hub get near-retail pricing. Rural markets 100+ miles from a hub pay delivery surcharges that add up across a full scope. The skill sources from Amazon, Lowe's, and Home Depot by region to capture these differences.

        Permit Requirements

          Some municipalities require permits for any work above certain dollar thresholds, adding **$500-$3,000** to the project. Others require permits only for structural or mechanical work. The skill notes permit requirements as a separate line item (not in the contractor SOW) so you can budget for them without inflating the rehab estimate.

        Seasonal Adjustments

          Q4 and Q1 labor costs run **10-15% higher** in cold climates due to reduced contractor availability. Fewer contractors willing to work, more demand for indoor trades (plumbing, electrical, drywall). If you are estimating a winter rehab in a cold market, expect higher labor bids. Conversely, summer in warm markets has longer days and more competition, keeping labor costs lower.

## Feed it your deals. It learns your market.

    Feed the skill contractor invoices from closed deals. It recalibrates every pricing assumption. Three to five deals and estimates match your contractor within 5%.

#### Do

        Feed it 3-5 closed deals with the actual contractor SOW line items, purchase price, sold price, and hold time. Include every category: paint, flooring, kitchen, bath, electrical, plumbing, windows, demo, appliances.

#### Don't

        Feed it theoretical numbers, estimates from deals you did not close, or only the total rehab cost without the line-item breakdown. The skill needs granular per-category data to recalibrate individual pricing assumptions.

### Draft your calibration data

    Paste your contractor SOW details from a closed deal. The skill will use this to adjust its pricing for your market.

    Three to five closed deals is the sweet spot. Feed it every line item from the contractor SOW, purchase price, sold price, and hold time. The skill recalibrates to your market within one iteration.

        **Example inspection report:** [View the sample report](https://drive.google.com/file/d/1YqwMJd8NS6sUYsY2S_3rSLdJyxDR6HU_/view?usp=sharing) from [Investor Bootz](https://investorbootz.com/) to see the format the skill works best with.

## Tools and links for rehab estimating.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, September 21 to September 25

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

      [#### Rehab Estimator Skill

Download the Claude skill file](https://drive.google.com/file/d/1AhPX4u2XFE1eilxOm6TC4M3hJlvFUNQl/view?usp=sharing)
      [#### Example Inspection Report

Sample report from Investor Bootz](https://drive.google.com/file/d/1YqwMJd8NS6sUYsY2S_3rSLdJyxDR6HU_/view?usp=sharing)
      [#### Investor Bootz

Investor-focused property inspections](https://investorbootz.com/)
      [#### Full Comp Report (5532 Joyce Ann Dr)

Two-Bucket analysis in Google Sheets](https://docs.google.com/spreadsheets/d/1_YBUHRsAB2JG1zuNJ_eOsaNGqKt-7hid/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

#### AI-Powered Comping Workflow

Companion guide: property valuation

      [#### Claude Pro ($20/mo)

All you need to run the rehab skill](https://claude.ai)
      [#### Deal Flow Tech Stack SOP

Full tool and process spreadsheet](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)

          Reset

  ×
