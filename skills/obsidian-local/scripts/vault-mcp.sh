#!/usr/bin/env bash
# Manage and call the headless obsidian-vault MCP server.
#   vault-mcp.sh ensure              start the container if it isn't healthy, then list tools
#   vault-mcp.sh tools               list tool names + arguments (* = required)
#   vault-mcp.sh call <tool> [json]  call one tool, print its text result
#   vault-mcp.sh stop | logs
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../server" && pwd)"
PORT="${OBSIDIAN_VAULT_MCP_PORT:-27125}"
BASE="http://127.0.0.1:$PORT"
export OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-/data/nextcloud_client/obsidian/lidaning}"
export VAULT_UID="$(stat -c %u "$OBSIDIAN_VAULT_PATH")" VAULT_GID="$(stat -c %g "$OBSIDIAN_VAULT_PATH")"

healthy() { curl -sf --noproxy '*' -m 2 "$BASE/healthz" >/dev/null 2>&1; }

post() {  # post <json> [session-id] -> response JSON (SSE "data:" line unwrapped)
  curl -s --noproxy '*' -m 60 -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    ${2:+-H "mcp-session-id: $2"} "$BASE/mcp" -d "$1"
}

session() {  # open an MCP session, print its id
  local sid
  sid=$(curl -s --noproxy '*' -m 10 -D - -o /dev/null -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' "$BASE/mcp" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"vault-mcp.sh","version":"1"}}}' \
    | awk 'tolower($1)=="mcp-session-id:"{print $2}' | tr -d '\r')
  [[ -n $sid ]] || { echo "error: MCP initialize failed at $BASE/mcp" >&2; exit 1; }
  post '{"jsonrpc":"2.0","method":"notifications/initialized"}' "$sid" >/dev/null
  echo "$sid"
}

rpc() {  # rpc <method> <params-json>
  local sid; sid=$(session)
  post "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"$1\",\"params\":$2}" "$sid" | sed -n 's/^data: //p'
}

ensure() {
  if healthy; then echo "obsidian-vault MCP: already running at $BASE/mcp"; return; fi
  echo "obsidian-vault MCP: not running, starting container..." >&2
  docker compose -f "$SERVER_DIR/docker-compose.yml" up -d --quiet-pull >&2 2>&1 | grep -vE "^ *#|Building|exporting" >&2 || true
  for _ in $(seq 1 30); do healthy && break; sleep 1; done
  healthy || { echo "error: server did not become healthy; see: $0 logs" >&2; exit 1; }
  echo "obsidian-vault MCP: started at $BASE/mcp"
}

tools() {
  rpc tools/list '{}' | python3 -c '
import json, sys
for t in json.load(sys.stdin)["result"]["tools"]:
    s = t["inputSchema"]; req = s.get("required", [])
    args = ", ".join(k + ("*" if k in req else "") for k in s.get("properties", {}))
    print(t["name"] + "(" + args + ")")'
}

call() {
  local tool=$1 args=${2:-'{}'}
  local params
  params=$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}))' "$tool" "$args")
  rpc tools/call "$params" | python3 -c '
import json, sys
r = json.load(sys.stdin)
if "error" in r: sys.exit("error: " + r["error"].get("message", str(r["error"])))
res = r["result"]
print("\n".join(c.get("text", "") for c in res.get("content", [])))
sys.exit(1 if res.get("isError") else 0)'
}

case "${1:-ensure}" in
  ensure) ensure; echo "tools:"; tools | sed 's/^/  /' ;;
  tools)  healthy || ensure >&2; tools ;;
  call)   shift; healthy || ensure >&2; call "$@" ;;
  stop)   docker compose -f "$SERVER_DIR/docker-compose.yml" down ;;
  logs)   docker compose -f "$SERVER_DIR/docker-compose.yml" logs --tail 50 ;;
  *)      sed -n '2,6p' "$0"; exit 2 ;;
esac
