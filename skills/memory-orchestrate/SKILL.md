---
name: memory-orchestrate
description: >
  Activate at session start or resume ("continue", "where were we?", "what
  did we do last time?"), when the user says "remember..." something, after
  a non-obvious design decision or a newly established project concept, and
  before session end (update SESSION.md). Project memory orchestration:
  recalls and records the project's session history (SESSION.md), its core
  concepts (CLAUDE.md Key Concepts, README.md), and user-stated memories
  (.claude/MEMORIES.md). Not a task tracker — tasks belong to tasks-queue.
---

## What this skill is for

It keeps the project's memory: **what happened** (sessions), **how the
project works** (core concepts), and **what the user told you to keep**
(memories). An agent that starts cold should be able to catch up from these
files alone.

| File | Holds | Rules |
|---|---|---|
| `SESSION.md` (project root, git-tracked) | One entry per session, newest first | [sessions.md](sessions.md) |
| `CLAUDE.md` → **Key Concepts** section | Core concepts, mechanisms, non-obvious decisions, gotchas — for agents | [concepts.md](concepts.md) |
| `README.md` | Concepts and features — for humans | [readme.md](readme.md) |
| `.claude/MEMORIES.md` (local, gitignored) | Things the user explicitly asked you to remember | [memories.md](memories.md) |

Tasks are **not** tracked here. The user's only task list is the vault's
`Tasks.md` (the `tasks-queue` skill). Never create `.claude/TODO.md`; if a
task surfaces, mention it and offer to add it via `tasks-queue`.

## Workflow

### 1. On start / resume — recall

1. Read the top 3 entries of `SESSION.md`, all of `.claude/MEMORIES.md`, and
   skim `CLAUDE.md`'s Key Concepts headings (they are already in context if
   CLAUDE.md is loaded — don't re-read it).
2. Give the user a recap of at most 5 lines: where the last session left
   off, anything it says is uncommitted/unfinished/pending the user's
   go-ahead, and any memory that bears on the current request.
3. Treat claims in these files ("fixed", "committed", "saved") as
   unverified. Spot-check anything you are about to rely on against the
   code, `git log`, or the file on disk.

Skip the recap if the user's first message is a self-contained question
unrelated to prior work — just answer it.

### 2. During the session — capture as it happens

- User says "remember…" → add to `.claude/MEMORIES.md` **now**, not at exit.
- A new concept, mechanism, or non-obvious decision (with its *why*) is
  established → merge it into `CLAUDE.md` Key Concepts per
  [concepts.md](concepts.md). If it changes what the project does for a
  human user, update `README.md` too.

### 3. Before exit — record

1. Prepend a `SESSION.md` entry per [sessions.md](sessions.md).
2. Re-check that step 2's concepts made it into CLAUDE.md/README.
3. Verify the writes landed (`git diff --stat`) before saying they did.

A `SessionEnd` hook (`~/.claude/hooks/summarize-session.sh`) runs a headless
Claude that also appends a SESSION.md entry and merges new concepts into
CLAUDE.md. It is a safety net, not a replacement: it only sees the
transcript, may duplicate an entry you already wrote (check the top entry
first), and does not fire when the terminal is killed without its fallback.
