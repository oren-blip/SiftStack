# Guide: siftmap-mastery

> Source: https://learn.datasift.ai/siftmap-mastery (Day 1, August 2026 cohort — fetched 2026-08-18)
> Part of the Challenge Hub Day 1 module list. Hub pages are sunset each cohort.

---

On this page

      On this page
      ×

# SiftMap Mastery

      Turn market research into targeted property lists

         14 min read
         Market Analysis
         $0 - $297/mo

## Most Investors Pull Lists Backwards

    They grab 50,000 records from a county, blast cold calls, and wonder why nobody picks up. The list was never the problem. The targeting was.

      SiftMap is the data engine inside DataSift, and where your data strategy starts. Pull property records filtered on dozens of criteria: property type, value, equity, ownership duration, distressors, the AI/Investor Score, geography down to the neighborhood.

      **This is the lead precision engine.** The most efficient records you can pull and market the same day, no build-out: precise list this morning, dialing this afternoon. First-to-market county sourcing is fresher and cheaper per contract but takes a 25-35 day build. Add it later.

      A tool is only as good as the strategy behind it. This guide walks you through the filter layering process that turns a raw county of records into a surgical list matched to your exact marketing budget and deal capacity.

    **Prerequisite:** This page picks up where Market Finder Workflow left off. Market Finder identifies your best counties, zip codes, and neighborhoods. SiftMap is where you pull the actual records based on those findings.

### The Filter Layering Funnel

    Each layer shrinks the list and increases targeting precision. Fewer records, higher conversion, smarter marketing spend.

      Four screens, one sluice. Each layer drops the records that will not convert; about 270 of 48,000 reach the tray.

    Real example: Ramsey County, MN (from Market Analysis training)

      **Why you start here:** the AI/Investor Score is the single most efficient lever. On live SiftMap supply (Knox and Blount TN, real sold data): Investor Score 80 runs about 30.6 doors per deal, 90+ about 22.8, versus roughly 218 for a broad all-single-family baseline.

      The 90+ band also carries the fattest margins (56% to 58%) and roughly $5.70M to $7.22M in gross deal value per 1,000 doors worked. Precision, same day, no build-out.

## Getting Oriented in SiftMap

    SiftMap lives inside your DataSift account. Here is how to navigate the interface and understand what you are looking at.

        1

#### Open SiftMap

          From your DataSift dashboard, click **SiftMap** in the left navigation. You will see a map view with a filter panel on the left side.

            The SiftMap filter panel with basic and advanced filter options.

        2

#### Understand the Filter Categories

          **Basic filters:** Estimated value, beds/baths, prospect list presets (equity tiers, foreclosure statuses). **Advanced filters:** Square footage, year built, lot size, vacancy, absentee status, cash buyer history, MLS status, days on market. **Pro filters:** Geographic targeting, distressor indicators, owner details (requires SiftMap Pro).

              Basic filters: MLS status, listing price, and foreclosure indicators. Available on all plans.

              Advanced filters: property characteristics like square footage, year built, and vacancy.

        3

#### Check Your Property Details

          Click any property pin to see four tabs of data: **Property** (structure, land, tax info), **Owner** (name, address, mortgage, equity, other properties), **Comps** (comparable sold properties), and **History** (transactions, mortgages, MLS, foreclosures).

              Property tab: structure, land, and tax data.

              Owner tab: name, mortgage, equity, other properties.

### Plan Record Limits

    Every plan includes free monthly records. Max 10,000 per single upload. Additional records cost $5 per 10,000.

         |
           | Plan | Monthly Free Records | Skip Trace | SiftMap Pro

           | Professional ($149/mo) | 10,000 | $0.15/record | +$297/mo add-on

           | Business ($299/mo) | 25,000 | $0.15/record | +$297/mo add-on

           | Expert ($499/mo) | 50,000 | Unlimited | Included

           | AI ($1,250/mo) | 100,000 | Unlimited | Included

#### Who Can Add Records?

    Only **Sensei/Owner**, **Super Admin**, **Admin**, and **Marketer** roles can add records from SiftMap. All other roles (Cleaner, Acquisitions, Dispositions, Lead Manager, Researcher, Prospector) are view-only.

