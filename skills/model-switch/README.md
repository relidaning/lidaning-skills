# Claude Code Multi-Provider Proxy (TypeScript)

A lightweight local proxy built with **Hono** that lets Claude Code talk to
DeepSeek, GLM, or Kimi. Switch providers inside a running session via the
built-in `/model` picker — no restart needed.

## Stack

- **[Hono](https://hono.dev/)** — ultra-fast web framework, runs on Node
- **tsx** — run TypeScript directly, no build step
- **Node 18+** native `fetch`

## Auth model (important)

The proxy is designed for **non-Anthropic providers only**. Claude Code's
OAuth/subscription session token is NOT a valid Anthropic developer API key.
Forwarding that token to `api.anthropic.com` returns 403 — the two auth
systems are separate.

| Scenario | How to launch |
|---|---|
| Use Anthropic (Sonnet/Opus) | `claude` (normal, no proxy) |
| Use DeepSeek / GLM / Kimi | `ANTHROPIC_BASE_URL=http://localhost:8787 claude` |
| Switch providers mid-session | `/model` picker inside a proxy session |

You cannot switch between Anthropic and other providers in the same session
unless you have a separate Anthropic developer API key (set as
`ANTHROPIC_API_KEY_REAL`).

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

| Variable           | Default         | Description                            |
|--------------------|-----------------|----------------------------------------|
| `DEFAULT_PROVIDER` | `deepseek`      | Provider used at session start         |
| `DEFAULT_MODEL`    | `deepseek-chat` | Model used at session start            |
| `PROXY_PORT`       | `8787`          | Port the proxy listens on              |

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
