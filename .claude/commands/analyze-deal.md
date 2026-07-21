---
description: Run full deal analysis on an investment property
argument-hint: [address or "use uploaded photos"]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch, Task
---

Run the complete deal-analyzer skill workflow for the property specified by $ARGUMENTS.

Load the deal-analyzer skill from ${CLAUDE_PLUGIN_ROOT}/skills/deal-analyzer/SKILL.md and follow its pipeline:

1. **Intake** — Gather property details from the argument, uploaded photos, and any context the user has provided. If only an address is given, research the property online (Zillow, Redfin, county records) to get GLA, bed/bath, year built, and any available photos.

2. **Photo Analysis** — If the user has uploaded property photos, analyze them room-by-room following the condition assessment checklist. If no photos are available, note this and widen contingency.

3. **Comp Analysis** — Execute the full comping workflow using the real-estate-comping skill methodology. Generate comp Excel workbook.

4. **Rehab Estimate** — Execute the full rehab estimation using the rehab-estimator skill methodology. Feed in comp findings (Bucket B finishes, renovation premium). Generate rehab Excel workbook.

5. **Deal Math** — Calculate all-in costs for both flip and wholetail exits including financing, holding, buying, and selling costs.

6. **Offer Strategy** — Calculate MAO (75% rule), compare exits by profit per month, and recommend the stronger strategy.

7. **Deliverables** — Present the in-context summary, then link all generated files.

If the user hasn't provided a purchase price, ask for it before running deal math. If they don't have one yet, still run comping + rehab and provide the MAO as their target offer.
