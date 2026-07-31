@echo off
REM === One-off cleanup of the 07/31/2026 June+July sold sweep ===
REM Deletes the pulled records that were never our leads, one pass per
REM month tag. Ceilings = the exact pull totals (4,389 June / 1,563 July);
REM the delete can never exceed them. Safe to run more than once — records
REM already deleted just drop out of the filter.
REM Logs to logs\manage_sold_monthly.log via the main bat.

call "D:\SiftStack\scripts\manage_sold_monthly.bat" --delete-strangers-only --sold-tag-date 2026-06 --pull-date 07/31/2026 --expected-max 4389
call "D:\SiftStack\scripts\manage_sold_monthly.bat" --delete-strangers-only --sold-tag-date 2026-07 --pull-date 07/31/2026 --expected-max 1563
