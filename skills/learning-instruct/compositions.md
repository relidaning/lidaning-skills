# compositions.md

The subject broken into teachable parts. Lives at
`.learning-instruct/compositions.md`. Created after researching the goal topic.

## Format

```markdown
# Compositions

1. **Generic functions** — declaring type parameters, inference, constraints
2. **Generic interfaces and types** — parameterized interfaces, mapped types
3. **Conditional types** — `extends` in type position, `infer`, distributive
   behavior
4. ~~**Generic classes** — type parameters on classes, static vs instance~~
   *Skipped — user already knows class generics from Java; not worth time*
5. **Advanced patterns** — template literal types, recursive types, branded
   types
```

Deprioritized items use ~~strikethrough~~ on the name and description, with
an italicized reason on the next line. They stay in the numbered list so the
original plan is visible. Renumber if an item is removed from the middle.

## Rules

- **3–8 parts** — fewer than 3 is probably too coarse; more than 8 is
  overwhelming
- **Logical order** — each part should build on the previous ones
- **Named, not numbered in the file** — parts are numbered for sequence but
  have descriptive names
- **Research-backed** — don't guess the breakdown. Search for how the topic
  is taught in reputable courses, books, or documentation
- **User-approved** — present the breakdown and let the user reorder, add,
  remove, or rename parts before locking it in
- **One concept per part** — if a part has an "and" in its name, consider
  splitting it
- **Strikethrough over delete** — when a part turns out to be unimportant,
  already known, or not worth time, mark it with ~~strikethrough~~ and add
  an italicized reason instead of removing it. The original plan stays
  visible. The user can see what was considered and why it was dropped
