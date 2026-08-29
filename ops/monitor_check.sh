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
AGE=$(( ( $(date +%s) - $(stat -f %m "$F") ) / 60 ))
[ "$AGE" -le "$MAX_AGE_MIN" ] || { echo "FAIL: last verdict ${AGE}m old (max $MAX_AGE_MIN)"; exit 1; }
tail -1 "$F" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'positions' in d and 'next_size' in d, 'verdict missing required fields'
print(f\"OK: {len(d['positions'])} position(s), {len(d['actions'])} action(s), {d['sessions_left']} sessions left\")
" || { echo 'FAIL: last line is not a valid verdict'; exit 1; }
