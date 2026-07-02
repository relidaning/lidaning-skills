---
name: coding-orchestrate
description: >
  Activate when a session starts, the user starts a new task, asks "what's
  next?", makes a design decision, or ends a session (update SESSION.md).
  Tracks session state, TODOs, and memories, and keeps README.md current.
---

## Principles

This is the skill that tells the agent what's going on: current goals,
history, and open items.

### When to activate

- Session start — read prior state before doing anything else
- New task, or the user asks "what's next?"
- A design decision is made — record it
- Session end — update SESSION.md before exiting

### Description files

- **`.claude/SESSION.md`**: Per-session log with goals, what was done, current state, and decisions. 1–2 sentences per session. **Update before every exit.**
- **`.claude/TODO.md`**: Items discovered during the conversation, format `- [ ] item`.
- **`.claude/MEMORIES.md`**: Things the user explicitly asked you to remember. Add when they say "remember xxx...".
- **`README.md`**: Key concepts, core features, and mechanisms of current app. Including how to install it or use it.
