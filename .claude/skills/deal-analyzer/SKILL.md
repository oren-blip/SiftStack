---
name: deal-analyzer
description: >
  This skill should be used when the user wants to "analyze a deal", "run the numbers on a property",
  "what's this property worth", "analyze this address", "comp and rehab", "full deal analysis",
  "what should I offer", "evaluate this investment property", "run a deal analysis",
  "look at this property", or provides property photos asking what the rehab and ARV would be.
  Also trigger when the user provides a property address with photos and wants to know
  if the deal makes sense, what to offer, or which exit strategy works best.
  This skill orchestrates the complete comping and rehab estimation workflow end-to-end.
version: 0.2.0
---

# Deal Analyzer — Full Property Analysis Pipeline

Orchestrate a complete investment property analysis from raw photos and an address through to ARV, rehab cost, deal math, and offer strategy. This skill ties together the **real-estate-comping** skill (for valuation) and the **rehab-estimator** skill (for renovation costs) into one streamlined pipeline.

The user should walk away with a clear picture: what's it worth, what does it cost to fix, what should I offer, and which exit strategy makes more money.

## Pipeline Overview

```
INTAKE → PHOTO ANALYSIS → COMP ANALYSIS → REHAB ESTIMATE → DEAL MATH → OFFER & EXIT STRATEGY → DELIVERABLES
```

Each phase feeds into the next. Data flows forward — comp findings inform rehab scope, rehab costs feed deal math, and deal math drives the offer.

## Phase 1: Intake

Collect from the user:

**Required:**
- Property address (full: street, city, state, zip)
- Property photos OR condition description (photos strongly preferred)

**Helpful (ask if not provided):**
- Square footage / bed / bath / year built (can be researched if address is given)
- Number of units (default: 1)
- Occupied? (Y/N) — affects hold time and eviction/vacancy considerations
- Purchase price or contract price (needed for deal math)
- Current "As Is" Value (if known — useful for wholesaling spread analysis)
- Known issues (roof, foundation, HVAC, etc.)
- Financing structure (supports multiple loans — see Phase 5 for details):
  - First Mortgage / primary lender terms (amount or LTV, rate, points)
  - Second Mortgage / Gap Fund / Private Money (if applicable)
  - Miscellaneous financing or liens (if applicable)
  - If not provided, defaults to 100% LTV hard money on purchase + rehab as a single first mortgage
- Exit strategy preference (or analyze both flip and wholetail)
- Evaluator name (for report attribution)
- Property description (e.g., "Off Market Lead", "MLS Listing", "Driving for Dollars")

**If the user only provides an address:**
Use web search and browser tools to look up the property on Zillow, Redfin, or county records to gather:
- GLA, bed/bath, year built, lot size
- Any available listing photos (for condition assessment)
- Tax records for annual property tax amount

**If the user provides photos:**
These are typically walkthrough photos the user took at the property. Analyze them directly — they are the primary source of truth for condition assessment. Do NOT search for other photos of the same property unless the user's photos are incomplete.

## Phase 2: Photo & Condition Analysis

Read and follow the photo analysis methodology from the **rehab-estimator** skill (Step 2).

Walk through every photo systematically. For each room/area visible:

| What to Assess | Rating Scale |
|---------------|-------------|
| Roof, siding, windows, foundation, concrete, landscaping, garage | Good / Fair / Poor / Missing |
| Kitchen (cabinets, counters, appliances, layout) | Good / Fair / Poor / Missing |
| Bathrooms (tile, fixtures, vanity, tub/shower) | Good / Fair / Poor / Missing |
| Flooring throughout | Good / Fair / Poor / Missing |
| Walls, ceilings, doors, trim | Good / Fair / Poor / Missing |
| Electrical, plumbing, HVAC, water heater | Good / Fair / Poor / Missing |

