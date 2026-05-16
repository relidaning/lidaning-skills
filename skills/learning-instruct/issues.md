# ISSUES.md

A log of problems encountered during learning and how they were resolved.
Lives at `.learning-instruct/ISSUES.md`. Records misunderstandings, tricky
concepts that blocked progress, errors made on exercises, gaps exposed by
quizzes, and what fixed them.

## Format

```markdown
# Issues

## 2026-05-16 — Confused distributive conditional types

**What happened:** User thought `T extends string ? "yes" : "no"` would
always return `"yes"` for `string`, even when `T` was `string | number`.
Expected `"yes" | "no"` but couldn't explain why.

**Root cause:** Didn't understand that conditional types distribute over
unions when the checked type is a bare type parameter.

**How we fixed it:**
- Walked through `Extract<string | number, string>` step by step on paper
- Showed the comparison with `[T] extends [string]` (non-distributive)
- User rebuilt `Extract` from scratch without looking

**Lesson:** Distributive behavior is invisible until you hit a union. Need
to visualize the distribution step explicitly.

## 2026-05-16 — Forgot array case in DeepReadonly scenario

**What happened:** User's `DeepReadonly<T>` worked for objects but mapped
`T[]` to `ReadonlyArray<T>` without making elements readonly too.

**Root cause:** Treating arrays as opaque — forgetting `Array<T>` is just
an object with numeric keys and a `length`.

**How we fixed it:**
- Walked through what `ReadonlyArray<T>` actually does vs `DeepReadonly<T>`
- User realized arrays need recursive readonly on their element type
- Added array-specific clause to the type

**Lesson:** Always check what standard library types actually guarantee.
Don't assume `ReadonlyArray<T>` is "deep enough" for your use case.
```

## Rules

- **Write when something goes wrong** — a quiz answer missed, a scenario
  solved incorrectly, a concept the user struggled to grasp, a blocker
  that took real work to resolve
- **Capture root cause** — not just what happened, but *why* it happened.
  What gap in understanding led to the issue?
- **Record the fix** — what specifically resolved it. An explanation, an
  exercise, a visualization, a counterexample.
- **Extract the lesson** — what to watch for next time. The general
  principle behind this specific issue.
- **Don't log trivial mistakes** — a typo or syntax error isn't an issue.
  Reserve this for genuine understanding gaps.
- **Date each entry** — makes it easy to scan and reference later
