#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  model-switch CLI — control the proxy WITHOUT a Claude session.
#
#  This is the rate-limit escape hatch: when Anthropic throttles you,
#  /model-switch inside Claude Code can't respond, but this script can
#  still flip you to DeepSeek/GLM/Kimi from a plain shell.
#
#  Usage:
#    ./switch.sh status                    # proxy + override + settings state
#    ./switch.sh list                      # available provider/model ids
#    ./switch.sh use deepseek/deepseek-chat  # switch (starts proxy if needed)
#    ./switch.sh off                       # back to official Anthropic direct
#    ./switch.sh start | stop              # proxy lifecycle
#
#  "use"  = set proxy override + persist ANTHROPIC_BASE_URL in
#           ~/.claude/settings.json (new sessions route through proxy;
#           an already-proxied running session switches instantly).
#  "off"  = clear override + remove ANTHROPIC_BASE_URL (new sessions
#           go direct to api.anthropic.com).
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

PORT="${PROXY_PORT:-8787}"
BASE="http://localhost:$PORT"
SETTINGS="$HOME/.claude/settings.json"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=/tmp/claude-proxy.log

curl_p() { curl -s --noproxy '*' "$@"; }

proxy_up() { curl_p --max-time 2 "$BASE/health" >/dev/null 2>&1; }

settings_base_url() {
  python3 -c "
import json
try:
    print(json.load(open('$SETTINGS')).get('env', {}).get('ANTHROPIC_BASE_URL', ''))
except FileNotFoundError:
    print('')
"
}

set_base_url() {
  python3 -c "
import json
try:
    d = json.load(open('$SETTINGS'))
except FileNotFoundError:
    d = {}
d.setdefault('env', {})['ANTHROPIC_BASE_URL'] = '$BASE'
json.dump(d, open('$SETTINGS', 'w'), indent=2)
"
}

unset_base_url() {
  python3 -c "
import json
try:
    d = json.load(open('$SETTINGS'))
except FileNotFoundError:
    raise SystemExit
d.get('env', {}).pop('ANTHROPIC_BASE_URL', None)
if not d.get('env'):
    d.pop('env', None)
json.dump(d, open('$SETTINGS', 'w'), indent=2)
"
}

cmd_start() {
  if proxy_up; then
    echo "✓ Proxy already running on :$PORT"
    return 0
  fi
  echo "🚀 Starting proxy on :$PORT ..."
  # shellcheck disable=SC1090
  [ -f "$HOME/.secrets" ] && source "$HOME/.secrets"
  # NODE_USE_ENV_PROXY: Node's fetch() ignores http_proxy/https_proxy by
  # default, but this machine reaches api.anthropic.com only through the
  # local xray proxy — without this, every Anthropic passthrough gets a
  # region-block 403 that Claude Code misreads as "please log in".
  (cd "$SKILL_DIR" && NODE_USE_ENV_PROXY=1 nohup npx tsx proxy.ts >"$LOG" 2>&1 &)
  for _ in $(seq 1 20); do
    proxy_up && { echo "✓ Proxy up (logs: $LOG)"; return 0; }
    sleep 0.5
  done
  echo "✗ Proxy failed to start — check $LOG" >&2
  return 1
}

cmd_stop() {
  local pid
  pid=$(lsof -ti:"$PORT" 2>/dev/null || true)
  if [ -n "$pid" ]; then
    kill "$pid" && echo "✓ Proxy stopped"
  else
    echo "No proxy running on :$PORT"
  fi
}

cmd_status() {
  if proxy_up; then
    echo "Proxy:    ✓ running on :$PORT"
    echo "Override: $(curl_p "$BASE/switch" | python3 -c 'import json,sys; print(json.load(sys.stdin)["override"] or "(none — default routing)")')"
  else
    echo "Proxy:    ✗ not running"
  fi
  local burl
  burl=$(settings_base_url)
  if [ -n "$burl" ]; then
    echo "Settings: new sessions route through proxy ($burl)"
    proxy_up || echo "          ⚠ but proxy is DOWN — new sessions will fail; run: $0 start (or: $0 off)"
  else
    echo "Settings: new sessions go direct to api.anthropic.com"
  fi
  echo "This shell: ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-(not set)}"
}

cmd_list() {
  if proxy_up; then
    curl_p "$BASE/v1/models" | python3 -c '
import json, sys
for m in json.load(sys.stdin)["data"]:
    print(f"  {m[\"id\"]:36} ({m[\"owned_by\"]})")
'
  else
    echo "Proxy not running — start it with: $0 start" >&2
    return 1
  fi
}

cmd_use() {
  local target="${1:-}"
  if [[ "$target" != */* ]]; then
    echo "Usage: $0 use <provider>/<model>   e.g. $0 use deepseek/deepseek-chat" >&2
    exit 1
  fi
  cmd_start
  local resp
  resp=$(curl_p -X POST "$BASE/switch" -H 'Content-Type: application/json' -d "{\"model\": \"$target\"}")
  if echo "$resp" | grep -q '"error"'; then
    echo "✗ $resp" >&2
    exit 1
  fi
  set_base_url
  echo "✓ Override set: $target"
  echo "✓ ANTHROPIC_BASE_URL persisted in $SETTINGS"
  echo "  • A session already running through the proxy switches immediately."
  echo "  • A non-proxied running session keeps its connection; relaunch claude to pick this up."
}

cmd_off() {
  if proxy_up; then
    curl_p -X DELETE "$BASE/switch" >/dev/null
    echo "✓ Proxy override cleared"
  else
    # proxy down — clear its persisted state directly so a later start doesn't restore the override
    rm -f "$HOME/.claude/state/model-switch.json"
    echo "✓ Proxy not running; cleared persisted override state"
  fi
  unset_base_url
  echo "✓ ANTHROPIC_BASE_URL removed from $SETTINGS"
  echo "  New sessions go direct to official api.anthropic.com. Relaunch claude to apply."
}

case "${1:-status}" in
  status) cmd_status ;;
  list)   cmd_list ;;
  use)    shift; cmd_use "${1:-}" ;;
  off|reset) cmd_off ;;
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  *)
    echo "Usage: $0 {status|list|use <provider/model>|off|start|stop}" >&2
    exit 1
    ;;
esac
