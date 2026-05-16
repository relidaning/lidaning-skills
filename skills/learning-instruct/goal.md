# GOAL.md

The user's learning goal. Lives at `.learning-instruct/GOAL.md` in the project
root. Created once when the user starts a new learning track.

## Format

```markdown
# Learning Goal

**Subject:** TypeScript generics
**Goal level:** Able to write and debug complex generic types in a production
codebase
**Background:** Comfortable with basic TypeScript — interfaces, unions,
narrowing. Never used generics beyond `Array<T>`.
**Date set:** 2026-05-16
```

## Rules

- **Read the project first** — before asking the user what they want to learn,
  scan CLAUDE.md, SESSION.md, TODO.md, MEMORIES.md, and recent git history.
  Form a best guess so the user can confirm rather than type from scratch.
- **One goal at a time** — completing or abandoning the current goal replaces
  this file
- **Be specific** — "Learn Rust" is too vague. "Be able to contribute to a
  Rust CLI tool at work" is actionable
- **Capture background** — what does the user already know? Prevents re-teaching
  and sets the starting point
- **Goal level is measurable** — "understand" is vague; "able to build X" or
  "pass Y certification" is concrete
- **Don't overwrite** — if GOAL.md exists, the user is mid-track. Ask if they
  want to continue or start fresh
