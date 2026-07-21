# Bulk Sequential Preset Map (Base Template)

This document provides the standard, recommended preset structure for a **Bulk Sequential** marketing workflow. Use this as the starting point for building a user's customized plan.

**Folder Name**: `01. Bulk Sequential`

| # | Preset Name | Purpose |
|---|---|---|
| 00 | Bulk Needs Skipped | Finds all new, unprocessed records from bulk lists that have no phone numbers and need to be skip traced. |
| 01 | Bulk Skipped NN | Isolates records that were skip traced but yielded no phone numbers, identifying them for a second skip trace attempt. |
| 02 | Bulk Ready to Call | The primary starting point for the bulk marketing cadence; contains all records with phone numbers ready for the multi-line dialer. |
| 03 | Bulk Call Follow Up | Manages follow-up calls for bulk lists, typically in a range of attempts (e.g., 1-6 calls). |
| 04 | Bulk Needs 1st Mail | Catches records that have completed the bulk calling sequence (e.g., 6+ attempts) and are ready for their first direct mail piece. |
| 05 | Bulk Mail Monthly | Manages the long-term nurture sequence for uncontacted bulk records, sending them a mail piece once per month. |
| 06 | Bulk Not Interested | Re-engages with owners from bulk lists who were previously not interested, following up on a quarterly basis. |
| 07 | Exhausted CC → DP | Segments records where all phone numbers have been marked as wrong or dead, sending them to Deep Prospecting. |
| 08 | Bulk Return Mail → DP | Segments bulk records where mail has been returned, indicating a bad address that requires Deep Prospecting. |
