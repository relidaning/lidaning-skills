# SESSION.md

Records what happened in each coding session. The file lives at the project
root as `SESSION.md`. Update it **before every exit** — when the user types
`/exit` or the session ends.

## Format

```markdown
# Sessions

## 2026-05-15 — Implement user authentication

### Goal
Add JWT-based login flow to the API.

### What we did
- Created POST /auth/login endpoint
- Added token generation and validation middleware
- Wrote integration tests (12 passing)

### Current state
Middleware wired into Express but not yet required on protected routes.

### Decisions
- Used `jsonwebtoken` over `passport` — fewer dependencies, sufficient
- Token expiry set to 24h after discussion with frontend team
```

## Rules

- **One file** — `SESSION.md` at project root, newest session first
- **Update before exit** — capture what happened before the session ends.
  Don't wait until the user asks.
- **Goal at the top** — set at session start, update if it changes
- **What we did** — meaningful steps completed, not every file edit
- **Current state** — what's in progress, what's blocked, what's next.
  Critical for fast context resumption.
- **Decisions** — capture why, not just what. Non-obvious choices only.
- **Read on resume** — when the user says "continue", read the last session
  entry first to understand where things left off.
