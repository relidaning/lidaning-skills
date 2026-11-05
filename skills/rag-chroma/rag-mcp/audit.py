"""Daily JSON-lines audit trail shared by HTTP, MCP and background indexing."""
import contextvars
import functools
import inspect
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(os.getenv("RAG_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs")))
_lock = threading.Lock()
_call_id = contextvars.ContextVar("rag_call_id", default=None)
TOOLS = {}


def event(kind, **details):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    row = {"timestamp": now.isoformat(timespec="milliseconds"), "event": kind,
           "call_id": _call_id.get(), **details}
    with _lock, (LOG_DIR / f"{now:%Y-%m-%d}.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def audited(fn):
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        arguments = signature.bind(*args, **kwargs)
        arguments.apply_defaults()
        params = dict(arguments.arguments)
        # Ingest logs IDs/counts, never another full copy of every document.
        if "documents" in params:
            docs = params.pop("documents")
            params["document_ids"] = [d.get("id") for d in docs]
        token = _call_id.set(uuid.uuid4().hex)
        started = time.monotonic()
        try:
            event("tool_start", tool=fn.__name__, arguments=params)
            result = await fn(*args, **kwargs)
            hits = result.get("results", result.get("chunks", result.get("items", [])))
            event("tool_end", tool=fn.__name__, duration_ms=round((time.monotonic()-started)*1000, 2),
                  status="partial" if result.get("errors") or result.get("error") else "ok",
                  retrieved=[{k: h[k] for k in ("id", "metadata", "source", "score", "match") if k in h}
                             for h in hits],
                  summary={k: result[k] for k in ("count", "ingested", "removed", "cleared", "errors", "error") if k in result})
            return result
        except Exception as exc:
            event("tool_error", tool=fn.__name__, error=str(exc),
                  duration_ms=round((time.monotonic()-started)*1000, 2))
            raise
        finally:
            _call_id.reset(token)

    TOOLS[fn.__name__] = wrapped
    return wrapped


def read_events(day="", limit=100):
    day = day or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(day, "%Y-%m-%d")
    if len(day) != 10:
        raise ValueError("date must be YYYY-MM-DD")
    path = LOG_DIR / f"{day}.log"
    rows = []
    if path.exists():
        with _lock, path.open(encoding="utf-8") as f:
            for line in deque(f, maxlen=max(1, min(limit, 1000))):
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return {"date": day, "events": list(reversed(rows)), "file": str(path)}