Build a condition summary that feeds both the comp analysis (to categorize the subject property's current condition) and the rehab estimate (to scope the work needed).

**Important:** Assess what you can actually see. Flag anything you can't assess from photos (e.g., "roof not visible — needs inspection"). Widen contingency for unknowns.

## Phase 3: Comp Analysis (ARV Determination)

Invoke the **real-estate-comping** skill methodology.

1. Determine if the property is in a disclosure or non-disclosure state
2. Read the appropriate comping framework reference:
   - Disclosure states → `real-estate-comping/references/disclosure-prompt.md`
   - Non-disclosure states → `real-estate-comping/references/non-disclosure-prompt.md`
3. Execute the full 9-step comp analysis
4. Generate the comp Excel workbook using the comping skill's script

**Key outputs to carry forward:**
- ARV (final number)
- Bucket A median PPSF (unrenovated)
- Bucket B median PPSF (renovated)
- Renovation premium percentage
- What finishes the renovated comps had (critical for rehab scoping)
- Median DOM from Bucket B comps (for hold time calculation)
- Market phase assessment

**Comp photo comparison:** When analyzing renovated comps (Bucket B), pull listing photos from Zillow/Redfin using browser tools to see what finish level the market is rewarding. This directly informs what the rehab scope should target — match the comps, don't exceed them.

## Phase 4: Rehab Estimate

Invoke the **rehab-estimator** skill methodology, feeding in the comp findings.

1. Read calibration data: `rehab-estimator/references/real-deal-calibration.md`
2. Read line item categories: `rehab-estimator/references/rehab-categories.md`
3. Read finish tiers: `rehab-estimator/references/finish-tiers.md`
4. Read wholetail scope differences: `rehab-estimator/references/wholetail-vs-rehab.md`
5. Read local pricing guide: `rehab-estimator/references/local-pricing-guide.md`

Build TWO parallel scopes:
- **Full Rehab** — match Bucket B comp finishes (Investor-Flip Grade)
- **Wholetail** — clean, functional, minimal spend (Builder to Mid Grade)

**Critical integration point:** The finish level MUST match what the renovated comps had. If Bucket B comps had LVP flooring and white shaker cabinets, that's what the full rehab scope targets. If comps had granite, budget granite. Over-improvement kills ROI.

Apply local pricing adjustments for the property's specific market.

Run the $/SF sanity check ($25-35 standard flip, $40-55 heavy, $60-80 gut-only).

Generate the rehab Excel workbook using the rehab-estimator script.

## Phase 5: Deal Math

Calculate the full deal cost picture. This is where comping meets rehab.

### For Full Rehab Exit:
```
Net Profit = ARV - Purchase Price - Rehab Cost - Financing - Holding - Buying Costs - Selling Costs
```

### For Wholetail Exit:
```
Wholetail Sale Price = Bucket A PPSF × GLA + 10-15% light premium
Net Profit = Wholetail Sale Price - Purchase Price - Wholetail Cost - Financing - Holding - Buying Costs - Selling Costs
```

### Hold Time (Dynamic):
```
Total Hold = Rehab Duration + Marketing Period + Closing Period
- Rehab Duration: from scope complexity (2-16 weeks depending on scope)
- Marketing Period: Bucket B median DOM from comp analysis
- Closing Period: 30 days
```

**Projected Sale Date:** Calculate from today's date + Total Hold Time. Present as "Assumes Sale is on or before [date]."

### Multi-Loan Financing Structure

The deal analyzer supports flexible financing with up to three loan positions. This allows modeling real-world scenarios like hard money + gap funding, conventional + private money, or any combination.

**First Mortgage (Primary Loan):**
The main acquisition loan. If the user doesn't specify terms, default to hard money:
- Loan amount = Purchase Price + Rehab Cost (100% LTV)
- Interest rate = 12% annual (interest-only)
- Points = 0%

**Second Mortgage / Gap Fund:**
Common for investors who use gap funding, private money, or a second lien to cover the difference between the first mortgage and total project cost. Typical use cases:
- First mortgage covers 80% of purchase, gap fund covers 20% of purchase + all rehab costs
- Hard money covers purchase, private money covers rehab
- Any other split the user specifies

If the user provides gap fund terms:
- Loan amount = user-specified OR auto-calculate as (Purchase × gap percentage) + Rehab costs
- Interest rate = user-specified (often 0-15% depending on source)
- Points = user-specified

**Miscellaneous Financing:**
Any additional financing (third lien, repair line of credit, etc.). Only include if user specifies.

**Financing Calculation (per loan):**
```
Monthly Interest = Loan Amount × (Annual Rate / 12)
Points Cost = Loan Amount × Points %
Total Financing Cost = (Monthly Interest × Hold Time) + Points Cost
```

**Total All Financing = Sum of all loan costs (First + Second + Misc)**

### Capital Analysis

These metrics show how much actual cash the investor needs and what return they're getting on their own money:

```
Down Payment Required at Closing = Purchase Price + Buying Costs - First Mortgage Amount
Committed Capital = Down Payment + (Rehab Cost - amounts covered by loans) + Holding Costs during rehab
```

**Cash on Cash Return:**
```
Cash on Cash Return = Net Profit / Committed Capital
Annualized Cash on Cash = Cash on Cash Return × (12 / Hold Time in months)
```

This is often more useful than total ROI because it measures return on the investor's actual out-of-pocket capital, not total project cost.

### Additional ROI Metrics

Present all of these in the deal summary:

| Metric | Formula | What It Tells You |
|--------|---------|------------------|
| Total Costs ROI | Net Profit / Total All-In Cost | Return relative to every dollar in the deal |
| Purchase + Rehab ROI | Net Profit / (Purchase + Rehab) | Simplified ROI excluding soft costs |
| Cash on Cash Return | Net Profit / Committed Capital | Return on YOUR actual money at risk |
| Annualized CoCR | CoCR × (12 / Hold Months) | Annualized return for comparing across deals |
| Profit per Month | Net Profit / Hold Time | Capital velocity metric |
| Cost Per Sq Ft | (Purchase + Rehab) / GLA | Quick sanity check on all-in basis |

### Validate the Spread:
```
Market Premium = (Bucket B PPSF - Bucket A PPSF) × GLA
Rehab budget should be 40-70% of Market Premium
> 70% = thin margin warning
< 40% = strong margin
```

## Phase 6: Offer & Exit Strategy

Present the decision framework:

### Maximum Allowable Offer (MAO)
```
MAO = ARV × 75% - Full Rehab Cost
```
(75% rule — more realistic than the old 70% rule)

### Exit Strategy Comparison Table
| Metric | Full Rehab (Flip) | Wholetail |
|--------|------------------|-----------|
| Sale Price (ARV) | $XXX,XXX | $XXX,XXX |
| Rehab Cost | $XX,XXX | $XX,XXX |
| All-In Cost | $XXX,XXX | $XXX,XXX |
| Net Profit | $XX,XXX | $XX,XXX |
| Total Costs ROI | XX% | XX% |
| Cash on Cash Return | XX% | XX% |
| Annualized CoCR | XX% | XX% |
| Timeline | X months | X months |
| Risk Level | Higher (more capital at risk) | Lower (less capital, faster) |
| Profit per Month | $X,XXX | $X,XXX |
| Committed Capital | $XX,XXX | $XX,XXX |

**Profit per Month** is often the most useful comparison — a wholetail that nets $15K in 6 weeks can beat a flip that nets $35K in 5 months when measured by capital velocity.

**Cash on Cash Return** matters when the investor is using leverage — it shows return on their actual skin in the game, not total project cost.

### Recommendation
Based on the numbers, recommend the stronger exit strategy with reasoning. Consider:
- Absolute profit vs profit per month
- Capital required (risk exposure) — compare Committed Capital
- Cash on Cash Return (especially when using leverage)
- Market conditions (hot market favors wholetail speed, slow market may need full rehab to compete)
- Investor's stated preference (if any)

## Phase 7: Deliverables

Generate all outputs using the existing skill scripts:

### From Comping:
1. **Comp Excel Workbook** — `real-estate-comping/scripts/generate_excel_report.py`

### From Rehab:
2. **Rehab Excel Workbook** — `rehab-estimator/scripts/generate_rehab_excel.py`

### Presentation Order:
1. Show the in-context summary (condition highlights → ARV → rehab costs → deal math → offer strategy)
2. Link the comp Excel workbook
3. Link the rehab Excel workbook

### In-Context Summary Format:

```
## Deal Analysis: [Address]
**Evaluator:** [Name] | **Date:** [Date] | **Units:** [#] | **Occupied:** [Y/N]

### Property Condition
[3-5 key findings from photo analysis]

### Valuation (ARV)
- ARV: $XXX,XXX (confidence: High/Moderate/Low)
- As-Is Value: $XXX,XXX (if available)
- Unrenovated PPSF: $XXX | Renovated PPSF: $XXX
- Market Premium: XX%
- Market Phase: [Seller's/Balanced/Buyer's]

### Rehab Estimates
| | Full Rehab | Wholetail |
|---|---|---|
| Estimate | $XX,XXX | $XX,XXX |
| $/SF | $XX | $XX |

### Financing Summary
| Loan | Amount | Rate | Points | Monthly Payment |
|------|--------|------|--------|-----------------|
| First Mortgage | $XXX,XXX | XX% | X% | $X,XXX |
| Second / Gap Fund | $XX,XXX | XX% | X% | $XXX |
| Total Financing Cost | — | — | — | $X,XXX |

### Full Deal Analysis
| | Full Rehab | Wholetail |
|---|---|---|
| Sale Price | $XXX,XXX | $XXX,XXX |
| Purchase | $XXX,XXX | $XXX,XXX |
| Rehab | $XX,XXX | $XX,XXX |
| Financing | $X,XXX | $X,XXX |
| Holding (X mo) | $X,XXX | $X,XXX |
| Buying Costs | $X,XXX | $X,XXX |
| Selling Costs | $XX,XXX | $XX,XXX |
| **Net Profit** | **$XX,XXX** | **$XX,XXX** |
| **Total Costs ROI** | **XX%** | **XX%** |
| **Cash on Cash** | **XX%** | **XX%** |
| **Annualized CoCR** | **XX%** | **XX%** |
| **Profit/Month** | **$X,XXX** | **$X,XXX** |

### Capital Requirements
| | Full Rehab | Wholetail |
|---|---|---|
| Down Payment at Closing | $XX,XXX | $XX,XXX |
| Committed Capital | $XX,XXX | $XX,XXX |
| Purchase + Rehab $/SF | $XXX | $XXX |

### Offer Strategy
- MAO (75% Rule): $XXX,XXX
- Assumes Sale on or before: [Date]
- Recommended Exit: [Flip/Wholetail] — [1-2 sentence reasoning]

### Caveats
[Unknowns, inspection items needed, market risks]
```

## Key Principles

1. **Photos are ground truth** — User-provided walkthrough photos are the primary evidence. Don't assume conditions the photos don't show.

2. **Comps drive finish level** — The rehab scope targets whatever the renovated comps had. Over-improving beyond comps is the #1 margin killer.

3. **All-in costs, always** — Never present profit as just ARV minus purchase minus rehab. Financing, holding, and transaction costs are real money.

4. **Both exits, every time** — Always present flip AND wholetail numbers unless the user explicitly only wants one. The best exit isn't always obvious.

5. **Profit per month > absolute profit** — Capital velocity matters. A faster, smaller profit can beat a bigger, slower one.

6. **Conservative by default** — Target low-to-mid pricing on rehab (35th percentile). Use 75% MAO rule. Don't inflate ARV with optimistic comp selection.

7. **Flag what you can't see** — Unknown roof, unseen crawlspace, no electrical panel photo = wider contingency and explicit callouts.

8. **Flexible financing** — Support real-world loan structures (multiple liens, gap funding, private money). Don't assume everyone uses a single hard money loan. Default to hard money only when no financing terms are provided.

9. **Show the investor's real exposure** — Committed Capital and Cash on Cash Return matter more than total project ROI when the investor is using leverage. Always present both.

10. **Universal applicability** — The deal analyzer works for any market, any financing structure, and any exit strategy. Don't hardcode assumptions that only apply to one geography or one lender type.

## Reference Files

The following reference files from the comping and rehab skills contain detailed methodology. Read them at the appropriate phase:

**Comping references** (Phase 3):
- `real-estate-comping/references/disclosure-prompt.md` — Full 9-step disclosure state framework
- `real-estate-comping/references/non-disclosure-prompt.md` — Triangulation method for TX, etc.
- `real-estate-comping/references/adjustment-cheatsheet.md` — Feature adjustment values

**Rehab references** (Phase 4):
- `rehab-estimator/references/real-deal-calibration.md` — Verified contractor pricing (read FIRST)
- `rehab-estimator/references/rehab-categories.md` — Complete line-item pricing
- `rehab-estimator/references/finish-tiers.md` — Material quality levels
- `rehab-estimator/references/wholetail-vs-rehab.md` — Scope differences between exits
- `rehab-estimator/references/local-pricing-guide.md` — Market-specific pricing adjustments