## Filter Layer 1: Base Characteristics

    Five filters form the foundation of every list pull, reducing a county from hundreds of thousands of properties to a workable starting set.

    **Validation step:** Use your Sold Properties analysis to verify these base criteria ranges match what is actually trading in your market. The filters below are starting points. Your sold data tells you whether to tighten or expand them.

          🏠

          Asset Type

          💰

          Value Range

          📅

          Year Built

          🕒

          Years Owned

          📈

          Equity

#### Asset Type: Single Family Residential

        Start with single-family residential. This is your bread and butter for wholesaling, flipping, and rental acquisitions. SiftMap also supports mobile homes, townhouses, multi-family, commercial, land, condos, RV parks, and warehouses.

        **When to expand:** If your market has strong manufactured housing or duplex activity (check Sold Properties), add those property types to your base criteria. But start narrow. One asset type, one strategy.

#### Estimated Value: The 60% Price Range

        This is the single most important filter for cost efficiency. Your Market Finder analysis identified the median home value for your county. The 60% price range captures properties from roughly 40% below to 20% above that median.

        **Example:** If median home value is $375K, your 60% range might be $200K to $600K. This eliminates ultra-cheap properties with thin margins and luxury homes that sit for months.

        **Source:** Pull this number directly from your Market Finder analysis. Do not guess.

#### Year Built: Market-Dependent Starting Point

        In most markets, 2000 or earlier is a solid starting point. Newer builds have less deferred maintenance and fewer ownership transitions, which means fewer motivated sellers. But this is not a universal rule.

        **Validate with Sold Properties:** check what year-built ranges actually transact in your market. Heavy post-2000 construction (Phoenix, Austin, parts of Florida): shift to 2005 or earlier. Older markets (Midwest, Northeast): 1990 or earlier. Sold data guides you, not a universal cutoff.

#### Years Owned: 5+ Years Minimum

        Owners who bought in the last 1-4 years are still in "new home" mode. They paid near-peak prices, have low equity, and have zero motivation to sell at a discount. Five-plus years of ownership means real equity accumulation and lifestyle changes that create motivation.

        **Turnover rate signal:** If adding this filter drops your record count by 50%, half the properties in that area changed hands in the last 5 years. That is a market velocity indicator worth noting.

#### Equity: 30% or Higher

        Low-equity owners cannot sell at a discount because there is no spread. You need owners with enough equity to absorb your wholesale fee or accept a below-market offer and still walk away with cash in their pocket.

        **Regional exception:** In Texas and California, where property values are high and appreciation cycles are different, 20% equity can still work. Everywhere else, 30% is the floor.

        **Available presets:** SiftMap includes preset equity tiers: Low Equity (0-20%), High Equity (30-99%), and Free and Clear (100%).

### Standard Filter Panels in SiftMap

    These are the standard filter panels available on all SiftMap plans. The base criteria above map directly to these UI controls.

        MLS Filters (Status, Listing Price, Sold Date) and Foreclosure Filters (Auction Date, Notice Date, Status, Notice Type). Available on all plans.

        Financial Details: Equity %, Estimated Value, Last Sales Price, Suggested Rent, Assessed Value. Set your 60% price range and 30%+ equity floor here.

        Property Details: Heated SqFt, Lot Size, Year Built, # of Units, Vacant status, Flood Zone. Check your Sold Properties data to set the right Year Built range for your market.

    If your 5-year ownership filter drops records by 50%, that is a turnover rate signal. Half the properties changed hands in 5 years. That tells you the market is active and competitive. Factor that into your channel strategy.

## Filter Layer 2: Geographic Targeting

    Geography is where Market Finder analysis becomes SiftMap execution. Three levels of precision, each requiring different plan tiers.

        County (All Plans)
        Zip Code (All Plans)
        Neighborhood PRO

#### County-Level: The Starting Point

        Every SiftMap user starts at the county level. Select your target county, apply base characteristics, and you get a broad count. In a mid-size metro county, expect 30,000 to 60,000 records after base criteria filtering.

        **Marketing strategy at this size:** bulk sequential. Power dialers like ReadyMode handle the volume, cold call first, always (never lead with SMS): text and voicemail follow up. You cannot afford to mail or door knock 48,000 properties.

        **Use case:** Operators who want maximum reach and rely on volume-based calling campaigns.

