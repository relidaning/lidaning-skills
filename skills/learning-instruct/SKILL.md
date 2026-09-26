---
name: learning-instruct
description: >
  Activate when user wants to learn, study, or find tutorials on a topic or
  skill — phrases like "I want to learn X", "help me learn X", "teach me X",
  "help me understand X", "study plan for X", "study X", "any tutorials on
  X" — or invokes /learning-instruct. Do not activate for "study"/"review"
  meaning examine or inspect (e.g. "study this log/code/output", a database
  table named study_plans) — that's investigation, not a request to be
  taught. Structured tutor: assess level → set goals → break topics → teach
  → evaluate.
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
python3 "$SKILL_DIR/besmart_sync.py" list
```

`$SKILL_DIR` is this skill's own directory, given to you at activation as
"Base directory for this skill". **Always resolve `besmart_sync.py` against
it, never against the current working directory** — the bare relative path
`skills/learning-instruct/besmart_sync.py` only exists when you happen to be
sitting in the lidaning-skills repo, so in every other project the script
would appear to be missing and, per the silent-fallback rule below, the whole
besmart integration would no-op without ever reporting an error. This applies
to every `besmart_sync.py` invocation in this file.

If the command errors (besmart's container isn't running, `docker`/`pyjwt`
unavailable, etc.), skip silently to the project-read flow below — besmart is
an enhancement, never a hard dependency. A *missing script* is not that case:
if the file isn't where you resolved it, say so rather than silently skipping.

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
- `.claude/SESSION.md` (or root `SESSION.md`) — recent goals and current state
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

Research the goal topic (use web search). **Anchor the whole track in a real,
industry problem**: before drafting parts, identify a concrete, real-world
problem or issue that the subject's actual industry-standard stack or tools
are used to solve in practice — not a toy example invented for teaching.
State it in 1-2 sentences (what's broken or needed, who hits this, what
stack/tools solve it for real) and design the composition as the path to
resolving it — each part is a step toward that resolution, not an isolated
topic.

**Name parts after the real-world workflow, not the underlying concepts.**
Break the problem down the way someone actually doing this job would: the
concrete milestones on the way to a working resolution (e.g. for "ship an
image classifier" — collect & label data, design the model, train it,
evaluate it, iterate on what evaluation surfaces, ship it) — not the
framework's chapter list (e.g. "Tensors & autograd", "Dataset & DataLoader",
"nn.Module"). The underlying concepts still get taught in full — they're the
toolset covered *inside* whichever workflow milestone needs them, not the
part's name or organizing principle. A user should be able to read the part
titles alone and see the shape of solving the actual problem, not a table of
contents for the library's API. Generate compositions.md content (opening
with the problem statement) and hand to coding-orchestrate.

Present the breakdown to the user, including the problem statement it's
anchored on. Let them reorder, add, or remove parts before proceeding.

If GOAL.md has a `BeSmart plan`, once the breakdown is locked in, push every
non-strikethrough part that doesn't already carry a `(besmart task #N)` tag
as a parent task:

```bash
python3 skills/learning-instruct/besmart_sync.py create-task <plan_id> "<part name>" "<part summary>" <planned_start> <planned_end>
```

Tag the part in compositions.md with the returned task id (see
[compositions.md](compositions.md)). besmart's `plan_tasks` are a WBS tree —
**every part gets a leaf breakdown, because the leaf is the actual teaching
unit, not the part.** A part is a stage of the workflow (e.g. "Design your
classifier"); a leaf is one concrete, specific real-life issue or symptom
that comes up while working that stage — narrow enough to have its own short
step-by-step fix, not a generic "install / concept / demo / interview
question" template. "Design your classifier" isn't taught as one block; it's
3-5 concrete issues in sequence, e.g. "you only have a few hundred images
for your rarest categories, training from scratch won't converge" → "you
swap in a pretrained backbone but the output layer shape doesn't match your
class count" → "fine-tuning the whole network overfits your small dataset."

**Chain the leaves — each one is caused by the previous one's fix.** Note in
that example that leaf 2 exists *because* leaf 1 was resolved by reaching for
a pretrained backbone, and leaf 3 exists *because* leaf 2 was resolved by
wiring that backbone in. That causal chain is what makes a track feel like a
tutorial walking the user through real work instead of a themed list of
exercises. Before locking the breakdown in, read the leaves of each part in
order and check that each one's issue could only have surfaced after the
previous one's resolution; if a leaf could be swapped to any position without
anything reading oddly, it's a topic wearing an issue's clothes — rewrite it
as the symptom that actually follows from the leaf before it. The same holds
one level up: each part should open on the situation the previous part's
completion creates.

Push each as a child of the part:

```bash
python3 skills/learning-instruct/besmart_sync.py create-task <plan_id> "<leaf name>" "<leaf detail>" <planned_start> <planned_end> --parent-task-id <parent_id>
```

Tag each leaf with `(leaf #N)`. Run `besmart_sync.py tree <plan_id>` to
confirm the live tree matches compositions.md before moving on.

### Phase 3: Teach

Work through each composition part one **leaf** (one concrete issue) at a
time — the leaf, not the part, is the teaching unit; a part is just the
label for the stage its leaves belong to.

Every leaf is taught as **what → how → why**, in that order, and all three
beats are mandatory. The user should never receive a resolution without
understanding why it worked, and never receive a concept that isn't attached
to the symptom that motivated it. For each leaf:

1. **What — state the issue** — the specific, narrow real-life problem this
   leaf covers, in the terms the user would actually hit it: the command they
   ran, the error or wrong output they got, what they expected instead. Not
   the part's broad problem restated — the concrete symptom this leaf
   actually is. Open by connecting it to the previous leaf's resolution
   ("now that X works, the next thing that breaks is…") so the sequence
   reads as one walkthrough rather than a list of separate exercises.
2. **How — resolve it, step by step** — walk the user hands-on through
   fixing it with the real stack, right now. Keep narration to just what's
   needed to make each step make sense — this is not the deep dive.
3. **Why — explain what just happened** — two things, both required, and
   this is the beat that keeps concepts from feeling bolted on:
   - **Why the fix works** — the mechanism. What was actually going wrong
     underneath the symptom, and what the change did about it.
   - **Why this is the standard answer** — name the industry-standard
     concept or practice this resolution is an instance of, and what
     trade-off it buys. This is where the vocabulary and mental model get
     delivered — as the explanation of a fix the user just performed, never
     as a standalone lecture block before or after it.

   Keep it to a few paragraphs. Exhaustive treatment is step 4's job.
4. **Write the full depth to the subject file** — internals, edge cases,
   variants, common mistakes, connections: everything "Comprehensiveness
   over brevity" (see Rules) requires still gets produced, right now, into
   `<Subject>.md` (verify with web search, same as always) — but as written
   reference material only. Do not paste, summarize, or print step 4's
   content into the chat reply at this point — write it to the file and stop
   talking about it until step 5 says otherwise. This is where exhaustive
   coverage actually lives.
5. **Invite the deep dive, don't force it** — check in: "Any questions about
   what's under the hood here, or ready for the next issue?" If they ask,
   answer from what you just wrote in step 4 (or go deeper live if their
   question isn't covered yet, and write that back too). If they don't ask,
   move on — the depth stays in the reference for whenever they want it.
6. **Check basic understanding** — a light check on the *what/how/why* of
   this leaf: can they say what the symptom was, reproduce the fix, and
   explain why it worked? The "why" half is the one that actually matters —
   a user who can repeat the commands but can't say what they addressed
   hasn't learned the leaf. Not a probe of every edge case from step 4
7. Mark the leaf done once the issue is resolved and basic understanding of
   *that resolution* is confirmed — not once every subtopic has been
   narrated aloud. Run `besmart_sync.py complete-task <plan_id> <leaf_id>`
   right then, not batched. besmart derives the parent part's checkmark
   automatically once every leaf under it is done — never call
   `complete-task` on a task that **has children**, since besmart silently
   no-ops it. (A part with no leaf breakdown at all is itself a leaf in
   besmart's tree, so completing its `(besmart task #N)` id directly is
   correct — the ban is on parents, not on parts.) Don't wait for Phase 4
   (see [steps.md](steps.md))

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
- besmart `plan_tasks` **leaf** rows ↔ compositions.md sub-items (linked via
  `(leaf #id)` tags) — each leaf is one concrete, specific real-life issue,
  mandatory for every part (see "Phase 2: Compose" and compositions.md); the
  old install/concept/demo/interview-question template is retired
- Only leaves carry completion state in besmart; a parent's checkmark is
  derived client-side from whether every leaf descendant is done. So Phase 3
  calls `complete-task` on the leaf id as each issue is resolved (or on the
  part id directly, for the rare part that IS a single issue with no leaf
  breakdown) — never on a parent that has children
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
- **Problem-first, then depth** — every composition opens on a real,
  industry-relevant problem solved by the subject's actual stack, and each
  part is a sequence of concrete, issue-sized leaves — not a block of
  concepts (see Phase 2/3). Depth is never skipped, only deferred: it gets
  written in full every time (step 4 below), but is narrated live only when
  asked for
- **Comprehensiveness over brevity — in the written reference, not the live
  narration** — `<Subject>.md` (and steps.md's record of what was covered)
  must cover ALL key concepts, subtopics, edge cases, variants, connections,
  and common mistakes for every leaf taught, so a reader could learn the
  topic from these files alone. This is a bar for what gets *written*
  (Phase 3 step 4) and for how deep you go *when the user asks* (step 5) —
  it is NOT a mandate to narrate every subtopic aloud before the user can
  move to the next issue. Conflating the two is what "problem-first" is
  correcting
- **Truth over confidence** — every explanation, concept, quiz answer, and
  scenario solution must be factually correct. Verify claims with web search
  before teaching. If unsure, say so and look it up — never guess. Cite sources
  when non-obvious
- **User owns the breakdown** — present compositions for approval; let them
  reshape it
- **Basic understanding over exhaustive mastery, per issue** — don't move to
  the next leaf until the user can reproduce or explain the resolution they
  just did. Full depth is always available (written to the subject file,
  answerable on request) but is never a gate to moving on
- **Practical application** — every leaf's own step-by-step resolution IS
  the application; nothing needs a separate bolted-on exercise unless the
  resolution itself was too easy to demonstrate real understanding
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
