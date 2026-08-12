---
name: obsidian-local
description: >
  Activate when user mentions Obsidian, vault, or notes, or asks to
  search/read/write/edit/delete vault content. Primary interface to the
  local Obsidian vault via MCP: read, write, patch, search, and delete.
---

## Overview

Connects to the Obsidian Local REST API plugin (coddingtonbear, v4.0.3+)
running at `$OBSIDIAN_MCP_URL` (default `http://127.0.0.1:27123`). Two access paths:

- **obsidian MCP** (HTTP, wired in `.mcp.json` directly to the Local REST
  API plugin's own `${OBSIDIAN_MCP_URL}/mcp/` endpoint — not a separate
  stdio server process) — high-level tools for get/write/patch/append/
  search/list/tags
- **Direct REST API** — fallback via `curl -k` when MCP endpoints 404

## Prerequisites

Obsidian must be running with the Local REST API plugin enabled.
`OBSIDIAN_MCP_TOKEN` and `OBSIDIAN_MCP_URL` must be set in the shell environment.

## Available operations

### obsidian MCP tools

| Tool | Purpose |
|---|---|
| `vault_read` | Read a note by vault-relative path (pass `target`/`targetType` for one heading/block/frontmatter key) |
| `vault_write` | Create or overwrite a note |
| `vault_patch` | Edit a section (heading, block) in place — also how frontmatter fields are get/set/deleted (`targetType: frontmatter`) |
| `vault_append` | Append content to a note |
| `search_query` | JsonLogic query over note metadata (tags, frontmatter, path glob/regexp) |
| `search_simple` | Full-text search with relevance scoring |
| `vault_list` | List files and directories |
| `tag_list` | List all tags with usage counts |
| `vault_get_document_map` | Discover a note's headings/blocks before patching |
| `vault_delete` | Permanently delete a note |
| `open_file` | Open a note in the Obsidian app |

### Direct REST API (fallback)

When MCP tools return 404, use `curl` directly. `$OBSIDIAN_MCP_URL` may
already end in `/` — always strip it with `${OBSIDIAN_MCP_URL%/}` before
appending a path, or the resulting `//` 404s:

```bash
curl -s -H "Authorization: Bearer $OBSIDIAN_MCP_TOKEN" \
  "${OBSIDIAN_MCP_URL%/}/vault/<path>"
```

Endpoints: `GET /vault/` (list), `GET /vault/<path>` (read),
`PUT /vault/<path>` (create/overwrite), `DELETE /vault/<path>` (delete).

## Workflows

### Search notes

1. **If RAG is available** (`rag_search` tool present): call `rag_search(query, k=10)` first — it returns semantic matches with vault-relative paths and snippets. Use those paths to read full notes as needed.
2. If RAG is unavailable or returns no useful results, try `search_simple` (text) or `search_query` (JSONLogic).
3. If that 404s, fall back to grepping via direct REST API reads.
4. Present matching paths and snippets.

### Read a note

`vault_read("path/to/note.md")` — returns full markdown body.

### Create a note

`vault_write` with path and content. Creates parent directories as needed.
Or `PUT /vault/path%2Fto%2Fnote.md` via REST API.

### Update a note

- Whole file: `vault_write` (overwrite)
- Section edit: `vault_patch` (heading/block/frontmatter)
- Append: `vault_append`
- Frontmatter only: `vault_patch` with `targetType: frontmatter`

New content added to a note (a create, a write, or an append — e.g. a word
pasted into a vocab log) is headed by the current date as an H1, `# YYYY-MM-DD`,
directly above that content. Before adding the heading, check whether a
`# YYYY-MM-DD` for today already exists in the note; if it does, append the
new content under that existing heading instead of adding a duplicate one.

### Delete a note

`vault_delete("path/to/note.md")` — irreversible, confirms with user first.

## Rules

- **RAG first for search** — if `rag_search` is available, always try it before `search_simple`/`search_query`; RAG gives semantic matches across the whole vault without requiring an exact path
- **Search before read** — if the user doesn't know the exact path, search first
- **MCP first, REST fallback** — prefer MCP tools; fall back to direct curl when they 404
- **Self-signed cert** — Obsidian uses self-signed TLS. Use `-k` with curl
- **Vault-relative paths** — all paths are relative to vault root, e.g. `Folder/Note.md`
- **Human-readable markdown** — when creating or updating a note, ensure the output is clean,
  well-structured markdown. Proper headings, balanced blank lines, fenced code blocks with
  language tags, readable link text, no wall-of-text paragraphs. The note should be
  immediately readable in Obsidian's preview and source modes
- **Date-stamp new content as H1** — any content written or appended to a note (create, write,
  or append) gets the current date as an H1 heading, `# YYYY-MM-DD`, directly above it. If a
  heading for today already exists in the note, add the new content under that heading instead
  of creating a duplicate
- **Generated docs go to vault root** — when Claude generates a standalone report/doc to save
  in the vault (e.g. a summary, an audit log, a run report) and the user hasn't given an
  explicit path, write it to the vault root (no subfolder) so the user can find it immediately
  without navigating. This overrides any other default subfolder convention unless the user
  specifies a path or a project's own docs say otherwise for that specific artifact.
  **Exception — paper summary notes**: notes produced by the `paper-fetch` skill for
  downloaded papers always go to `0_dev/AI/Papers/`, not the vault root.
