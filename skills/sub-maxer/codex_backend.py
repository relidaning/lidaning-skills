"""Codex CLI adapters. Quota reads never create a thread or start a model turn."""
import json
import math
import os
import queue
import subprocess
import threading
import time
import tomllib
from pathlib import Path


class CodexError(ValueError):
    pass


def read_rate_limits(timeout=45):
    """Use the authenticated CLI, keeping stdin open through both replies."""
    proc = subprocess.Popen(
        ["codex", "app-server", "--listen", "stdio://",
         "-c", 'forced_login_method="chatgpt"'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True,
    )
    messages = queue.Queue()

    def reader():
        for line in proc.stdout:
            messages.put(line)
        messages.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def reply(request_id):
        while True:
            try:
                line = messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise CodexError("Codex quota read timed out") from None
            if line is None:
                raise CodexError("Codex app-server closed before the quota reply")
            try:
                message = json.loads(line)
            except ValueError:
                raise CodexError("Invalid Codex app-server response") from None
            if message.get("id") != request_id:
                continue
            if "error" in message:
                # Do not echo raw upstream errors: they can contain account data.
                raise CodexError("Codex quota request rejected; check ChatGPT CLI login")
            if not isinstance(message.get("result"), dict):
                raise CodexError("Missing Codex quota result")
            return message["result"]

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "lidaning_maxer", "version": "1.0.0"}}})
        reply(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "account/rateLimits/read"})
        return reply(2)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        thread.join(timeout=1)
        proc.stdin.close()
        proc.stdout.close()


def normalize_usage(result, now=None, limit_id="codex"):
    """Match by duration, never assume primary means 5h or secondary means 7d.

    The scheduler implements 5h/7d budgets. Other plans/windows fail closed.
    A null reset is accepted only for a known, unused window.
    """
    now = time.time() if now is None else now
    buckets = result.get("rateLimitsByLimitId")
    if buckets is not None:
        if not isinstance(buckets, dict):
            raise CodexError("Invalid Codex quota buckets")
        bucket = buckets.get(limit_id)
    else:
        bucket = result.get("rateLimits")
        if isinstance(bucket, dict) and bucket.get("limitId") not in (None, limit_id):
            bucket = None
    if not isinstance(bucket, dict):
        raise CodexError(f"Codex quota bucket {limit_id!r} unavailable")
    windows = {}
    for name in ("primary", "secondary"):
        window = bucket.get(name)
        if isinstance(window, dict):
            windows[window.get("windowDurationMins")] = window
    out = {"age": 0}
    for duration, prefix in ((300, "five"), (10080, "seven")):
        window = windows.get(duration)
        if not window:
            raise CodexError(f"Codex {duration}-minute quota window unavailable")
        used, reset = window.get("usedPercent"), window.get("resetsAt")
        if (isinstance(used, bool) or not isinstance(used, (int, float))
                or not math.isfinite(used) or not 0 <= used <= 100):
            raise CodexError("Invalid Codex usage percentage")
        if reset is not None and (isinstance(reset, bool)
                or not isinstance(reset, (int, float)) or not math.isfinite(reset)
                or reset <= now):
            raise CodexError("Codex returned an expired or invalid reset; retry later")
        if reset is None and used != 0:
            raise CodexError("Codex returned usage without a reset")
        out[prefix + "_pct"], out[prefix + "_reset"] = used, reset
    return out


def news_tool_overrides():
    """Disable configured MCP/plugin tools as well as shell/app tools for news.

    Inspect config locally rather than starting MCP services to enumerate them.
    Command-line values override user and project configuration layers.
    """
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    paths = {home / "config.toml"}
    cwd = Path.home() / ".claude/state/claude-maxer-work"
    paths.update(p / ".codex/config.toml" for p in (cwd, *cwd.parents))
    servers, plugins = set(), set()

    def collect(config):
        servers.update(config.get("mcp_servers", {}))
        plugins.update(config.get("plugins", {}))
        for profile in config.get("profiles", {}).values():
            if isinstance(profile, dict):
                collect(profile)

    for path in paths:
        if path.exists():
            with path.open("rb") as f:
                collect(tomllib.load(f))
    overrides = ["--disable", "shell_tool", "--disable", "apps", "--disable", "multi_agent",
                 "--disable", "hooks"]
    for table, names in (("mcp_servers", servers), ("plugins", plugins)):
        for name in sorted(names):
            overrides += ["-c", f"{table}.{json.dumps(name)}.enabled=false"]
    return overrides


def worker_command(prompt, model="", news=False):
    # Queue model IDs belong to Claude. Use only an explicitly configured Codex
    # model, otherwise let the authenticated CLI's configured default apply.
    command = ["codex", "exec", "--json", "--skip-git-repo-check",
               "--color", "never", "-c", 'approval_policy="never"',
               "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
               "--sandbox", "read-only" if news else "workspace-write"]
    if news:
        prompt = ("Use web search and fetch only. Do not run shell commands, write files, "
                  "or call MCP tools. Return the requested content in your final reply.\n\n" + prompt)
        command += ["-c", 'web_search="live"', *news_tool_overrides()]
    else:
        command += ["--add-dir", "/data/apps", "-c", "sandbox_workspace_write.network_access=true"]
    if model:
        command += ["--model", model]
    return command + [prompt]


def parse_output(process):
    """Adapt JSONL into the small result/modelUsage interface maxer consumes."""
    reply, usage, complete, failed = [], {}, False, process.returncode != 0
    for line in process.stdout.splitlines():
        event = json.loads(line)
        kind = event.get("type")
        if kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            reply.append(event["item"].get("text", ""))
        elif kind == "turn.completed":
            complete, usage = True, event.get("usage") or {}
        elif kind in ("turn.failed", "error"):
            failed = True
    if failed or not complete or not reply:
        raise CodexError(f"Codex worker failed (exit {process.returncode}) or returned no completed reply")
    cached = int(usage.get("cached_input_tokens") or 0)
    return {"result": "\n".join(reply), "modelUsage": {"codex": {
        "inputTokens": max(0, int(usage.get("input_tokens") or 0) - cached),
        "cacheReadInputTokens": cached,
        "outputTokens": int(usage.get("output_tokens") or 0),
    }}}
