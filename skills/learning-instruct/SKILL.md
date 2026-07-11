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

This skill does **not** write files directly. It generates content and passes
it to coding-orchestrate for storage. Before handing off, it detects whether
a notes MCP (like Obsidian) is connected and asks the user where to store
the materials — vault or local project.

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

If no goal is active (check with coding-orchestrate), **read the project
first** to understand what the user is working on. Look at:

- `CLAUDE.md` — project overview and skills
- `SESSION.md` — recent session goals and current state
- `TODO.md` — what's planned or in progress
- `MEMORIES.md` — user preferences
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
   subtopics are covered

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

Hand all evaluation output to coding-orchestrate for recording.

## Rules

- **Generate, don't write** — this skill generates markdown content and hands
  it to coding-orchestrate. It never writes files directly. It checks for
  connected notes MCPs to offer the user a storage choice (vault vs project),
  but doesn't know vault paths or I/O details — coding-orchestrate handles that
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

## Additional resources

- For goal format and rules, see [goal.md](goal.md)
- For compositions format and rules, see [compositions.md](compositions.md)
- For steps and evaluation format, see [steps.md](steps.md)
- For subject reference format, see [subject.md](subject.md)
- For issue log format, see [issues.md](issues.md)
- For documentation ingestion format, see [documentations.md](documentations.md)
