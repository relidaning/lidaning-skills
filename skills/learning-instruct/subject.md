# Subject reference file

A living reference of the subject being learned — key concepts, quiz
questions with answers, scenarios with solutions, and gotchas. Lives at
`.learning-instruct/<Subject>.md`, named after the subject itself (e.g.,
`TypeScript-Generics.md`, `Rust-Ownership.md`). Accumulates as the user
progresses, so they can review anytime to memorize and reinforce.

The file is created during Phase 2 (Compose) when the subject is confirmed.
Update it as teaching goes — every quiz, scenario, and key concept adds to it.

## Format

```markdown
# Subject Reference: <Subject Name>

## Key Concepts

### Generic constraints (`extends`)
**What it is:** Limits a type parameter to types that extend a given type.
**Example:** `<T extends HasId>` means T must have an `id` property.
**Why it matters:** Lets you access known properties on a generic type safely.

### Conditional types
**What it is:** A type that picks between two branches based on a condition.
**Example:** `T extends string ? "text" : "other"`
**Why it matters:** Enables type-level branching — the foundation of mapped
conditional types and infer.

## Quiz Log

### Q: What's the difference between `extends` in a generic constraint vs. in a conditional type?
**Answer:** In a constraint (`<T extends U>`), it restricts what T can be.
In a conditional (`T extends U ? X : Y`), it checks assignability at the
type level and branches — no restriction, just logic.

### Q: Why does `T extends never` never resolve to the true branch?
**Answer:** Because `never` is the empty union — distributive conditional
types distribute over unions, and distributing over an empty union
produces... nothing (never).

## Scenario Log

### S: Build a `DeepReadonly<T>` type
**Problem:** Write a generic type that makes all properties of T readonly,
recursively into nested objects. Handle arrays.
**Solution:** [user's solution or model answer]
**Notes:** User handled objects correctly but forgot arrays need `readonly`
on the array type itself, not just `ReadonlyArray<T>`.

## Gotchas

- Distributive conditional types only kick in when the checked type is a
  bare type parameter. `[T] extends [U]` disables distribution.
- `never` is the identity element of unions — `T | never` is just `T`.
```

## Rules

- **Accumulate as you go** — after each quiz or scenario, write the question,
  answer, and user's performance to this file. After explaining a key concept,
  add it to the Key Concepts section.
- **Concise entries** — each concept entry is 2–4 lines. A definition, an
  example, and why it matters. Not a re-explanation of the whole topic.
- **User-visible** — tell the user when you add to SUBJECT.md. This file is
  their study guide; they should know it's growing.
- **Quiz answers are definite** — write the correct answer, not a summary of
  the user's response. Note if the user got it right or wrong.
- **Scenario notes** — capture what the user did well and what they missed.
  Model answers are welcome.
- **Gotchas are high-value** — these are the things that trip people up.
  Collect them aggressively.
- **Keep it organized** — sections clearly separated. Newest entries at the
  bottom within each section.
