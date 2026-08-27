#!/usr/bin/env bash
# Overnight eCourts catch-up for the SmartSkip Group 2 rename proposals.
#
# Tyler/Odyssey rate-limits Parties to roughly 13 calls per 45 minutes. The
# 21:45 run used an 8-second gap, burned its burst allowance in ~7 cases and
# aborted. This paces at 200s/case - just under the sustained limit - so a round
# can walk the whole remaining list instead of tripping the abort. Between
# rounds it waits out a full throttle window; cached hex IDs and cached fills
# mean every round picks up where the last stopped.
#
# reenrich does NOT write back to its input - it emits a fresh CSV and logs
# "Wrote CSV: <path>". So each round chains the previous round's OUTPUT in as
# the next round's INPUT, which is also the only honest way to count what is
# still blank. (Checking the original input would report 33 forever.)
#
# Read-only against the court. Writes NOTHING to DataSift.
set -u
cd /d/SiftStack
CUR=output/smartskip_group2_recheck.csv
LOG=logs/ecourts_catchup_20260825.log
PY=.venv/Scripts/python.exe

blanks () {
  "$PY" -c "
import csv,sys
rows=list(csv.DictReader(open(sys.argv[1],newline='',encoding='utf-8-sig')))
print(sum(1 for r in rows if not (r.get('Personal Representative') or '').strip()))
" "$1"
}

echo "===== catch-up started $(date '+%Y-%m-%d %H:%M:%S'); blank=$(blanks "$CUR")" >> "$LOG"

for round in 1 2 3 4 5 6 7 8; do
  echo "===== round $round  $(date '+%Y-%m-%d %H:%M:%S')  input=$CUR" >> "$LOG"
  OUT_TMP=$(mktemp)
  "$PY" reenrich_ftm_executors.py --csv "$CUR" \
        --inter-case-delay 200 --max-consecutive-fails 8 --retries 2 \
        > "$OUT_TMP" 2>&1
  cat "$OUT_TMP" >> "$LOG"

  # "Wrote CSV: output\nc_estates_ftm_....csv" - take the last one, normalise slashes
  NEW=$(grep -a "Wrote CSV:" "$OUT_TMP" | tail -1 | sed 's/.*Wrote CSV: *//' | tr -d '\r' | tr '\' '/')
  rm -f "$OUT_TMP"
  if [ -n "$NEW" ] && [ -f "$NEW" ]; then
    CUR="$NEW"
  else
    echo "  round $round produced no CSV - keeping $CUR" >> "$LOG"
  fi

  REM=$(blanks "$CUR")
  echo "  round $round done; still blank: $REM  (carrying $CUR)" >> "$LOG"
  if [ "$REM" = "0" ]; then
    echo "  ALL RESOLVED - stopping early" >> "$LOG"
    break
  fi
  echo "  sleeping 45m for the throttle window" >> "$LOG"
  sleep 2700
done
echo "===== catch-up finished $(date '+%Y-%m-%d %H:%M:%S'); final=$CUR blank=$(blanks "$CUR")" >> "$LOG"
