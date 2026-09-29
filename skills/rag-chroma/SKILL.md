---
name: rag-chroma
description: >
  Activate when user asks to search documents by meaning, ingest content
  (PDFs/URLs/notes/Word/Excel), query the knowledge base, or manage the RAG
  index. ChromaDB + ONNX semantic search pipeline with Obsidian vault sync.
---

## When to activate

Invoke this skill when:
- User asks to search for information by meaning or semantic similarity
- User wants to ingest content (PDF, URL, markdown, Word, Excel)
- User asks "what do my documents say about X?" or similar
- User wants to check RAG index status or remove documents
- User wants to load Obsidian vault notes into the search index

## Overview

- **ChromaDB** (Docker, port 8000) — vector database
- **rag-mcp** (Docker, port 8081) — FastMCP HTTP server, all-MiniLM-L6-v2 ONNX embeddings

## Prerequisites

```bash
docker compose -f skills/rag-chroma/docker-compose.yml up -d
```

The vault is read from disk: `docker-compose.yml` bind-mounts
`${OBSIDIAN_VAULT_PATH:-/data/nextcloud_client/obsidian/lidaning}` read-only at `/vault`:
the same folder, under the same variable, that obsidian-local's `obsidian-vault-mcp`
container serves. No Obsidian app, REST API or token is needed. `rag_answer` additionally requires `LLM_API_KEY` set in `docker-compose.yml`'s environment
(it raises at call time if unset) — `LLM_BASE_URL` (default: OpenAI) and `LLM_MODEL`
(default `gpt-4o-mini`) are optional overrides for a non-OpenAI-compatible backend.

## MCP tools

| Tool | Purpose |
|---|---|
| `rag_load(doc_id?)` | Load vault notes into the index. No arg = all notes recursively; pass a vault-relative path for one note. |
| `rag_search(query, k, collection?)` | Semantic search — returns `[{id, metadata, score, snippet}]` |
| `rag_answer(query, k=4)` | Retrieve top-k chunks and generate a grounded, cited answer via an LLM — returns `{answer, sources, chunks}`. Use this instead of `rag_search` when the user wants a synthesized answer, not raw snippets. Requires `LLM_API_KEY` (see Prerequisites). |
| `rag_ingest(documents, collection?)` | Embed and store arbitrary text — accepts `[{id, content, metadata}]` |
| `rag_list(collection, limit?)` | Every entry's `{id, metadata}` in a small collection (not for the vault index) |
| `rag_status()` | Doc count per collection, tracked files, watch interval |
| `rag_remove(doc_id, collection?)` | Remove a single chunk by ID |
| `rag_clear()` | Wipe the vault index (irreversible) |

`collection` defaults to `documents`, the vault index. Other collections hold
data that isn't vault notes and are never touched by the watcher:

| Collection | Owner | Contents |
|---|---|---|
| `papers` | claude-maxer's daily Papers task | One entry per proposed paper; id `arxiv:<id>` or the bare URL; metadata `title, url, source, date, proposed, kind` (`recent`/`foundational`) |

To answer "which papers have you proposed about X?", `rag_search` with
`collection: "papers"`; to list them all, `rag_list`.

Unattended scripts with no MCP session use `scripts/rag_mcp.py` (`call(tool, args)`,
or `rag_mcp.py <tool> '<json>'` from a shell).

## Vault watcher

The server watches the vault folder on disk (default every 60 seconds). A note
whose mtime hasn't changed isn't even read; skipped or failed notes are logged
as warnings (`docker logs rag-chroma-rag-mcp-1`), not swallowed:

- **Modified note** → remove stale chunks, re-index with updated content
- **Deleted note** → remove all its chunks from ChromaDB
- **New note** → index immediately on next tick

Change detection uses MD5 content hashing. Signatures are stored in ChromaDB
metadata so state survives container restarts without a full re-index.

To change the interval: set `WATCH_INTERVAL=<seconds>` in `docker-compose.yml`.

## Architecture

```
docker compose up
  ├── chromadb :8000              (vector store)
  └── rag-mcp  :8081              (FastMCP HTTP)
       ├── ONNX all-MiniLM-L6-v2  (embeddings, pre-cached at build)
       ├── ChromaDB HttpClient     (store/query)
       ├── vault watcher          (scans /vault on disk every 60s)
       └── GET /health            (Docker healthcheck; opens no MCP session)
```
