---
name: model-switch
description: >
  Activate when user asks to route Claude Code through a non-Anthropic
  provider — DeepSeek, GLM (z.ai), Kimi (Moonshot), or OpenRouter — or to
  start, stop, or check the model-switch proxy. Do NOT activate for the
  built-in /model command or plain Claude-model switches (Sonnet/Opus/Haiku)
  when the session isn't running through the proxy. Multi-provider LLM
  proxy: route mid-session to any backend without restart.
---

# Model Switch Proxy

## When to activate

Invoke this skill when:
- User mentions DeepSeek, GLM, Kimi, or OpenRouter by name
- User asks to run Claude Code against a different/cheaper/non-Anthropic provider
- User wants to start, stop, or check the proxy status
- User asks about multi-provider routing or model backends

**Skip** when the user is just switching between Anthropic Claude models
(Sonnet/Opus/Haiku) with Claude Code's built-in `/model` command — that's
harness config, not the proxy. Exception: the session is already running
through the proxy (`ANTHROPIC_BASE_URL=http://localhost:8787`), where
`/model` is fed by the proxy's picker.

A local Hono proxy that sits between Claude Code and any Anthropic-compatible LLM
provider. Switch models inside a running session without restarting.

## Interactive picker (explicit `/model-switch` invocation)

When the user invokes `/model-switch` directly, run this flow:

1. **Ensure the proxy is up** — `curl -s --noproxy '*' http://localhost:8787/health`.
   If it's down, start it with `./switch.sh start` in the skill dir (sources
   `~/.secrets` and sets `NODE_USE_ENV_PROXY=1` so Node's fetch honors
   `http_proxy`/`https_proxy` — required to reach api.anthropic.com through
   the local xray proxy; without it every Anthropic passthrough 403s and
   Claude Code loops on login prompts) and re-check.
2. **Show current state** — `GET /switch` returns the active override (or null);
   `GET /v1/models` lists what's available.
3. **Ask the user** with AskUserQuestion. Nine models don't fit one question:
   ask the provider first (Anthropic / DeepSeek / GLM / Kimi), then that
   provider's models, marking the current override "(current)" if set.
4. **Apply on confirmation** — delegate to `switch.sh` so it stays the single
   source of truth for proxy state and settings persistence:
   - **Non-Anthropic model confirmed** →
     ```bash
     ./switch.sh use deepseek/deepseek-chat
     ```
     Starts the proxy if it's down, sets the sticky server-side override (an
     already-proxied running session switches immediately, no restart), and
     persists `"env": { "ANTHROPIC_BASE_URL": "http://localhost:8787" }` into
     `~/.claude/settings.json` in one step.
   - **Anthropic model confirmed, or user reverts** →
     ```bash
     ./switch.sh off
     ```
     Clears the proxy override and removes `ANTHROPIC_BASE_URL` from
     `~/.claude/settings.json`, restoring direct-to-Anthropic routing.
   - This is the **only** flow allowed to touch `ANTHROPIC_BASE_URL` in
     settings. Never set it at install time, on proxy start, or anywhere else —
     the default base URL stays direct unless the user confirms a switch via
     `/model-switch`.
5. **Say what it applies to** — the settings `env` takes effect for **new**
   sessions; already-running sessions keep the base URL they launched with
   (check with `echo $ANTHROPIC_BASE_URL`; proxied = `http://localhost:8787`).
   If the current session isn't proxied, say the switch is persisted but this
   session keeps its current model until restarted — a plain `claude` launch
   now picks up the proxy automatically. If it is proxied, the switch applies
   immediately.

**Recovery**: if the proxy is down while `ANTHROPIC_BASE_URL` is persisted,
every new session fails to connect. Fix by restarting the proxy, or remove the
`ANTHROPIC_BASE_URL` key from the `env` block in `~/.claude/settings.json` to
go back direct.

Routing precedence in the proxy: in-chat `/model provider/model` text command >
`/switch` override > `provider/` prefix in the request's model field > defaults.

## First-time setup

```bash
cd skills/model-switch
npm install
```

Store API keys in `~/.secrets` (chmod 600):

```bash
cat >> ~/.secrets << 'EOF'
export DEEPSEEK_API_KEY="sk-xxx"
export Z_AI_API_KEY="xxx"
export KIMI_API_KEY="xxx"
export OPENROUTER_API_KEY="sk-or-xxx"
EOF
chmod 600 ~/.secrets
source ~/.secrets
```

## Usage

### 1. Start the proxy

```bash
cd skills/model-switch
./switch.sh start        # sources ~/.secrets, sets NODE_USE_ENV_PROXY=1, backgrounds it
# or manually:
source ~/.secrets && NODE_USE_ENV_PROXY=1 npx tsx proxy.ts
```

`NODE_USE_ENV_PROXY=1` is required: Node's fetch() ignores `http_proxy`/
`https_proxy` by default, and this machine reaches api.anthropic.com only
through the local xray proxy — without it, Anthropic passthrough returns a
region-block 403 that Claude Code misreads as a login failure.

### 2. Launch Claude Code pointed at the proxy

```bash
ANTHROPIC_BASE_URL="http://localhost:8787" claude
```

(Manual export is only needed for ad-hoc runs — confirming a non-Anthropic
model via `/model-switch` persists this variable into `~/.claude/settings.json`
`env`, so a plain `claude` launch routes through the proxy until you revert.)

No API key needed — Anthropic is the default provider and uses your existing
OAuth session (from `claude auth login`) as a passthrough.

### 3. Switch models inside the session

Use Claude Code's built-in `/model` command — it opens a picker populated from
the proxy's `/v1/models` endpoint. Select any entry like `deepseek/deepseek-chat`
and the proxy routes all subsequent requests to that provider. No restart needed.

Available models in the picker:

| ID | Provider |
|----|----------|
| `deepseek/deepseek-chat` | DeepSeek |
| `deepseek/deepseek-reasoner` | DeepSeek R1 |
| `glm/glm-4.6` | z.ai GLM |
| `glm/glm-4.5-air` | z.ai GLM |
| `kimi/moonshot-v1-8k` | Moonshot |
| `kimi/moonshot-v1-32k` | Moonshot |
| `anthropic/claude-sonnet-4-6` | Anthropic (direct) |
| `anthropic/claude-opus-4-7` | Anthropic (direct) |
| `anthropic/claude-haiku-4-5` | Anthropic (direct) |

## Shell shortcuts (optional)

Add to `~/.zshrc`:

```bash
source /data/apps/lidaning-skills/skills/model-switch/shell-setup.sh
```

Then:

```bash
deepseek       # launch Claude via DeepSeek
deepseek-r1    # launch Claude via DeepSeek R1
glm            # launch Claude via GLM (z.ai)
kimi           # launch Claude via Kimi
proxy-status   # show provider configuration status
proxy-logs     # tail proxy output
```

## Environment variables

| Variable           | Default              | Description                       |
|--------------------|----------------------|-----------------------------------|
| `DEFAULT_PROVIDER` | `anthropic`          | Provider when no `/model` command |
| `DEFAULT_MODEL`    | `claude-sonnet-4-6`  | Model when no `/model` command    |
| `PROXY_PORT`       | `8787`               | Proxy listen port                 |

## Adding a provider

Edit the `PROVIDERS` object in `proxy.ts`:

```ts
myProvider: {
  baseUrl: "https://api.xxx.com/anthropic/v1/messages",
  apiKeyEnv: "MY_API_KEY",
},
```

Then `/model myProvider/some-model` works immediately.
