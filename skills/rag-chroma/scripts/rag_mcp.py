#!/usr/bin/env python3
"""Minimal Python client for the rag-mcp server, for unattended callers
(cron, scripts) that have no MCP session of their own.

    from rag_mcp import call
    call("rag_search", {"query": "diffusion models", "k": 3, "collection": "papers"})

Base URL: $RAG_MCP_URL, default http://127.0.0.1:8081. Localhost traffic
bypasses http_proxy. Raises RagError when the server is down or a tool fails.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = (os.environ.get("RAG_MCP_URL") or "http://127.0.0.1:8081").rstrip("/")
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class RagError(RuntimeError):
    pass


def _post(payload, sid=None, timeout=60):
    headers = dict(_HEADERS, **({"mcp-session-id": sid} if sid else {}))
    req = urllib.request.Request(f"{BASE}/mcp", data=json.dumps(payload).encode(),
                                 headers=headers)
    with _opener.open(req, timeout=timeout) as r:
        sid = r.headers.get("mcp-session-id") or sid
        body = r.read().decode()
    # Responses may arrive as SSE: unwrap the "data:" line.
    for line in body.splitlines():
        if line.startswith("data: "):
            body = line[6:]
            break
    return (json.loads(body) if body.strip() else None), sid


def _close(sid):
    """End the session so the server doesn't keep it around."""
    req = urllib.request.Request(f"{BASE}/mcp", method="DELETE",
                                 headers={"mcp-session-id": sid})
    try:
        _opener.open(req, timeout=5).close()
    except (urllib.error.URLError, OSError):
        pass


def call(tool, arguments=None, timeout=60):
    """Call one tool; return its structured result (usually a dict)."""
    try:
        _, sid = _post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "rag_mcp.py", "version": "1"}},
        }, timeout=10)
        if not sid:
            raise RagError(f"MCP initialize failed at {BASE}/mcp")
        try:
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
            r, _ = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": tool, "arguments": arguments or {}}},
                         sid, timeout)
        finally:
            _close(sid)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RagError(f"rag-mcp unreachable at {BASE}: {e}") from e
    if not r:
        raise RagError(f"empty response from {tool}")
    if "error" in r:
        raise RagError(r["error"].get("message", str(r["error"])))
    res = r["result"]
    if res.get("isError"):
        raise RagError(" ".join(c.get("text", "") for c in res.get("content", [])))
    if "structuredContent" in res:
        return res["structuredContent"]
    text = "".join(c.get("text", "") for c in res.get("content", []))
    try:
        return json.loads(text)
    except ValueError:
        return text


if __name__ == "__main__":
    # rag_mcp.py <tool> ['<json arguments>']
    if len(sys.argv) < 2:
        sys.exit("usage: rag_mcp.py <tool> ['<json arguments>']")
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(sys.argv[1], args), ensure_ascii=False, indent=1))
