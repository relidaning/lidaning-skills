---
name: claude-maxer
description: >
  Activate when the user asks about Claude Pro/Max usage limits, the 5-hour
  rolling window, weekly (7-day) quota, or mentions "claude-maxer". Documents
  and manages the scheduled keep-alive + opportunistic-work routine that
  maximizes Claude subscription utilization.
---

# claude-maxer

A hybrid cloud + local system that (1) opens Claude Pro's 5-hour rolling
usage window at fixed points in the day, and (2) opportunistically runs real
work in that window when there's quota headroom — instead of a pure no-op
ping.

## Why hybrid

The cloud routine (claude.ai scheduled routines / `RemoteTrigger`) is
reliable regardless of whether this machine is on, but runs in an isolated
sandbox with **no access to real usage numbers** — there is no tool or API
that exposes a Claude Pro/Max account's actual 5h/7d usage percentage to a
running session, cloud or local.

The only place that number genuinely exists is the `rate_limits` object the
Claude Code harness passes to the **statusLine hook** on every render during
an interactive session on this machine — and it's not persisted anywhere by
default. So the usage-aware part of this system has to run locally, where
that data is available; the pure window-opening ping can safely stay in the
cloud.

## Components

### 1. Cloud ping (window opener)

- **Routine name:** `claude-maxer-daily-ping`, **ID:** `trig_01NMTNTnaybi5FP4XqKx5uBs`
- **Cron (UTC):** `0 3,8,13,17,22 * * *` = 06:00/11:00/16:00/21:00/01:00 Asia/Shanghai
- Fires a trivial Haiku 4.5 "reply ack" prompt against this repo — no real
  work, just exists to start/extend the 5h window at each slot.
- Manage via the `schedule` skill or https://claude.ai/code/routines.
- The API forces the default tool preset regardless of `allowed_tools: []`
  requested at creation (platform limitation) — low-risk since the prompt
  forbids taking any action.

### 2. Usage snapshot cache (local)

`~/.claude/scripts/statusline.py` was patched to write every render's
`rate_limits` payload to `~/.claude/state/usage_snapshot.json` (with a
`cached_at` timestamp). This is a passive side effect of normal interactive
use — no daemon, nothing runs when the machine is idle/off. Consequence: the
snapshot is only as fresh as your last interactive session.

### 3. Usage gate

`skills/claude-maxer/check_usage.py` reads that snapshot and exits 0
(proceed) or 1 (skip), printing its reasoning:
- No snapshot yet, or unreadable → skip
- `five_hour` or `seven_day` `used_percentage` >= 95 → skip
- Otherwise → proceed, **regardless of the snapshot's age**

Age is deliberately not a gate: headless work never refreshes the snapshot
(see caveat below), so gating on staleness would cap every loop at ~30
minutes no matter what. If nothing else updates the cache mid-loop, it stays
below the skip threshold for the whole run — the loop's iteration/wall-clock
caps (below) are the real backstop, not this check.

### 4. Local cron (usage check + real work, looped)

A real OS crontab entry (not the session-scoped `CronCreate` — that only
fires while a Claude Code REPL is idle, unreliable for 1am/6am with nothing
open) runs at **05:02/10:02/15:02/20:02/00:02** Asia/Shanghai — 1 hour
*before* each cloud ping slot, so the long-term work has run its course
before the next window-opening ping fires:

```
2 5,10,15,20,0 * * * /data/apps/lidaning-skills/skills/claude-maxer/run_maxer_work.sh >> /tmp/claude-maxer-cron.log 2>&1
```

`run_maxer_work.sh` loops rather than running one task and exiting:

1. Before each iteration: runs `check_usage.py`; if it says skip, logs and
   breaks out of the loop.
2. Otherwise picks one of the 4 work types at random each iteration (not a
   fixed cycle — `ITER` resets to 1 on every fresh cron fire, so a
   deterministic order would mean short runs always land on the same first
   type), running it headlessly via
   `claude -p --model claude-sonnet-5 --output-format json --max-budget-usd 3
   --dangerously-skip-permissions` in this repo. `--max-budget-usd 3` is a
   per-call safety net, not a loop-level budget.
3. Logs every iteration (ran/skipped/failed + cost + running total) to
   `~/.claude/state/claude-maxer.log.jsonl`.

**Loop stop conditions** (whichever hits first):
- usage gate returns skip (missing snapshot, or either window >= 95%)
- `MAX_ITERATIONS` (8) reached
- `MAX_MINUTES` (50) elapsed — leaves headroom before the next cron fire,
  which is ~5h later

**Important caveat:** real per-iteration usage % is not observable here.
`claude -p` (any `--output-format`) never includes `rate_limits` in its
output — that field only exists in the interactive statusLine hook payload
(confirmed by testing `--output-format json` directly), which never fires in
headless/print mode. So across a whole loop, the usage gate is really only
checking whatever the last *interactive* session on this machine last saw,
not what the loop itself has been consuming. The iteration/wall-clock caps
exist because of this — without them the loop would have no real stop
condition short of an actual interactive session pushing the cached % over
95%.

This only fires opportunistically — if the machine is off or asleep at a
slot, that slot's work silently doesn't happen (the cloud ping still opens
the window regardless).

**Cron PATH gotcha:** cron runs with a minimal `PATH` (just
`/usr/bin:/bin`-ish), which does not include `claude`, `git`, `gh`, or `npm`
from their real install locations (`~/.local/bin`, nvm's node bin, etc). The
first real fire hit exactly this (`claude: command not found`, logged in
`/tmp/claude-maxer-last-run.log`). `run_maxer_work.sh` now explicitly
prepends those dirs to `PATH` at the top of the script — if any of those
tools get reinstalled to a different path (e.g. a node version bump changes
the nvm path), update that `export PATH=...` line.

## The 4 work types

Each prompt tells the headless agent it's running unattended and to stay
within scope:

- **skill-audit** — SkillOpt-style pass over `skills/*`: score trigger
  clarity + body quality per CLAUDE.md's criteria, bounded edits (≤4) for
  anything under 8/10, re-score to confirm improvement.
- **todo-triage** — read `.claude/TODO.md`, implement 1-2 small unambiguous
  items, check them off.
- **dep-audit** — read-only `npm outdated`/`npm audit` across Node
  subprojects under `skills/`, report only if something's new since the last
  report. Never runs install/update/audit-fix.
- **papers-digest** — pull trending papers from
  https://huggingface.co/papers/trending, summarize 2-3 via WebFetch, write
  a note to the Obsidian vault via the `obsidian-local` skill.

**Safety gate:** skill-audit, todo-triage, and dep-audit all work on a new
`claude-maxer/<type>-<timestamp>-i<iteration>` branch and open a **draft
PR** — never push to master directly. The iteration suffix keeps branch
names unique when the same type recurs within one loop run. papers-digest
only writes to the Obsidian vault, not the repo, so it needs no PR.

## Inspecting / adjusting

- Live routine: `schedule` skill, or https://claude.ai/code/routines
  (deletion also goes through that URL — can't delete via API)
- Local cron: `crontab -l` / `crontab -e`
- Run history: `~/.claude/state/claude-maxer.log.jsonl`
- Last headless run's full output: `/tmp/claude-maxer-last-run.log`
- Test the gate/work-selection without actually running work:
  `skills/claude-maxer/run_maxer_work.sh --dry-run`
