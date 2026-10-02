---
name: claude-maxer
description: >
  Trigger this skill when the request contains 'In order to untilize my claude limitation ...',   'to max my claude limitation ...', 
  'as my limitation of claude subscription has xx left ...', '5h', '7d', etc. Users want to leverate their Claude subscriptions. 
  Check if the background script exists, make one if it doesn't. Execute tasks follow the strategies.
  Work comes from the task queue (tasks-queue skill) when one is available; the tasks listed here
  are the defaults, run only when no task queue is available.
  Also trigger when the user wants to pause, disable, switch off, resume or re-enable claude-maxer,
  or to ignore / respect the weekly (7d) limit, or to turn back-to-back windows (b2b) on or off.
argument-hint: "[scheduler on|off [--until T]] [weekly on|off [--until T]] [b2b on|off] [show] [status]"
---

# Claude-maxer

Uses up spare Claude subscription quota on work that ends up in the vault.
**This file is the control file.** `maxer.py` reads the **Settings** block
and the **Tasks** section below at the start of every run, so editing them
changes what runs next time, with no code change and no reinstall. The timing
and safety mechanics (reading usage, never opening an off-schedule window,
stopping tasks before a reset) are in `maxer.py`, because a model can't
reliably keep time.

## Arguments (`/claude-maxer <args>`)

When the skill is invoked with arguments, they are a command: run the
matching line below in **one** Bash call, with the script's absolute path
(`/data/apps/lidaning-skills/skills/claude-maxer/run_maxer_work.sh <args>`;
the installed skill directory has only the `.md` files, not the scripts),
show its output, and do nothing else (no task work, no script checks, no
other skill calls). `--until T` passes through
unchanged (`2h`, `3d`, `18:00`, `2026-10-01`).

| arguments | runs |
|---|---|
| `scheduler off [--until T]` | `./run_maxer_work.sh off [--until T]` |
| `scheduler on` | `./run_maxer_work.sh on` |
| `weekly off [--until T]` | `./run_maxer_work.sh weekly off [--until T]` (ignore the 7d budget) |
| `weekly on` | `./run_maxer_work.sh weekly on` (respect it again) |
| `b2b on [--until T]` | `./run_maxer_work.sh b2b on [--until T]` (back-to-back windows: open the next one as soon as the last resets) |
| `b2b off` | `./run_maxer_work.sh b2b off` (open windows in the pin hours only) |
| `show` | `./run_maxer_work.sh show` (current settings: scheduler, weekly and b2b switches, cron block, Settings values; offline) |
| `status` | `./run_maxer_work.sh status` (settings plus live usage, budget and the queue's next task) |

Switches can be combined in one call, e.g.
`/claude-maxer scheduler on weekly off b2b on`. After `scheduler off`, say whether a
task is still running (`pgrep -af 'claude -p'`): the switch stops new tasks,
not one already in progress. Anything else is not a command: treat it as a
normal request. With no arguments, the skill works as described below.

## Schedule (crontab, machine-local CST)

| cron                        | command | does                                                     |
| --------------------------- | ------- | -------------------------------------------------------- |
| `*/10 * * * *`              | `tick`  | decides from the real 5h reset time (below)              |
| `*/2 * * * *`               | fetch   | refreshes the usage snapshot (costs no quota)            |

The 5h window rolls: it opens on the first request after the last one
expired, whoever sends it, so its reset isn't at a fixed hour. Fixed cron
times for `run` filled windows at the wrong time whenever the reset had
drifted, so the timing lives in `maxer.py` and cron only wakes it up:

- **Window open** → `run` once per window, `RUN_LEAD_MIN` (60) before its
  actual reset. A window you opened at 10:40 gets filled from ~14:40.
- **No window open, during a pin hour** (`OPEN_HOURS`: 03, 08, 13, 18, 23)
  → `open` once per pin hour. A late reset (say 08:40) is picked up at the
  next tick in the same hour, and a failed ping retries on the next tick.
- **No window open, back-to-back on** (`b2b on`) → every hour counts as a
  pin hour, so the next window opens at the first tick after a reset,
  whatever the time (a 10:40 reset reopens at 10:40, not at 13:00).
- **Anything else** → exit without writing anything. `open` and `run` log
  their own decisions, skips included, so each window and pin gets one line
  in the vault log, not one per tick.

The remote routine `claude-maxer-daily-ping` (`trig_01NMTNTnaybi5FP4XqKx5uBs`,
cron `10 0,5,10,15,19 * * *` UTC = 10 min after each pin) is the
backup opener in case this machine is off. Manage the local block with
`./enroll_cron.sh install|remove|status|print`.

**24h isn't a multiple of 5h.** A window lasts exactly 5h from its first
request, so the 23:00 window runs until 04:00 and the 03:00 pin finds it
still open. That's four real windows a day (23, 08, 13, 18). With `b2b on`
the 04:00 reset reopens at once and the windows chain round the clock
(about 4.8 a day), drifting with whoever opened the last one. The weekly
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
**The queue decides the order** (`tasks_queue.py next`); `run` decides only
whether there is quota and whether the task fits in what's left of the
window (if a repo task is too big, it asks again with `--small` and gets
news). The order, as the queue hands it out:

1. **An undone item in the vault's `Tasks.md`.** It runs alone, as a
   `claude -p` session with full tools and no permission prompts
   (`--dangerously-skip-permissions`) in `/data/apps`. The session works out
   which repo the task means, implements it, and commits to master. It never
   pushes, and it stops if the repo is on another branch or has someone
   else's uncommitted work. The task is checked off only if a new commit
   really landed on master in the repo the session named. A failed or
   skipped task is retried on the next run and dropped after 2 attempts
   (counts in `~/.claude/state/claude-maxer-vault-fails.json`; delete an
   entry to retry it; `run` passes those as `--skip`).
2. **One news batch, if today hasn't had one yet** (`concurrency` news
   tasks in parallel; `run` reports it with `tasks_queue.py news-ran`).
   News tasks marked `(daily)` in tasks-queue (e.g. Papers) lead this batch
   every day and never run as filler.
