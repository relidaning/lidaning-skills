#!/usr/bin/env bash
# claude-maxer: enroll/remove the crontab entries that drive maxer.py.
#
#   */10 * * * *   tick  maxer.py decides from the actual 5h reset time:
#                        run ~1h before it, open a window in a pin hour
#
# The timing lives in maxer.py (OPEN_HOURS, RUN_LEAD_MIN), not in cron,
# because the 5h window rolls and its reset isn't at a fixed hour. Override
# the tick interval with MAXER_TICK_SCHEDULE="<cron expr>".
#
# The entry lives between BEGIN/END marker comments, so install is idempotent
# (re-running replaces the block) and remove touches nothing else in the
# crontab — the usage-polling entries and unrelated jobs are left alone.
#
# Usage: enroll_cron.sh [install|remove|status|print] [--agent claude|codex]

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SKILL_DIR/run_maxer_work.sh"
TICK_SCHEDULE="${MAXER_TICK_SCHEDULE:-*/10 * * * *}"
ACTION="status"
AGENT="claude"
while (($#)); do
  case "$1" in
    --agent)
      [[ $# -ge 2 ]] || { echo "--agent needs claude or codex" >&2; exit 2; }
      AGENT="$2"; shift 2 ;;
    install|remove|status|print) ACTION="$1"; shift ;;
    *) echo "Usage: $0 [install|remove|status|print] [--agent claude|codex]" >&2; exit 2 ;;
  esac
done
[[ "$AGENT" == claude || "$AGENT" == codex ]] || { echo "Unknown agent: $AGENT" >&2; exit 2; }
LOG="/tmp/$AGENT-maxer-cron.log"
BEGIN="# BEGIN $AGENT-maxer schedule (managed by enroll_cron.sh)"
END="# END $AGENT-maxer schedule"

block() {
  echo "$BEGIN"
  if [[ "$AGENT" == codex ]]; then
    echo "$TICK_SCHEDULE $RUNNER --agent codex tick >> $LOG 2>&1"
  else
    echo "$TICK_SCHEDULE $RUNNER tick >> $LOG 2>&1"
  fi
  echo "$END"
}

# `crontab -l` exits 1 when the user has no crontab yet — treat as empty.
current() { crontab -l 2>/dev/null || true; }

without_block() {
  current | awk -v b="$BEGIN" -v e="$END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip'
}

case "$ACTION" in
  install)
    [[ -x "$RUNNER" ]] || { echo "ERROR: $RUNNER missing or not executable" >&2; exit 1; }
    { without_block; block; } | crontab -
    echo "Enrolled:"; block
    ;;
  remove)
    without_block | crontab -
    echo "Removed $AGENT-maxer schedule block (other crontab entries untouched)."
    ;;
  status)
    if current | grep -qxF "$BEGIN"; then
      current | awk -v b="$BEGIN" -v e="$END" '$0 == b { p = 1 } p; $0 == e { p = 0 }'
    else
      echo "Not enrolled."
    fi
    ;;
  print)
    block
    ;;
  *)
    echo "Usage: $0 [install|remove|status|print]" >&2
    exit 2
    ;;
esac
