"""Reads the vault through the obsidian-vault MCP server (obsidian-local).

rag-mcp used to read the vault folder from disk. Going through the server
instead means rag sees exactly what the server exposes, whatever rules the
server applies, without knowing about them.

One MCP session is kept open and reused; any error or timeout drops it
(closing it, so supergateway doesn't keep a child process per stale session)
and the next call opens a new one. The server's sessions have been seen to
hang while its /healthz stays OK, hence the short timeout.
"""

import json
import logging
import os
import threading

import httpx

URL = os.getenv("VAULT_MCP_URL", "http://127.0.0.1:27125/mcp")
TIMEOUT = float(os.getenv("VAULT_MCP_TIMEOUT", "30"))
BATCH = 10  # read_multiple_notes accepts at most 10 paths

_log = logging.getLogger(__name__)


class VaultError(RuntimeError):
    pass


class VaultClient:
    def __init__(self, url: str = URL):
        self.url = url
        self._http = httpx.Client(timeout=TIMEOUT, trust_env=False)
        self._sid = None
        self._lock = threading.Lock()  # the watcher thread and tool calls share it
        self._id = 0

    # -- transport ---------------------------------------------------------

    def _post(self, payload: dict, sid=None) -> httpx.Response:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if sid:
            headers["mcp-session-id"] = sid
        return self._http.post(self.url, json=payload, headers=headers)

    @staticmethod
    def _body(resp: httpx.Response) -> dict:
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            for line in resp.text.splitlines():
                if line.startswith("data: "):
                    return json.loads(line[6:])
            raise VaultError("empty event stream")
        return resp.json()

    def _session(self) -> str:
        if self._sid:
            return self._sid
        resp = self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "rag-mcp", "version": "1"}}})
        sid = resp.headers.get("mcp-session-id")
        if resp.status_code != 200 or not sid:
            raise VaultError(f"initialize failed: HTTP {resp.status_code}")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        self._sid = sid
        return sid

    def _drop(self):
        if self._sid:
            try:
                self._http.delete(self.url, headers={"mcp-session-id": self._sid}, timeout=5)
            except Exception:
                pass
        self._sid = None

    def close(self):
        with self._lock:
            self._drop()

    def call(self, tool: str, args: dict):
        """Call one tool; returns its JSON result. Raises VaultError."""
        with self._lock:
            for attempt in (1, 2):  # a restarted server invalidates the session once
                try:
                    self._id += 1
                    resp = self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                                       "params": {"name": tool, "arguments": args}}, self._session())
                    if resp.status_code in (400, 404) and attempt == 1:
                        self._drop()
                        continue
                    msg = self._body(resp)
                except (httpx.HTTPError, ValueError, VaultError) as e:
                    self._drop()
                    if attempt == 2:
                        raise VaultError(f"{tool}: {e}") from e
                    continue
                if "error" in msg:
                    raise VaultError(f"{tool}: {msg['error'].get('message', msg['error'])}")
                result = msg["result"]
                text = "\n".join(c.get("text", "") for c in result.get("content", []))
                if result.get("isError"):
                    raise VaultError(f"{tool}: {text[:300]}")
                return json.loads(text)
        raise VaultError(f"{tool}: no response")

    # -- vault operations --------------------------------------------------

    def list_notes(self) -> list[str]:
        """Every .md note the server exposes, as vault-relative paths."""
        notes, todo = [], [""]
        while todo:
            d = todo.pop()
            got = self.call("list_directory", {"path": d})
            prefix = f"{d}/" if d else ""
            notes += [prefix + f for f in got.get("files", []) if f.endswith(".md")]
            todo += [prefix + sub for sub in got.get("dirs", [])]
        return sorted(notes)

    def mtimes(self, paths: list[str]) -> dict[str, float]:
        out = {}
        for i in range(0, len(paths), 100):
            for info in self.call("get_notes_info", {"paths": paths[i:i + 100]}):
                out[info["path"]] = info["modified"]
        return out

    def read(self, paths: list[str]) -> dict[str, dict]:
        """{path: {"content", "frontmatter"}} for the paths the server let us read."""
        out = {}
        for i in range(0, len(paths), BATCH):
            got = self.call("read_multiple_notes", {"paths": paths[i:i + BATCH]})
            for note in got.get("ok", []):
                out[note["path"]] = {"content": note.get("content", ""),
                                     "frontmatter": note.get("frontmatter") or {}}
            for err in got.get("err", []) or []:
                _log.warning("read failed: %s", err)
        return out
