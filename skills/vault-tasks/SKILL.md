---
name: vault-tasks
description: >
  Activate when the user asks about the vault-tasks queue, the vault's Tasks
  note, the status of Tasks.md processing, "vault-tasks", or unattended task
  work landing in /data/apps/myfollows. Reads and checks off undone items in
  the Obsidian vault's Tasks note via `vault_tasks.py pick|list|mark`. This
  skill owns no schedule — report that claude-maxer runs the drain hourly as
  its priority-1 work type, rather than pointing at a standalone cron entry.
---

# vault-tasks

The queue interface between the Obsidian vault's Tasks note and unattended
work in `/data/apps/myfollows`. It reads undone items and checks them off.
**It does not schedule anything** — see [Scheduling](#scheduling).

## Vault binding

| | |
|---|---|
| Note | `Tasks.md` at the vault root — `[[Tasks]]` |
| Transport | Obsidian Local REST API, `${OBSIDIAN_MCP_URL%/}/vault/Tasks.md` |
| Override | `VAULT_TASKS_PATH` env var, if the note ever moves |

`vault_tasks.py` talks to the REST API directly rather than through the
`mcp__obsidian__*` tools, because an unattended caller has no MCP session.
Two env gotchas it already handles, both of which bit earlier versions:
`OBSIDIAN_MCP_URL` carries a trailing slash (naive appending gives a `//`
path the API 404s on), and localhost traffic must bypass `http_proxy`.

Env vars are interactive-shell-only — the token lives in `~/.zshrc.local`,
the URL in `~/.zshrc`, and sourcing `~/.zshrc.local` alone leaves the URL
empty. An unattended caller must set both:

```bash
source "$HOME/.zshrc.local"                      # OBSIDIAN_MCP_TOKEN
export OBSIDIAN_MCP_URL="http://127.0.0.1:27123/"
```

## CLI

```bash
python3 vault_tasks.py pick             # first undone task text; exit 1 if none
python3 vault_tasks.py list             # all undone tasks as "lineno<TAB>text"
python3 vault_tasks.py mark "<text>"    # rewrite that line as "- [x] <text>"
```

`mark` matches the task's exact stripped text, so pass back what `pick`
returned verbatim.

## What counts as a task

A list item (`- …`, `* …`, `1. …`) not already `- [x]`, or a standalone
prose paragraph — the note predates the checkbox format and `mark` is what
converted handled lines to `- [x] …`.

A bare prose line **directly under a list item** is a continuation of that
item, not a task of its own: long entries soft-wrap onto a second physical
line when typed in Obsidian. Fixed 2026-08-11 after the old rule ("any
non-empty non-heading line without `- [x]`") made `pick` return the second
half of an already-checked entry. That misfire was live and not cosmetic —
the orphaned half described work on the `claude-maxer` skill in
`lidaning-skills`, but the runner would have handed it to a session scoped
to `/data/apps/myfollows`, and marking it would have split one user item
into two checked lines.

## Scheduling

**None here, by design.** The `*/30` crontab entry was commented out
2026-08-10; `run_tasks.sh` was deleted 2026-08-11 at the user's request,
who is implementing the drain inside `claude-maxer` instead. Recover the
old runner from git history if it's ever wanted as a reference:

```bash
git show vault-tasks/unschedule-and-maxer-tuning^:skills/vault-tasks/run_tasks.sh
```

Do **not** re-add a second cron loop: two independent loops sharing one
quota pool each pass the usage gate on their own while jointly exhausting
the 5h window, which is exactly why the standalone entry died.

**Current reality check** — the drain *is* implemented: `run_maxer_work.sh`
picks a task with `vault_tasks.py pick`, runs it with `cwd=/data/apps/myfollows`,
commits directly to master (no branch/PR — the user's explicit choice
2026-08-08, unlike claude-maxer's own dep-audit/todo-triage work), and
`mark`s it only on success. See claude-maxer's SKILL.md "Work priority"
section for the authoritative description — this file doesn't duplicate it,
to avoid the two drifting out of sync again. A crontab comment once claimed
this fold-in existed for a day before it actually did; if this section ever
looks stale, verify with
`grep -n 'Tasks\.md' skills/claude-maxer/run_maxer_work.sh` rather than
trusting either doc.

Because commits land on master unreviewed, a bad unattended change ships
without a gate. If that stops feeling safe, switch the prompt to the
branch+draft-PR pattern rather than raising the budget cap.

## Operational notes

- Run log from the retired standalone runner:
  `~/.claude/state/vault-tasks.log.jsonl` — 51 runs, 12 `done` /
  39 `skipped`, ending 2026-08-10 15:56. Kept for history; nothing appends
  to it now.
- Old per-run transcript path: `/tmp/vault-tasks-last-run.log`.
