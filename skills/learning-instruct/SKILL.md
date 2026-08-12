---
name: learning-instruct
description: >
  Activate when user says "I want to learn X", "teach me X", "help me
  understand X", "study plan for X", or invokes /learning-instruct.
  Structured tutor: assess level → set goals → break topics → teach → evaluate.
---

## Overview

This skill tutors the user through a structured learning process. It generates
markdown content — goal, compositions, steps, subject reference, issues log,
and documentation summaries. It hands all output to the coding-orchestrate
skill, which owns the recording layer and knows where to persist it.

For local project storage, this skill does **not** write files directly — it
generates content and passes it to coding-orchestrate for storage. The one
exception is the vault: when Obsidian is reachable, this skill writes subject
files there directly via the REST API rather than routing through
coding-orchestrate (see "Storage location" below). Before handing off local
content, it detects whether a notes MCP (like Obsidian) is connected and asks
the user where to store the materials — vault or local project.

### Generated files (handed to coding-orchestrate)

- **GOAL.md** — what the user wants to learn
- **[compositions.md](compositions.md)** — the subject broken into parts
- **[steps.md](steps.md)** — step-by-step teaching plan and progress
- **`<Subject>.md`** ([format](subject.md)) — comprehensive living reference
  named after the subject; ALL key concepts in depth, quiz Q&A, scenarios,
  and gotchas. A standalone study guide, not a quick-reference card
- **[ISSUES.md](issues.md)** — problems encountered, root causes, resolutions
- **[DOCUMENTATIONS.md](documentations.md)** — index of user-provided resources
  summarized into `docs/`
- Evaluation — interview questions to assess mastery and find gaps

## Workflow

### Phase 1: Goal

If no goal is active (check with coding-orchestrate), **check besmart before
reading the project**. besmart (`/data/apps/besmart`) is a separate app with
its own "Study Plans" feature; when it's reachable it is the resource this
skill draws curricula from — see "BeSmart integration" below for the full
data flow. List its incomplete plans:

```bash
python3 skills/learning-instruct/besmart_sync.py list
```

If the command errors (besmart's container isn't running, `docker`/`pyjwt`
unavailable, etc.), skip silently to the project-read flow below — besmart is
an enhancement, never a hard dependency.

If plans come back, present them (name, description, date range) and ask
whether to use one as this session's goal, or set a goal that isn't on
besmart at all. Don't auto-pick — let the user choose.

- **User picks a besmart plan** — generate GOAL.md from the plan's
  name/description, record `**BeSmart plan:** #<id>` in it (see
  [goal.md](goal.md)). If the plan already has tasks, treat them as the
  Phase 2 breakdown (present for confirmation, same as any composition); if
  it has none, run Phase 2 normally and push the resulting parts to besmart
  as tasks afterward.
- **User declines / no plans exist** — fall back to reading the project
  first, below. If the resulting goal is genuinely new, also create it in
  besmart (`besmart_sync.py create-plan ...`) so besmart stays the single
  place all curricula — past and present — are listed, then record the
  returned id in GOAL.md the same way.

**Read the project first** to understand what the user is working on. Look at:

- `CLAUDE.md` — project overview and skills
- `SESSION.md` — recent session goals and current state
- `.claude/TODO.md` — what's planned or in progress
- `.claude/MEMORIES.md` — user preferences
- `git log --oneline -10` — recent commits and what's been built
- The current branch name

From this context, formulate a best guess: what is the user likely trying to
learn? Present it plainly:

> It looks like you're working on [project description]. Are you trying to
> learn [guessed topic]? If that's right, I'll start there. If not, tell me
> what you actually want to learn — be specific about the subject and what
> level of mastery you're aiming for.

Let the user confirm or correct. Once confirmed, generate GOAL.md content and
hand it to coding-orchestrate for recording.

If the project context doesn't give enough signal, fall back to asking:

> What do you want to learn? Be specific — what's the subject, and what level
> of mastery are you aiming for?

Once the goal is confirmed, assess the user's level from their background.
Make a judgment call and state it:

