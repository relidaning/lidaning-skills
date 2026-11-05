---
name: rag-chroma
description: >
  Activate when user asks to search documents by meaning, ingest content
  (PDFs/URLs/notes/Word/Excel), query the knowledge base, or manage the RAG
  index. ChromaDB + ONNX semantic search pipeline with Obsidian vault sync.
---

## Agent compatibility

Use the current agent’s available MCP tools for the `rag` server. Tool
prefixes vary between Claude Code and Codex; discover them by capability.
Resolve bundled scripts relative to this loaded skill directory.

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
| `rag_load(doc_id?, prefix?)` | Load vault notes. No args = all notes; `doc_id` = one note; `prefix` = one directory recursively (e.g. `0_dev/0_AI`). |
| `rag_search(query, k, collection?, mode?)` | Hybrid search — returns `[{id, metadata, score, snippet, match}]`. `mode`: `hybrid` (default), `vector` (meaning only) or `keyword` (BM25 only: file names, IDs, rare terms). `score` is always cosine similarity; `match` says which ranker found the hit. |
| `rag_answer(query, k=4)` | Retrieve top-k chunks and generate a grounded, cited answer via an LLM — returns `{answer, sources, chunks}`. Use this instead of `rag_search` when the user wants a synthesized answer, not raw snippets. Requires `LLM_API_KEY` (see Prerequisites). |
| `rag_ingest(documents, collection?)` | Embed and store arbitrary text — accepts `[{id, content, metadata}]` |
| `rag_list(collection, limit?)` | Every entry's `{id, metadata}` in a small collection (not for the vault index) |
| `rag_status()` | Doc count per collection, tracked files, watch interval |
| `rag_remove(doc_id, collection?)` | Remove a single chunk by ID |
| `rag_clear()` | Wipe the vault index (irreversible) |
| `rag_sources(collection?, prefix?)` | List indexed source paths and chunk counts. |
| `rag_chunks(collection?, source?, offset?, limit?, doc_id?)` | Browse complete chunk text and metadata; pages up to 100 chunks. |
| `rag_logs(date?, limit?)` | Read daily audit events, newest first; date is `YYYY-MM-DD`. |

`collection` defaults to `documents`, the vault index. Other collections hold
data that isn't vault notes and are never touched by the watcher:

| Collection | Owner | Contents |
|---|---|---|
| `papers` | sub-maxer's daily Papers task | One entry per proposed paper; id `arxiv:<id>` or the bare URL; metadata `title, url, source, date, proposed, kind` (`recent`/`foundational`) |

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

- **Chunks** (`rag-mcp/chunker.py`, `md-structure-v3`): parse ATX and Setext
  headings into a tree, ignoring headings inside fenced code. Keep an entire
  section with its subsections when it fits; otherwise recurse into lower-level
  headings, then paragraphs, then sentences. Only an indivisible oversized
  sentence/block uses token-bounded splitting. Unrelated top-level sections are
  never merged and there is no text overlap. Frontmatter is dropped; each chunk
  carries its full heading ancestry in its context header. The complete stored
  text, including the header, stays within 300 embedding tokens. Metadata stores
  `heading`, `tokens`, `split_reason`, and `chunker`. An ancestry header too large
  to fit produces an explicit indexing error rather than silent truncation.
- **Search**: the vector ranking (e5 cosine) and a BM25 keyword ranking
  (`rag-mcp/bm25.py`; Chinese indexed as character unigrams + bigrams) are
  merged by reciprocal rank fusion. The BM25 index is in memory, rebuilt from
  Chroma on the first search after a write.
- **Version changes**: an embedding model mismatch rebuilds collections to
  avoid mixing incompatible vectors. A chunker change preserves the index;
  new/edited notes use the new chunker, and `rag_load(prefix="folder")` explicitly
  rebuilds a directory. Older unchanged notes keep their chunks until loaded.
  Replacement upserts new chunks before removing stale IDs so embedding failures
  preserve the old note. Other collections (such as `papers`) are unaffected by
  vault chunker updates.
- Similarity scores from e5 are compressed (unrelated text still scores
  ~0.7–0.8), so compare scores against each other, not against thresholds
  carried over from the old MiniLM model.

## Web inspector and logs

Open **http://localhost:8081/** (or the machine's LAN address on port 8081).
The inspector is part of the existing RAG service, with no separate frontend
build or hosted account. Search shows complete passages and ranking scores;
Chunks filters indexed source paths and pages through stored text, heading
hierarchy, token counts and split reasons. Tools exposes every MCP tool with
editable JSON arguments. Activity reads the daily audit trail. Generated answers
require the service's LLM configuration; retrieval and browsing do not.

The HTTP tool endpoint shares the audited MCP implementations. It rejects
cross-origin/form submissions and requires an explicit confirmation for index
removal/clearing. This is a trusted local/LAN inspector with the same access as
the existing MCP service; it does not add authentication or public hosting.

Logs persist at **`skills/rag-chroma/logs/YYYY-MM-DD.log`**, mounted as
`/skill/logs` in Docker (`RAG_LOG_DIR` overrides the directory). Each line is JSON:
local timestamp with timezone, event, call ID, tool name, arguments including
query/keywords and ranking mode, duration, result/error, and retrieved chunk
IDs, sources, headings and scores. Answer retrieval is also logged before the
LLM call, so failed answer generation still leaves retrieval evidence.
Indexing events record source path, chunk count and chunker version. Ingest logs
IDs rather than copying document bodies. Logs contain private queries/source
paths and are gitignored; there is no automatic retention/deletion policy.

After source changes, rebuild/restart just this service:

```bash
docker compose -f skills/rag-chroma/docker-compose.yml build rag-mcp
docker compose -f skills/rag-chroma/docker-compose.yml up -d --no-deps rag-mcp
```

Offline tests use fake vault/index data and temporary logs. With the service
image built, run them without connecting to the live vault:

```bash
docker compose -f skills/rag-chroma/docker-compose.yml run --rm --no-deps \
  -v "$PWD/skills/rag-chroma/tests:/app/tests:ro" \
  rag-mcp python -m unittest discover -s tests -v
```

## Architecture

```
docker compose up
  ├── chromadb :8000              (vector store)
  └── rag-mcp  :8081              (FastMCP HTTP)
       ├── ONNX multilingual-e5-small (embeddings, baked into the image)
       ├── BM25 keyword index      (in memory, per collection)
       ├── ChromaDB HttpClient     (store/query)
       ├── vault watcher          (polls obsidian-vault-mcp every 60s)
       ├── GET / (web inspector), POST /api/call (shared tool functions)
       ├── daily JSON audit logs (persistent host bind mount)
       └── GET /health            (Docker healthcheck; opens no MCP session)
```
