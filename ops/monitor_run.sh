#!/bin/bash
# Contest position monitor. Every 15 min during RTH, 2026-08-28 → 2026-09-04.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p ops/logs
END=2026-09-04
[ "$(date +%F)" \> "$END" ] && exit 0            # self-retires after the contest
H=$(date +%H); M=$(date +%u)
[ "$M" -gt 5 ] && exit 0                          # weekdays only
[ "$H" -lt 9 ] || [ "$H" -ge 16 ] && exit 0       # RTH-ish, ET
eval "$(grep -E '^(ALPACA_API_KEY|ALPACA_SECRET_KEY)=' ops/.env 2>/dev/null | sed 's/^/export /')"
../automated-trading/.venv/bin/python ops/monitor.py --json \
  >> ops/logs/monitor.jsonl 2>> ops/logs/monitor.err
# Capture BEFORE any other command runs. `echo "$(date) exit=$?"` expands the
# command substitution first, so $? reports date's status (always 0) and every
# line logged a false green regardless of what the monitor did.
rc=$?
ts=$(date -u +%FT%TZ)
echo "$ts exit=$rc" >> ops/logs/monitor.log
exit "$rc"                                # let launchd see a real failure
