---
name: coding-orchestrate
description: >
  Track coding session progress with TODO lists, session summaries, and
  README maintenance. Also the recording layer — knows where every skill's
  output should be persisted and handles the I/O. Use when the user starts a
  new task, asks "what's next" or "where are we", makes a design decision,
  wants a progress summary, or asks to update the README.
---

## Overview

This skill has two jobs:

1. **Orchestrate** — keep project-level files in sync with reality
2. **Record** — persist skill-generated content to the right location

It's the only skill that knows *where* things go. Other skills (like
learning-instruct) generate content but don't know about file locations,
the vault, or the I/O mechanism. This skill routes their output.

### Orchestration files (project root)

- **[SESSION.md](sessions.md)** — 1–2 sentences per session.
  **Update before every exit.**
- **[TODO.md](todos.md)** — things discovered during conversation that need
  doing. Add as they surface.
- **[MEMORIES.md](memories.md)** — things the user explicitly asked you to
  remember. Add when they say "remember that…".
- **[README.md](readme.md)** — key concepts, core features, and mechanisms
  of the project. Keep it current.

### Recording layer

When other skills produce structured output (study plans, teaching materials,
key concepts, reference notes), this skill persists them to the Obsidian vault
under `obsidian-rag/`. It uses the obsidian-local skill's tools or the REST
API directly.

The vault path mapping:

| Source | Vault path |
|---|---|
| learning-instruct GOAL.md | `obsidian-rag/GOAL.md` |
| learning-instruct compositions.md | `obsidian-rag/compositions.md` |
| learning-instruct steps.md | `obsidian-rag/steps.md` |
| learning-instruct subject file | `obsidian-rag/<Subject>.md` |
| learning-instruct ISSUES.md | `obsidian-rag/ISSUES.md` |
| learning-instruct DOCUMENTATIONS.md | `obsidian-rag/DOCUMENTATIONS.md` |
| learning-instruct docs/ | `obsidian-rag/docs/` |
| Key concepts surfaced in conversation | `obsidian-rag/<topic>.md` |

## Rules summary

| File | When | Why |
| ---- | ---- | --- |
| SESSION.md | Before `/exit` or session end | 1–2 sentence summary of what happened |
| TODO.md | As things are discovered in conversation | Never lose a task to chat scroll |
| MEMORIES.md | When user says "remember that…" | Persist explicit user preferences |
| README.md | When concepts, features, or mechanisms change | Onboard new readers in 5 minutes |

## Recording rules

- **Vault is the target** — learning-instruct output and key concepts go to
  `obsidian-rag/` in the Obsidian vault, not local `.learning-instruct/`
- **Write through obsidian-local** — use `obsidian_write_note` or direct
  REST API PUT to `https://127.0.0.1:27124/vault/obsidian-rag%2F<file>`
- **Keep vault and local in sync** — if a local copy exists at
  `.learning-instruct/`, update it too, but the vault copy is authoritative
- **Other skills don't know about I/O** — learning-instruct generates content
  and hands it off. This skill decides where it lands
- **Record proactively** — when a key concept, insight, or reference is
  surfaced in conversation, write it to the vault without being asked

## Additional resources

- For session format and rules, see [sessions.md](sessions.md)
- For TODO format and rules, see [todos.md](todos.md)
- For memories format and rules, see [memories.md](memories.md)
- For README guidelines, see [readme.md](readme.md)
