#!/bin/bash
# Validator: the monitor produced a fresh verdict this session.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
F=ops/logs/monitor.jsonl
MAX_AGE_MIN=${MONITOR_MAX_AGE_MIN:-45}
[ "$(date +%F)" \> "2026-09-04" ] && { echo "OK: contest over"; exit 0; }
# The monitor self-gates weekends, so "stale" is the correct state Sat/Sun and
# the freshness check must not call it a failure. Without this the loop went
# red for 48h every weekend — a false alarm that trains you to ignore the
# alarm, which is worse than no alarm.
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
  test -s "$F" || { echo "FAIL: no $F and none was ever written"; exit 1; }
  echo "OK: weekend — monitor correctly idle, last verdict $(date -r "$F" +%F\ %H:%M)"
  exit 0
fi
test -s "$F" || { echo "FAIL: no $F — monitor has never produced a verdict"; exit 1; }
# Same class of false alarm as the weekend gate above, just for the overnight gap: the
# schedule (docs/loop/registry.json) only fires 09:30-15:45 ET on weekdays, so a check run
# pre-market or after close will always see a stale last verdict even though the monitor
# is correctly idle. Proven 2026-09-02: audit ran at 09:08 ET (before the 09:30 open) and
# reported "1042m old" as a failure. Widen the window 15 min on each side for launchd jitter.
NOWHM=$((10#$(date +%H%M)))
if [ "$NOWHM" -lt 915 ] || [ "$NOWHM" -gt 1600 ]; then
  echo "OK: outside trading hours (09:30-15:45 ET) — monitor correctly idle, last verdict $(date -r "$F" +%F\ %H:%M)"
  exit 0
fi
AGE=$(( ( $(date +%s) - $(stat -f %m "$F") ) / 60 ))
[ "$AGE" -le "$MAX_AGE_MIN" ] || { echo "FAIL: last verdict ${AGE}m old (max $MAX_AGE_MIN)"; exit 1; }
tail -1 "$F" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'positions' in d and 'next_size' in d, 'verdict missing required fields'
print(f\"OK: {len(d['positions'])} position(s), {len(d['actions'])} action(s), {d['sessions_left']} sessions left\")
" || { echo 'FAIL: last line is not a valid verdict'; exit 1; }
