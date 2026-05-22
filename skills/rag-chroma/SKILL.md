---
name: rag-chroma
description: >
  General-purpose RAG pipeline with ChromaDB and ONNX embeddings. Ingest text
  content, embed it with all-MiniLM-L6-v2, store in ChromaDB, and search by
  meaning. The agent decides what to ingest and when to retrieve — this skill
  provides the tools, the LLM provides the context on where content comes from
  and when it's relevant.
---

## Overview

A standalone RAG pipeline exposed as an MCP server. Two jobs:

1. **Ingest** — take text content, embed, store in ChromaDB
2. **Retrieve** — semantic search when the agent determines stored context helps

This skill knows nothing about Obsidian, filesystem layout, URL fetching, or
any specific data source. It accepts text and metadata, embeds it, and returns
search results. The LLM — informed by other skills — decides what content to
feed in and when to pull it back out.

- **ChromaDB** (Docker, port 8000) — vector database
- **rag-mcp** (Docker, port 8081) — FastMCP server, SSE transport,
  all-MiniLM-L6-v2 ONNX embeddings (no GPU/torch needed)

## Prerequisites

```bash
docker compose -f skills/rag-chroma/docker-compose.yml up -d
```

Both chromadb (healthy) and rag-mcp (healthy) must be up.

## MCP tools

| Tool | Purpose |
|---|---|
| `rag_search(query, k)` | Semantic search — returns `{results: [{id, metadata, score, snippet}]}` |
| `rag_ingest(documents)` | Embed and store — accepts `[{id, content, metadata}]`, returns `{ingested, errors}` |
| `rag_status()` | Show model, collection name, doc count |
| `rag_remove(doc_id)` | Remove a document from the index by its ID |
| `rag_clear()` | Wipe the index (irreversible) |

## Architecture

```
docker compose up
  ├── chromadb :8000          (vector store)
  └── rag-mcp  :8081          (FastMCP, SSE transport)
       ├── ONNX all-MiniLM-L6-v2  (embeddings)
       └── ChromaDB HttpClient     (store/query)
```

## Workflows

### Ingest

The agent — using knowledge from other skills or user context — provides text
content and metadata to `rag_ingest`. The server embeds and stores it. The
server doesn't know or care whether the text came from a markdown file, a URL,
a PDF, an Obsidian vault, or a user paste.

### Retrieve

The agent calls `rag_search` whenever it determines stored context would help
answer a question, ground a claim, or fill a gap. The user should not need to
explicitly ask for a search.

### Update

`rag_remove(doc_id)` then `rag_ingest([{id, content, metadata}])` with the updated text.

## Rules

- **Agent decides when to retrieve** — not user-driven
- **Agent decides what to ingest** — the skill provides the tool, the LLM
  provides the content (sourced from other skills, user input, or its own
  capabilities)
- **No hardcoded sources** — this skill doesn't reference specific file paths,
  APIs, or data origins
- **Chunk large content** — split at ~1000 token boundaries with overlap
- **Cosine distance** — scores in [0,1] for intuitive relevance ranking
- **Model pre-cached** — ONNX model (~80MB) downloaded at build time
