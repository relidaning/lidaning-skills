# SESSION.md

Records what happened in each coding session. The file lives at
`.claude/SESSION.md` (under the project root). Update it **before every exit** —
when the user types `/exit` or the session ends.

> **Safety net:** the `SessionEnd` hook in `~/.claude/settings.json` runs a
> headless Claude that also writes this file automatically, so the entry is
> guaranteed even if the skill is not explicitly invoked at exit.

## Format

Keep it short. 1–2 sentences per session is enough — just enough to remember
what happened when you come back.

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
- **1–2 sentences** — a title line and a body line. No sections, no bullet
  lists. If it needs more, the session was too broad.
- **Include decisions inline** — if you made a non-obvious choice, mention
  the why in the same sentence. No separate Decisions section.
- **Read on resume** — when the user says "continue", read the last session
  entry first to understand where things left off.