> Based on your background, I'd put you at [beginner / intermediate /
> advanced] on this topic. Does that feel right? I'll tailor the teaching
> to that level.

Let the user correct. This level drives the depth and pace of Phase 3.

#### Storage location

Once the goal and level are set, check whether Obsidian is reachable. Probe it
silently using the env vars defined in the obsidian-local skill (`$OBSIDIAN_MCP_URL`
and `$OBSIDIAN_MCP_TOKEN`):

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $OBSIDIAN_MCP_TOKEN" \
  "${OBSIDIAN_MCP_URL%/}/vault/"
```

(`$OBSIDIAN_MCP_URL` may have a trailing slash — always strip it with
`${OBSIDIAN_MCP_URL%/}` before appending a path, or the API returns 404 on
the resulting `//` and Obsidian looks unreachable when it isn't.)

- **Obsidian reachable (2xx)** — write subject files directly to the vault
  root as `<Subject>.md` via `PUT ${OBSIDIAN_MCP_URL%/}/vault/<Subject>.md`
  (root, not a subfolder — per user preference, generated docs go to the vault
  root so they're easy to find). Do **not** ask the user; just write there and
  tell them the note path. On every subsequent update, overwrite the same path.
- **Obsidian unreachable** — fall back to coding-orchestrate for local project storage.

### Phase 2: Compose

Research the goal topic (use web search). Break it down into logical parts —
concepts, skills, or subtopics that build on each other. Generate
compositions.md content and hand to coding-orchestrate.

Present the breakdown to the user. Let them reorder, add, or remove parts
before proceeding.

If GOAL.md has a `BeSmart plan`, once the breakdown is locked in, push every
non-strikethrough part that doesn't already carry a `(besmart task #N)` tag
as a parent task:

```bash
python3 skills/learning-instruct/besmart_sync.py create-task <plan_id> "<part name>" "<part summary>" <planned_start> <planned_end>
```

Tag the part in compositions.md with the returned task id (see
[compositions.md](compositions.md)). besmart's `plan_tasks` are a WBS tree —
for parts substantial enough to benefit from it, also push a leaf breakdown
(install/setup → concept → demo → interview question is a reliable default
shape) as children of that parent:

```bash
python3 skills/learning-instruct/besmart_sync.py create-task <plan_id> "<leaf name>" "<leaf detail>" <planned_start> <planned_end> --parent-task-id <parent_id>
```

Tag each leaf with `(leaf #N)`. Run `besmart_sync.py tree <plan_id>` to
confirm the live tree matches compositions.md before moving on.

### Phase 3: Teach

Work through each composition part one at a time. For each part:

1. **Explain comprehensively** — cover the core idea, how it works, use cases,
   variants/forms, edge cases & limitations, connections to other concepts,
   and common mistakes. Don't just teach the happy path — go deep on every
   subtopic that falls under this part. Use web search to verify your
   explanations and to find important points you might have missed.
2. **Check understanding** — ask targeted questions that probe edge cases
   and connections, not just recall of the definition
3. **Apply** — have the user write code, solve a problem, or explain back.
   Choose exercises that exercise the tricky parts, not just the basics
4. **Audit coverage** — before marking done, check: did you cover EVERY
   subtopic listed in the compositions breakdown? Did you miss any edge
   cases, variants, or "what you can't do" items? Go back and fill gaps
5. Mark the part as done only when understanding is demonstrated AND all
   subtopics are covered. besmart only lets **leaves** carry completion
   state — a parent's checkmark is derived from its children, not settable
   directly. So: as each `(leaf #N)`-tagged sub-item is covered, run
   `besmart_sync.py complete-task <plan_id> <leaf_id>` right then, not
   batched to the end of the part. If the part has no leaf breakdown (just a
   `(besmart task #N)` tag on the part itself), complete that task directly
   once the whole part is done. Don't wait for Phase 4 (see [steps.md](steps.md))

Hand steps.md updates to coding-orchestrate as progress is made.

#### Interactive hints

While in Phase 3, the user can invoke these at any time:

**`/learning-instruct next`** — Give the next key insight, tip, or concept that
builds on what was just covered. Push the user one layer deeper. Not a repeat
of the last explanation — something new that connects or extends.

**`/learning-instruct quiz`** — Pop a question about the current part. Test
understanding with a focused, single-concept question. After the user answers,
explain the correct answer and why. Hand the Q&A to coding-orchestrate for
the subject file.

**`/learning-instruct scenario`** — Pop a realistic problem that requires
applying the current concept. More open-ended than a quiz — the user should
solve or design something. After they answer, evaluate their solution and
point out what they handled well and what they missed. Hand the problem,
solution, and notes to coding-orchestrate for the subject file.

These commands only work when a learning track is active (goal exists and
a part is in progress).

#### Resource ingestion

When the user provides a URL or document during a learning track:

1. Fetch and read the resource (use WebFetch for URLs, Read for local files)
2. Generate a summary file — source content only, no added knowledge
3. Generate an updated DOCUMENTATIONS.md index entry
4. Hand both to coding-orchestrate for recording

**Critical rule: source content only.** Summarize what the resource actually
says. Do NOT mix in explanations, context, or corrections from your own
knowledge. The summary must be a faithful mirror of the source.

See [documentations.md](documentations.md) for format and full rules.

### Phase 4: Evaluate

After all parts are taught, run a comprehensive evaluation:

1. Generate questions spanning all composition parts — mix of conceptual,
   practical, and scenario-based
2. Ask them one at a time. Evaluate each answer.
3. Score each composition area: mastered / proficient / needs work
4. Generate findings for steps.md under an Evaluation section
5. Recommend which parts to revisit and how to strengthen them
6. If GOAL.md has a `BeSmart plan` and every part is done, run
   `besmart_sync.py complete-plan <plan_id>` so the plan shows complete in
   besmart too

Hand all evaluation output to coding-orchestrate for recording.

## BeSmart integration

[besmart](/data/apps/besmart) is a separate personal productivity app (Node/
TypeScript, port 5090) with its own "Study Plans" feature. As of the plan
module's WBS rewrite, `plan_tasks` is a tree (`parent_task_id`,
`sort_order`), not a flat list — this skill treats besmart as the **plan
resource** — the place curricula are listed as a work-breakdown structure
and progress is visible on a dashboard/streak — while this skill remains the
**teaching engine**: it generates the actual step breakdown, tutorials,
quizzes, and the living subject reference that besmart itself has no notion
of. Neither app owns the other; they're linked per-goal by ids.

