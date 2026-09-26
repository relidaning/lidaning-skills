#!/usr/bin/env bash
# claude-maxer: enroll/remove the crontab entries that drive maxer.py.
#
#   0 3,8,13,18 * * *   open  start the pinned 5h windows (03-08, 08-13,
#                             13-18, 18-23; 23-03 is the buffer, see maxer.py)
#   */15 * * * *        run   acts only in a window's last hour, filling it
#                             toward 95%; every other tick is a cheap no-op
#
# Times are this machine's local time (CST / Asia/Shanghai). Override with
# MAXER_OPEN_SCHEDULE / MAXER_RUN_SCHEDULE="<cron expr>".
#
# The entry lives between BEGIN/END marker comments, so install is idempotent
# (re-running replaces the block) and remove touches nothing else in the
# crontab — the usage-polling entries and unrelated jobs are left alone.
#
# Usage: enroll_cron.sh [install|remove|status|print]   (default: status)

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SKILL_DIR/run_maxer_work.sh"
OPEN_SCHEDULE="${MAXER_OPEN_SCHEDULE:-0 3,8,13,18 * * *}"
RUN_SCHEDULE="${MAXER_RUN_SCHEDULE:-*/15 * * * *}"
LOG="/tmp/claude-maxer-cron.log"
BEGIN="# BEGIN claude-maxer schedule (managed by enroll_cron.sh)"
END="# END claude-maxer schedule"

block() {
  echo "$BEGIN"
  echo "$OPEN_SCHEDULE $RUNNER open >> $LOG 2>&1"
  echo "$RUN_SCHEDULE $RUNNER run >> $LOG 2>&1"
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
    echo "Enrolled:"; block
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
