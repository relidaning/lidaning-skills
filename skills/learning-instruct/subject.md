# Subject reference file

A living reference of the subject being learned — ALL key concepts, quiz
questions with answers, scenarios with solutions, and gotchas. Lives at
`.learning-instruct/<Subject>.md`, named after the subject itself (e.g.,
`TypeScript-Generics.md`, `Rust-Ownership.md`). Accumulates as the user
progresses, so they can review anytime to memorize and reinforce.

This file is the **comprehensive study guide** for the subject. It must
contain every important point, not just highlights. Someone reading this
file cold should walk away with a solid understanding of the topic — it's
a standalone reference, not a cheat sheet.

The file is created during Phase 2 (Compose) when the subject is confirmed.
Update it as teaching goes — every quiz, scenario, and key concept adds to it.

## Format

```markdown
# Subject Reference: <Subject Name>

## Key Concepts

### Generic constraints (`extends`)

**Core idea:** Limits a type parameter to types that extend (are assignable to)
a given type. `<T extends HasId>` means T must have an `id` property.

**How it works:** The compiler checks each type argument against the constraint
at the call site. If the argument doesn't satisfy the constraint, it's a
compile error. The constraint also serves as a "capability grant" — once T
extends HasId, you can access `id` on values of type T inside the function
body.

**Use cases:**
- Accessing known properties on an otherwise unknown type
- Enforcing a minimum interface that callers must satisfy
- Narrowing a generic to work with a specific category of types

**Variants:**
- Single constraint: `<T extends SomeType>`
- Multiple constraints via intersection: `<T extends A & B>`
- Constraint using another type parameter: `<T extends U, U>`
- Self-referential constraint: `<T extends Comparable<T>>`

**Edge cases & limitations:**
- You can't constrain to a union directly; `extends string | number` accepts
  any type narrower than the union, not just `string` or `number`
- Constraints don't narrow the return type — the caller still sees `T`, not
  the constrained type
- `extends {}` accepts anything except `null` and `undefined`

**Connections:**
- `extends` in constraints vs. `extends` in conditional types — same keyword,
  different mechanism (restriction vs. branching)
- Related to bounded polymorphism / bounded quantification in other languages

**Common mistakes:**
- Over-constraining: `<T extends { id: number; name: string }>` when you
  only need `id` — constrain to what you use
- Confusing constraint position with conditional type position

### Conditional types

**Core idea:** A type-level conditional that picks between two branches based
on assignability. `T extends U ? X : Y` — if T is assignable to U, resolve
to X; otherwise Y.

**How it works:** The compiler evaluates the condition at compile time. When
the checked type is a concrete type, the result is immediate. When it's a
generic parameter, evaluation is deferred until instantiation. When the
checked type is a bare type parameter that's a union, the conditional
**distributes** over the union members.

**Use cases:**
- Extracting types: `T extends Promise<infer V> ? V : never`
- Filtering unions: `T extends string ? T : never` → `Extract<T, string>`
- Type-level mapping: transforming one type to another based on structure
- Excluding types: `T extends any[] ? never : T` → `Exclude<T, any[]>`

**Variants:**
- Simple conditional: `T extends U ? X : Y`
- Nested conditional: `T extends A ? X : T extends B ? Y : Z`
- Conditional with `infer`: `T extends Array<infer E> ? E : never`
- Distributive conditional (bare type parameter as checked type)

**Distributive behavior — critical detail:**
When the checked type is a **bare** type parameter, the conditional
distributes over unions: `Extract<'a' | 1, string>` becomes
`('a' extends string ? 'a' : never) | (1 extends string ? 1 : never)` = `'a'`.
To disable distribution, wrap in a tuple: `[T] extends [U] ? X : Y`.

**Edge cases & limitations:**
- `T extends never` — the never branch always wins because never is the
  empty union; distribution over an empty union produces never (nothing)
- `any` in conditional types: `any extends U ? X : Y` resolves to `X | Y`
  (both branches), because `any` is both assignable to and not assignable
  to everything
- Deeply nested conditionals become unreadable — extract to named helper types
- Conditional types can't reference themselves directly (no recursion without
  a level limit in some versions)

**Common mistakes:**
- Forgetting distribution: writing `T extends U ? X : Y` and being surprised
  when union Ts explode the result
- Using `T extends null` when you mean `T extends null | undefined` — they're
  different
- Expecting `T extends string ? "yes" : "no"` to narrow T to string in the
  true branch (it doesn't, not in the way a runtime check does)

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
- `keyof any` is `string | number | symbol` — not just `string`.
- `T extends {}` accepts everything except `null` and `undefined`.
```

## Rules

- **Comprehensive, not concise** — each concept entry should cover: core idea,
  how it works (mechanics), when to use it, variants/forms, edge cases &
  limitations, connections to other concepts, and common mistakes. A reader
  should understand the concept from this file alone, without needing the
  chat transcript.
- **Don't skip subtleties** — if a concept has a tricky edge case, a surprising
  behavior, or an exception, include it. These details are what separate
  surface familiarity from real understanding.
- **Cover ALL key concepts** — every concept taught in steps.md should appear
  here. If a concept matters enough to teach, it matters enough to document
  in full. No "highlights only" — include everything.
- **Accumulate as you go** — after each quiz or scenario, write the question,
  answer, and user's performance to this file. After explaining a key concept,
  add it to the Key Concepts section immediately while details are fresh.
- **User-visible** — tell the user when you add to the subject file. This file
  is their study guide; they should know it's growing.
- **Quiz answers are definite** — write the correct answer, not a summary of
  the user's response. Note if the user got it right or wrong.
- **Scenario notes** — capture what the user did well and what they missed.
  Model answers are welcome.
- **Gotchas are high-value** — these are the things that trip people up.
  Collect them aggressively. Every concept has gotchas; find them.
- **Keep it organized** — sections clearly separated. Newest entries at the
  bottom within each section.