**Data flow:**
- besmart `study_plans` row ↔ this skill's GOAL.md (linked via `BeSmart plan: #id`)
- besmart `plan_tasks` **parent** rows ↔ this skill's compositions.md parts
  (linked via `(besmart task #id)` tags)
- besmart `plan_tasks` **leaf** rows, when a part gets one, ↔ compositions.md
  sub-items (linked via `(leaf #id)` tags) — install/concept/demo/interview-
  question is the default shape for a leaf breakdown, but isn't mandatory for
  every part
- Only leaves carry completion state in besmart; a parent's checkmark is
  derived client-side from whether every leaf descendant is done. So Phase 3
  calls `complete-task` on the leaf id as each sub-step is covered (or on the
  part id directly, for parts with no leaf breakdown) — never on a parent
  that has children
- All parts done (Phase 4) → `complete-plan` → besmart plan flips done
- The rich content (Subject.md, steps.md, quizzes, issues) never lives in
  besmart — it stays in this skill's usual output (vault or local project).
  besmart only ever sees task names, descriptions, tree structure, and
  completion state.

**The bridge script:** `skills/learning-instruct/besmart_sync.py` — a CLI
wrapping besmart's `/api/plans` HTTP API. It mints its own JWT at call time
(reads `JWT_SECRET` from the running `besmart-besmart-1` container via
`docker exec`, falling back to parsing besmart's `docker-compose.yml` — never
hardcoded in this repo) so no credential setup is needed. Subcommands: `list
[--all]`, `plan <id>`, `tree <id>` (human-readable WBS outline), `create-plan`,
`update-plan`, `create-task [--parent-task-id]`, `update-task`,
`complete-task`, `complete-plan`, `delete-task` (cascades to descendants),
`delete-plan`, `indent-task`, `outdent-task`, `move-task <up|down>`.
`update-plan`/`update-task` only send the fields you pass (e.g. rescheduling
dates without touching completion state). All output JSON on stdout except
`tree`. Override `BESMART_URL`, `BESMART_USER_ID`, `BESMART_EMAIL`,
`BESMART_CONTAINER`, or `BESMART_JWT_SECRET` via env if the defaults (this
user's besmart instance, `http://127.0.0.1:5090`) don't apply.

**Never a hard dependency** — every besmart call in this skill is best-effort.
If besmart isn't running, `docker` isn't reachable, or the script errors for
any reason, fall back silently to the plain (no-besmart) flow described in
each phase above. A learning track with no `BeSmart plan` line in GOAL.md
works exactly as it did before this integration existed.

## Rules

- **Generate, don't write, for local project storage** — this skill generates
  markdown content and hands it to coding-orchestrate, which owns local vault
  paths and I/O details. The vault path is the one exception: when Obsidian is
  reachable, this skill writes subject files there directly (see "Storage
  location") instead of handing off
- **Files evolve with conversation** — the generated content is live, not
  one-time. Whenever the conversation changes something (goal shifts,
  composition reordered, part mastered, new insight surfaced), regenerate
  the relevant content and hand it off. Don't batch — update as you go
- **Goal first** — don't skip to teaching without a clear, specific goal
- **Comprehensiveness over brevity** — in teaching content (subject.md,
  steps.md), depth beats conciseness. Cover ALL key concepts, subtopics,
  edge cases, variants, connections, and common mistakes. A reader should
  learn the topic from these files alone. Don't skip the "boring" parts —
  limitations and what-you-can't-do are often the most valuable
- **Truth over confidence** — every explanation, concept, quiz answer, and
  scenario solution must be factually correct. Verify claims with web search
  before teaching. If unsure, say so and look it up — never guess. Cite sources
  when non-obvious
- **User owns the breakdown** — present compositions for approval; let them
  reshape it
- **Mastery over coverage** — don't move to the next part until the user
  demonstrates understanding of the current one
- **Practical application** — every part should include an exercise or
  application, not just explanation
- **Honest evaluation** — don't inflate scores. Identify real gaps so the
  user knows where to focus
- **Write to the subject content immediately** — after every quiz, scenario, or
  key concept explanation, generate the update for the subject file right away
- **Detect and record issues proactively** — when a learning track is active,
  watch the conversation for signs of a problem: the user pastes an error,
  describes a blocker, expresses confusion, gets a quiz wrong, or says
  something didn't work. Recognize it as an issue and generate ISSUES.md
  content without the user having to ask
- **Track gaps in the subject file as they happen** — whenever the user answers
  incorrectly, partially, or expresses uncertainty during Phase 3, immediately
  update the subject file to mark that concept with a `> **Needs review:**`
  blockquote explaining what they missed and why. Do not wait for the Phase 4
  evaluation. If Obsidian is reachable, write the updated file to the vault
  right away so the note reflects the current state of the conversation
- **BeSmart sync is best-effort, never blocking** — a failed or unavailable
  `besmart_sync.py` call is a skip, not an error to surface loudly or retry.
  Teaching proceeds regardless; besmart is a convenience layer on top, not a
  dependency of this skill's core workflow

## Additional resources

- For goal format and rules, see [goal.md](goal.md)
- For compositions format and rules, see [compositions.md](compositions.md)
- For steps and evaluation format, see [steps.md](steps.md)
- For subject reference format, see [subject.md](subject.md)
- For issue log format, see [issues.md](issues.md)
- For documentation ingestion format, see [documentations.md](documentations.md)
- For the besmart bridge script and data flow, see "BeSmart integration"
  above and [besmart_sync.py](besmart_sync.py)
