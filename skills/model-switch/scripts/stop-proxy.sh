#!/usr/bin/env bash
# Auto-stopped by Claude Code Stop hook.
set -euo pipefail

PORT="${PROXY_PORT:-8787}"
PID=$(lsof -ti:"$PORT" 2>/dev/null) || true

if [ -n "${PID:-}" ]; then
    kill "$PID" 2>/dev/null || true
fi
