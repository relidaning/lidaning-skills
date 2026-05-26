#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  Claude Code Multi-Provider Shell Integration
#  Add this file to your ~/.bashrc or ~/.zshrc:
#    source ~/claude-proxy/shell-setup.sh
# ═══════════════════════════════════════════════════════════

# ── API Keys ─────────────────────────────────────────────
# Store keys in ~/.secrets (chmod 600) and source it here.
# Example ~/.secrets:
#   export DEEPSEEK_API_KEY="sk-xxx"
#   export Z_AI_API_KEY="xxx"
#   export KIMI_API_KEY="xxx"
#   export OPENROUTER_API_KEY="sk-or-xxx"
[ -f "$HOME/.secrets" ] && source "$HOME/.secrets"

# ── Proxy config ──────────────────────────────────────────
CLAUDE_PROXY_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_PROXY_PORT="${PROXY_PORT:-8787}"

# Start the TypeScript proxy in the background
proxy-start() {
    if lsof -ti:"$CLAUDE_PROXY_PORT" &>/dev/null; then
        echo "⚠️  Proxy already running on :$CLAUDE_PROXY_PORT"
        return 0
    fi
    echo "🚀 Starting Claude proxy on :$CLAUDE_PROXY_PORT ..."
    cd "$CLAUDE_PROXY_DIR" && npx tsx proxy.ts &>/tmp/claude-proxy.log &
    disown
    sleep 1
    echo "✓ Proxy started (logs: /tmp/claude-proxy.log)"
}

# Stop the proxy
proxy-stop() {
    local pid
    pid=$(lsof -ti:"$CLAUDE_PROXY_PORT")
    if [ -n "$pid" ]; then
        kill "$pid" && echo "✓ Proxy stopped"
    else
        echo "No proxy running on :$CLAUDE_PROXY_PORT"
    fi
}

# Show proxy logs
proxy-logs() {
    tail -f /tmp/claude-proxy.log
}

# ── Provider shortcuts ────────────────────────────────────
# Each function starts the proxy (if not running) and launches claude
# pointed at a specific provider/model via DEFAULT_PROVIDER env var.

_claude_via_proxy() {
    local provider="$1"
    local model="$2"
    shift 2
    proxy-start
    # Do NOT set ANTHROPIC_API_KEY — that would override Claude Code's OAuth
    # session and cause repeated login prompts when the proxy forwards
    # auth-verification requests upstream. The proxy injects the real
    # provider key for /v1/messages itself.
    DEFAULT_PROVIDER="$provider" \
    DEFAULT_MODEL="$model" \
    ANTHROPIC_BASE_URL="http://localhost:$CLAUDE_PROXY_PORT" \
        claude "$@"
}

# DeepSeek (great for code, cheap)
deepseek() {
    _claude_via_proxy "deepseek" "deepseek-chat" "$@"
}

# DeepSeek Reasoner (R1 — slower, stronger reasoning)
deepseek-r1() {
    _claude_via_proxy "deepseek" "deepseek-reasoner" "$@"
}

# GLM (z.ai)
glm() {
    _claude_via_proxy "glm" "glm-4.6" "$@"
}

# Kimi (Moonshot AI)
kimi() {
    _claude_via_proxy "kimi" "moonshot-v1-32k" "$@"
}

# Sonnet via proxy (default — uses OAuth, switchable to DeepSeek/GLM/Kimi mid-session)
sonnet() {
    _claude_via_proxy "anthropic" "claude-sonnet-4-6" "$@"
}

# Real Anthropic (bypass proxy entirely)
claude-anthropic() {
    unset ANTHROPIC_BASE_URL
    claude "$@"
}

# ── Status helper ─────────────────────────────────────────
proxy-status() {
    if lsof -ti:"$CLAUDE_PROXY_PORT" &>/dev/null; then
        echo "✓ Proxy running on :$CLAUDE_PROXY_PORT"
        curl -s "http://localhost:$CLAUDE_PROXY_PORT/providers" | \
            node -e "
const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
d.forEach(p=>console.log(\`  \${p.keyConfigured?'✓':'✗'} \${p.key.padEnd(12)} → \${p.baseUrl}\`));
" 2>/dev/null || \
            curl -s "http://localhost:$CLAUDE_PROXY_PORT/providers"
    else
        echo "✗ Proxy not running  (run: proxy-start)"
    fi
}

echo "Claude proxy helpers loaded. Commands: proxy-start, proxy-stop, proxy-status, proxy-logs"
echo "Model shortcuts: sonnet, deepseek, deepseek-r1, glm, kimi, claude-anthropic"
