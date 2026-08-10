---
name: vault-tasks
description: >
  Activate when the user asks about the vault-tasks automation, the status
  of Tasks.md processing, "vault-tasks", or unattended task work landing in
  /data/apps/myfollows. Documents and manages the local cron routine that
  reads undone items from the vault's Tasks.md and implements them one at a
  time.
---

# vault-tasks

A local cron routine that turns freeform items in the Obsidian vault's
`Tasks.md` into real code changes in `/data/apps/myfollows`, one task per
run, and checks each off in the vault when done.

## How it works

1. `run_tasks.sh` fires from the local crontab every 30 minutes.
2. It gates on usage first, reusing `claude-maxer`'s snapshot + 95%
   threshold check (`check_usage.py`) so this doesn't compound with
   claude-maxer's own consumption.
3. `vault_tasks.py pick` reads `Tasks.md` over the Obsidian Local REST API
   (not the MCP tool -- cron has no MCP session) and returns the first
   undone line: any non-empty, non-heading line not already starting with
   `- [x]`. The file currently has no checkbox syntax at all, so every
   plain-text line counts as undone until handled.
4. The picked task text is handed to `claude -p` as the entire task
   description, scoped to `/data/apps/myfollows`, with instructions to
   implement it, run lint/typecheck/build for the touched area if one
   exists, and commit **directly to master** (per the user's explicit
   choice on 2026-08-08 -- no branch/PR review gate, unlike claude-maxer's
   dep-audit/todo-triage work). It does **not** push to any remote.
5. On success, `vault_tasks.py mark` rewrites that exact line as
   `- [x] <original text>` in `Tasks.md`.
6. One task per run by design (the user's choice) -- some entries (e.g. a
   full page redesign) are too large to safely bound to one 30-minute slot
   if a run tried to batch several. A `flock` on `/tmp/vault-tasks.lock`
   also prevents a long-running task from overlapping the next cron fire.

## Files

- `run_tasks.sh` -- the cron entry point (env setup, usage gate, one
  `claude -p` call, marking).
- `vault_tasks.py` -- `pick`/`mark` against `Tasks.md` via the Obsidian
  Local REST API directly (works headlessly; the MCP tool needs a live
  session).

## Operational notes

- Log: `~/.claude/state/vault-tasks.log.jsonl` (one line per run: skipped
  with reason, done, failed, or handled-but-unmarked).
- Last run's full `claude -p` transcript/output: `/tmp/vault-tasks-last-run.log`.
- Per-run budget cap: `--max-budget-usd 5`; wall-clock cap: `timeout 25m`.
- Cron line: `*/30 * * * * /data/apps/lidaning-skills/skills/vault-tasks/run_tasks.sh >> /tmp/vault-tasks-cron.log 2>&1`.
- To pause: comment out that crontab line (`crontab -e`) -- same pattern as
  the disabled `claude-maxer` opportunistic-work entry already in this
  crontab. Nothing else needs to change.
- Direct-to-master commits mean a bad unattended change can land without
  review -- if that stops feeling safe, the fix is switching `run_tasks.sh`'s
  prompt to the branch+draft-PR pattern claude-maxer uses for its own
  code-touching work, not a bigger budget cap.
