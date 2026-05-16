# steps.md

Teaching progress and evaluation. Lives at `.learning-instruct/steps.md`.
Tracks which compositions have been taught, what was covered, and the
evaluation results.

## Format

```markdown
# Teaching Steps

## Part 1: Generic functions — done

### Taught
- Declaring type parameters with `<T>`
- Type inference from arguments
- Constraints with `extends`

### Exercise
User wrote a generic `first<T>(arr: T[]): T` and a constrained `merge<U, V>`
function. Handled edge cases correctly.

### Notes
Understood inference quickly but needed an extra example for constraints.

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

- **One part at a time** — don't teach the next until the current one clicks
- **Capture specific examples** — record the code or problems the user worked
  through; they're useful context when resuming
- **Exercise every part** — the user must apply the concept, not just hear
  about it
- **Evaluation is honest** — "Needs work" is more useful than polite
  "Proficient". The point is to find gaps.
- **Recommendations are actionable** — "Study more" is useless. "Rebuild the
  generic `Promise.all` type from scratch" is concrete.
- **Mark progress clearly** — each part is `done`, `in progress`, or `not started`
