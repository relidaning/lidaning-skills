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
sandbox without this machine's credential file, so it can't check usage
before deciding to work.

Locally there are two sources for real usage numbers, both feeding
`~/.claude/state/usage_snapshot.json`: the **OAuth usage endpoint**
(component 2b — primary; works headlessly, no browser or login), and the
`rate_limits` object the Claude Code harness passes to the **statusLine
hook** on every render during an interactive session (passive fallback,
only fresh while you're actively using Claude Code). So the usage-aware
part of this system runs locally; the pure window-opening ping can safely
stay in the cloud.

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

### 2b. OAuth usage fetcher (headless-safe refresh, primary source)

`skills/claude-maxer/fetch_usage_oauth.py` closes the "snapshot only
refreshes during interactive sessions" gap: it GETs
`https://api.anthropic.com/api/oauth/usage` — the same endpoint the CLI's
`/usage` screen uses — authenticating with the Claude Code OAuth
`accessToken` from `~/.claude/.credentials.json` (header
`anthropic-beta: oauth-2025-04-20`). The response carries `five_hour` and
`seven_day` `utilization` + ISO `resets_at`, plus model-scoped weekly
limits (e.g. a per-model Fable cap). It writes the 5h/7d numbers into the
same `usage_snapshot.json` (tagged `"source": "oauth-api"`, scoped limits
under `scoped_limits`), so `check_usage.py` needs no changes.

- **No setup, no browser.** Discovered 2026-07-03; this replaced a
  Playwright scraper of claude.ai/new#settings/usage
  (`fetch_usage_web.py`, kept in the repo as a fallback) whose login flow
  Cloudflare's human-verification blocked.
- **Token freshness — fully self-sufficient:** access tokens live ~8h; the
  script refreshes an expired (or `--refresh`-forced) token itself via the
  same OAuth flow the CLI uses (`console.anthropic.com/v1/oauth/token`,
  Claude Code's public client_id) and atomically writes the rotated
  access+refresh tokens back to `~/.claude/.credentials.json` (0600) — the
  refresh token is single-use, so persisting the new one immediately is
  what keeps the CLI's own auth working too. A 401/403 mid-fetch triggers
  one refresh-and-retry. No interactive session is ever needed. Exit 0 =
  snapshot written, exit 2 = auth problem (refresh itself rejected —
  re-login with `claude` needed), exit 1 = other failure. On nonzero exit
  the cached snapshot is left untouched.
- **Background refresh:** a crontab entry runs it every 15 minutes
  (`*/15 * * * * HOME=/home/shake /usr/bin/python3 …/fetch_usage_oauth.py
  --vault-log > /tmp/claude-maxer-usage-fetch.log 2>&1`), so the snapshot
  stays fresh with zero interaction — the machine's other cron jobs can
  trust it. Verified to work under cron's stripped env (`env -i HOME=…`):
  the script defaults the proxy internally and needs only `HOME`. Querying
  the usage endpoint is metadata-only — it does not consume quota or open
  the 5h window.
- **Vault heartbeat (`--vault-log`):** each fetch appends one line to a
  daily note at `claude-maxer/usage/YYYY-MM-DD.md` via Obsidian's Local
  REST API. Format as of 2026-08-11:

  ```
  - 08:30 — 5h **100%** (resets 10:59), sonnet-5 'skill-audit ($0.42)'
  ```

  The trailing clause is the point of the note: a column of bare
  percentages can't answer the only question worth asking of it — a window
  went to 100%, in exchange for *what*? `run_maxer_work.sh` writes each
  iteration to `~/.claude/state/maxer_activity.json` and `_activity_suffix()`
  reads it, dropping records older than 30 min so an idle stretch doesn't
  re-attribute one run's work to every later heartbeat. 7d was dropped from
  the note the same day — it moves too slowly to earn a line every 15
  minutes, and is still in the snapshot for `check_usage.py`'s pro-rata gate — a human-visible proof the loop is alive, and a usage history
  over the day. It talks to `127.0.0.1:27123` directly (proxy bypassed),
  reading the token from `$OBSIDIAN_MCP_TOKEN` or parsing
  `~/.zshrc.local` under cron. Vault errors (Obsidian closed, plugin off)
  only print a `WARN` — the snapshot fetch still succeeds.
- **Proxy:** uses `$https_proxy`/`$http_proxy`, defaulting to
  `http://127.0.0.1:10808` (same xray requirement as `claude -p`).
- **Debugging:** `--raw` dumps the full API response; `--no-write` prints
  the parsed result without touching the snapshot.

`run_maxer_work.sh` calls this (best-effort, 60s timeout) before every
iteration's gate check, so the loop sees its own consumption instead of a
frozen snapshot.

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
open) drives this. Cadence was tightened from an hourly-offset schedule to
every 30 minutes on 2026-08-11 (a gated fire that skips costs one metadata
call, not quota, and the old 2h gap meant a window could reset unused):

```
*/30 * * * * /data/apps/lidaning-skills/skills/claude-maxer/run_maxer_work.sh >> /tmp/claude-maxer-cron.log 2>&1
```

Check `crontab -l` for the current state (enabled/disabled and cadence both
change over time — this file is documentation, not the source of truth).

`run_maxer_work.sh` loops rather than running one task and exiting:

1. Before each iteration: runs `check_usage.py`; if it says skip, logs and
   breaks out of the loop.
2. Otherwise picks a work type via `pick_work_type()` — a *weighted* draw
   (`WEIGHTS`), skipping any type that has hit its `DAILY_CAP` for the
   calendar day, counted from `ran` entries in the run log. Still random
   rather than a fixed cycle: `ITER` resets to 1 on every fresh cron fire,
   so a deterministic order would mean short runs always land on the same
   first type. If every type is capped, the loop logs and breaks. Runs it
   headlessly via
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

**Important caveat (now mitigated):** `claude -p` (any `--output-format`)
never includes `rate_limits` in its output — that field only exists in the
interactive statusLine hook payload, which never fires in headless/print
mode. Originally that meant the loop could never see its own consumption.
The OAuth usage fetcher (component 2b) fixes this: each iteration refreshes
the snapshot straight from the usage API before the gate check. If the
fetch fails (expired token, network), the loop silently degrades to the old
frozen-snapshot behavior, which is why the iteration/wall-clock caps stay
in place as the backstop.

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

**Cron proxy gotcha:** this machine only reaches `api.anthropic.com` through
a local proxy — v2rayN/xray listening on `127.0.0.1:10808` (check with
`ss -tlnp | grep 10808`), exported as `http_proxy`/`https_proxy` in the
interactive shell. Cron inherits none of the interactive shell's env, so
`claude -p` went out unproxied and the API returned `403 Failed to
authenticate` — indistinguishable from a real auth failure without digging
in (reproduced by running `env -i claude -p ...`, which hit the identical
error; adding the two proxy vars back fixed it). Also inherited the same
missing-env symptom: `HOME` was unset too, which breaks credential file
lookup (`~/.claude/.credentials.json` resolves to `/.claude/...`) — cron on
this box sets neither `HOME` nor a proxy. `run_maxer_work.sh` now explicitly
exports `HOME` and both proxy vars at the top, before the `PATH` fix. If the
proxy client/port ever changes, update those two `export` lines. Every
cron-fired iteration before this fix failed silently this way (8/8 failures
in one run, logged as `"status": "failed"` in `claude-maxer.log.jsonl` with
no real work done) — the loop's cost/iteration accounting still looked
fine (`$0` spent) because auth failures don't reach the API metering, so
this class of failure produces no cost signal to notice it by.

## The 5 work types

Each prompt tells the headless agent it's running unattended and to stay
within scope. The `weight`/`cap` columns are `WEIGHTS` and `DAILY_CAP` in
`run_maxer_work.sh`; cap `—` means uncapped.

| type | weight | cap/day | output |
|---|---|---|---|
| skill-audit | 3 | — | draft PR |
| todo-triage | 3 | — | draft PR |
| dep-audit | 2 | — | draft PR |
| papers-digest | 1 | 1 | vault note |
| news-digest | 1 | 1 | vault note |

**Why the mix is weighted (retuned 2026-08-11).** It used to be a uniform
draw over all five, which put 40% of every window into digests. The vault's
own record (`claude-maxer/usage/2026-08-11.md`) showed the 06:00 window
going 27% → 100% in ~40 minutes, and what the user could point at
afterwards was a handful of digest notes — *seven* for the one day, several
of them same-day duplicates, because every fire re-derived the day's digest
from scratch. Digests are cheap to produce and near-worthless on repeat, so
they are now down-weighted to ~20% combined *and* hard-capped at one note
per type per day, with the prompts told to append to the existing day's note
rather than create a `-2`/`-3` twin. The goal was never to spend less quota
— it is to stop paying digest prices for duplicate output.

- **skill-audit** — SkillOpt-style pass over `skills/*`: score trigger
  clarity + body quality per CLAUDE.md's criteria, bounded edits (≤4) for
  anything under 8/10, re-score to confirm improvement.
- **todo-triage** — read `.claude/TODO.md`, implement 1-2 small unambiguous
  items, check them off.
- **dep-audit** — read-only `npm outdated`/`npm audit` across Node
  subprojects under `skills/`, report only if something's new since the last
  report. Never runs install/update/audit-fix.
- **papers-digest** — pull trending papers from
  https://huggingface.co/papers/trending, summarize 2-3 via WebFetch, append
  to `claude-maxer/digest/papers-YYYY-MM-DD.md` in the vault.
- **news-digest** — pull the top 10 Hacker News front-page stories via its
  public API (`hacker-news.firebaseio.com`), pick the 3 most interesting by
  score/discussion, summarize via WebFetch, append to
  `claude-maxer/digest/news-YYYY-MM-DD.md`. Source choice: HN was picked as
  the default over Reddit/lobste.rs/
  GitHub Trending because it needs no auth, has a stable public API, and is
  the standard broad-coverage source for "what's interesting in tech today."
  If that turns out to be the wrong fit, swap the source in the
  `news-digest` case of `build_prompt()` in `run_maxer_work.sh`.

**Safety gate:** skill-audit, todo-triage, and dep-audit all work on a new
`claude-maxer/<type>-<timestamp>-i<iteration>` branch and open a **draft
PR** — never push to master directly. The iteration suffix keeps branch
names unique when the same type recurs within one loop run. papers-digest
and news-digest only write to the Obsidian vault, not the repo, so they
need no PR.

### Vault output convention

Everything this loop generates lives **under `claude-maxer/`** in the vault
— digests in `claude-maxer/digest/`, usage heartbeats in
`claude-maxer/usage/`. Set 2026-08-11 at the user's request; it narrows the
older "generated docs go to the vault root" preference, which still holds
for one-off docs a human asked for. The seven root-level digest notes from
before that were consolidated into `claude-maxer/digest/news-2026-08-11.md`
and `papers-2026-08-11.md`.

Two failure modes the digest prompts now name explicitly, both observed:

- **The filename must end in `.md`.** A fire once wrote
  `news-digest-2026-08-11` with no extension, so Obsidian didn't treat it
  as a note and no wiki-link could reach it. The REST API happily serves it
  anyway, and `GET /vault/<name>/` returns its *content* instead of a
  listing — which makes an extensionless file look like a folder in a probe.
- **zsh doesn't word-split unquoted expansions.** The Bash tool runs zsh, so
  `for id in $ids` over ids captured from a previous command iterates *once*
  with the whole string, building one URL full of spaces. Every HN fetch
  comes back empty and reads like an API flake. Use `${=ids}`, a zsh array,
  or do the fan-out in `python3`.

### Not yet implemented: the vault-tasks drain

A crontab comment claimed for a day that `run_maxer_work.sh` drains the
vault's `Tasks.md` as priority-1 work. It never did — grep it for
`Tasks.md` and you get nothing. The `vault-tasks` skill's own runner was
deleted 2026-08-11 (the user is implementing the drain here instead), so
**nothing drains that queue right now.** `skills/vault-tasks/vault_tasks.py`
provides `pick`/`list`/`mark`; that skill's SKILL.md documents the contract
the drain has to honor (commit direct to master in `/data/apps/myfollows`,
one task per run, mark only on success).

## Inspecting / adjusting

- Live routine: `schedule` skill, or https://claude.ai/code/routines
  (deletion also goes through that URL — can't delete via API)
- Local cron: `crontab -l` / `crontab -e` (work loop enabled since
  2026-08-10 21:22 at `*/30 * * * *`, unless later commented out — plus the
  15-min usage-snapshot refresh; its last run's output is in
  `/tmp/claude-maxer-usage-fetch.log`)
- Run history: `~/.claude/state/claude-maxer.log.jsonl`
- Last headless run's full output: `/tmp/claude-maxer-last-run.log`
- Test the gate/work-selection without actually running work:
  `skills/claude-maxer/run_maxer_work.sh --dry-run`
- Check current usage on demand:
  `python3 skills/claude-maxer/fetch_usage_oauth.py` (add `--no-write` to
  just look, `--raw` for the full API response). The Playwright fallback
  (`fetch_usage_web.py`) needs a one-time `--login` that Cloudflare's human
  check currently blocks — only reach for it if the OAuth endpoint dies.
