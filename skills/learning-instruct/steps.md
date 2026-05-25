# steps.md

Teaching progress and a detailed knowledge reference. Lives at
`.learning-instruct/steps.md`. Tracks which compositions have been taught,
but more importantly records the full scope of knowledge shared — every
explanation, example, insight, edge case, variant, connection, and exercise —
so the user can review and recall the material later without re-reading
the chat. This file is the **complete transcript of teaching**, not an
outline or summary.

## Format

```markdown
# Teaching Steps

## Part 1: Generic functions — done

### Concepts explained

**Type parameters** — `<T>` declares a type variable that the caller provides.
```ts
function identity<T>(value: T): T {
  return value;
}
```
The compiler infers `T` from the argument unless you specify it explicitly.

**Inference** — TypeScript narrows `T` from the argument type at each call
site. `identity("hello")` infers `T = string`. Works positionally with
multiple parameters.

**Constraints** — `extends` restricts what `T` can be:
```ts
function getProperty<T extends { id: number }>(obj: T) {
  return obj.id; // OK — T is guaranteed to have id
}
```
Misuse: over-constraining. If you only need `.id`, constrain to `{ id: number }`,
not `{ id: number; name: string }`.

**Multiple type parameters** — functions can declare more than one type
parameter. Order matters for inference — leading parameters infer first,
trailing ones must be explicit.
```ts
function pair<T, U>(first: T, second: U): [T, U] {
  return [first, second];
}
```

**Optional type parameters** — default types for when the caller doesn't
specify:
```ts
function createMap<K, V = string>(): Map<K, V> { ... }
```

### Full coverage checklist

Every subtopic in this composition part. Nothing skipped:

- [x] Declaring type parameters (`<T>`)
- [x] Inference from arguments
- [x] Constraints (`extends`)
- [x] Multiple type parameters and inference order
- [x] Default type parameters
- [x] Explicit type argument syntax (`identity<string>(...)`)
- [x] Generic arrow functions (`const fn = <T>(x: T) => x`)
- [x] What you CAN'T do with generics (no `new T()`, no `instanceof T`)

### Edge cases discussed
- What happens when no argument matches the constrained position
- Inference with union arguments: `identity<string | number>("hello")` infers
  `T = string | number` only if the argument is typed that way
- Inference fails with conflicting candidates — TS errors, doesn't pick one

### Exercise & outcome
User wrote `first<T>(arr: T[]): T | undefined` — handled empty array case.
Then wrote `merge<T extends object, U extends object>(a: T, b: U): T & U`.
Got both right; minor stumble on empty-array return type.

### Notes
Understood inference quickly. Constraints needed an extra example — the "why"
clicked when we compared `{ id: number }` vs `extends { id: number }` side
by side.

## Part 2: Generic interfaces — in progress

...

## Evaluation

### Scores

| Area | Rating | Notes |
|---|---|---|
| Generic functions | Mastered | Strong on inference and constraints |
| Generic interfaces | Proficient | Understands mapped types but slow to apply |
| Conditional types | Needs work | Confuses distributive behavior |
| Generic classes | Not yet evaluated | — |
| Advanced patterns | Not yet evaluated | — |

### Recommendations

1. **Revisit conditional types** — work through the `Extract`/`Exclude` examples
   again, then build a custom `DeepPartial<T>`
2. **Practice generic interfaces** — convert the user's existing project types
   to generics as an exercise
```

## Rules

- **Write the full knowledge, not highlights** — after teaching a concept,
  record every explanation, code example, edge case, variant, connection to
  other concepts, and common mistake discussed. Someone reading this file
  should be able to learn the material, not just see a list of topic names.
- **Coverage checklist required** — each part must include a checklist of
  EVERY subtopic that falls under it. Mark each as taught. The checklist
  ensures nothing slips through. Audit it before marking a part done.
- **One part at a time** — don't teach the next until the current one clicks
- **Code examples are essential** — include every code snippet written or
  shown. The user will review these later; seeing the actual code is better
  than reading a description of it.
- **Don't skip the "boring" parts** — a concept's edge cases, limitations,
  and what-you-can't-do are often more valuable than the happy path. Cover
  them and record them.
- **Exercise every part** — the user must apply the concept, not just hear
  about it. Record what they built and how it went.
- **Evaluation is honest** — "Needs work" is more useful than polite
  "Proficient". The point is to find gaps.
- **Recommendations are actionable** — "Study more" is useless. "Rebuild the
  generic `Promise.all` type from scratch" is concrete.
- **Mark progress clearly** — each part is `done`, `in progress`, or `not started`
- **Update as you teach** — don't batch the write for the end. After each
  concept, add it to steps.md while it's fresh. The user can review at any
  point and see current progress.
