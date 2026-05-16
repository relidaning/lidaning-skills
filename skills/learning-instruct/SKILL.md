---
name: learning-instruct
description: >
  Structured learning tutor. Guides user through setting a learning goal,
  researching and breaking down a subject into parts, teaching step by step,
  and evaluating mastery with questions. Use when the user wants to learn
  something new, asks for a study plan, wants to be tutored on a topic, or
  invokes /learning-instruct.
---

## Overview

This skill tutors the user through a structured learning process. It manages
four files under `.learning-instruct/` at the project root:

- **[GOAL.md](goal.md)** — what the user wants to learn
- **[compositions.md](compositions.md)** — the subject broken into parts
- **[steps.md](steps.md)** — step-by-step teaching plan and progress
- Evaluation — interview questions to assess mastery and find gaps

## Workflow

### Phase 1: Goal

If `.learning-instruct/GOAL.md` doesn't exist, ask the user:

> What do you want to learn? Be specific — what's the subject, and what level
> of mastery are you aiming for?

Write their answer to `GOAL.md` using the format in [goal.md](goal.md).

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

### Phase 4: Evaluate

After all parts are taught, run a comprehensive evaluation:

1. Generate questions spanning all composition parts — mix of conceptual,
   practical, and scenario-based
2. Ask them one at a time. Evaluate each answer.
3. Score each composition area: mastered / proficient / needs work
4. Write findings to `steps.md` under an Evaluation section
5. Recommend which parts to revisit and how to strengthen them

## Rules

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

## Additional resources

- For goal format and rules, see [goal.md](goal.md)
- For compositions format and rules, see [compositions.md](compositions.md)
- For steps and evaluation format, see [steps.md](steps.md)
