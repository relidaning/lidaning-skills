#!/usr/bin/env node
/**
 * Claude Code Multi-Provider Proxy (TypeScript)
 *
 * Usage:
 *   npx tsx proxy.ts
 *
 * Then in another terminal:
 *   export ANTHROPIC_BASE_URL="http://localhost:8787"
 *   claude
 */

import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ProviderConfig {
  baseUrl: string;
  apiKeyEnv: string;
  authStyle: "bearer" | "x-api-key" | "both";
  stripHeaders?: string[];
}

interface Message {
  role: "user" | "assistant";
  content: string | ContentBlock[];
}

interface ContentBlock {
  type: string;
  text?: string;
}

interface AnthropicRequest {
  model: string;
  messages: Message[];
  stream?: boolean;
  max_tokens?: number;
  [key: string]: unknown;
}

// ─── Provider Registry ────────────────────────────────────────────────────────

const PROVIDERS: Record<string, ProviderConfig> = {
  anthropic: {
    baseUrl: "https://api.anthropic.com/v1/messages",
    apiKeyEnv: "ANTHROPIC_API_KEY_REAL", // requires a real API key, not OAuth session token
    authStyle: "x-api-key",
  },
  deepseek: {
    baseUrl: "https://api.deepseek.com/anthropic/v1/messages",
    apiKeyEnv: "DEEPSEEK_API_KEY",
    authStyle: "bearer",
    stripHeaders: ["anthropic-beta"],
  },
  glm: {
    baseUrl: "https://api.z.ai/api/anthropic/v1/messages",
    apiKeyEnv: "Z_AI_API_KEY",
    authStyle: "both",
    stripHeaders: ["anthropic-beta"],
  },
  kimi: {
    baseUrl: "https://api.moonshot.ai/anthropic/v1/messages",
    apiKeyEnv: "KIMI_API_KEY",
    authStyle: "bearer",
    stripHeaders: ["anthropic-beta"],
  },
};

// ─── Config ───────────────────────────────────────────────────────────────────

const DEFAULT_PROVIDER = process.env.DEFAULT_PROVIDER ?? "anthropic";
const DEFAULT_MODEL = process.env.DEFAULT_MODEL ?? "claude-sonnet-4-6";
const PORT = Number(process.env.PROXY_PORT ?? 8787);

// Server-side model override, set via POST /switch. While active it wins over
// the model name in incoming requests, so a running session can be switched
// from outside (e.g. by the model-switch skill) without touching the client.
//
// Persisted to STATE_FILE so a proxy restart keeps routing to the switched
// provider — otherwise settings.json would still point sessions at the proxy
// while the proxy silently fell back to Anthropic (and its rate limit).
const STATE_FILE = `${process.env.HOME}/.claude/state/model-switch.json`;

let switchOverride: { provider: string; model: string } | null = null;
try {
  const saved = JSON.parse(readFileSync(STATE_FILE, "utf8"));
  if (saved?.provider && saved?.model) {
    switchOverride = { provider: saved.provider, model: saved.model };
    console.log(`⚡ Restored override from state: ${saved.provider}/${saved.model}`);
  }
} catch {
  // no state file yet — start with no override
}

function persistOverride() {
  try {
    mkdirSync(dirname(STATE_FILE), { recursive: true });
    writeFileSync(STATE_FILE, JSON.stringify(switchOverride ?? {}, null, 2));
  } catch (err) {
    console.error(`✗ Failed to persist override to ${STATE_FILE}:`, err);
  }
}

