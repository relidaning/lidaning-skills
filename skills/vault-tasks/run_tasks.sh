#!/usr/bin/env bash
# vault-tasks: reads undone items from the Obsidian vault's Tasks.md and
# implements one per run in /data/apps/myfollows, commits to master, and
# checks the task off. Fired by local crontab every 30 minutes.
#
# Usage: run_tasks.sh [--dry-run]

set -euo pipefail

# cron on this box doesn't set $HOME, and its minimal PATH lacks claude/git.
export HOME="/home/shake"
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.nvm/versions/node/v24.15.0/bin:$HOME/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# api.anthropic.com is only reachable via the local xray proxy on this box.
export http_proxy="http://127.0.0.1:10808"
export https_proxy="http://127.0.0.1:10808"

# Obsidian Local REST API env vars are interactive-shell-only; cron needs
# them sourced explicitly. OBSIDIAN_MCP_TOKEN lives in ~/.zshrc.local;
# OBSIDIAN_MCP_URL is set here directly since sourcing alone leaves it empty.
source "$HOME/.zshrc.local"
export OBSIDIAN_MCP_URL="http://127.0.0.1:27123/"

SKILL_DIR="/data/apps/lidaning-skills/skills/vault-tasks"
MAXER_DIR="/data/apps/lidaning-skills/skills/claude-maxer"
TARGET_REPO="/data/apps/myfollows"
LOG_FILE="$HOME/.claude/state/vault-tasks.log.jsonl"
LOCK_FILE="/tmp/vault-tasks.lock"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  # $1=status $2=detail
  python3 -c "
import json, sys, time
print(json.dumps({'ts': time.time(), 'status': sys.argv[1], 'detail': sys.argv[2]}))
" "$1" "$2" >> "$LOG_FILE"
}

# Don't overlap with a still-running previous iteration (a big task can
# outlast one 30-minute slot).
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "skipped" "previous run still in progress"
  exit 0
fi

# Usage gate, reusing claude-maxer's snapshot + threshold check as-is.
set +e
python3 "$MAXER_DIR/fetch_usage_oauth.py" >/dev/null 2>&1
CHECK_OUTPUT="$(python3 "$MAXER_DIR/check_usage.py")"
CHECK_STATUS=$?
set -e
if [[ $CHECK_STATUS -ne 0 ]]; then
  log "skipped" "$CHECK_OUTPUT"
  exit 0
fi

TASK="$(python3 "$SKILL_DIR/vault_tasks.py" pick || true)"
if [[ -z "$TASK" ]]; then
  log "skipped" "no undone tasks"
  exit 0
fi

if $DRY_RUN; then
  echo "[dry-run] would handle: $TASK"
  exit 0
fi

PROMPT="You are running unattended as part of the vault-tasks scheduled routine. Repo: $TARGET_REPO. A task from the Obsidian vault's Tasks.md reads: \"$TASK\". Implement it in this repo: make the necessary code/UI changes, and run any existing lint/typecheck/build step for the touched area if one exists. Keep the change scoped to what this task describes -- do not fold in unrelated cleanup. When done, commit the change directly to the current branch (master) with a descriptive commit message referencing the task. Do not push to any remote."

OUT_FILE="/tmp/vault-tasks-last-run.log"
{
  echo "=== $(date -Iseconds) ==="
  echo "task: $TASK"
} > "$OUT_FILE"

cd "$TARGET_REPO"
set +e
RESULT_JSON="$(timeout 25m claude -p "$PROMPT" --model claude-sonnet-5 --output-format json --max-budget-usd 5 --dangerously-skip-permissions 2>>"$OUT_FILE")"
CALL_STATUS=$?
set -e
echo "$RESULT_JSON" >> "$OUT_FILE"

if [[ $CALL_STATUS -eq 0 ]]; then
  if python3 "$SKILL_DIR/vault_tasks.py" mark "$TASK"; then
    log "done" "$TASK"
  else
    log "handled_but_unmarked" "$TASK -- claude succeeded but marking Tasks.md failed, check $OUT_FILE"
  fi
else
  log "failed" "$TASK -- see $OUT_FILE"
fi
