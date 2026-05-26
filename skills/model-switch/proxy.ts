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

const DEFAULT_PROVIDER = process.env.DEFAULT_PROVIDER ?? "deepseek";
const DEFAULT_MODEL = process.env.DEFAULT_MODEL ?? "deepseek-chat";
const PORT = Number(process.env.PROXY_PORT ?? 8787);

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
  c.json({ status: "ok", providers: Object.keys(PROVIDERS), port: PORT }),
);

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
  // Anthropic via proxy only when the user opted in with a developer key.
  if (process.env.ANTHROPIC_API_KEY_REAL) {
    models.unshift(
      { id: "anthropic/claude-sonnet-4-6", object: "model", owned_by: "anthropic" },
      { id: "anthropic/claude-opus-4-7", object: "model", owned_by: "anthropic" },
      { id: "anthropic/claude-haiku-4-5", object: "model", owned_by: "anthropic" },
    );
  }
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

  // The anthropic provider requires a developer API key (ANTHROPIC_API_KEY_REAL).
  // OAuth subscription tokens cannot be relayed via a custom base URL — Anthropic
  // returns 403. Users who want Sonnet on their subscription should bypass the
  // proxy entirely (use the `sonnet` shortcut).
  if (providerKey === "anthropic" && !process.env.ANTHROPIC_API_KEY_REAL) {
    return c.json(
      {
        error: {
          type: "configuration",
          message:
            "anthropic via proxy needs ANTHROPIC_API_KEY_REAL (a developer API key). " +
            "For subscription Sonnet/Opus, launch claude without the proxy (see the `sonnet` shortcut).",
        },
      },
      501,
    );
  }

  body.model = modelName;

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
// If Anthropic returns 401/403 (user is on DeepSeek-only, no valid OAuth, or
// ANTHROPIC_API_KEY is dummy), we stub a 200 so Claude Code doesn't drop into
// a login loop. /v1/messages still hits the configured provider directly.
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

  if (upstream.status === 401 || upstream.status === 403) {
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
