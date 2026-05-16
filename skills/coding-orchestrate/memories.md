# MEMORIES.md

Things the user explicitly asked you to remember. The file lives at the project
root as `MEMORIES.md`. Add entries when the user says "remember that…",
"don't forget…", "note for next time…", or similar.

## Format

```markdown
# Memories

## 2026-05-15 — Use tabs not spaces in this project
**Context:** User noticed I was indenting with spaces during the refactor.
**What to remember:** All files in this repo use tabs. Configure editor accordingly.

## 2026-05-15 — Don't auto-run tests
**Context:** After I ran `npm test` unprompted.
**What to remember:** The test suite hits a shared staging DB. Only run tests
when the user explicitly asks.
```

## Rules

- **One file** — `MEMORIES.md` at project root
- **Explicit requests only** — the user must ask you to remember something.
  Don't infer memories from conversation. This keeps the file high-signal.
- **Add immediately** — when the user says "remember that…", add it right
  then. Don't wait until session end.
- **Include context** — a short note on *why* this was worth remembering.
  Helps future-you judge whether it still applies.
- **Don't duplicate** — check the existing list before adding
- **Read on session start** — when resuming work, check MEMORIES.md to
  recall user preferences and conventions
- **Remove stale entries** — if a memory no longer applies, delete it
- **Delete when empty** — if all memories are removed, delete the file
