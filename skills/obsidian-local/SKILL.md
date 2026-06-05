---
name: obsidian-local
description: >
  Local Obsidian vault access via the Obsidian Local REST API MCP server.
  Search notes, read full content, create new notes, update/revise/patch
  existing notes, and delete notes. Use when the user wants to find, read,
  write, edit, or delete notes in their Obsidian vault.
---

## Overview

Connects to the Obsidian Local REST API plugin (coddingtonbear, v4.0.3+)
running at `$OBSIDIAN_MCP_URL` (default `http://127.0.0.1:27123`). Two access paths:

- **obsidian MCP** (cyanheads/obsidian-mcp-server, stdio) — high-level tools
  for get/write/patch/append/search/list/tags
- **Direct REST API** — fallback via `curl -k` when MCP endpoints 404

## Prerequisites

Obsidian must be running with the Local REST API plugin enabled.
`OBSIDIAN_MCP_TOKEN` and `OBSIDIAN_MCP_URL` must be set in the shell environment.

## Available operations

### obsidian MCP tools

| Tool | Purpose |
|---|---|
| `obsidian_get_note` | Read a note by vault-relative path |
| `obsidian_write_note` | Create or overwrite a note |
| `obsidian_patch_note` | Edit a section (heading, block, frontmatter) in place |
| `obsidian_append_to_note` | Append content to a note |
| `obsidian_search_notes` | Search by text or JSONLogic predicate |
| `obsidian_list_notes` | List files and directories |
| `obsidian_list_tags` | List all tags with usage counts |
| `obsidian_manage_frontmatter` | Get/set/delete frontmatter fields |
| `obsidian_delete_note` | Permanently delete a note |
| `obsidian_open_in_ui` | Open a note in the Obsidian app |

### Direct REST API (fallback)

When MCP tools return 404, use `curl` directly:

```bash
curl -s -H "Authorization: Bearer $OBSIDIAN_MCP_TOKEN" \
  "$OBSIDIAN_MCP_URL/vault/<path>"
```

Endpoints: `GET /vault/` (list), `GET /vault/<path>` (read),
`PUT /vault/<path>` (create/overwrite), `DELETE /vault/<path>` (delete).

## Workflows

### Search notes

1. **If RAG is available** (`rag_search` tool present): call `rag_search(query, k=10)` first — it returns semantic matches with vault-relative paths and snippets. Use those paths to read full notes as needed.
2. If RAG is unavailable or returns no useful results, try `obsidian_search_notes` with text or JSONLogic mode.
3. If that 404s, fall back to grepping via direct REST API reads.
4. Present matching paths and snippets.

### Read a note

`obsidian_get_note("path/to/note.md")` — returns full markdown body.

### Create a note

`obsidian_write_note` with path and content. Creates parent directories as needed.
Or `PUT /vault/path%2Fto%2Fnote.md` via REST API.

### Update a note

- Whole file: `obsidian_write_note` (overwrite)
- Section edit: `obsidian_patch_note` (heading/block/frontmatter)
- Append: `obsidian_append_to_note`
- Frontmatter only: `obsidian_manage_frontmatter`

### Delete a note

`obsidian_delete_note("path/to/note.md")` — irreversible, confirms with user first.

## Rules

- **RAG first for search** — if `rag_search` is available, always try it before `obsidian_search_notes`; RAG gives semantic matches across the whole vault without requiring an exact path
- **Search before read** — if the user doesn't know the exact path, search first
- **MCP first, REST fallback** — prefer MCP tools; fall back to direct curl when they 404
- **Self-signed cert** — Obsidian uses self-signed TLS. Use `-k` with curl
- **Vault-relative paths** — all paths are relative to vault root, e.g. `Folder/Note.md`
- **Human-readable markdown** — when creating or updating a note, ensure the output is clean,
  well-structured markdown. Proper headings, balanced blank lines, fenced code blocks with
  language tags, readable link text, no wall-of-text paragraphs. The note should be
  immediately readable in Obsidian's preview and source modes