#### Zip Code: Where Precision Starts

        Your Market Finder Zip Code Analysis ranked zip codes by four metrics: median sales price, days on market, median home value, and investor transaction volume. Those rankings become your SiftMap geographic filters.

          Your Market Finder Zip Code Analysis tab. These rankings feed directly into SiftMap geographic filters.

        **The workflow:** Take your top 3-5 zip codes from Market Finder. Enter them as geographic filters in SiftMap. Your 48,000-record county list drops to 20,000-25,000.

        **Marketing strategy at this size:** Bulk sequential marketing with direct mail. The list is small enough for mail to be cost-effective alongside your calling campaigns, and the zip codes were selected for investor activity and market velocity.

        **Warning:** Dark zip codes on the heat map can be misleading. A zip code with high investor transaction volume might also have 75+ days on market. Always cross-reference with days on market and median price before selecting.

#### Neighborhood: Surgical Precision SiftMap Pro Required

        This is where real precision happens. Bad zip codes can contain great neighborhoods. Market Finder's Neighborhood Analysis revealed which micro-areas within your top zips actually perform. SiftMap Pro lets you filter down to those specific neighborhoods.

          Your Market Finder Neighborhood Analysis tab. These neighborhood rankings become your SiftMap Pro neighborhood filters.

        **Example:** In Ramsey County, MN, zip code 55108 looked poor overall. But the neighborhood Como Park North within that zip code had excellent metrics: low days on market, active investor transactions, and properties within the 60% price range.

        **Marketing strategy at this size:** Niche sequential marketing. At 200-500 records, you can afford the full 3-day cadence: call, text, direct mail, door knock. Every property gets multiple touches across every channel.

          📍

            **SiftMap Pro: $297/mo add-on**
            Included free with Expert ($499/mo) and AI ($1,250/mo) plans. Required for neighborhood-level geographic filtering, distressor indicators, and expanded owner details.

#### Do

        Use Market Finder rankings to select zip codes and neighborhoods. Cross-reference investor transaction volume with days on market. Re-evaluate quarterly.

#### Don't

        Pick the darkest heat map zip without checking other metrics. Ignore neighborhood data within a weak zip code. Assume last quarter's top area is still the best.

## Prospect List Presets

    When you add records from SiftMap, the system auto-generates and assigns relevant lists. Prioritize and segment your data without manual tagging.

        Free Lists (All Plans)
        Pro Distressor Lists PRO

        Eight prospect lists automatically assigned to every record based on property and owner data. Available on all plans.

          The 8 free prospect lists auto-assigned to records.

          Free and Clear (100% Equity)
          Owners who own the property outright with no mortgage. Maximum flexibility for deal structuring. Often older homeowners who have paid off their mortgage over decades.

          High Equity (30-99%)
          Owners with significant equity built up. Enough spread to absorb a wholesale fee or below-market offer while still leaving cash for the seller.

          Low Equity (0-20%)
          Owners with minimal equity. These are typically newer purchases or properties in flat/declining markets. Limited wholesale potential but useful for identifying novation or subject-to candidates.

          Negative Equity
          Owners who owe more than the property is worth. Traditional wholesale does not work here, but short sale, subject-to, or novation strategies may apply.

          Owner Occupied
          The owner lives at the property. Different marketing approach than absentee owners. These sellers often have emotional attachment and need a longer nurture cycle.

          Absentee
          Owner does not live at the property. Often landlords, inherited property holders, or out-of-state owners. Higher motivation to sell due to management burden or distance.

          Pre-Foreclosure
          Properties in the early stages of foreclosure proceedings. Owners facing default but still have time to sell. High urgency, high motivation. Time-sensitive outreach required.

          Foreclosure
          Properties in active foreclosure. Auction dates set. Even more urgent than pre-foreclosure: bottom-of-funnel, fast-cycle deals where the auction clock forces a decision. But a foreclosure is NOT first-to-market. The lis pendens fired earlier and the owner has already absorbed heavy marketing, so it is the most saturated list. It needs a higher-caliber caller and premium touches to stand out.

        24 specialized distressor lists auto-assigned when records are added via SiftMap Pro. These identify specific motivation triggers at the owner and property level.

          The 24 Pro distressor lists for granular segmentation.

#### Pre-Foreclosure Variants

        Notice of Default, Lis Pendens, Court Order, Final Judgment. Each represents a different stage and urgency level in the foreclosure process.

#### Liens & Financial

        Tax Lien, Federal Lien, HOA Lien, Judgment Lien, Tax Delinquent, Low Income, Short Term Loan. Financial pressure creates motivation to sell.

