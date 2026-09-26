# steps.md

Teaching progress and a detailed knowledge reference. Lives at
`.learning-instruct/steps.md`. Tracks which leaves have been taught, but more
importantly records the full walkthrough — every symptom hit, every
resolution performed, why each fix worked, and the depth that came out of it —
so the user can review and recall the material later without re-reading the
chat. This file is the **complete transcript of teaching**, not an outline or
summary.

It is organized **by leaf, in the order taught** — the same causal sequence
the user lived through. It is deliberately not organized by concept: a
concept-indexed record is what the subject file (`<Subject>.md`) is for, and
splitting the record into "concepts covered" over here and "exercises done"
over there is exactly what makes a learning track feel like two unrelated
things bolted together.

## Format

```markdown
# Teaching Steps

## Part 1: Diagnose the misuse — done

Stage goal: reproduce the untyped/`any` failure and pin down what caller code
is doing wrong.

### Leaf 1.1: A caller passes `{ name: string }` where `{ id: number }` was required, and it compiles anyway — done

**What went wrong.** In `src/config/load.ts` the user called
`parseConfig({ name: "svc-a" })` against a helper whose callers are supposed
to pass `{ id: number }`. `tsc` reported no error; the failure only showed up
at runtime as `undefined` where an id was expected.

**How we fixed it.** Walked the actual repro:
1. Reproduced with a 4-line file, confirmed `tsc --noEmit` stayed silent.
2. Inspected the signature — `parseConfig(input: any): any`.
3. Replaced the `any` parameter with a type parameter:
   ```ts
   function parseConfig<T>(input: T): T { ... }
   ```
4. Re-ran `tsc --noEmit` — the bad call still compiled, which set up the next
   leaf, but the return type stopped being `any`.

**Why it worked.** The `any` on the parameter was erasing the caller's type
before it could ever be checked — `any` is assignable both to and from
everything, so the compiler had nothing left to compare. A type parameter
keeps the caller's actual type flowing through the function instead of
flattening it, which is why the return type became useful immediately even
though the argument check didn't tighten yet.

**Why this is the standard answer.** This is *generic type parameters* — the
industry-standard way to write a function that is polymorphic over its input
without giving up type information. The trade-off it buys: you keep one
implementation instead of N overloads, and pay for it with a signature the
caller has to be able to infer.

**Depth written to the subject file.** Type parameters, call-site inference,
explicit type arguments, generic arrow function syntax, and what you can't do
with a type parameter (`new T()`, `instanceof T`) — all written to
`TypeScript-Generics.md` under Key Concepts.

**Understanding check.** Asked what would happen if only the return type had
been changed to `T` and the parameter left `any`. User answered correctly
(inference has nothing to infer *from*, `T` falls back to `unknown`) — which
is the exact setup for the next leaf.

### Leaf 1.2: You add `<T>` but every call site infers `T = unknown` — in progress

...

## Evaluation

### Scores

| Area | Rating | Notes |
|---|---|---|
| Diagnose the misuse | Mastered | Strong on inference and where `any` erases checks |
| Constrain the signature | Proficient | Understands mapped types but slow to apply |
| Fix inference at call sites | Needs work | Confuses distributive behavior |

### Recommendations

1. **Revisit conditional types** — work through the `Extract`/`Exclude` examples
   again, then build a custom `DeepPartial<T>`
2. **Practice generic interfaces** — convert the user's existing project types
   to generics as an exercise
```

## Rules

- **Organized by leaf, in taught order** — one `### Leaf N.M: <the symptom>`
  section per leaf, under its part, in the sequence the user actually worked
  through. Never regroup the record by concept, and never split it into a
  "concepts" section plus a separate "exercises" section — the resolution IS
  the exercise, and the concept IS the explanation of that resolution
- **Record all four beats** — every leaf section carries **what went wrong**,
  **how we fixed it**, **why it worked** (the mechanism), and **why this is
  the standard answer** (the named concept plus its trade-off). A leaf
  section missing the "why" halves is incomplete no matter how detailed the
  steps are
- **Write the full knowledge, not highlights** — record every command run,
  code example, error message, edge case, variant, connection, and common
  mistake discussed. Someone reading this file should be able to follow the
  same path themselves, not just see a list of topic names
- **Show the chain** — each leaf section should make clear how its symptom
  followed from the previous leaf's fix. If it doesn't, say so plainly rather
  than inventing a link — an unchained leaf is a signal the composition needs
  reshaping (see compositions.md)
- **Code examples are essential** — include every snippet written or shown,
  and the actual output/error where it matters. The user will review these
  later; seeing the real code and the real error beats a description of them
- **Don't skip the "boring" parts** — a concept's edge cases, limitations,
  and what-you-can't-do are often more valuable than the happy path. Cover
  them, and point at the subject file where the exhaustive version lives
- **Point at the depth, don't duplicate it** — the leaf section names what
  was written to `<Subject>.md`; the full treatment lives there, not here
- **Evaluation is honest** — "Needs work" is more useful than polite
  "Proficient". The point is to find gaps
- **Recommendations are actionable** — "Study more" is useless. "Rebuild the
  generic `Promise.all` type from scratch" is concrete
- **Mark progress clearly** — each leaf and each part is `done`,
  `in progress`, or `not started`
- **Complete the linked besmart task on mastery** — besmart's `plan_tasks`
  are a WBS tree; only leaves carry completion state (a parent's checkmark
  is derived from its children). As each `(leaf #N)`-tagged sub-item is
  covered, immediately run `besmart_sync.py complete-task <plan_id>
  <leaf_id>` — don't wait for the whole part. For a part with no leaf
  breakdown, complete its `(besmart task #N)` id directly once the part is
  done. When every part in the plan is done, also run `besmart_sync.py
  complete-plan <plan_id>`. Don't batch any of this for Phase 4 — besmart's
  dashboard/streak should reflect progress as it happens
- **Update as you teach** — don't batch the write for the end. After each
  leaf, add its section to steps.md while it's fresh. The user can review at
  any point and see current progress
