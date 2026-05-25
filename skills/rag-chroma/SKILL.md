---
name: rag-chroma
description: >
  RAG pipeline backed by ChromaDB and ONNX embeddings, with Obsidian vault
  integration. Load vault notes into the index, search by meaning, and keep
  the index automatically in sync as notes are created, modified, or deleted.
---

## Overview

- **ChromaDB** (Docker, port 8000) — vector database
- **rag-mcp** (Docker, port 8081) — FastMCP HTTP server, all-MiniLM-L6-v2 ONNX embeddings

## Prerequisites

```bash
docker compose -f skills/rag-chroma/docker-compose.yml up -d
```

Requires `OBSIDIAN_MCP_TOKEN` in the shell environment (Obsidian Local REST API plugin).

## MCP tools

| Tool | Purpose |
|---|---|
| `rag_load(doc_id?)` | Load vault notes into the index. No arg = all notes recursively; pass a vault-relative path for one note. |
| `rag_search(query, k)` | Semantic search — returns `[{id, metadata, score, snippet}]` |
| `rag_ingest(documents)` | Embed and store arbitrary text — accepts `[{id, content, metadata}]` |
| `rag_status()` | Show doc count, tracked files, watch interval |
| `rag_remove(doc_id)` | Remove a single chunk by ID |
| `rag_clear()` | Wipe the entire index (irreversible) |

## Vault watcher

The server watches the Obsidian vault automatically (default every 60 seconds):

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
       └── vault watcher          (polls Obsidian REST API every 60s)
```
