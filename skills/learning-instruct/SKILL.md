---
name: learning-instruct
description: >
  Structured learning tutor. Reads project context to infer what the user is
  working on, assesses their level, then guides them through goal setting,
  topic breakdown, step-by-step teaching, and mastery evaluation. Supports
  /learning-instruct next/quiz/scenario for interactive hints, questions,
  and real-world problems during teaching. Use when the user wants to learn
  something new, asks for a study plan, wants to be tutored on a topic, or
  invokes /learning-instruct.
---

## Overview

This skill tutors the user through a structured learning process. It manages
five files under `.learning-instruct/` at the project root:

- **[GOAL.md](goal.md)** — what the user wants to learn
- **[compositions.md](compositions.md)** — the subject broken into parts
- **[steps.md](steps.md)** — step-by-step teaching plan and progress
- **[SUBJECT.md](subject.md)** — living reference of key concepts, quiz Q&A,
  scenarios, and gotchas; the user's study guide
- Evaluation — interview questions to assess mastery and find gaps

## Workflow

### Phase 1: Goal

If `.learning-instruct/GOAL.md` doesn't exist, **read the project first** to
understand what the user is working on. Look at:

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

Let the user confirm or correct. Once confirmed, write to `GOAL.md` using the
format in [goal.md](goal.md).

If the project context doesn't give enough signal, fall back to asking:

> What do you want to learn? Be specific — what's the subject, and what level
> of mastery are you aiming for?

Once the goal is confirmed, assess the user's level from their background.
Make a judgment call and state it:

> Based on your background, I'd put you at [beginner / intermediate /
> advanced] on this topic. Does that feel right? I'll tailor the teaching
> to that level.

Let the user correct. This level drives the depth and pace of Phase 3.

### Phase 2: Compose

Research the goal topic (use web search). Break it down into logical parts —
concepts, skills, or subtopics that build on each other. Write to
`compositions.md` using the format in [compositions.md](compositions.md).

Present the breakdown to the user. Let them reorder, add, or remove parts
before proceeding.

### Phase 3: Teach

Work through each composition part one at a time. For each part:

1. Explain the concept clearly, with examples
2. Ask the user questions to check understanding
3. Have them apply it (write code, solve a problem, explain back)
4. Mark the part as done only when they demonstrate understanding

Track progress in `steps.md` using the format in [steps.md](steps.md).

#### Interactive hints

While in Phase 3, the user can invoke these at any time:

**`/learning-instruct next`** — Give the next key insight, tip, or concept that
builds on what was just covered. Push the user one layer deeper. Not a repeat
of the last explanation — something new that connects or extends.

**`/learning-instruct quiz`** — Pop a question about the current part. Test
understanding with a focused, single-concept question. After the user answers,
explain the correct answer and why. Write the Q&A to SUBJECT.md.

**`/learning-instruct scenario`** — Pop a realistic problem that requires
applying the current concept. More open-ended than a quiz — the user should
solve or design something. After they answer, evaluate their solution and
point out what they handled well and what they missed. Write the problem,
solution, and notes to SUBJECT.md.

These commands only work when a learning track is active (GOAL.md exists and
a part is in progress). If invoked without context, guide the user back to
the current part.

### Phase 4: Evaluate

After all parts are taught, run a comprehensive evaluation:

1. Generate questions spanning all composition parts — mix of conceptual,
   practical, and scenario-based
2. Ask them one at a time. Evaluate each answer.
3. Score each composition area: mastered / proficient / needs work
4. Write findings to `steps.md` under an Evaluation section
5. Recommend which parts to revisit and how to strengthen them

## Rules

- **Files evolve with conversation** — the managed markdown files are live
  documents, not one-time writes. Whenever the conversation changes something
  (goal shifts, composition reordered, part mastered, new insight surfaced,
  exercise completed, level adjusted), update the relevant file immediately.
  Don't batch updates — write as you go.
- **Goal first** — don't skip to teaching without a clear, specific goal
- **Research properly** — use web search to find authoritative sources and
  current best practices for the subject
- **User owns the breakdown** — present compositions for approval; let them
  reshape it
- **Mastery over coverage** — don't move to the next part until the user
  demonstrates understanding of the current one
- **Practical application** — every part should include an exercise or
  application, not just explanation
- **Honest evaluation** — don't inflate scores. Identify real gaps so the
  user knows where to focus
- **Write to SUBJECT.md immediately** — after every quiz, scenario, or key
  concept explanation, add it to SUBJECT.md right away. This file is the
  user's study guide — it should always be current and review-ready

## Additional resources

- For goal format and rules, see [goal.md](goal.md)
- For compositions format and rules, see [compositions.md](compositions.md)
- For steps and evaluation format, see [steps.md](steps.md)
- For subject reference format, see [subject.md](subject.md)
