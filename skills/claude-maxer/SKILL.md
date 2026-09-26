---
name: claude-maxer
description: >
  Trigger this skill when the request contains 'In order to untilize my claude limitation ...',   'to max my claude limitation ...', 
  'as my limitation of claude subscription has xx left ...', '5h', '7d', etc. Users want to leverate their Claude subscriptions. 
  Check if the background script exists, make one if it doesn't. Execute tasks follow the strategies.
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
weekly_target: 95      # the 7d % to reach by the weekly reset...
weekly_slack: 5        # ...paced evenly across the week, plus this much slack
concurrency: 3         # tasks run in parallel per batch
model: claude-opus-5-5 # model for the tasks
budget_usd: 5          # per-task cost cap (claude -p --max-budget-usd)
task_timeout_min: 25   # per-task time cap
```

The weekly pace line (`weekly_target × fraction of week elapsed +
weekly_slack`) is usually what stops a run. One 95% window costs about 7pp
of the week, so filling every window would use up the weekly cap in about
three days. Set `weekly_slack: 100` to turn the pacing off.

## Tasks

Each `### Title` below is one task. Its body is the prompt sent to a
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
- `claude-maxer/log/YYYY-MM-DD.md`: one block per run (usage at start,
  link to the news note), a line per task and per batch, and why it stopped.

Notes are written straight to the vault folder
(`/data/nextcloud_client/obsidian/lidaning`), not through the obsidian-vault
MCP container, whose sessions hung mid-run on 2026-09-27. Checks, skips,
pings and errors go only to `~/.claude/state/claude-maxer.log.jsonl`. If
this file can't be parsed, `run` logs `skill_error` there and does nothing.

## Commands

```
./run_maxer_work.sh status          # usage, pace line, parsed tasks/settings, run decision
./run_maxer_work.sh run --dry-run   # gate decision + the first task's full prompt
./run_maxer_work.sh open --dry-run  # what the opener would do
```

Any setting can be overridden for a manual test with env `MAXER_<KEY>`,
e.g. `MAXER_CONCURRENCY=1`.
