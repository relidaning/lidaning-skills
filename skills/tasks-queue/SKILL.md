---
name: tasks-queue
description: >
  Activate when the request mentions tasks or spare capacity — "tasks", "my
  tasks", "task list", "Tasks.md", "what's next to do", "any undone tasks",
  "leverage the limitation", "use up my limit", "spare quota/usage", "what can
  Claude work on", or "tasks-queue". Owns the user's priority queue of work:
  the vault's `Tasks.md` is the highest-priority tier, then one daily news
  batch, then optimizing the user's apps under /data/apps, then more news.
  Decides what runs next (`tasks_queue.py next`), and lists, picks and
  checks off items via `list|pick|mark|news|optimize`. An unattended caller
  (claude-maxer) decides only when there is quota and asks it for work.
---

# tasks-queue

The user's priority queue of work. **It decides what runs next**
(`next`) and checks vault tasks off. The caller decides only *when* there
is quota to spend; see [Scheduling](#scheduling).

## Priority

| Order | Source | Done when |
|---|---|---|
| 1 (highest) | undone items in the vault's `Tasks.md` | `mark` checks it off |
| 2 | one [news](#news-tasks) batch, the first time the queue is drained each day | once per day |
| 3 | [Optimize tasks](#optimize-tasks): one app under `/data/apps` per task | never; apps rotate, least recently visited first |
| 4 (lowest) | more [news tasks](#news-tasks), as filler | never; they rotate and repeat |

- A `Tasks.md` task always goes first, whenever there is one.
- News gets one early slot per day (the daily digest stays fresh), then
  drops below optimization. The queue remembers the day in
  `~/.claude/state/tasks-queue-news-day.json`; the caller reports it with
  `news-ran` once it starts that batch.
- Anything outside this queue, such as a caller's own built-in default
  tasks, ranks below all of it and runs only when the queue can't be read.
- When the user asks what to work on, or wants to use leftover
  quota, run `pick` first and offer that task before anything else.
- Never track or propose tasks anywhere but `Tasks.md`. It is the only
  authoritative list of specific work; the optimize and news tiers are
  standing categories the user set up, not task lists.

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
python3 tasks_queue.py next [--small] [--skip "<vault task>"]...
                                        # the next task as JSON: {kind: vault, text}
                                        # | {kind: news, why: daily|filler} | {kind: optimize, ...}
python3 tasks_queue.py news-ran         # today's news batch has started
python3 tasks_queue.py pick             # first undone task text; exit 1 if none
python3 tasks_queue.py list             # all undone tasks as "lineno<TAB>text"
python3 tasks_queue.py mark "<text>"    # rewrite that line as "- [x] <text>"
python3 tasks_queue.py news             # news tasks as JSON [{title, prompt}]
python3 tasks_queue.py optimize         # next app as JSON {app, path, base, branch, worktree,
                                        #   repo, remote, pr, prompt}; exit 1 if none
python3 tasks_queue.py optimize-done <app> <skip|optimized|findings|failed> [note]
python3 tasks_queue.py optimize-list    # every app visited so far, with its status
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

**This queue owns the order; the caller owns the clock.** `next` applies
the [Priority](#priority) table. The caller (claude-maxer) decides whether
there is quota, and whether the returned task fits in what's left of the
window: if a repo task (vault/optimize) is too big, it asks again with
`--small` and gets news. It passes `--skip` for vault tasks it won't run
(already tried this run, or failed too often). Two rules from past runs:

- **One quota spender.** Add work to this queue, not a new cron loop. Two
  loops sharing one quota pool each pass the usage gate on their own while
  together exhausting the 5h window. That is why the old standalone `*/30`
  runner was removed on 2026-08-10.
- **Mark only verified work.** A caller marks a vault task only after
  checking that the work landed (e.g. a new commit exists), never on the
  worker's word alone.

## Optimize tasks

Order 3. Each task takes **one app** under `/data/apps`, reads its code,
finds what is worth improving (memory, CPU, latency, stability,
power-efficiency, startup time, disk/log growth, or whatever else matters
for that app), fixes the best of it, and reports what it did.

- `optimize` picks the app visited least recently (never-visited first).
  Non-git directories are skipped without a session: the work has to land
  as a reviewable commit. `lidaning-skills` is never picked, because the
  worker would be editing the scheduler that runs it.
- On an app's first visit the worker decides whether it is a real app
  (runs in the background, or is installed as a command) or a toy,
  learning, data-only or abandoned project. A skip is recorded and never
  revisited; delete the app's entry in
  `~/.claude/state/tasks-queue-optimize.json` to have it looked at again.
- **Every fix ends as a PR.** The worker never touches the app's own
  checkout: it works in a fresh git worktree on a new `opt/<app>-<stamp>`
  branch cut from the remote's base branch, so your uncommitted work and
  current branch don't matter. It pushes over https and opens a PR with
  `gh`, only when origin is your own GitHub repo (`relidaning/*`). For
  anything else (jellyfin-web's origin is upstream jellyfin) the commits
  stay on a local branch.
- The caller runs the prompt below in the app's directory with full tools,
  records the outcome with `optimize-done`, files the worker's report in
  the vault, and removes the worktree afterwards (the branch stays). It
  counts "optimized" only if the PR exists (or, with no PR allowed, the
  local branch has a new commit).
- Rotation means each real app is revisited later with fresh eyes; the
  previous reports in the vault note are the worker's starting point.

```optimize-prompt
You are running unattended. Your job: make one of the user's apps better where it
actually matters, deliver the fix as a pull request, and report what you did. The
app is `{app}` at `{path}`, and you are in that directory.

1. Decide what it is. Read the README, CLAUDE.md, entrypoints, Dockerfile /
   docker-compose.yml, and check whether it is running now (`docker ps`, `ps`,
   `systemctl --user`, crontab, `~/.local/bin`). A real app runs in the background
   or is installed as a command. If it is a toy, a learning exercise, a
   data-only folder, or abandoned, stop here and report APP: skip.
2. If a report from an earlier visit exists at
   `/data/nextcloud_client/obsidian/lidaning/claude-maxer/optimize/{app}.md`, read it
   first, and check its PRs (`gh pr list --repo {repo} --state all --search "head:opt/"`).
   Don't redo what was done or is waiting in an open PR; follow up on what it left open.
3. Find the gaps. Look for what costs the most for how this app is used:
   memory (leaks, unbounded caches, large images/containers), CPU (busy loops,
   polling where an event would do, redundant work), latency (N+1 queries,
   missing indexes, sync I/O on hot paths), stability (unhandled errors, missing
   restart policy/healthcheck, retries without backoff, unbounded log files),
   power-efficiency (idle wakeups, tight poll intervals, always-on work that could
   be on demand), and anything else you judge important. Measure the current state
   where you can without disturbing it: `docker stats --no-stream`, `ps`, RSS,
   timings of a local run, query plans, image size, log size.
4. Choose. Rank the findings by impact over risk and fix the top one to three
   that you can verify. Prefer small, contained changes over rewrites.
5. Make the change in a separate worktree, never in `{path}` itself:
       git -C {path} fetch {remote} {base}
       git -C {path} worktree add -b {branch} {worktree} FETCH_HEAD
   (If the fetch fails, use the local `{base}` instead of FETCH_HEAD.) Edit, build
   and test only in `{worktree}`.
6. Verify. Run the app's existing lint/typecheck/build/test steps for what you
   touched. Measure again the same way as before (a local run in the worktree) so
   you can state before -> after. If you can't measure a change, say so; never
   invent numbers.
7. Commit in `{worktree}` on `{branch}`. {pr_rule}

Rules:
- Do not restart, redeploy or rebuild a running service, container or installed
  command, and don't edit crontab, systemd units, or files outside `{worktree}`.
  If a change needs a redeploy to take effect, say so under "Left for the user".
- Never commit to `{base}` or any existing branch, never force-push, never merge.
- No sudo, no deleting user data, no dependency upgrades beyond what a fix needs.
- If the best fix needs a decision from the user, don't make it: report it.

Reply with a report in exactly this shape (it is filed verbatim into the vault):

### What it is
One or two lines: what the app does, how it runs, whether it is running now.

### Findings
A numbered list. Each: the metric (memory / CPU / latency / stability / power /
other), what you found with file:line, and the evidence (a measurement or the code).

### What I chose and why
Which findings you acted on, and why those over the others.

### What changed
Per change: what you did and the result as before -> after with how you measured
it (or "not measurable here: <why>").

### Left for the user
Findings you didn't act on, redeploys needed, decisions to make. "Nothing" if so.

End with exactly these three lines:
APP: skip <one-line reason> | optimized | findings <one-line reason nothing was committed>
BRANCH: {branch} | none
PR: <PR url> | none
```

## News tasks

Order 2 once a day, then order 4.
 Each `### Title` is one task; its body says *what* to collect, and
the caller adds output rules (numbered, linked items, no invented URLs).
They rotate in order across runs. Add, remove or reword freely.

A title ending in `(daily)` is pinned instead: it runs in every day's first
batch, never as filler, so it produces exactly one section a day. Its
prompt also gets the past 7 days' titles to skip, not just today's.

Papers also has a memory: every paper it proposes is stored in rag-chroma's
`papers` collection, listed in the next prompt as already covered, and a
repeat that slips through anyway (same arXiv ID, or the same paper reworded
or linked elsewhere) is dropped before the note is written. See
claude-maxer's `maxer.py` (`PAPER_TASKS`).

### Papers (daily)
Find the 5 AI, machine learning and deep learning research papers most worth reading right now. Each must be either very important (a major lab's model or technique report, or a result the field is actively building on) or clearly trending in the last 7 days (high on Hugging Face Daily Papers, alphaXiv or arXiv trending, or widely discussed on X, Reddit or Hacker News). Prefer papers from the last 2 weeks; include an older paper only if it newly became important. At least one of the 5, listed last, must instead be a foundational paper of any year that shaped how AI, machine learning or deep learning developed (for example backpropagation, AlexNet, dropout, Adam, the Transformer, scaling laws); vary the era and area from day to day, and for it the "Chosen because" sentence names what later work it inspired. Link the arXiv abstract page (arxiv.org/abs/…) when there is one, otherwise the paper's official page. Use the first author's lab or the org as Source and the submission date as the date. The first sentence says what the paper does; the second starts with "Chosen because" and gives the reason with its evidence (e.g. upvote count, who released it, or who is discussing it).

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
