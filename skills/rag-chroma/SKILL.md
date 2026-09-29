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
- **rag-mcp** (Docker, port 8081) — FastMCP HTTP server, multilingual-e5-small ONNX embeddings (Chinese and English), hybrid vector + BM25 search

## Prerequisites

```bash
docker compose -f skills/rag-chroma/docker-compose.yml up -d
```

The vault is read through obsidian-local's `obsidian-vault-mcp` server
(`VAULT_MCP_URL`, default `http://127.0.0.1:27125/mcp`), not from disk, so the
index holds exactly the notes that server exposes. That container must be
running (`obsidian-local/scripts/vault-mcp.sh ensure`); while it's down the
index stays as it was, and `rag_status.vault_sync.last_error` says why. No
Obsidian app, REST API or token is needed. `rag_answer` additionally requires `LLM_API_KEY` set in `docker-compose.yml`'s environment
(it raises at call time if unset) — `LLM_BASE_URL` (default: OpenAI) and `LLM_MODEL`
(default `gpt-4o-mini`) are optional overrides for a non-OpenAI-compatible backend.

## MCP tools

| Tool | Purpose |
|---|---|
| `rag_load(doc_id?)` | Load vault notes into the index. No arg = all notes recursively; pass a vault-relative path for one note. |
| `rag_search(query, k, collection?, mode?)` | Hybrid search — returns `[{id, metadata, score, snippet, match}]`. `mode`: `hybrid` (default), `vector` (meaning only) or `keyword` (BM25 only: file names, IDs, rare terms). `score` is always cosine similarity; `match` says which ranker found the hit. |
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

The server polls the vault server (default every 60 seconds): it lists every
note and its modified time, and a note whose time hasn't changed isn't even
read. Skipped or failed notes are logged as warnings
(`docker logs rag-chroma-rag-mcp-1`), not swallowed, and `rag_status.vault_sync`
shows the last successful sync. An unreachable vault server skips the tick;
it is never taken to mean the notes were deleted.

- **Modified note** → remove stale chunks, re-index with updated content
- **Deleted note** (or one the vault server no longer exposes) → remove all its chunks from ChromaDB
- **New note** → index immediately on next tick

Change detection uses MD5 content hashing. Signatures are stored in ChromaDB
metadata so state survives container restarts without a full re-index.

To change the interval: set `WATCH_INTERVAL=<seconds>` in `docker-compose.yml`.

## Chunking and search

- **Chunks** (`rag-mcp/chunker.py`): a note is cut at its headings, then at
  paragraphs (a fenced code block stays whole); only an oversized block is split
  further, by line, sentence, then token count. Each chunk is at most 300
  tokens of the embedding model, so nothing is truncated (e5 reads 512).
  Frontmatter is dropped, and each chunk starts with a header, `note/path >
  Heading > Subheading`, so it carries its context; the heading path is also in
  the `heading` metadata.
- **Search**: the vector ranking (e5 cosine) and a BM25 keyword ranking
  (`rag-mcp/bm25.py`; Chinese indexed as character unigrams + bigrams) are
  merged by reciprocal rank fusion. The BM25 index is in memory, rebuilt from
  Chroma on the first search after a write.
- **Model changes rebuild**: each collection's metadata records its `embed`
  model (and, for `documents`, its `chunker` version). At startup a mismatch
  rebuilds it: `documents` is recreated empty and re-indexed by the watcher
  (~10 min for the whole vault, search results partial meanwhile); other
  collections are re-embedded from their stored text.
- Similarity scores from e5 are compressed (unrelated text still scores
  ~0.7–0.8), so compare scores against each other, not against thresholds
  carried over from the old MiniLM model.

## Architecture

```
docker compose up
  ├── chromadb :8000              (vector store)
  └── rag-mcp  :8081              (FastMCP HTTP)
       ├── ONNX multilingual-e5-small (embeddings, baked into the image)
       ├── BM25 keyword index      (in memory, per collection)
       ├── ChromaDB HttpClient     (store/query)
       ├── vault watcher          (polls obsidian-vault-mcp every 60s)
       └── GET /health            (Docker healthcheck; opens no MCP session)
```