#### Life Events & Distress

        Probate, Estate, Bankruptcy, Eviction, Vacancy, Divorce, Credit Distress. These are life disruptions that often trigger a property sale.

#### Demographics

        Senior Homeowners. The second highest reason people sell their homes. Downsizing, health changes, estate planning.

#### List Stacking

        A single property can appear on multiple lists simultaneously. An absentee owner who is also tax delinquent and senior appears on three lists. The more lists a property stacks, the higher the motivation signal.

## Filter Layer 3: SiftMap Pro Distressors

    Distressors are the motivation indicators that separate a cold list from a warm one. SiftMap Pro filters by them before you pull.

        👤

        Homeowner Distressors

        5 indicators

        🏘

        Property Distressors

        5 indicators

        💵

        Financial Distressors

        7 indicators

        ⚖

        Legal & Life Events

        5 indicators

#### Homeowner Distressors

      Indicators tied to the owner's personal situation and property relationship.

- **Senior Owners (55+/65+)** Second highest reason people sell. Downsizing, health changes, estate planning.

- **Absentee (Out of State)** Owner lives in a different state. Management burden increases with distance. Gold when combined with senior and multi-property.

- **Multi-Property Owners (3-6)** Landlords with portfolio fatigue. Small portfolios are the sweet spot: big enough to be a burden, small enough that they handle it themselves.

- **Investor Type** Filter by owner classification: investor, landlord, or primary resident. Useful for targeting tired landlords specifically.

- **15+ Years Ownership** Long-term owners who may be "tired landlords" in spirit. Small niche, high conversion. These owners have maximum equity and maximum lifestyle change since purchase.

#### Property Distressors

      Indicators tied to the property condition or legal status.

- **Pre-Foreclosure (4 variants)** Notice of Default, Lis Pendens, Court Order, Final Judgment. Each stage represents increasing urgency.

- **Vacant** No one living at the property. Often indicates abandonment, recent move-out, or estate situation. No utility connections.

- **Eviction** Active eviction proceedings. The owner is dealing with a problem tenant and may be motivated to sell the headache entirely.

- **Code Violations** Municipal code enforcement actions. The owner faces fines and repair mandates. Selling becomes easier than fixing.

- **MLS Status** Filter by active, pending, expired, or withdrawn listings. Expired and withdrawn are strong motivation signals.

#### Financial Distressors

      Indicators tied to the owner's financial situation and property economics.

- **Tax Delinquent** Owner has not paid property taxes. In Florida, 7.5% of private sellers are tax delinquent. High value exchange: solve their tax problem, get a deal.

- **Tax Lien** Government lien filed against the property for unpaid taxes.

- **Federal Lien** IRS or federal agency lien. Adds legal complexity but also motivation.

- **HOA Lien** Homeowner association lien for unpaid dues. Common in subdivisions and condos.

- **Judgment Lien** Court-ordered lien from a lawsuit. Creates title issues that motivate sale.

- **Low Income** Owner income below area median. May lack resources for maintenance and repairs.

- **Short Term Loan** Adjustable rate or balloon mortgage approaching reset. Payment shock creates urgency.

#### Legal & Life Events

      Major life disruptions that often trigger a property sale decision.

- **Obituary (native, SiftMap Pro)** A notice-of-death flag on the property owner, the most first-to-market source there is: nearly uncontested. Weekly auto-add, nationwide. Sensitive list: never mention the death, never cold text (see the callout below).

- **Probate** Property in probate court after owner death. Heirs often want cash, not a property to manage. A long, top-of-funnel legal process you nurture.

- **Estate** Property held in an estate but not yet in probate. Similar motivation to probate but earlier in the process.

- **Bankruptcy** Owner has filed for bankruptcy protection. Property may need to be liquidated as part of proceedings.

- **Divorce** Active divorce proceedings. Neither party wants the property or both need the equity divided. Time-sensitive and emotional.

