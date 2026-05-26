---
name: model-switch
description: >
  Multi-provider LLM proxy for Claude Code. Route requests to DeepSeek, GLM, Kimi,
  Anthropic, or OpenRouter. Switch models mid-session with /model provider/model-name.
  Includes shell shortcuts for launching Claude with different backends.
---

# Model Switch Proxy

A local Hono proxy that sits between Claude Code and any Anthropic-compatible LLM
provider. Switch models inside a running session without restarting.

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
source ~/.secrets && npx tsx proxy.ts
```

### 2. Launch Claude Code pointed at the proxy

```bash
ANTHROPIC_BASE_URL="http://localhost:8787" claude
```

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
| `anthropic/claude-opus-4-6` | Anthropic (direct) |

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
