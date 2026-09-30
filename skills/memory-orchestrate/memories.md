# MEMORIES.md

Things the user explicitly asked you to remember. The file lives at
`.claude/MEMORIES.md` (under the project root). Add entries when the user
says "remember that…", "don't forget…", "note for next time…", or similar.

## Format

```markdown
# Memories

## 2026-05-15 — Don't auto-run tests
**Context:** After I ran `npm test` unprompted.
**What to remember:** The test suite hits a shared staging DB. Only run tests
when the user explicitly asks.
```

## Rules

- **One file** — `.claude/MEMORIES.md`
- **Explicit requests only** — the user must ask you to remember something.
  Don't infer memories from conversation. This keeps the file high-signal.
- **Add immediately** — when the user says "remember that…", add it right
  then. Don't wait until session end.
- **Include context** — a short note on *why* this was worth remembering.
  Helps future-you judge whether it still applies.
- **Don't duplicate** — check the existing list before adding
- **Verify stated facts** — if the memory is a claim about the code ("this
  repo uses X"), check it against the codebase first; if it doesn't match,
  tell the user and record what they want, not the unverified claim
- **Read on session start** — when resuming work, check MEMORIES.md to
  recall user preferences and conventions
- **Remove stale entries** — if a memory no longer applies, delete it
- **Delete when empty** — if all memories are removed, delete the file