- **Credit Distress** Owner's credit score indicates financial hardship. Broad indicator that encompasses multiple underlying issues.

      **Native Obituary: the most first-to-market list you can pull.** A notice-of-death flag on the property owner, the least-saturated, nearly-uncontested source there is: you reach the property before it ever becomes a marketed list.

      A "last obituary date" field lets you work the timing. Records auto-add weekly, nationwide coverage. If the family files probate, the obituary flag is removed and replaced by a probate flag.

      **Access:** included in the $499/mo Expert plan (SiftMap Pro plus unlimited skip trace), or via the SiftMap Pro add-on (about $297/mo) on the $149/mo Professional plan. No AI plan required.

      Real anchor: about a 12% contact rate and 7% lead rate off SiftMap obituary plus a skip trace alone, before deep-prospecting the heirs. Efficiency: the deceased niche sits in the Elite band, about 14.8 doors per deal on real sold data (Pre-Probate/Deceased).

      **Handle it with care.** Never mention the death. Open soft: "do you have any plans for the property?" Direct mail goes to the family of the deceased, and you deep-prospect the heir. Never cold text an obituary or deceased record, ever.

### Pro Filter Panels in SiftMap

    These Pro-exclusive filter panels unlock distressor targeting, advanced geography, owner demographics, and data quality controls.

        Pro filter panel: Homeowner and Property Distressors with "Stacked" option (two or more distressors), Advanced Geography (ZIP, City, Neighborhood, Municipality with Include/Exclude), and Data Details quality filters.

        Owner Details (Pro): Filter by Owner Age, Mailing Address is Post Office (absentee indicator), Owner is Investor, and Owners with Multiple Properties.

### How Distressors Appear on Records

    When you pull records with distressor filters, each property shows which prospect lists it matches. This is how you verify your targeting is working.

        7400 Battle Creek Ln at a glance: AI scores (100/86/84), 89% equity, Off Market status, and distressor tags visible without clicking into the record.

        The same property expanded. The Lists tab shows matched Prospect Lists (High Equity, Owner Occupied) and Distressors PRO (Pre-Foreclosures, Bankruptcy Properties). This is how you verify your filter targeting is working.

      🔒

        **SiftMap Pro: $297/mo add-on**
        Included with Expert ($499/mo) and AI ($1,250/mo) plans. Unlocks all distressor filters, geographic neighborhood targeting, expanded owner details, and buyer data.

## Filter Layer 4: AI Scoring

    The precision lever, and the one you lead with. The AI/Investor Score predicts a transaction before it happens: the single most efficient lever in SiftMap.

    Applied last in the funnel, a 50-100 score filter cuts list size by roughly 50% while keeping the highest-probability leads.

    **The efficiency case:** Score 80 runs about 30.6 doors per deal, 90+ about 22.8, versus roughly 218 broad baseline (live Knox and Blount TN sold data). The 90+ band sources the fattest margins, 56% to 58%, and the most gross value per 1,000 doors.

    **Run it parallel, do not stack it.** Backtested: AND-stacking a distress list onto a high score makes efficiency worse (Distress AND Score 80 = about 48.4 doors per deal versus 30.6 for Score 80 alone). Pull score and acute distressors as parallel lists.

        🎯

        Investor AI Score (Off-Market)

        Included in AI plan ($1,250/mo)

        🏠

        Realtor AI Score

        $297/mo add-on

        📊

        Investor AI Score (On-Market)

        $297/mo add-on

#### Investor AI Score (Off-Market)

      Predicts the likelihood a property will sell to an investor in an off-market transaction. This is the primary score for wholesalers, flippers, and buy-and-hold investors doing outbound marketing.

      **How to use:** Add the AI score filter in SiftMap and set the range to 50-100. Properties scoring above 50 have characteristics that historically correlate with investor purchases: equity levels, ownership duration, owner demographics, and distressor presence.

      **Pricing:** Included in the AI plan ($1,250/mo). Also available as a $297/mo add-on for Expert plan subscribers. Off-Market AI Score is county-specific.

#### Realtor AI Score

      Predicts the likelihood a property will list on the MLS with an agent before it actually lists. Useful for agents and novation investors who want to reach homeowners before they sign with someone else.

      **How to use:** Filter for scores 50-100 to find properties likely to list soon. For novation strategies, combine with the Investor AI Score (On-Market) to identify properties likely to both list and attract investor buyers.

      **Pricing:** $297/mo add-on. Available for all plan tiers. Nationwide coverage.

#### Investor AI Score (On-Market)

      Scores every MLS-listed property nationwide for the likelihood of an investor purchase. This is the key score for novation investors and anyone targeting listed properties.

      **How to use:** Add this score as a filter on active MLS listings. Properties with high on-market investor scores are likely to sell to an investor, making them strong novation candidates.

      **Novation targeting example:** AI score 50+ (off-market) combined with Realtor AI score 50+ and 15-30% equity = properties likely to list AND likely to sell to investors. One training example showed 880 records dropping to 346 after adding the Realtor score filter.

      **Pricing:** $297/mo add-on. Available for all plan tiers. Nationwide coverage.