// Headers Claude Code sends that we should never forward upstream
const ALWAYS_STRIP = new Set([
  "host",
  "content-length",
  "transfer-encoding",
  "connection",
]);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildUpstreamHeaders(
  incoming: Headers,
  config: ProviderConfig,
): Record<string, string> {
  const out: Record<string, string> = {};

  const providerStrip = new Set(
    (config.stripHeaders ?? []).map((h) => h.toLowerCase()),
  );

  const apiKey = process.env[config.apiKeyEnv];
  if (!apiKey) throw new Error(`env var ${config.apiKeyEnv} is not set`);

  incoming.forEach((val, key) => {
    const lower = key.toLowerCase();
    if (ALWAYS_STRIP.has(lower)) return;
    if (lower === "authorization") return;
    if (lower === "x-api-key") return;
    if (lower === "content-type") return; // set explicitly below; copying too duplicates the header
    if (providerStrip.has(lower)) return;
    out[key] = val;
  });

  if (config.authStyle === "bearer" || config.authStyle === "both") {
    out["Authorization"] = `Bearer ${apiKey}`;
  }
  if (config.authStyle === "x-api-key" || config.authStyle === "both") {
    out["x-api-key"] = apiKey;
  }

  out["Content-Type"] = "application/json";
  return out;
}

/**
 * Parses `/model <provider>/<model>` from the last user message.
 * Mutates `messages` in-place to strip the command.
 */
function parseModelCommand(messages: Message[]): [string, string] | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== "user") continue;

    const text =
      typeof msg.content === "string"
        ? msg.content
        : (msg.content as ContentBlock[])
            .filter((b) => b.type === "text")
            .map((b) => b.text ?? "")
            .join("");

    const trimmed = text.trim();
    if (!trimmed.startsWith("/model ")) continue;

    const token = trimmed.split(/\s+/)[1] ?? "";
    if (!token.includes("/")) continue;

    const slash = token.indexOf("/");
    const provider = token.slice(0, slash);
    const model = token.slice(slash + 1);

    // Strip command from message
    const cleaned = trimmed.replace(`/model ${token}`, "").trim();
    if (cleaned) {
      if (typeof msg.content === "string") {
        messages[i] = { ...msg, content: cleaned };
      } else {
        messages[i] = {
          ...msg,
          content: (msg.content as ContentBlock[]).map((b) =>
            b.type === "text"
              ? { ...b, text: b.text?.replace(`/model ${token}`, "").trim() }
              : b,
          ),
        };
      }
    } else if (messages.length > 1) {
      messages.splice(i, 1);
    } else {
      messages[i] = { ...msg, content: "continue" };
    }

    return [provider, model];
  }
  return null;
}

// ─── App ──────────────────────────────────────────────────────────────────────

const app = new Hono();

app.use("*", async (c, next) => {
  const start = Date.now();
  await next();
  const ms = Date.now() - start;
  console.log(`${c.req.method} ${c.req.path} → ${c.res.status} (${ms}ms)`);
});

app.get("/health", (c) =>
  c.json({
    status: "ok",
    providers: Object.keys(PROVIDERS),
    port: PORT,
    override: switchOverride
      ? `${switchOverride.provider}/${switchOverride.model}`
      : null,
  }),
);

// ── /switch — server-side model override ──────────────────────────────────────
app.get("/switch", (c) =>
  c.json({
    override: switchOverride
      ? `${switchOverride.provider}/${switchOverride.model}`
      : null,
  }),
);

app.post("/switch", async (c) => {
  let body: { model?: string };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400);
  }
  const token = body.model ?? "";
  const slash = token.indexOf("/");
  if (slash <= 0 || slash === token.length - 1) {
    return c.json({ error: 'Expected {"model": "<provider>/<model>"}' }, 400);
  }
  const provider = token.slice(0, slash);
  const model = token.slice(slash + 1);
  if (!PROVIDERS[provider]) {
    const msg = `Unknown provider "${provider}". Available: ${Object.keys(PROVIDERS).join(", ")}`;
    return c.json({ error: msg }, 400);
  }
  switchOverride = { provider, model };
  persistOverride();
  console.log(`⚡ Switch override → ${provider}/${model}`);
  return c.json({ override: `${provider}/${model}` });
});

app.delete("/switch", (c) => {
  switchOverride = null;
  persistOverride();
  console.log("⚡ Switch override cleared");
  return c.json({ override: null });
});

