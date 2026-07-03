---
name: coding-orchestrate
description: >
  Activate at session start, when the user starts a new task or asks "what's
  next?", after a non-obvious design decision, or before session end (update
  SESSION.md). Tracks session progress via SESSION.md, TODO.md, MEMORIES.md,
  and README.md.
---

## Principles

This is the skill that tells the agent what's going on: prior sessions, open
TODOs, user-stated memories, and the project's current shape.

### Description files

- **`.claude/SESSION.md`**: To describe what we have done in what time, use 1–2 sentences per session. **Update before every exit.** See [sessions.md](sessions.md) for format and rules.
- **`.claude/TODO.md`**: Items discovered during the conversation, for later. See [todos.md](todos.md) for format and rules.
- **`.claude/MEMORIES.md`**: Things the user explicitly asked you to remember. Add when they say "remember xxx...". See [memories.md](memories.md) for format and rules.
- **`README.md`**: Key concepts, core features, and mechanisms of current app. Including how to install it or use it. See [readme.md](readme.md) for what a good README contains.
