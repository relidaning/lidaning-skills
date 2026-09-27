---
name: tasks-queue
description: >
  Activate when the request mentions tasks or spare capacity — "tasks", "my
  tasks", "task list", "Tasks.md", "what's next to do", "any undone tasks",
  "leverage the limitation", "use up my limit", "spare quota/usage", "what can
  Claude work on", or "tasks-queue". Owns the user's priority queue of work:
  the vault's `Tasks.md` is the highest-priority tier, then the news tasks
  listed in this skill. Lists, picks, and checks off undone items via
  `tasks_queue.py list|pick|mark|news`. Owns no schedule; an unattended caller
  that spends spare quota drains it.
---

# tasks-queue

The user's priority queue of work. It hands out the next task and checks
vault tasks off. **It does not schedule anything**; see
[Scheduling](#scheduling).

## Priority

| Tier | Source | Done when |
|---|---|---|
| 1 (highest) | undone items in the vault's `Tasks.md` | `mark` checks it off |
| 2 | [News tasks](#news-tasks) below | never; they rotate and repeat |

- A tier-1 task always goes first. Tier 2 runs only while `pick` exits 1
  (no undone vault task).
- Anything outside this queue, such as a caller's own built-in default
  tasks, ranks below both tiers and runs only when the queue can't be read.
- When the user asks what to work on, or wants to use leftover
  quota, run `pick` first and offer that task before anything else.
- Never track or propose tasks anywhere but `Tasks.md`. It is the only
  authoritative list of real work.

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
python3 tasks_queue.py news             # tier-2 news tasks as JSON [{title, prompt}]
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

**None here, by design.** Whatever spends the spare quota calls this
queue and owns the schedule. This skill stays a passive queue and never
calls back into its callers. Two rules from past runs:

- **One scheduler per quota pool.** Add the drain to whatever already spends
  the Claude quota, not as a new cron loop. Two loops sharing one pool each
  pass the usage gate on their own while together exhausting the 5h window.
  That is why the old standalone `*/30` runner was removed on 2026-08-10.
- **Mark only verified work.** A caller marks a vault task only after
  checking that the work landed (e.g. a new commit exists), never on the
  worker's word alone.

## News tasks

Tier 2. Each `### Title` is one task; its body says *what* to collect, and
the caller adds output rules (numbered, linked items, no invented URLs).
They rotate in order across runs. Add, remove or reword freely.

### AI
Find the 10 most important stories from the last 48 hours on AI and machine learning: model releases, research, AI companies, policy.

### Big tech
Find the 10 most important stories from the last 48 hours on big tech (Apple, Google, Microsoft, Meta, Amazon, Nvidia, Tesla and peers): products, business, regulation.

### World
Find the 10 most important breaking world news stories from the last 48 hours: politics, conflicts, disasters, major international events.

### Security
Find the 10 most important cybersecurity stories from the last 48 hours: major breaches, actively exploited vulnerabilities, security research.

### Dev & open source
Find the 10 most important stories from the last 48 hours on software development and open source: languages, frameworks, dev tools, notable releases.

### Science & space
Find the 10 most important science and space stories from the last 48 hours: research breakthroughs, space missions, health and medicine.

### Markets
Find the 10 most important markets and economy stories from the last 48 hours: central banks, major market moves, macro data, big deals.

### China tech
Find the 10 most important stories from the last 48 hours on China's technology sector and economy: Chinese tech companies, AI labs, chips, policy.

## Operational notes

- Run log from the retired standalone runner:
  `~/.claude/state/vault-tasks.log.jsonl` (old name kept on disk): 51 runs,
  12 `done` / 39 `skipped`, ending 2026-08-10 15:56. Nothing appends to it
  now.