app.get("/providers", (c) =>
  c.json(
    Object.entries(PROVIDERS).map(([key, cfg]) => ({
      key,
      baseUrl: cfg.baseUrl,
      keyConfigured: Boolean(process.env[cfg.apiKeyEnv]),
    })),
  ),
);

/**
 * GET /v1/models — feeds Claude Code's built-in /model picker.
 * Anthropic models listed first so they appear at the top.
 */
app.get("/v1/models", (c) => {
  const models = [
    // Anthropic (passthrough — uses your OAuth token)
    { id: "anthropic/claude-sonnet-4-6", object: "model", owned_by: "anthropic" },
    { id: "anthropic/claude-opus-4-7", object: "model", owned_by: "anthropic" },
    { id: "anthropic/claude-haiku-4-5", object: "model", owned_by: "anthropic" },
    // DeepSeek
    { id: "deepseek/deepseek-chat", object: "model", owned_by: "deepseek" },
    { id: "deepseek/deepseek-reasoner", object: "model", owned_by: "deepseek" },
    // GLM
    { id: "glm/glm-4.6", object: "model", owned_by: "z.ai" },
    { id: "glm/glm-4.5-air", object: "model", owned_by: "z.ai" },
    // Kimi
    { id: "kimi/moonshot-v1-8k", object: "model", owned_by: "moonshot" },
    { id: "kimi/moonshot-v1-32k", object: "model", owned_by: "moonshot" },
  ];
  return c.json({ object: "list", data: models });
});

