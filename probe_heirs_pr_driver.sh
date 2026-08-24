#!/usr/bin/env bash
# Drive probe_heirs_pr_20260822.py one throttle window at a time.
#
# The court answers ~9-13 Parties calls, then hard-refuses for a long
# cooldown (project_parties_api_throttle_heirs_of). Grinding through the
# refusal just burns the IP we need for the nightly pipeline, so this
# takes one window, backs all the way off for COOLDOWN_MIN, and retries.
# The probe itself is resumable — settled cases are never re-asked.
#
# Usage: bash probe_heirs_pr_driver.sh [max_windows]
set -u

MAX_WINDOWS="${1:-10}"
COOLDOWN_MIN="${COOLDOWN_MIN:-60}"
# The court has usually JUST cut us off when this launches, so back off
# before the first window instead of walking straight into the refusal.
INITIAL_COOLDOWN_MIN="${INITIAL_COOLDOWN_MIN:-60}"
OUT_CSV="output/heirs_pr_probe.csv"
LOG="logs/probe_heirs_pr_driver.log"

log() { echo "$(date '+%H:%M:%S') [driver] $*" | tee -a "$LOG"; }

log "start — up to $MAX_WINDOWS window(s), ${COOLDOWN_MIN}min cooldown between"

if (( INITIAL_COOLDOWN_MIN > 0 )); then
  log "initial cooldown ${INITIAL_COOLDOWN_MIN}min (letting the throttle reset)"
  sleep $((INITIAL_COOLDOWN_MIN * 60))
fi

for ((w = 1; w <= MAX_WINDOWS; w++)); do
  log "window $w/$MAX_WINDOWS starting"
  python probe_heirs_pr_20260822.py >> logs/probe_heirs_pr_run.out 2>&1
  rc=$?

  open=$(python - "$OUT_CSV" <<'PY'
import csv, sys
settled = {"PR FOUND",
           "PR FOUND - but occupied, review before marketing",
           "CONTACT ONLY (not a formal PR)",
           "COURT HAS NO PR"}
try:
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
except OSError:
    print(-1); raise SystemExit
print(sum(1 for r in rows if (r.get("Verdict") or "") not in settled))
PY
)
  done_n=$(python - "$OUT_CSV" <<'PY'
import csv, sys
settled = {"PR FOUND",
           "PR FOUND - but occupied, review before marketing",
           "CONTACT ONLY (not a formal PR)",
           "COURT HAS NO PR"}
try:
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
except OSError:
    print(0); raise SystemExit
print(sum(1 for r in rows if (r.get("Verdict") or "") in settled))
PY
)

  log "window $w done (rc=$rc) — settled so far: $done_n, still open in file: $open"

  # Keep going until the court stops giving us anything. One barren window
  # is normal — its throttle allowance varies a lot run to run (window 1
  # answered 9, window 2 only 2) — so require TWO in a row before quitting.
  if [[ "$done_n" == "${prev_done:-}" ]]; then
    barren=$((${barren:-0} + 1))
    log "window $w added nothing (${barren} in a row)"
    if (( barren >= 2 )); then
      log "two barren windows — the court is done with us; stopping early"
      break
    fi
  else
    barren=0
  fi
  prev_done="$done_n"

  if (( w < MAX_WINDOWS )); then
    log "cooling down ${COOLDOWN_MIN}min before window $((w + 1))"
    sleep $((COOLDOWN_MIN * 60))
  fi
done

log "driver finished — settled: ${prev_done:-0}. Report: $OUT_CSV"
