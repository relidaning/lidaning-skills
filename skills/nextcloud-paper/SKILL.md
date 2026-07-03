---
name: nextcloud-paper
description: >
  Activate when user mentions Nextcloud, or asks to list, read, upload,
  download, move, copy, delete, or search files in their self-hosted cloud
  storage. Operates the local Nextcloud instance via MCP (WebDAV file tools),
  with a direct curl fallback.
---

## Overview

Operates the self-hosted Nextcloud (Docker container `mynextcloud-nextcloud-1`,
`http://127.0.0.1:8080`) through the `nextcloud` MCP server
([cbcoutinho/nextcloud-mcp-server](https://github.com/cbcoutinho/nextcloud-mcp-server),
run via `uvx`, WebDAV app only). Two access paths:

- **nextcloud MCP** (stdio) — `nc_webdav_*` tools for file operations
- **Direct WebDAV REST** — fallback via `curl` when MCP tools are unavailable
  (e.g. unattended/headless sessions where env vars from `~/.zshrc.local` are not set)

## Prerequisites

- Nextcloud container running: `docker ps | grep mynextcloud-nextcloud-1`
  (health check: `curl -s http://127.0.0.1:8080/status.php`)
- `NEXTCLOUD_HOST`, `NEXTCLOUD_USERNAME`, `NEXTCLOUD_PASSWORD` (an app
  password, not the login password) set in the shell environment — stored in
  `~/.zshrc.local`. The MCP server reads these exact names; `.mcp.json` just
  passes them through.
- First MCP start after a cache eviction re-downloads the package via `uvx`;
  the machine needs the proxy (`127.0.0.1:10808`) for that, but not for
  talking to Nextcloud itself.

## Access scope

The skill may only operate inside these directories (paths relative to the
files root). Edit this list to grant or revoke access — changes take effect
immediately (installed skills are symlinks).

<!-- ALLOWED_DIRS:BEGIN -->
- `papers/`
<!-- ALLOWED_DIRS:END -->

Enforcement rules:

- Every path argument (read, write, list, move, copy, delete, search scope)
  must resolve to one of the allowed directories or a descendant of one.
  Refuse anything else and tell the user which directory blocked it.
- Both endpoints of a move/copy must be in scope.
- Listing the files root (`""`) is permitted only to locate allowed
  directories; do not read or descend into out-of-scope results.
- Account-wide search (`nc_webdav_search_files`, `nc_webdav_find_by_name`,
  `nc_webdav_find_by_type`, `nc_webdav_list_favorites`): pass an allowed
  directory as the search scope when the tool supports it, and always drop
  out-of-scope paths from results before showing them.
- This is instruction-level enforcement — the app password itself can reach
  the whole account. Treat the list as a hard rule, not a suggestion.

## Available operations

### nextcloud MCP tools

| Tool | Purpose |
|---|---|
| `nc_webdav_list_directory` | List files/folders at a path ("" = root) |
| `nc_webdav_read_file` | Read file content (text decoded, binary base64) |
| `nc_webdav_write_file` | Create or overwrite a file |
| `nc_webdav_create_directory` | Create a directory (parents included) |
| `nc_webdav_delete_resource` | Delete a file or directory |
| `nc_webdav_move_resource` | Move or rename a file/directory |
| `nc_webdav_copy_resource` | Copy a file/directory |
| `nc_webdav_search_files` | Full WebDAV SEARCH (name/type/size/date filters) |
| `nc_webdav_find_by_name` | Find files by name pattern (e.g. `%.pdf`) |
| `nc_webdav_find_by_type` | Find files by MIME type (e.g. `image/png`) |
| `nc_webdav_list_favorites` | List files marked as favorites |

### Direct WebDAV (fallback)

Base URL: `$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<path>`,
auth `-u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD"`.

```bash
# List a directory
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -X PROPFIND -H "Depth: 1" \
  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<path>/"

# Download / upload
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -o local.bin \
  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<path>"
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -T local.bin \
  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<path>"

# Mkdir / delete / move
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -X MKCOL  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<dir>"
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -X DELETE "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<path>"
curl -s -u "$NEXTCLOUD_USERNAME:$NEXTCLOUD_PASSWORD" -X MOVE \
  -H "Destination: $NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<new-path>" \
  "$NEXTCLOUD_HOST/remote.php/dav/files/$NEXTCLOUD_USERNAME/<old-path>"
```

In unattended sessions the env vars are missing — `source ~/.zshrc.local`
in Bash first (same pattern as the Obsidian token).

## Workflows

### Browse / find files

1. Known location: `nc_webdav_list_directory(path)` — `""` for root.
2. Unknown location: `nc_webdav_find_by_name("%term%")` or
   `nc_webdav_search_files` with filters; then list/read the hits.

### Upload a local file

Small text files: `nc_webdav_write_file`. For large or binary files prefer the
curl `-T` upload — it streams from disk instead of passing content through
context.

### Download

`nc_webdav_read_file` for text you need to see; curl `-o` for binaries or
anything you'll hand to another program.

### Reorganize

`nc_webdav_create_directory` → `nc_webdav_move_resource` /
`nc_webdav_copy_resource`. Moving a directory moves its contents.

## Rules

- **Paths are relative to the user's files root** — no leading `/`, no
  `remote.php` prefix in MCP tool paths (`Documents/report.pdf`).
- **Confirm before delete** — `nc_webdav_delete_resource` on a directory is
  recursive and irreversible (well, Trash bin aside; don't rely on it).
- **Don't pipe big binaries through MCP** — use the curl fallback for
  uploads/downloads over ~1 MB.
- **App password only** — never put the real login password in
  `NEXTCLOUD_PASSWORD`; revoke/rotate app passwords in Nextcloud under
  Settings → Security → Devices & sessions.
- **MCP first, curl fallback** — prefer `nc_webdav_*` tools; fall back to
  direct WebDAV when the MCP server isn't connected.
