---
name: coding-orchestrate
description: >
  Track coding session progress with TODO lists, session summaries, and
  README maintenance. Use when the user starts a new task, asks "what's next"
  or "where are we", makes a design decision, wants a progress summary, or
  asks to update the README.
---

## Overview

This skill keeps four files at the project root in sync with reality:

- **[SESSION.md](sessions.md)** — 1–2 sentences per session.
  **Update before every exit.**
- **[TODO.md](todos.md)** — things discovered during conversation that need
  doing. Add as they surface.
- **[MEMORIES.md](memories.md)** — things the user explicitly asked you to
  remember. Add when they say "remember that…".
- **[README.md](readme.md)** — key concepts, core features, and mechanisms
  of the project. Keep it current.

## General rules

- **Always check the current date before web search.** Web search results
  need the current year to be relevant. Query the date first, then include
  the year in search terms.

## Rules summary

| File        | When                                          | Why                                               |
| ----------- | --------------------------------------------- | ------------------------------------------------- |
| SESSION.md  | Before `/exit` or session end                 | 1–2 sentence summary of what happened |
| TODO.md     | As things are discovered in conversation      | Never lose a task to chat scroll                  |
| MEMORIES.md | When user says "remember that…"               | Persist explicit user preferences and conventions |
| README.md   | When concepts, features, or mechanisms change | Onboard new readers in 5 minutes                  |

## Additional resources

- For session format and rules, see [sessions.md](sessions.md)
- For TODO format and rules, see [todos.md](todos.md)
- For memories format and rules, see [memories.md](memories.md)
- For README guidelines, see [readme.md](readme.md)
