#!/usr/bin/env bash
# claude-maxer cron entry point. Sets up the environment that cron lacks,
# then hands off to maxer.py, which holds all the logic (window plan, gate,
# tasks, vault log): see its docstring.
#
# Usage: run_maxer_work.sh run|open|status [--dry-run] | off [--until WHEN] | on

set -euo pipefail

# cron sets no $HOME (breaks ~/.claude/.credentials.json lookup) and a minimal
# PATH without claude (~/.local/bin).
export HOME="/home/shake"
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.nvm/versions/node/v24.15.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# api.anthropic.com is reachable only through the local xray proxy; without
# these every `claude -p` fails with "403 Failed to authenticate".
export http_proxy="http://127.0.0.1:10808"
export https_proxy="http://127.0.0.1:10808"
export NODE_USE_ENV_PROXY=1
# Localhost (the obsidian-vault MCP container) must bypass the proxy.
export no_proxy="localhost,127.0.0.1"

export OBSIDIAN_MCP_URL="${OBSIDIAN_MCP_URL:-http://127.0.0.1:27125}"

exec python3 "$(dirname "$(readlink -f "$0")")/maxer.py" "$@"
