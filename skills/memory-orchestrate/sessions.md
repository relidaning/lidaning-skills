# SESSION.md

Records what happened in each coding session. The file lives at
`SESSION.md`, at the project root — not under `.claude/` (that would make it
gitignored; the session log is meant to be versioned). Update it **before
every exit** — when the user types `/exit` or the session ends.

> **Safety net:** the `SessionEnd` hook (`~/.claude/hooks/summarize-session.sh`)
> runs a headless Claude that also writes an entry from the transcript. Check
> the top entry before writing, so the same session isn't logged twice.

## Format

Keep it short — a title line and a body of 1–5 sentences: what was done,
any non-obvious decision and its why, and **what was left unfinished** (the
part the next session needs most).

```markdown
# Sessions

## 2026-05-15 — Implement user authentication
Added JWT-based login (POST /auth/login, token validation middleware, 12 tests).
Middleware wired but not yet required on protected routes.
```

If a non-obvious decision was made, fold it into the summary rather than
adding a separate section:

```markdown
## 2026-05-16 — Switch to Redis for sessions
Moved session store from Postgres to Redis to cut login latency.
Used ioredis over node-redis — cleaner API, better cluster support.
```

## Rules

- **One file** — `SESSION.md` at project root, newest session first
- **Update before exit** — capture what happened before the session ends.
  Don't wait until the user asks.
- **1–5 sentences** — a title line and one paragraph. No sections, no bullet
  lists.
- **State what's pending** — uncommitted work, unapplied fixes, anything
  waiting on the user. Say "Uncommitted." when it is.
- **Include decisions inline** — if you made a non-obvious choice, mention
  the why in the same sentence. No separate Decisions section.
- **Read on resume** — when the user says "continue", read the last session
  entry first to understand where things left off.
