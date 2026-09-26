#!/usr/bin/env python3
"""Minimal Python client for the headless obsidian-vault MCP container.

For unattended callers (cron, scripts) that have no MCP session of their own.
Same server as `vault-mcp.sh call`; the Obsidian app does not need to run.

    from vault_mcp import call, read_note, write_note
    fm, body = read_note("Tasks.md")
    write_note("Tasks.md", body, frontmatter=fm)

Base URL: $OBSIDIAN_MCP_URL (trailing slash tolerated), default
http://127.0.0.1:27125. Localhost traffic bypasses http_proxy.
"""
import http.client
import json
import os
import subprocess
import urllib.error
import urllib.request

BASE = (os.environ.get("OBSIDIAN_MCP_URL") or "http://127.0.0.1:27125").rstrip("/")
ENSURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault-mcp.sh")
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class VaultError(RuntimeError):
    pass


def _post(payload, sid=None, timeout=60):
    headers = dict(_HEADERS, **({"mcp-session-id": sid} if sid else {}))
    req = urllib.request.Request(
        f"{BASE}/mcp", data=json.dumps(payload).encode(), headers=headers
    )
    with _opener.open(req, timeout=timeout) as r:
        sid = r.headers.get("mcp-session-id") or sid
        try:
            body = r.read().decode()
        except http.client.IncompleteRead as e:
            # supergateway sometimes drops the connection before the final
            # empty chunk; the payload itself has already arrived.
            body = e.partial.decode()
    # Responses may arrive as SSE: unwrap the "data:" line.
    for line in body.splitlines():
        if line.startswith("data: "):
            body = line[6:]
            break
    return (json.loads(body) if body.strip() else None), sid


def _session():
    _, sid = _post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "vault_mcp.py", "version": "1"}},
    }, timeout=10)
    if not sid:
        raise VaultError(f"MCP initialize failed at {BASE}/mcp")
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid


def call(tool, arguments=None):
    """Call one tool; return its text result. Raises VaultError on tool errors."""
    try:
        sid = _session()
    except (urllib.error.URLError, ConnectionError):
        # Container down: start it (same as `vault-mcp.sh ensure`), retry once.
        subprocess.run([ENSURE, "ensure"], check=True, capture_output=True)
        sid = _session()
    # Not retried: a write may already have been applied.
    r, _ = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": tool, "arguments": arguments or {}}}, sid)
    if not r:
        raise VaultError(f"empty response from {tool}")
    if "error" in r:
        raise VaultError(r["error"].get("message", str(r["error"])))
    res = r["result"]
    text = "\n".join(c.get("text", "") for c in res.get("content", []))
    if res.get("isError"):
        raise VaultError(text)
    return text


def exists(path):
    try:
        call("read_note", {"path": path})
        return True
    except VaultError as e:
        if "not found" in str(e).lower():
            return False
        raise


def read_note(path):
    """Return (frontmatter dict, body str)."""
    r = json.loads(call("read_note", {"path": path}))
    return r.get("fm") or {}, r.get("content", "")


def write_note(path, content, frontmatter=None, mode="overwrite"):
    args = {"path": path, "content": content, "mode": mode}
    if frontmatter:
        args["frontmatter"] = frontmatter
    return call("write_note", args)