// ── POST /v1/messages ──────────────────────────────────────────────────────────
app.post("/v1/messages", async (c) => {
  let body: AnthropicRequest;
  try {
    body = await c.req.json<AnthropicRequest>();
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  // Determine provider + model
  let providerKey = DEFAULT_PROVIDER;
  let modelName = body.model ?? DEFAULT_MODEL;

  // Parse "provider/model" from body.model (set by Claude Code's built-in /model picker)
  if (modelName.includes("/")) {
    const slash = modelName.indexOf("/");
    const parsedProvider = modelName.slice(0, slash);
    if (PROVIDERS[parsedProvider]) {
      providerKey = parsedProvider;
      modelName = modelName.slice(slash + 1);
    }
  }

  // Precedence: in-chat /model command > /switch override > body.model prefix
  if (switchOverride) {
    providerKey = switchOverride.provider;
    modelName = switchOverride.model;
  }

  const cmd = parseModelCommand(body.messages);
  if (cmd) {
    [providerKey, modelName] = cmd;
    console.log(`⚡ Switch → ${providerKey}/${modelName}`);
  }

  const config = PROVIDERS[providerKey];
  if (!config) {
    const msg = `Unknown provider "${providerKey}". Available: ${Object.keys(PROVIDERS).join(", ")}`;
    console.error(msg);
    return c.json({ error: msg }, 400);
  }

  body.model = modelName;

  // OAuth passthrough: when routing to anthropic without a developer key,
  // forward the user's existing auth headers (OAuth bearer) straight through.
  if (providerKey === "anthropic" && !process.env.ANTHROPIC_API_KEY_REAL) {
    const headers: Record<string, string> = {};
    c.req.raw.headers.forEach((val, key) => {
      if (!ALWAYS_STRIP.has(key.toLowerCase())) headers[key] = val;
    });
    const authHdr = c.req.raw.headers.get("authorization") ?? "";
    const apiKeyHdr = c.req.raw.headers.get("x-api-key") ?? "";
    const authSummary = authHdr
      ? `authorization=${authHdr.slice(0, 12)}…(${authHdr.length})`
      : apiKeyHdr
        ? `x-api-key=${apiKeyHdr.slice(0, 6)}…(${apiKeyHdr.length})`
        : "NO_AUTH_HEADER";
    console.log(`→ [anthropic-oauth] ${modelName} stream=${body.stream ?? false} ${authSummary}`);

    let upstream: Response;
    try {
      upstream = await fetch(config.baseUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
    } catch (err) {
      console.error(`✗ Network error reaching ${config.baseUrl}:`, err);
      return c.json({ error: `Proxy network error: ${String(err)}` }, 502);
    }

    if (!upstream.ok) {
      const errText = await upstream.text();
      console.error(`✗ anthropic-oauth upstream ${upstream.status}: ${errText.slice(0, 400)}`);
      return new Response(errText, {
        status: upstream.status,
        headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
      });
    }

    if (body.stream && upstream.body) {
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": upstream.headers.get("content-type") ?? "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
      });
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  let upstreamHeaders: Record<string, string>;
  try {
    upstreamHeaders = buildUpstreamHeaders(c.req.raw.headers, config);
  } catch (err) {
    console.error(err);
    return c.json({ error: (err as Error).message }, 500);
  }


  console.log(`→ [${providerKey}] ${modelName}  stream=${body.stream ?? false}`);
  console.log(`  url: ${config.baseUrl}`);

  let upstream: Response;
  try {
    upstream = await fetch(config.baseUrl, {
      method: "POST",
      headers: upstreamHeaders,
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.error(`✗ Network error reaching ${config.baseUrl}:`, err);
    return c.json({ error: `Proxy network error: ${String(err)}` }, 502);
  }

  if (!upstream.ok) {
    const errText = await upstream.text();
    console.error(`✗ ${providerKey} returned ${upstream.status}:`);
    console.error(errText);
    return new Response(errText, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  }

  if (body.stream && upstream.body) {
    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  const data = await upstream.json();
  return c.json(data);
});

// ── Catch-all: forward anything else to Anthropic with original auth ──────────
// Handles session verification, OAuth token checks, and any other endpoints
// Claude Code calls that are not /v1/messages or /v1/models.
//
// If Anthropic returns an error (401/403 = no valid OAuth; 429 = rate limited;
// 5xx = unavailable), we stub a 200 so Claude Code stays functional and
// /v1/messages still routes to the configured provider. Without this, a rate
// limit or outage on Anthropic prevents Claude Code from starting at all, even
// when the user is routing through a non-Anthropic provider.
app.all("*", async (c) => {
  const rawUrl = c.req.url;
  const queryString = rawUrl.includes("?") ? "?" + rawUrl.split("?").slice(1).join("?") : "";
  const url = `https://api.anthropic.com${c.req.path}${queryString}`;

  const headers: Record<string, string> = {};
  c.req.raw.headers.forEach((val, key) => {
    if (!ALWAYS_STRIP.has(key.toLowerCase())) headers[key] = val;
  });

  const body =
    c.req.method !== "GET" && c.req.method !== "HEAD"
      ? await c.req.raw.arrayBuffer()
      : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(url, { method: c.req.method, headers, body });
  } catch (err) {
    console.log(`→ [passthrough-stub] ${c.req.method} ${c.req.path} (upstream unreachable)`);
    return c.json({}, 200);
  }

  if (!upstream.ok) {
    console.log(`→ [passthrough-stub] ${c.req.method} ${c.req.path} (upstream ${upstream.status})`);
    return c.json({}, 200);
  }

  console.log(`→ [passthrough] ${c.req.method} ${c.req.path} → ${upstream.status}`);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: Object.fromEntries(upstream.headers.entries()),
  });
});

// ─── Start ────────────────────────────────────────────────────────────────────

const providerStatus = Object.entries(PROVIDERS)
  .map(([k, v]) => `  ${process.env[v.apiKeyEnv] ? "✓" : "✗"} ${k} (${v.apiKeyEnv})`)
  .join("\n");

serve({ fetch: app.fetch, port: PORT }, () => {
  console.log(`
╔══════════════════════════════════════════════╗
║   Claude Code Multi-Provider Proxy  (TS)    ║
╠══════════════════════════════════════════════╣
║  Listening: http://localhost:${PORT}              ║
╚══════════════════════════════════════════════╝

Providers:
${providerStatus}

Default: ${DEFAULT_PROVIDER} / ${DEFAULT_MODEL}

Launch Claude Code:
  ANTHROPIC_BASE_URL="http://localhost:${PORT}" claude

Switch providers inside the session via the built-in /model picker.
`);
});
