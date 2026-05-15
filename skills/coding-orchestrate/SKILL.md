---
name: coding-orchestrate
description: >
  Track coding session progress with TODO lists, session summaries, and
  README maintenance. Use when the user starts a new task, asks "what's next"
  or "where are we", makes a design decision, wants a progress summary, or
  asks to update the README.
---

## Overview

This skill keeps three files at the project root in sync with reality:

- **[SESSION.md](sessions.md)** — what happened each session.
  **Update before every exit.**
- **[TODO.md](todos.md)** — things discovered during conversation that need
  doing. Add as they surface.
- **[README.md](readme.md)** — key concepts, core features, and mechanisms
  of the project. Keep it current.

## Rules summary

| File | When | Why |
|---|---|---|
| SESSION.md | Before `/exit` or session end | Record what happened, current state, decisions |
| TODO.md | As things are discovered in conversation | Never lose a task to chat scroll |
| README.md | When concepts, features, or mechanisms change | Onboard new readers in 5 minutes |

## Additional resources

- For session format and rules, see [sessions.md](sessions.md)
- For TODO format and rules, see [todos.md](todos.md)
- For README guidelines, see [readme.md](readme.md)
