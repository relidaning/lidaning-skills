#!/usr/bin/env bash
# claude-maxer: enroll/remove the crontab entry that fires run_maxer_work.sh.
#
# Default schedule: 03:30, 07:30, 12:30, 17:30, 22:30 every day, in this
# machine's local time (CST / Asia/Shanghai — cron has no per-entry timezone
# here). Override with MAXER_SCHEDULE="<cron expr>".
#
# The entry lives between BEGIN/END marker comments, so install is idempotent
# (re-running replaces the block) and remove touches nothing else in the
# crontab — the usage-polling entries and unrelated jobs are left alone.
#
# Usage: enroll_cron.sh [install|remove|status|print]   (default: status)

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SKILL_DIR/run_maxer_work.sh"
SCHEDULE="${MAXER_SCHEDULE:-30 3,7,12,17,22 * * *}"
LOG="/tmp/claude-maxer-cron.log"
BEGIN="# BEGIN claude-maxer schedule (managed by enroll_cron.sh)"
END="# END claude-maxer schedule"

block() {
  echo "$BEGIN"
  echo "$SCHEDULE $RUNNER >> $LOG 2>&1"
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

case "${1:-status}" in
  install)
    [[ -x "$RUNNER" ]] || { echo "ERROR: $RUNNER missing or not executable" >&2; exit 1; }
    { without_block; block; } | crontab -
    echo "Enrolled: $SCHEDULE -> $RUNNER"
    ;;
  remove)
    without_block | crontab -
    echo "Removed claude-maxer schedule block (other crontab entries untouched)."
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