### AI Score Filters in SiftMap

    The AI Scores panel shows all three score types with range inputs. Set your minimum to 50 to filter for high-probability properties.

      The AI Scores filter panel. Set ranges for Investor AI Score (Off-Market), Investor AI Score (On-Market), and Realtor AI Score. Note: Off-Market AI Score only works for counties you are subscribed to.

### Impact on List Size

      Adding an AI score filter of 50-100 dramatically reduces list size while concentrating on the highest-probability properties.

        Without AI Filter
        With AI Score 50-100

            ~25,000

            Zip Code Filtered

            ~542

            Neighborhood + Distressors

            ~12,000

            Zip Code + AI (~50% reduction)

            ~270

            Neighborhood + Distressors + AI

## Building & Saving Presets

    This is where Market Finder analysis becomes a repeatable system. Tiered presets mean you never start a data pull from scratch.

    SiftMap saves filter configurations as named presets. Instead of rebuilding 8 filters every pull, you select a preset from a dropdown. Build three tiers of presets, each tied to a different list size and marketing budget.

        T1

        Hyper-Targeted

        200-500

        Niche sequential marketing

        T2

        Focused

        20K-25K

        Bulk sequential + mail

        T3

        Volume

        48K+

        Cold call only

#### Tier 1: Hyper-Targeted (200-500 Records)

      **Filters:** Base criteria + top 3-5 neighborhoods (from Market Finder) + 2-3 stacked distressors + AI score 50-100 (if available).

      **Marketing:** Niche sequential marketing. Every property gets the full 3-day cadence: call, text, direct mail, door knock. At this list size, you can afford to touch every property across every channel.

      **Example preset name:** "Ramsey T1 - Como Park Senior Absentee"

      **Review cadence:** Weekly. At 200 records, you should know the status of every property.

#### Tier 2: Focused (20,000-25,000 Records)

      **Filters:** Base criteria + top 3-5 zip codes (from Market Finder). No distressor stacking at this level, just geographic focus.

      **Marketing:** Bulk sequential marketing with direct mail layered in. The list is too large for door knocking but small enough for mail to generate ROI.

      **Example preset name:** "Ramsey T2 - Top Zips Base Criteria"

      **Review cadence:** Monthly. Check which zip codes are producing responses and deals. Promote top performers to Tier 1.

#### Tier 3: Volume (48,000+ Records)

      **Filters:** Base criteria only, county-wide. No geographic or distressor filtering. This is your broad-reach campaign.

      **Marketing:** bulk sequential via power dialer (ReadyMode). At this volume you fish with a net, not a spear. Cold call first, always (never lead with SMS): calls ($0.03-$0.06), then text ($0.01) and voicemail follow-ups, then direct mail for the reachable tail.

      **Example preset name:** "Ramsey T3 - County Cold Call"

      **Review cadence:** Quarterly. Assess which counties are worth keeping in the rotation.

### Default Presets vs. Custom Presets

    Every SiftMap account comes with 20 default presets (Judgment, Quick Resale, Adjustable Loans, Negative Equity, Cash Buyer, Bank Owned REO, and more). These are a starting point. The real power is building your own custom presets based on your Market Finder research and target strategy.

        Default Presets: 20 system-generated presets available on every account. Good starting point, but custom presets built from your Market Finder data are where the real targeting happens.

        Saved Presets: my 4 custom presets. Each pairs a data strategy (AI score or stacked distressors) with a geographic tier from Market Finder.

### My Preset Strategy: Two Parallel Approaches

    These presets run two data strategies in parallel. AI score presets target the algorithmic signal. The equity + stacked preset targets the motivation signal. Different data, different angles, same market.

#### AI Score Presets (3 Geographic Tiers)

        Each preset pairs **Single Family + AI Score 50+** with a different geographic tier from Market Finder.

- Tier 1 Zips: Best-performing zip codes from Market Finder. Smallest list, highest probability. Niche sequential marketing.

- Tier 2 Zips: Good zip codes with solid metrics but not top performers. Mid-size list. Bulk sequential + mail.

