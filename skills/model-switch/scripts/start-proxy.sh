#!/usr/bin/env bash
# Auto-started by Claude Code SessionStart hook.
# Idempotent — safe to call multiple times.
set -euo pipefail

PORT="${PROXY_PORT:-8787}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="/tmp/claude-proxy.log"

# Source API keys
[ -f "$HOME/.secrets" ] && source "$HOME/.secrets"

# Already running?
if lsof -ti:"$PORT" &>/dev/null; then
    exit 0
fi

# Start proxy in background
cd "$SKILL_DIR"
nohup npx tsx proxy.ts >"$LOG_FILE" 2>&1 &
disown

# Wait until healthy
for i in $(seq 1 30); do
    if curl -s "http://localhost:$PORT/health" &>/dev/null; then
        exit 0
    fi
    sleep 0.1
done

echo "WARN: proxy started but health check timed out" >&2
exit 0
