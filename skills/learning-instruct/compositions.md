# compositions.md

The subject broken into teachable parts. Lives at
`.learning-instruct/compositions.md`. Created after researching the goal topic.

## Format

```markdown
# Compositions

**Problem:** A production TS library exposes a `parseConfig<T>()` helper that
callers keep misusing — wrong shapes slip through untyped, or inference gives
up and everything becomes `any`. Fixing it for real requires generics done
right: constrained type parameters, inference, and enough of the type system
to know why `new T()` doesn't work inside a generic function.

1. **Diagnose the misuse** *(besmart task #101)* — reproduce the untyped/`any`
   failure, pin down exactly what caller code is doing wrong
   - **A caller passes `{ name: string }` where `{ id: number }` was
     required, and it compiles anyway** *(leaf #201)* — reproduce it, see
     the untyped hole, name the fix direction: type parameters (`<T>`)
   - **You add `<T>` but every call site infers `T = unknown`** *(leaf
     #202)* — the specific inference-gives-up symptom, walked to a fix
   - **Two near-identical calls silently resolve to different overloads**
     *(leaf #203)* — a real symptom surfaced while diagnosing, worth its own
     fix before moving on
2. **Constrain the signature so bad calls can't compile** *(besmart task #102)*
   — now that `T` flows through, make it reject the shapes it should
   - **`<T>` accepts anything, so the bad call from leaf 1 still
     compiles** *(leaf #204)* — add `T extends { id: number }`, watch the
     original bug finally fail at compile time
   - **The constraint you added rejects a caller that was legitimately
     passing extra fields** *(leaf #205)* — over-constraining; narrow it to
     what the body actually reads
   - **A second helper needs the same shape and you've now written it
     twice** *(leaf #206)* — lift it into a parameterized interface
3. **Fix inference at the real call sites** *(besmart task #103)* — the
   constraint holds, but real callers still have to annotate by hand
   - **Callers must write `parseConfig<Cfg>(...)` explicitly or `T` widens
     to the constraint** *(leaf #207)* — inference order with multiple type
     parameters
   - **One call site passes a union and gets a result typed for the whole
     union instead of the branch it took** *(leaf #208)* — distributive
     conditional types, `[T] extends [U]` to switch it off
   - **You need the element type out of `Config[]` and there's no
     parameter to infer it from** *(leaf #209)* — `infer`
4. ~~**Handle the `new T()` edge case with a class-based variant**~~ — type
   parameters on classes, static vs instance
   *Skipped — user already knows class generics from Java; not worth time*
5. **Roll the fix out to every caller** — verify the original bug is dead
   - **The codemod misses arrow-function call sites** *(leaf #210)* —
     generic arrow function syntax and the `.tsx` ambiguity
   - **Two config kinds are structurally identical, so the compiler lets
     you swap them** *(leaf #211)* — branded types
   - **`tsc` passes but you can't prove the original bug can't return**
     *(leaf #212)* — add the failing case as a type-level test
```

Note the part names describe the *fix workflow* (diagnose → constrain →
verify inference → handle the edge case → roll out), not a table of contents
for TypeScript's generics feature. But the parts themselves are still too
coarse to teach directly — the **leaves** are the real teaching unit: each
one is a specific, concrete symptom narrow enough to have its own short
step-by-step fix (not "install/concept/demo/interview," which is a
concept-shaped template wearing an issue-shaped disguise). The underlying
concepts (type parameters, constraints, inference, conditional types) are
still taught in full — as the vocabulary named while resolving each leaf's
specific symptom, and written in full depth to the subject file — not as a
standalone lecture block before or after the leaf's resolution.

`*(besmart task #N)*` on a numbered part is optional — only present when
GOAL.md has a `BeSmart plan` and this part was pushed to (or pulled from)
that plan's `plan_tasks`. besmart's `plan_tasks` are a WBS tree
(`parent_task_id`/`sort_order`), so a part maps to a **parent** task —
parents have no completion state of their own, it's derived from their
children. Parts with no besmart plan omit the tag entirely.

Sub-bullets under a part with `*(leaf #N)*` are **required**, pushed as
**children** of that part's besmart task (via `besmart_sync.py create-task
<plan_id> ... --parent-task-id <parent_id>`). This is where Phase 3 actually
teaches and calls `complete-task` — only leaves are completable; besmart
derives the parent's checkmark once every leaf is done. Every leaf names a
concrete, specific real-life issue or symptom (see "Diagnose the misuse"
above) — not a generic install/concept/demo/interview template, and not a
restatement of the part's own broad problem. A part with only 1-2 genuinely
distinct issues still gets a leaf breakdown, just a short one; the only case
that skips leaves entirely is a part so small it IS a single issue (rare —
most parts are stages containing several).

Deprioritized items use ~~strikethrough~~ on the name and description, with
an italicized reason on the next line. They stay in the numbered list so the
original plan is visible. Renumber if an item is removed from the middle.

## Rules

- **Opens with the problem** — a 1-2 sentence `**Problem:**` line naming the
  real, industry-relevant issue the subject's actual stack resolves; the
  numbered parts are the path to resolving it, not a standalone topic list
  (see "Phase 2: Compose" in SKILL.md)
- **Parts are workflow milestones, not concept names** — name each part after
  the real step someone takes toward resolving the problem (diagnose, design,
  build, verify, ship — whatever the actual job looks like for this problem),
  not after the subject's own chapter/API list. The concepts still get taught
  in full; they're the toolset inside a milestone, not the milestone's name
- **Leaves are issue-sized, and required** — every part breaks into leaves,
  and every leaf is one concrete, specific real-life symptom narrow enough
  to have its own short step-by-step fix (see the leaf breakdown rules
  below). A part is where you're headed; a leaf is the actual thing you hit
  and fix along the way — that's the unit Phase 3 teaches
- **Leaves chain — each is caused by the previous one's fix** — the leaves
  under a part are a causal sequence, not a set. Leaf N+1 is the thing that
  breaks *because* leaf N was resolved the way it was. Test it before
  locking the breakdown in: if a leaf could be reordered anywhere in the
  part without reading oddly, it isn't an issue, it's a topic — rewrite it
  as the symptom that actually follows. Parts chain the same way, one level
  up: each opens on the situation the previous part's completion creates.
  This is what makes the plan read as a tutorial walking the user through
  real work rather than a themed list of exercises
- **3–8 parts** — fewer than 3 is probably too coarse; more than 8 is
  overwhelming
- **Logical order** — each part should build on the previous ones
- **Named, not numbered in the file** — parts are numbered for sequence but
  have descriptive names
- **Research-backed** — don't guess the breakdown. Search for how the topic
  is taught in reputable courses, books, or documentation
- **User-approved** — present the breakdown and let the user reorder, add,
  remove, or rename parts before locking it in
- **One stage per part** — a part covers one stage of the workflow. Don't
  split a part just because its name contains "and" ("collect & label the
  images" is one stage); split it when it actually contains two stages a
  practitioner would do at different times, with different output
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