- Tier 3 Zips: County-wide with AI filter applied. Largest list, broadest reach. Bulk sequential via power dialer.

#### Stacked Distressor Preset

        **Single Family + 50% Equity + Stacked** uses SiftMap Pro's stacked distressor list instead of AI scoring.

        This preset targets owners with at least 50% equity who match two or more distressor indicators (senior + absentee, tax delinquent + vacant, pre-foreclosure + multi-property). No AI subscription required. Just SiftMap Pro ($297/mo or included with Expert/AI plans).

### Presets in Action

    When you activate a saved preset, SiftMap loads the full filter configuration and shows matching properties on the map. Here is what that looks like with a favorited preset selected and results loading.

        Favorited presets in the dropdown. One click loads the full filter configuration. The AI Score + Tier presets and the 50% Equity + Stacked preset are visible in the selector.

        The 50% Equity + Stacked distressor preset active in SiftMap. 8,795 properties matched. Each pin on the map represents a property matching the equity and multi-distressor criteria.

      An AI Score 50+ preset active in SiftMap. 16,498 properties matched. The AI layer dramatically narrows results compared to base criteria alone while surfacing highest-probability leads.

    I run two parallel approaches: AI score presets per zip tier for the algorithmic edge, the 50% equity + stacked distressor preset for the motivation edge. Re-run Market Finder every 90 days and update your presets.

      **Niche vs. bulk sequential:** most SiftMap lists are big enough for bulk sequential (power dialers, cold-call-led). Niche sequential (the full 3-day cadence) fits lists under 1,000 records from a high-priority neighborhood or zip with stacked distressors. Execution: Niche Sequential Marketing and Bulk Sequential Marketing.

      5-DAY DEAL FLOW CHALLENGE

### Next live cohort: Monday, August 17 to August 21

      5 days live with Ty. 34 interactive modules. A community of 1,047+ investors. Save your seat in the next cohort. Already enrolled? Use this guide as your between-session refresher.

        Save Your Seat →

## Adding Records to Your CRM

    You have filtered. You have targeted. Now you add the records to your DataSift CRM for marketing and outreach.

        1

#### Select Your Records

          After applying your filters, SiftMap shows the record count for your current selection. Review the count against your plan's monthly limit before proceeding.

            SiftMap with filters applied showing 299 matching properties. Review your record count against your plan's monthly limit before adding to your account.

        2

#### Click "Add to Account"

          The blue "Add to Account" button pulls your selected records into your CRM. Max 10,000 per single upload. If your list is larger, you will need multiple pulls.

            The Add to Account interface with record count and plan limits.

        3

#### Tag and Assign Lists

          During the add process, assign a **tag** (e.g., "SiftMap_Mar2026_T1_ComoPark") and optionally assign to a **list**. Tags help you track which pull produced which records. System-generated prospect lists are assigned automatically.

            Tag and list assignment during the record add process.

        4

#### Verify in Activity Log

          After adding, check the **Activity** tab to confirm your upload processed correctly. You will see the record count, upload date, and any duplicates that were skipped.

            Activity log confirming successful record upload.

    Records flagged "incomplete" can be manually researched by a VA. 200 records a week. That is gold everyone else ignores. Incomplete records often mean missing phone numbers or addresses, but the property and owner data is still there.

## Marketing Allocation by List Size

    Your list size dictates your channel strategy. Bigger lists need cheaper channels. Smaller lists earn the expensive ones.

        48K records

          $0.03-$0.06

        Cold call only

        20-25K records

          $0.50-$2.00

        Bulk sequential + mail

        500 records

          Multi-channel

        Niche sequential (call, text, mail, knock)

        200 or fewer

          $1.50-$4.00+

        Personal attention + deep prospecting

    **The real math:** "I would rather be the person at 4,000 records across seven different counties doing targeted outreach than the person at 48,000 records in one county just blasting calls." Scale right, but do fewer people that are more targeted in more counties.

## The Most Powerful Lists You Can Pull

    17 proven list configurations: 9 singles, 2 age filters, 6 stacked combos. Every one pulls inside SiftMap and markets the same day.

    Enrich any pull with SiftMap data like owner age, equity, and ownership duration.

