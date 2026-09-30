# Core concepts (CLAUDE.md → Key Concepts)

The project's core concepts live in the **Key Concepts** section of the
project-root `CLAUDE.md`, because that file is loaded into every session —
a concept written there is recalled automatically, one written anywhere
else has to be looked up. The `SessionEnd` hook writes to the same place.

## What belongs

- **Mechanisms** — how a part of the project actually works, especially
  where it differs from what the code's names suggest.
- **Decisions with their why** — "X instead of Y, because Z". A decision
  without its reason gets undone by the next session.
- **Gotchas** — verified failure modes, with the symptom, the root cause,
  and the fix, so the next session recognizes them.
- **Boundaries** — what a component deliberately does *not* do, and who
  owns that instead.

## What doesn't

- What happened in a session (→ `SESSION.md`).
- Things derivable from the code, `git log`, or `--help`.
- Unverified claims. Verify first, or mark it as unverified.
- Tasks (→ vault `Tasks.md` via `tasks-queue`).

## Format

One bold lead sentence stating the concept, then the explanation:

```markdown
**Installed SKILL.md files are symlinks** — `install.sh` symlinks each
top-level `*.md` file into `<skills>/<name>/`, so edits take effect
immediately, but a new `.md` file needs a reinstall.
```

## Rules

- **Merge, don't append** — find the existing concept on the same topic and
  update it. Add a new one only if no existing one covers it.
- **Correct stale entries** — if a concept turns out wrong, fix it in place
  and say what changed and when; don't leave the old claim standing.
- **Absolute dates** — "2026-09-29", never "today" or "last week".
- **Only project-level** — a one-off fact from a single chat is not a
  concept.
