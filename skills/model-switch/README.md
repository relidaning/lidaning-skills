# Claude Code Multi-Provider Proxy (TypeScript)

A lightweight local proxy built with **Hono** that lets Claude Code talk to
DeepSeek, GLM, or Kimi. Switch providers inside a running session via the
built-in `/model` picker — no restart needed.

## Stack

- **[Hono](https://hono.dev/)** — ultra-fast web framework, runs on Node
- **tsx** — run TypeScript directly, no build step
- **Node 18+** native `fetch`

## Auth model

The proxy defaults to **Sonnet via your existing `claude auth login` OAuth
session** — no developer API key required. Launching `claude` with
`ANTHROPIC_BASE_URL=http://localhost:8787` lands you on
`anthropic/claude-sonnet-4-6` exactly like a normal Claude Code session,
except you can now `/model`-switch into DeepSeek/GLM/Kimi without restarting.

Do NOT set `ANTHROPIC_API_KEY` — setting it (even to a dummy value)
overrides the OAuth session and triggers a login loop. Leave it unset;
the proxy also stubs any 401/403 Anthropic returns so the loop can't fire.

| Scenario | How to launch |
|---|---|
| Default: Sonnet via OAuth, switchable | `ANTHROPIC_BASE_URL=http://localhost:8787 claude` |
| Land directly on DeepSeek / GLM / Kimi | `deepseek` / `glm` / `kimi` shortcut |
| Bypass proxy entirely | `claude-anthropic` |
| Switch providers mid-session | `/model` picker inside a proxy session |

Setting `ANTHROPIC_API_KEY_REAL` to a real developer API key is optional —
it lets the `anthropic/*` picker entries hit the developer API instead of
OAuth, which gives you access to e.g. `claude-opus-4-7` without a Max
subscription.

## Quick Start

### 1. Install

```bash
cd skills/model-switch
npm install
```

### 2. Set API keys in `~/.secrets` (chmod 600)

```bash
cat >> ~/.secrets << 'EOF'
export DEEPSEEK_API_KEY="sk-xxx"
export Z_AI_API_KEY="xxx"
export KIMI_API_KEY="xxx"
EOF
chmod 600 ~/.secrets
source ~/.secrets
```

### 3. Start the proxy

```bash
cd skills/model-switch
source ~/.secrets && npx tsx proxy.ts
# or via the start script (idempotent, runs in background):
bash scripts/start-proxy.sh
```

### 4. Launch Claude Code via proxy (starts on DeepSeek by default)

```bash
ANTHROPIC_BASE_URL="http://localhost:8787" claude
```

No `ANTHROPIC_API_KEY` needed — you're already logged in via OAuth.

### 5. Switch providers mid-session

Type `/model` in the chat to open the built-in picker. It is populated from
the proxy's `/v1/models` endpoint and shows all configured providers.

Select e.g. `glm/glm-4.6` — the proxy parses the `provider/model` string from
the request and routes accordingly. No restart needed.

> **Note:** typing `/model` as a slash command in Claude Code opens the picker
> UI — it does NOT send a message to the model. The picker is the switching
> mechanism, not in-chat text commands.

## Shell Shortcuts (optional)

```bash
# Add to ~/.zshrc
source /data/apps/lidaning-skills/skills/model-switch/shell-setup.sh
```

Then:

```bash
deepseek        # start claude via DeepSeek
deepseek-r1     # start claude via DeepSeek Reasoner (R1)
glm             # start claude via GLM (z.ai)
kimi            # start claude via Kimi
proxy-start     # start proxy in background
proxy-stop      # stop proxy
proxy-status    # show provider config + key status
proxy-logs      # tail proxy output
```

## Environment Variables

| Variable           | Default              | Description                            |
|--------------------|----------------------|----------------------------------------|
| `DEFAULT_PROVIDER` | `anthropic`          | Provider used at session start         |
| `DEFAULT_MODEL`    | `claude-sonnet-4-6`  | Model used at session start            |
| `PROXY_PORT`       | `8787`               | Port the proxy listens on              |

## Supported Providers

| Key         | Endpoint                                        | Auth env var          |
|-------------|-------------------------------------------------|-----------------------|
| `deepseek`  | `https://api.deepseek.com/anthropic/v1/messages`| `DEEPSEEK_API_KEY`    |
| `glm`       | `https://api.z.ai/api/anthropic/v1/messages`    | `Z_AI_API_KEY`        |
| `kimi`      | `https://api.moonshot.ai/anthropic/v1/messages` | `KIMI_API_KEY`        |
| `anthropic` | `https://api.anthropic.com/v1/messages`         | `ANTHROPIC_API_KEY_REAL` (developer API key only) |

## Adding a Provider

Edit `PROVIDERS` in `proxy.ts`:

```ts
myProvider: {
  baseUrl: "https://api.myprovider.com/anthropic/v1/messages",
  apiKeyEnv: "MY_PROVIDER_API_KEY",
  authStyle: "bearer",           // "bearer", "x-api-key", or "both"
  stripHeaders: ["anthropic-beta"], // headers the provider rejects
},
```

Then `/model myProvider/some-model` works immediately.

## How model routing works

1. Claude Code calls `GET /v1/models` on startup → proxy returns all provider/model pairs
2. User opens `/model` picker → selects e.g. `deepseek/deepseek-chat`
3. Claude Code sends subsequent requests with `body.model = "deepseek/deepseek-chat"`
4. Proxy splits on `/` → `provider=deepseek`, `model=deepseek-chat`
5. Proxy injects DeepSeek API key and forwards to DeepSeek's endpoint