### Single Lists

    Each targets a single distressor or life event. You can pull every one inside SiftMap today. Several (probate, pre-foreclosure, tax delinquent, code violations, evictions) can ALSO be sourced first-to-market from your county clerk once you stand up that pipeline for durable, uncontested consistency.

        Probate

        Heirs want cash. Highest average deal size in the vault. Property is emotional weight, not an asset.

        FTM

        Vacant

        "The #1 most important motivation factor of all." Stacks with everything. If nobody lives there, somebody wants out.

        Sift

        Pre-Foreclosure (NOD)

        Highest urgency variant. 30-90 day window before auction. Clock is ticking, and they know it.

        FTM

        Tax Delinquent

        Compounding pressure. 7.5% of FL private sellers are tax delinquent. Financial strain that only gets worse.

        FTM

        Divorce

        Court-mandated timeline. Forced seller by law. Both parties want this done yesterday.

        Sift

        Bankruptcy

        Court-ordered liquidation. No negotiation leverage for the seller. The court decides, not the owner.

        Sift

        Eviction

        Landlord at breaking point with a problem tenant. Tired of the fight, ready to sell the headache.

        FTM

        Code Violations

        Municipality pressure plus repair costs. The city is on their back, and fixing it costs more than selling.

        FTM

        Obituary

        Native to SiftMap and the most first-to-market source there is. A notice-of-death flag, least-saturated and nearly uncontested. Deceased owner, so you deep-prospect the heir. No cold text, ever.

        Sift

### Age Filters

    Demographics that signal life-stage motivation. Stack these with any single list above.

        Owner Age 65+

        2nd highest reason people sell. Unlocks senior downsizer, estate planning, and retirement stacks.

        Sift

        Owner Age 25-35

        Overleveraged young owners. Pairs with Low Equity and Pre-Foreclosure for maximum financial pressure.

        Sift

### Power Stacks

    Combine two or three filters for exponentially higher conversion. Each stack multiplies motivation signals.

        Probate + Vacant

        Vault-proven, highest conversion stack. Heir doesn't live there, wants cash fast. No emotional attachment to the property.

        FTM Sift 2 filters

        Pre-Foreclosure + Vacant

        "Zombie Properties." Double distressor, maximum urgency. Nobody home, bank closing in. These move fast.

        FTM Sift 2 filters

        Age 65+ + High Equity + Free & Clear

        Premium downsizing leads. $50K-$150K+ deals. No mortgage payoff eating your margin. Senior with full equity ready to simplify.

        Sift 3 filters

        Absentee + Vacant

        Classic industry workhorse. Simple two-filter pull, consistent results. Both filters are free on every plan.

        Sift 2 filters

        Tax Delinquent + Pre-Foreclosure

        Financial pressure from two directions at once. Avi's exact combo for $100K+ deals.

        FTM 2 filters

        Senior (55+) + Absentee + Multi-Property

        "Gold leads." 14 contracts in 2021, roughly 3 houses each, $1.3M revenue. Age plus inconvenience plus portfolio fatigue.

        Sift 3 filters

    **Two filters is good. Three is gold.** Every additional filter narrows the list but multiplies the motivation per record. A 200-record hyper-niche list will outperform a 20,000-record spray-and-pray list every time.

## Resources & Next Steps

    Continue building your data strategy with these tools and guides.

            5-Day Deal Flow Challenge

#### Next live cohort: Monday, August 17 to August 21

          5 days live with Ty. 34 interactive modules. Save your seat in the next cohort. Already enrolled? Use this page as your between-session refresher.

        Save Your Seat

#### Market Finder Workflow

The upstream analysis that feeds your SiftMap presets

#### Data Priority Pyramid

Understand FTM, Niche, and AI data tiers

#### Niche Sequential Marketing

Set up CRM filters for your SiftMap lists

#### Deep Prospecting

Research owners on your targeted lists

      [#### SiftMap Pro Help Article

Official feature documentation and setup guide](https://intercom.help/reisift/en/articles/12922078-siftmap-pro)
      [#### Deal Flow Tech Stack SOP

Full tool recommendations by phase](https://docs.google.com/spreadsheets/d/1pWC1cSKn0YIGvILRMQG4WlaGe-GZU1dU5ivPIzmafxc/edit?usp=sharing)
      [#### Critical Resource Hub

All 83 tools and resources across 5 days](https://docs.google.com/spreadsheets/d/1bQBHLsxVwXbsbz9SBcfpatPaFgAIsICo/edit?usp=sharing&ouid=114370733537958861976&rtpof=true&sd=true)

 Reset

  ×
