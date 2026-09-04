#!/bin/bash
# One-shot deadline flatten. Fires 10:00 ET Fri 2026-09-04 — a full hour of
# margin before the 15:00 UTC scoring snapshot, and 30 minutes after the open
# so the spreads it has to cross have settled.
#
# Giani's call (2026-09-03, book +$1,753): "if it's not negative we should cut
# it before 11." Then on 09-04: "you can do it. The whole reason I wanted to do
# this was to automate it and have it run by you/grok." So this is the primary
# path, not a fallback — no human step on the last morning. If he happens to
# run ./ops/flatten.py --execute himself first, there are no positions left and
# this exits having done nothing.
#
# Refuses to act on any day but the deadline, and unloads itself either way, so
# a fire that arrives late can never submit orders into an unrelated market.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p ops/logs
LOG=ops/logs/flatten-backstop.log
DEADLINE=2026-09-04
ts() { date -u +%FT%TZ; }
say() { echo "$(ts) $*" >> "$LOG"; }

# Which job am I? The 10:00 primary and the 10:20 retry share this script, and
# each must retire only itself.
LABEL="${FILLTRUE_FLATTEN_LABEL:-com.giani.filltrue-flatten}"

unload_self() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>>ops/logs/launchd.err || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
}

# Never trade on a day that is not the deadline. The two wrong-day cases are
# not the same, and collapsing them is a bug:
#
#   before — an early wake must stand by, NOT unload. Retiring here would
#            silently disarm the job and the 10:30 backstop never fires.
#   after  — launchd replays a missed StartCalendarInterval on wake from
#            sleep, so a late fire could land on a Monday with a live book.
#            That one retires for good.
TODAY=$(date +%F)
if [[ "$TODAY" < "$DEADLINE" ]]; then
  say "before the deadline (today=$TODAY) — standing by, still armed for $DEADLINE"
  exit 0
fi
if [ "$TODAY" != "$DEADLINE" ]; then
  say "past the deadline (today=$TODAY) — retiring without acting"
  unload_self
  exit 0
fi

set -a; [ -f ops/.env ] && . ops/.env; set +a

# Call the venv interpreter explicitly, exactly as monitor_run.sh does.
# `./ops/flatten.py` was two separate silent no-ops: the file is not +x (exit
# 126), and its #!/usr/bin/env python3 shebang resolves to the system python,
# which has no `requests`. Either one would have made the 10:00 fire do
# nothing at all while still retiring the job. Found 2026-09-04 by running
# this script on deadline day.
PY_BIN=../automated-trading/.venv/bin/python
if [ ! -x "$PY_BIN" ]; then
  say "FATAL: interpreter $PY_BIN missing — cannot flatten, leaving job armed"
  exit 1
fi
out="$("$PY_BIN" ops/flatten.py --execute 2>&1)"; rc=$?
say "[$LABEL] flatten --execute exit=$rc"
echo "$out" >> "$LOG"

REPO="$HOME/project-claude"
if source "$REPO/agent-runtime/lib/util.sh" 2>/dev/null && source "$REPO/agent-runtime/lib/discord.sh" 2>/dev/null; then
  if [ "$rc" -eq 0 ]; then
    msg="**FillTrue flattened** [$LABEL] (10:30 ET backstop, exit 0) — every leg filled and confirmed against the broker. Nothing open into the 11:00 snapshot.
\`\`\`
$(echo "$out" | tail -20)
\`\`\`"
  else
    msg="**FillTrue flatten INCOMPLETE — exit $rc.** At least one leg did not fill. You have until 11:00 ET. Run \`cd ~/project-claude/filltrue && ./ops/flatten.py --execute\` and see what is still open.
\`\`\`
$(echo "$out" | tail -20)
\`\`\`"
  fi
  if chan="$(discord_channel)"; then
    discord_post "$chan" "$msg" >/dev/null || say "warn: Discord not delivered"
  else say "warn: no Discord channel resolved"; fi
else say "warn: agent-runtime discord lib unavailable"; fi

unload_self
say "retired"
exit "$rc"
