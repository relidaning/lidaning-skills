---
name: obsidian-local
description: >
  Activate when user mentions Obsidian, vault, or notes, or asks to
  search/read/write/edit/delete vault content. Primary interface to the
  local Obsidian vault via a headless MCP server (auto-started in Docker,
  Obsidian app not required): read, write, patch, search, tag, move, and delete.
---

## Overview

Two MCP servers, one skill:

- **obsidian-vault** (primary) — headless server that edits the vault's
  files directly, so the Obsidian app does **not** need to be running.
  It's the `obsidian-vault-mcp` Docker container (`@bitbonsai/mcpvault`
  behind `supergateway`), built from this skill's `server/` dir. It serves
  `http://127.0.0.1:27125/mcp` and mounts the vault
  `/data/nextcloud_client/obsidian/lidaning` at `/vault`. Its tools show up as
  `mcp__obsidian-vault__*`.
- **obsidian** (app-only extras) — the Local REST API plugin's own
  endpoint at `${OBSIDIAN_MCP_URL}/mcp/` (default `http://127.0.0.1:27123`).
  Works only while Obsidian is running. Use it only for what needs the live
  app: `command_execute` (e.g. `app:reload`), `open_file`, and
  `active_file_get_path`.

Helper script: `/data/apps/lidaning-skills/skills/obsidian-local/scripts/vault-mcp.sh`
(referred to below as `vault-mcp.sh`).

## Step 0 — ensure the server is up (every time the skill triggers)

Before any vault operation, run:

```bash
/data/apps/lidaning-skills/skills/obsidian-local/scripts/vault-mcp.sh ensure
```

It checks `/healthz`. If the server isn't healthy, it starts the container
(`docker compose up -d`, and builds the image on first run), waits for it,
and prints the tool list with arguments (`*` = required). Don't skip this
step because the tools look loaded: the container may have been stopped
since the session started.

## Calling the tools

1. **`mcp__obsidian-vault__*` tools are available in this session** → call them directly.
2. **They aren't** (the server was down when the session started, so Claude
   Code never connected) → call the same tools through the script. The
   arguments are the same JSON:

   ```bash
   vault-mcp.sh call read_note '{"path":"Folder/Note.md"}'
   vault-mcp.sh call search_notes '{"query":"lora","limit":10}'
   ```

   It prints the tool's text result and exits 1 on a tool error. Running
   `/mcp` → reconnect `obsidian-vault` also loads the native tools for the
   rest of the session.

Other subcommands: `vault-mcp.sh tools`, `vault-mcp.sh logs`, `vault-mcp.sh stop`.

## obsidian-vault tools

| Tool | Purpose |
|---|---|
| `read_note(path)` | Read a note (frontmatter + body) |
| `read_multiple_notes(paths[≤10])` | Batch read |
| `get_note_outline(path)` | Headings with line numbers, without the body |
| `read_note_lines(path, startLine, endLine)` | Read one section after `get_note_outline` |
| `write_note(path, content, frontmatter?, mode?)` | Create/overwrite; `mode`: `overwrite` (default) \| `append` \| `prepend`. Creates parent dirs |
| `patch_note(path, oldString, newString, replaceAll?)` | Exact-string replace inside a note (in-place section edit) |
| `search_notes(query, limit?, pathPrefix?, searchContent?, searchFrontmatter?, caseSensitive?, excludePaths?)` | Full-text / frontmatter search |
| `list_directory(path?)` | List dirs and files (`""` = vault root) |
| `get_frontmatter(path)` / `update_frontmatter(path, frontmatter, merge?)` | Read / set frontmatter without touching the body |
| `manage_tags(path, operation, tags?)` | `add` \| `remove` \| `list` tags on a note |
| `list_all_tags()` | All tags with counts (frontmatter + inline) |
| `get_notes_info(paths)` | Size/dates metadata without content |
| `get_vault_stats(recentCount?)` | Note/folder counts, recently modified files |
| `wiki_link(document)` | Resolve and read a `[[Wiki Link]]` |
| `move_note(oldPath, newPath, overwrite?)` | Rename/move a note |
| `move_file(oldPath, newPath, confirmOldPath, confirmNewPath)` | Move any file (binary-safe) |
| `delete_note(path, confirmPath, trashMode?)` | `trashMode`: `none` (permanent, default) \| `local` (vault `.trash`) \| `system` |

### App-only (obsidian plugin server, needs Obsidian running)

| Tool | Purpose |
|---|---|
| `command_execute` / `command_list` | Run Obsidian commands, e.g. `app:reload` after editing `.obsidian/` settings |
| `open_file` | Open a note in the Obsidian app |
| `active_file_get_path` | Which note is open right now |

If the app is closed, say so and skip these steps. Don't try to start Obsidian.
Direct REST fallback (only if the plugin's MCP endpoint 404s). Strip the
trailing `/` from `$OBSIDIAN_MCP_URL` first:

```bash
curl -sk -H "Authorization: Bearer $OBSIDIAN_MCP_TOKEN" "${OBSIDIAN_MCP_URL%/}/vault/<path>"
```

## Workflows

### Search notes

1. **If RAG is available** (`rag_search` tool present): call `rag_search(query, k=10)` first — it returns semantic matches with vault-relative paths and snippets. Use those paths to read full notes as needed.
2. If RAG is unavailable or returns nothing useful, use `search_notes` (add `pathPrefix` to scope it to a folder).
3. Present matching paths and snippets.

### Read a note

`read_note("path/to/note.md")`. For long notes, run `get_note_outline` first,
then `read_note_lines` for just the section you need.

### Create a note

`write_note` with `path` and `content`. It creates parent directories as needed.

### Update a note

- Whole file: `write_note` (default `overwrite`)
- Section edit: `get_note_outline` / `read_note` to find the exact text, then `patch_note`
- Append: `write_note` with `mode: "append"`
- Frontmatter only: `update_frontmatter` (`merge: true` keeps the other keys)

New content added to a note (a create, a write, or an append — e.g. a word
pasted into a vocab log) is headed by the current date as an H1, `# YYYY-MM-DD`,
directly above that content. Before adding the heading, check with
`get_note_outline` whether a `# YYYY-MM-DD` for today already exists in the note. If it
does, add the new content under that existing heading instead of creating a duplicate
(use `patch_note` to insert it at the end of that section, or append if it's the last section).

### Delete a note

Confirm with the user first. Then call `delete_note(path, confirmPath=path)`. Prefer
`trashMode: "local"` unless the user asks for a permanent delete.

## Rules

- **Ensure first** — run `vault-mcp.sh ensure` whenever this skill triggers, before any vault call
- **obsidian-vault first** — use it for all file operations; the plugin server is only for app-only actions
- **RAG first for search** — if `rag_search` is available, always try it before `search_notes`;
  RAG gives semantic matches across the whole vault without requiring an exact path
- **Search before read** — if the user doesn't know the exact path, search first
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
