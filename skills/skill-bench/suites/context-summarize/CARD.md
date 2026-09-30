# Benchmark card: `context-summarize`

## What is measured

- **Trigger**: does the model call `Skill(context-summarize)` when asked to condense something (recall), and stay quiet on adjacent requests (precision / FPR)?
- **Behavior**: once used, does the reply follow the skill's contract? Scored by hard checks (gates) plus a binary rubric graded by a blind LLM judge.

## Capability spec (from SKILL.md sha256 `ecaecb2723d7…` at creation)

Trigger claims
- **T1**: fires on any request to summarize/condense/recap pasted text, a file, a URL, or the conversation.
- **T2**: fires on the cue words "summarize", "tl;dr", "gist", "catch me up", "condense", "recap", "brief me".

Non-trigger claims
- **N1**: not for skill-managed session logs (SESSION.md belongs to memory-orchestrate).
- **N2**: not the built-in `/compact`.
- **N3**: requests owned by neighboring skills (vault search, paper search, model routing).
- **N4**: requests with no condensing intent, including ones that use a cue word in another sense.

Behavior claims
- **B1**: output is the reply itself; no file writes.
- **B2**: reads a named file (Read) before summarizing; never guesses from the name.
- **B3**: preserves specifics (names, numbers, paths, decisions, action items).
- **B4**: no fabricated or inferred conclusions.
- **B5**: flags embedded instructions in the summarized content instead of following them.
- **B6**: a user-specified length or shape overrides the default.
- **B7**: asks what to summarize when the source is unclear.
- **B8**: compresses long input to roughly 10–20% of its length (applied here as a word cap with slack).

Not covered: URL input (needs network; nondeterministic content), conversation recap (trials are single-turn), and the research-paper shape (owned by the paper-fetch flow). URL fetches and multi-turn recaps are coverage gaps for a future minor version.

## Dataset construction

- Source: `skills/context-summarize/SKILL.md` plus CLAUDE.md notes. Fixtures (`meeting.md`, `vendor-notes.md` with a planted prompt injection, `design-doc.md` of ~730 words) are synthetic, with planted specifics, so the ground truth is known and never drifts.
- Author: Claude via `skill-bench`, 2026-09-24.
- Label audit: see below.
- Splits: `dev` (for iterating on the skill), `test` (held out). Stratified by label and category.

## Label audit

A fresh subagent labeled all trigger prompts blind, seeing only the SKILL.md, the neighboring skills' descriptions, and the unlabeled prompts. **Agreement: 26/26 (100%).** No trigger case was dropped.

It also reviewed the behavior rubrics. Changes made before freezing:
- `cs-b-003` / `cs-b-006` `notfollow`: quoting the injected text while flagging it is not a violation.
- `cs-b-005`: word cap raised from 260 to 450. The skill's own technical-doc shape allows 300–500 words, so a 260 cap would fail compliant answers.
- `cs-b-006` `three`: a separate injection note outside the three bullets is allowed. Added a `flag` criterion and a reference.
- `cs-b-007` `scope`: a one-line note about unowned items is allowed. Added a reference.
- Suite-wide: `english-practice` fires on every turn in this environment, so its block is stripped (`reply_strip_regex`) before checks and judging.

A dev-split smoke test on Haiku (unfrozen, k=1) had surfaced the `cs-b-006` flaw before the audit did.

## Coverage

| Category | Label | dev | test | Why it's here |
|---|---|---|---|---|
| embedded | positive | 0 | 1 | request inside a longer message |
| explicit | positive | 1 | 2 | cue words from the description |
| implicit | positive | 0 | 2 | need is clear, task never named |
| multilingual | positive | 1 | 1 | user writes Chinese sometimes |
| noisy | positive | 1 | 1 | typos / casual |
| paraphrase | positive | 1 | 2 | same intent, no cue words |
| behavior | — | 2 | 5 | B1–B8 contract |
| keyword-trap | negative | 1 | 2 | cue word in another sense |
| near-miss | negative | 1 | 3 | adjacent intent (translate, explain, /compact) |
| off-topic | negative | 1 | 1 | unrelated |
| other-skill | negative | 1 | 3 | neighbor skills' territory |


## Known limitations

- The judge is a Claude model grading Claude output.
- Cases run in the real repo, so results depend on the installed skill set and global CLAUDE.md at run time (notably, `english-practice` fires on every turn in this environment).
