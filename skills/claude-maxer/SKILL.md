---
name: claude-maxer
description: >
  Trigger this skill when the request contains 'In order to untilize my claude limitation ...',   'to max my claude limitation ...', 
  'as my limitation of claude subscription has xx left ...', '5h', '7d', etc. Users want to leverate their Claude subscriptions. 
  Check if the background script exists, make one if it doesn't. Execute tasks follow the strategies.
---

# Claude-maxer

Pins the 5h usage window to fixed clock times, then fills each window to
~95% during its last hour with news-digest work written to the vault. All
logic lives in `maxer.py` (its docstring is the full spec). Cron calls it
through `run_maxer_work.sh`, which supplies the HOME/PATH/proxy env that cron
lacks.

## Window plan

24h is not a multiple of 5h, so at most four windows a day can repeat on
fixed times:

| window      | opened by                          | filled by `run` |
| ----------- | ---------------------------------- | --------------- |
| 03:00–08:00 | `open` at 03:00 (+ remote at 03:10) | 07:00–07:50     |
| 08:00–13:00 | `open` at 08:00 (+ remote at 08:10) | 12:00–12:50     |
| 13:00–18:00 | `open` at 13:00 (+ remote at 13:10) | 17:00–17:50     |
| 18:00–23:00 | `open` at 18:00 (+ remote at 18:10) | 22:00–22:50     |
| 23:00–03:00 | nothing (4h buffer)                | —               |

- No ping at 23:00. A window opened then would run to 04:00 and swallow the
  03:00 one. If you work in the buffer and open a window yourself, that day's
  03:00 pin is lost, and the 08:00 pin restores the schedule.
- If the previous window is still open because it started late, `open` waits
  for that reset (up to 20 min) and pings right after it.
- The remote routine `claude-maxer-daily-ping`
  (`trig_01NMTNTnaybi5FP4XqKx5uBs`, cron `10 0,5,10,19 * * *` UTC) is the
  backup opener in case the local one fails. When the local one worked, it
  lands inside the open window and costs one Haiku word.

## Filling a window (`run`, cron every 15 min)

A tick does nothing unless a window is open and resets within 10–65 min. It
never opens a window itself. In that last hour it starts news-digest tasks in
batches (up to 3 in parallel). After each batch it refreshes usage and sizes
the next batch from how much 5h% the last one used. It stops when:

- 5h usage reaches **95%**, or one more task (sized from the last batch)
  would push it past 98%. Hitting 100% would lock you out until the reset;
- 7d usage passes its **pace line**, `95% × (fraction of the week elapsed) + 5%`.
  This is the binding limit: one full window costs ~7pp of the week, so four
  a day would use up the weekly cap in about three days. Expect only about
  two windows a day to reach 95%;
- the reset is less than 10 min away. Running tasks are killed 2 min before
  the reset, because a request after it would open an off-schedule window.

Each task is `claude -p` on Opus with only WebSearch/WebFetch available (no
MCP, no write tools). It collects 10 stories from the last 48h in one domain,
rotating through ai, big-tech, world, security, dev, science, markets and
china-tech. Stories already in that day's note are passed in so they aren't
repeated.

## Output (vault, written only when tasks run)

- `claude-maxer/news/YYYY-MM-DD.md`: all of the day's digests in one note,
  one `## HH:MM · Topic` section per task.
- `claude-maxer/log/YYYY-MM-DD.md`: one block per run, with a line per
  task and per batch (5h after it) and a stop reason.

Notes are written straight to the vault folder
(`/data/nextcloud_client/obsidian/lidaning`), not through the obsidian-vault
MCP container, whose sessions hung mid-run on 2026-09-27. Skips, pings and
errors go only to `~/.claude/state/claude-maxer.log.jsonl`. The old
`claude-maxer/usage/` notes (a line every 15 min) are no longer written.

## Commands

```
./run_maxer_work.sh status          # usage, pace line, and whether run would act now
./run_maxer_work.sh run --dry-run   # gate decision + sample prompt, no work
./run_maxer_work.sh open --dry-run  # what the opener would do
./enroll_cron.sh install|remove|status|print   # the managed crontab block
```

Tunables (env): `MAXER_TARGET_5H` (95), `MAXER_WEEKLY_TARGET` (95),
`MAXER_WEEKLY_SLACK` (5), `MAXER_CONCURRENCY` (3), `MAXER_MODEL`
(claude-opus-5-5), `MAXER_BUDGET_USD` (5 per task).

The `*/15` crontab line running `fetch_usage_oauth.py` (outside the managed
block) keeps the usage snapshot fresh for the statusline. It shares
`/tmp/claude-usage-fetch.lock` with maxer.py, because the OAuth refresh token
is single-use.
