# compositions.md

The subject broken into teachable parts. Lives at
`.learning-instruct/compositions.md`. Created after researching the goal topic.

## Format

```markdown
# Compositions

1. **Generic functions** *(besmart task #101)* — declaring type parameters,
   inference, constraints
   - **Install/setup** *(leaf #201)* — nothing to install; TS project already exists
   - **Concept: type parameters & inference** *(leaf #202)* — `<T>`, call-site inference, constraints
   - **Demo: write a constrained generic function** *(leaf #203)* — real exercise against the user's code
   - **Interview Q** *(leaf #204)* — "Why can't you `new T()` inside a generic function?"
2. **Generic interfaces and types** *(besmart task #102)* — parameterized
   interfaces, mapped types
3. **Conditional types** — `extends` in type position, `infer`, distributive
   behavior
4. ~~**Generic classes** — type parameters on classes, static vs instance~~
   *Skipped — user already knows class generics from Java; not worth time*
5. **Advanced patterns** — template literal types, recursive types, branded
   types
```

`*(besmart task #N)*` on a numbered part is optional — only present when
GOAL.md has a `BeSmart plan` and this part was pushed to (or pulled from)
that plan's `plan_tasks`. besmart's `plan_tasks` are a WBS tree
(`parent_task_id`/`sort_order`), so a part maps to a **parent** task —
parents have no completion state of their own, it's derived from their
children. Parts with no besmart plan omit the tag entirely.

Sub-bullets under a part with `*(leaf #N)*` are optional finer-grained
steps pushed as **children** of that part's besmart task (via
`besmart_sync.py create-task <plan_id> ... --parent-task-id <parent_id>`).
This is where Phase 3 actually calls `complete-task` — only leaves are
completable; besmart derives the parent's checkmark once every leaf is
done. Not every part needs a leaf breakdown — add one when the part is big
enough that "install / concept / demo / interview question" sub-steps add
real value, and skip it for small parts where the part-level task is
granular enough on its own.

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
- **Sync new parts to besmart** — if GOAL.md has a `BeSmart plan`, every part
  without a `(besmart task #N)` tag needs a parent task created via
  `besmart_sync.py create-task <plan_id> ...` before compositions.md is
  considered final. Strikethrough parts are not pushed (nothing to complete)
- **Sync leaf sub-steps the same way** — when a part gets a leaf breakdown,
  each leaf without a `(leaf #N)` tag needs a child task via
  `besmart_sync.py create-task <plan_id> ... --parent-task-id <parent_id>`.
  Use `besmart_sync.py tree <plan_id>` to check the live structure matches
  this file before considering it final
