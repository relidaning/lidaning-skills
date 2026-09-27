---
name: tasks-queue
description: >
  Activate when the request mentions tasks or spare capacity — "tasks", "my
  tasks", "task list", "Tasks.md", "what's next to do", "any undone tasks",
  "leverage the limitation", "use up my limit", "spare quota/usage", "what can
  Claude work on", or "tasks-queue". Owns the user's priority queue of work:
  the vault's `Tasks.md` is the highest-priority source, above every other
  task. Lists, picks, and checks off undone items via
  `tasks_queue.py list|pick|mark`. Owns no schedule; nothing drains the queue
  unattended — say so plainly.
---

# tasks-queue

The user's priority queue of work. It reads undone items and checks them
off. **It does not schedule anything**; see [Scheduling](#scheduling).

## Priority

The vault's `Tasks.md` is the top of the queue. It outranks every other
source of work: tasks Claude proposes, backlog notes, and filler work
that exists only to use spare quota.

- When the user asks what to work on, or wants to use leftover
  quota, run `pick` first. If it returns a task, offer that task before
  anything else.
- Only an empty queue (`pick` exits 1) leaves room for lower-priority work.
- Never track or propose tasks anywhere but `Tasks.md`. It is the only
  authoritative list.

## Vault binding

| | |
|---|---|
| Note | `Tasks.md` at the vault root — `[[Tasks]]` |
| Transport | Headless obsidian-vault MCP container at `$OBSIDIAN_MCP_URL` (default `http://127.0.0.1:27125`), via `obsidian-local/scripts/vault_mcp.py` |
| Override | `TASKS_QUEUE_PATH` env var, if the note ever moves |

`tasks_queue.py` calls the container over HTTP itself, not through
Claude's `mcp__obsidian-vault__*` tools, because an unattended caller has no
MCP session. The Obsidian app need not run, and no token is needed. Cron
doesn't source `~/.zshrc`, so the default URL applies there; the client
starts the container via `vault-mcp.sh ensure` if it's down. It keeps the
note's frontmatter across rewrites.

## CLI

```bash
python3 tasks_queue.py pick             # first undone task text; exit 1 if none
python3 tasks_queue.py list             # all undone tasks as "lineno<TAB>text"
python3 tasks_queue.py mark "<text>"    # rewrite that line as "- [x] <text>"
```

`mark` matches the task's exact stripped text, so pass back what `pick`
returned verbatim. Mark a task only once its work is actually done and
verified.

## What counts as a task

A list item (`- …`, `* …`, `1. …`) not already `- [x]`, or a standalone
prose paragraph (the note predates the checkbox format, and `mark` is what
converted handled lines to `- [x] …`).

A bare prose line **directly under a list item** is a continuation of that
item, not a separate task, because long entries soft-wrap onto a second
physical line when typed in Obsidian. Treating the wrapped half as its own
task would hand half a sentence to the worker as the whole job, and
marking it would split one user item into two checked lines (fixed
2026-08-11).

## Scheduling

**None here, by design.** Nothing drains the queue unattended right now;
`list`/`pick`/`mark` are for manual or in-session use.

If an unattended drain is ever wanted, the caller owns it. This skill stays a
passive queue and never calls back into a scheduler. Two rules from past
runs:

- **One scheduler per quota pool.** Add the drain to whatever already spends
  the Claude quota, not as a new cron loop. Two loops sharing one pool each
  pass the usage gate on their own while together exhausting the 5h window.
  That is why the old standalone `*/30` runner was removed on 2026-08-10.
- **Gate unattended changes.** An earlier drain committed to master
  unreviewed. Prefer a branch plus a draft PR.

The old runner is in git history for reference:
`git show fd340bf6:skills/claude-maxer/run_maxer_work.sh`.

## Operational notes

- Run log from the retired standalone runner:
  `~/.claude/state/vault-tasks.log.jsonl` (old name kept on disk): 51 runs,
  12 `done` / 39 `skipped`, ending 2026-08-10 15:56. Nothing appends to it
  now.
