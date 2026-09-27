---
name: claude-maxer
description: >
  Trigger this skill when the request contains 'In order to untilize my claude limitation ...',   'to max my claude limitation ...', 
  'as my limitation of claude subscription has xx left ...', '5h', '7d', etc. Users want to leverate their Claude subscriptions. 
  Check if the background script exists, make one if it doesn't. Execute tasks follow the strategies.
  Work comes from the task queue (tasks-queue skill) when one is available; the tasks listed here
  are the defaults, run only when no task queue is available.
  Also trigger when the user wants to pause, disable, switch off, resume or re-enable claude-maxer.
---

# Claude-maxer

Uses up spare Claude subscription quota on work that ends up in the vault.
**This file is the control file.** `maxer.py` reads the **Settings** block
and the **Tasks** section below at the start of every run, so editing them
changes what runs next time, with no code change and no reinstall. The timing
and safety mechanics (reading usage, never opening an off-schedule window,
stopping tasks before a reset) are in `maxer.py`, because a model can't
reliably keep time.

## Schedule (crontab, machine-local CST)

| cron                        | command | does                                                     |
| --------------------------- | ------- | -------------------------------------------------------- |
| `0 3,8,13,18,23 * * *`      | `open`  | starts a 5h window (waits up to 20 min for a late reset) |
| `0 2,7,12,17,22 * * *`      | `run`   | fills the window that's open, about 1h before it ends    |
| `*/15 * * * *`              | fetch   | refreshes the usage snapshot (costs no quota)            |

The remote routine `claude-maxer-daily-ping` (`trig_01NMTNTnaybi5FP4XqKx5uBs`,
cron `10 0,5,10,15,19 * * *` UTC = 10 min after each local `open`) is the
backup opener in case this machine is off. Manage the local block with
`./enroll_cron.sh install|remove|status|print`.

**24h isn't a multiple of 5h.** A window lasts exactly 5h from its first
request, so the 23:00 window runs until 04:00. The 03:00 `open` finds it
still open and does nothing, the 02:00 `run` fills the 23:00 window, the
07:00 `run` usually finds no window (it never opens one), and 08:00 starts
the next window. That's four real windows a day (23, 08, 13, 18). The weekly
cap limits the total anyway.

## Settings

```maxer-settings
target_5h: 95          # stop filling a window at this 5h %
overshoot: 3           # never start a task likely to end above target + this
weekly_target: 95      # spend the week up to this 7d %, split into daily budgets
concurrency: 3         # tasks run in parallel per batch
model: claude-opus-5-5 # model for the tasks
budget_usd: 5          # per-task cost cap (claude -p --max-budget-usd)
task_timeout_min: 25   # per-task time cap
```

**Daily budget.** At the first decision of each day (and again if a new week
starts), what's left of the week up to `weekly_target` is split evenly over
the days left until the weekly reset. Today may spend one share, so today's
7d ceiling = 7d now + share. Heavy use earlier in the week shrinks the share,
but it never blocks a day outright. One full 95% window costs about 7pp of
the week, so a share of ~9pp is roughly 1⅓ full windows a day. Your own
interactive use comes out of the same budget. Raise `weekly_target` to spend
more, but at 100 you may be locked out until the weekly reset.

## Where the work comes from

**When a task queue is available, run the tasks it provides. When no task
queue is available, run the default tasks listed under [Tasks](#tasks).**
Any task queue outranks the defaults here.

Today the queue is the `tasks-queue` skill (`../tasks-queue/tasks_queue.py`).
Before each batch, `run` asks it for work, in this order:

1. **An undone item in the vault's `Tasks.md`.** It runs alone, as a
   `claude -p` session with full tools and no permission prompts
   (`--dangerously-skip-permissions`) in `/data/apps`. The session works out
   which repo the task means, implements it, and commits to master. It never
   pushes, and it stops if the repo is on another branch or has someone
   else's uncommitted work. The task is checked off only if a new commit
   really landed on master in the repo the session named. A failed or
   skipped task is retried on the next run and dropped after 2 attempts
   (counts in `~/.claude/state/claude-maxer-vault-fails.json`; delete an
   entry to retry it).
2. **The queue's news tasks**, when no vault task is waiting.
3. **The defaults below**, only when the queue can't be read (script missing,
   vault container down) or lists no news tasks.

## Tasks

The default tasks, used only when no task queue is available. Each
`### Title` below is one task. Its body is the prompt sent to a
headless `claude -p` that has only WebSearch and WebFetch. Tasks rotate in
this order across runs. The engine appends the output rules (a numbered list
of linked items, no invented URLs, skip items already in today's note), so a
prompt only needs to say *what* to collect. Add, remove or reword freely.

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

## Output (vault, written only when tasks run)

- `claude-maxer/news/YYYY-MM-DD.md`: all of the day's output in one note,
  one `## HH:MM · Task` section per task.
- Vault tasks land as commits in their own repo, not in the news note.
- `claude-maxer/log/YYYY-MM-DD.md`: today's budget, then one line for
  **every scheduled decision** (each `open` and `run`, including skips and
  why), and a block for each run that starts tasks: usage at start, a link
  to the news note, a line per task and per batch, and why it stopped.

Notes are written straight to the vault folder
(`/data/nextcloud_client/obsidian/lidaning`), not through the obsidian-vault
MCP container, whose sessions hung mid-run on 2026-09-27. Everything also goes
to `~/.claude/state/claude-maxer.log.jsonl`. Manual `status`/`--dry-run`
calls are never written to the vault. If
this file can't be parsed, `run` logs `skill_error` there and does nothing.

## Commands

```
./run_maxer_work.sh status          # usage, today's budget, parsed tasks/settings, run decision
./run_maxer_work.sh run --dry-run   # gate decision + the first task's full prompt
./run_maxer_work.sh open --dry-run  # what the opener would do
./run_maxer_work.sh off             # switch off until `on`
./run_maxer_work.sh off --until 3d  # or 2h, 30m, 18:00, 2026-10-01, "2026-10-01 08:00"
./run_maxer_work.sh on              # switch back on
```

**The switch.** `off` writes `~/.claude/state/claude-maxer-off.json`; while
it exists, every scheduled `open` and `run` does nothing and logs
`skipped: switched off …` (so the vault log still shows the machine is alive),
and a run already in progress stops starting new tasks. `--until` expires it
by itself. The crontab stays untouched. When the user asks to pause, disable,
stop, resume or re-enable claude-maxer, run these commands. The cloud backup
ping (`claude-maxer-daily-ping` routine) can't see this file; it only opens a
window and spends almost nothing, but pause it via the schedule skill if the
user wants zero activity.

Any setting can be overridden for a manual test with env `MAXER_<KEY>`,
e.g. `MAXER_CONCURRENCY=1`.
