# steps.md

Teaching progress and a detailed knowledge reference. Lives at
`.learning-instruct/steps.md`. Tracks which compositions have been taught,
but more importantly records the actual knowledge shared — explanations,
examples, insights, edge cases, and exercises — so the user can review
and recall the material later without re-reading the chat.

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

### Key insights
- Inference beats explicit annotation in most cases — let TS do the work
- Constraints let you access known properties on an otherwise generic type
- Generic functions are functions that return the *same* type you pass in,
  not just `any`

### Edge cases discussed
- What happens when no argument matches the constrained position
- Inference with union arguments: `identity<string | number>("hello")` infers
  `T = string | number` only if the argument is typed that way

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

- **Write the knowledge, not just the outline** — after teaching a concept,
  record the explanation, code examples, key insights, and edge cases in
  steps.md. Someone reading this file should understand the material, not
  just see a list of topic names.
- **One part at a time** — don't teach the next until the current one clicks
- **Code examples are essential** — include the actual code written or shown.
  The user will review these later; seeing the code is better than reading a
  description of it.
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