3. **A review task**, when an app has optimization PRs nobody has judged
   yet: one app's open `opt/` PRs, at most 3 per task. The session tests
   each in a fresh worktree and squash-merges on GitHub the ones it could
   verify; it holds what it can't prove or what is yours to decide
   (secrets, stored data, deployment), and closes what is superseded. It
   never redeploys. `run` reads each PR's real state back with `gh`, files
   the report in `claude-maxer/optimize/<app>.md`, and tells the queue
   which PRs are still open, so they wait for you and aren't reviewed
   again. Details and the worker prompt: tasks-queue's `## Review tasks`.
   Then **an optimize task**: one app under `/data/apps`, delivered as a PR. It
   runs alone, in the app's directory, but edits only a fresh git worktree
   on a new `opt/<app>-<stamp>` branch, so your checkout is never touched.
   It pushes and opens a PR only for your own `relidaning/*` repos (a local
   branch otherwise). It never restarts or redeploys anything. `run` files
   the report in `claude-maxer/optimize/<app>.md`, removes the worktree, and
   counts "optimized" only if `gh` can see the PR (or the local branch got
   a new commit); anything else is logged as findings. Details and the
   worker prompt: tasks-queue's `## Optimize tasks`.
4. **More news tasks**, as filler, when no app is left to optimize or the
   room left in the window is too small for one.
5. **The defaults below**, only when the queue can't be read (script missing,
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
Find the 2 most important breaking world news stories from the last 48 hours: politics, conflicts, disasters, major international events.

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
- `claude-maxer/optimize/<app>.md`: one dated report per optimize visit
  (what it is, findings, what was chosen and why, before → after, what's
  left for you). The fix itself is a PR in the app's repo. Review tasks
  add a `review` section to the same note: per PR, merged, held or closed,
  with the evidence and whether a redeploy is needed.
- `claude-maxer/log/YYYY-MM-DD.md`: today's budget, then one line for
  **every scheduled decision** (each `open` and `run` a tick starts,
  including skips and why), and a block for each run that starts tasks: usage at start, a link
  to the news note, a line per task and per batch, and why it stopped.

Notes are written straight to the vault folder
(`/data/nextcloud_client/obsidian/lidaning`), not through the obsidian-vault
MCP container, whose sessions hung mid-run on 2026-09-27. Everything also goes
to `~/.claude/state/claude-maxer.log.jsonl`. Manual `status`/`--dry-run`
calls are never written to the vault. If
this file can't be parsed, `run` logs `skill_error` there and does nothing.

## Commands

```
./run_maxer_work.sh status          # usage, today's budget, parsed tasks/settings, run decision, next tick action
./run_maxer_work.sh run --dry-run   # gate decision + the first task's full prompt
./run_maxer_work.sh open --dry-run  # what the opener would do
./run_maxer_work.sh off             # switch off until `on`
./run_maxer_work.sh off --until 3d  # or 2h, 30m, 18:00, 2026-10-01, "2026-10-01 08:00"
./run_maxer_work.sh on              # switch back on
./run_maxer_work.sh weekly off      # ignore the weekly (7d) limit; also takes --until
./run_maxer_work.sh weekly on       # respect it again (today's budget ceiling applies)
./run_maxer_work.sh b2b on          # back-to-back windows; also takes --until
./run_maxer_work.sh b2b off         # open windows in the pin hours only
```

**The switch.** `off` writes `~/.claude/state/claude-maxer-off.json`; while
it exists, every `open` and `run` a tick starts does nothing and logs
`skipped: switched off …` (so the vault log still shows the machine is alive),
and a run already in progress stops starting new tasks. `--until` expires it
by itself. The crontab stays untouched. When the user asks to pause, disable,
stop, resume or re-enable claude-maxer, run these commands. The cloud backup
ping (`claude-maxer-daily-ping` routine) can't see this file; it only opens a
window and spends almost nothing, but pause it via the schedule skill if the
user wants zero activity.

**The weekly switch.** `weekly off` writes
`~/.claude/state/claude-maxer-weekly-off.json`; while it exists, `run`
ignores today's weekly-budget ceiling and fills every open window to
`target_5h`. The 5h target, the window timing and the main off switch still
apply. About 7pp of the week goes per full window, so four windows a day can
use up the week in a few days. Once 7d reaches 100% Anthropic locks you out
(interactive use too) until the weekly reset. `--until` works as for `off`.
`status` shows the switch, and each run's log line notes when the ceiling was
ignored. When the user asks to ignore, disable, drop, respect or re-enable
the weekly limit, run these commands.

**The back-to-back switch.** `b2b on` writes
`~/.claude/state/claude-maxer-b2b.json`; while it exists, the tick opens a
new window as soon as the last one has reset, at any hour, so no time
passes with no window open. Without it (the default) windows open only in
the pin hours, which keeps them on fixed slots but leaves gaps after a
drifted reset and between 04:00 and 08:00. Only the opening changes: each
window is still filled in its last hour, and the 5h target, the weekly
budget and the main off switch apply as before. An opening ping costs
almost nothing. `show` and `status` print the switch. When the user asks to
turn back-to-back (b2b, chained windows) on or off, run these commands.

Any setting can be overridden for a manual test with env `MAXER_<KEY>`,
e.g. `MAXER_CONCURRENCY=1`.
