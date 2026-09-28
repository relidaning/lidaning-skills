---
name: skillopt
description: >
  Activate when the user asks to optimize, improve, tune, or fix a specific
  skill toward a stated goal ("make skillX also do Y", "skillX keeps missing
  Z, fix it", "improve skillX's trigger rate on Haiku"), asks for a general
  skill-quality audit ("audit my skills", "score my skills", "run SkillOpt"),
  or invokes /skillopt. Runs a bounded, validation-gated edit loop against a
  target skill's SKILL.md instead of hand-editing it once and hoping — do
  not skip straight to a manual Edit when this skill applies. Skip for
  routine SKILL.md edits with no stated optimization goal (e.g. "rename this
  skill", "fix this typo").
---

# SkillOpt

Adapts the loop from arXiv:2605.23904 ("SkillOpt: Executive Strategy for
Self-Evolving Agent Skills") to a single Claude Code session: treat a
SKILL.md as the *trainable state*, propose small validated edits, keep only
the ones that measurably help. The paper's reference code
(`/data/open-app/SkillOpt/`, loop in `skillopt/engine/trainer.py`) trains
against scoreable benchmarks (SearchQA, ALFWorld, …) with a separate
optimizer LLM and dozens of API rollouts per step. We don't have that at
that scale, but an automated trigger check does exist: run the candidate against fixed probe
prompts with `claude -p "<prompt>" --model <id> --output-format stream-json
--verbose` and grep the stream for `"name":"Skill"` (TRIGGERED/SKIPPED per
probe, 2 passes per candidate since single probes are noisy). Always pass
`--disallowedTools Bash Edit Write NotebookEdit Task mcp__obsidian__vault_write
mcp__obsidian__vault_append mcp__obsidian__vault_patch mcp__obsidian__vault_delete
mcp__obsidian-vault__write_note mcp__obsidian-vault__patch_note
mcp__obsidian-vault__delete_note mcp__obsidian-vault__move_note
mcp__obsidian-vault__move_file mcp__obsidian-vault__update_frontmatter
mcp__obsidian-vault__manage_tags`
— without it, probes run in the repo under test with full write access — and
diff the repo after a probe batch. This version scales the paper's mechanics
down to fit inside a conversation, with Claude playing optimizer, the probe
script playing the held-out trigger validator, and a **fresh-context
subagent** judging body-output quality against the held-out probes (same
fresh-eyes principle as `/code-review`'s verify pass, standing in for the
paper's separate optimizer-vs-target-model split).

**If the target has a frozen `skill-bench` suite**
(`skills/skill-bench/suites/<skill>/suite.json`), use it instead of ad-hoc
probes: reflect on `bench.py run <skill> --split dev` results, and gate the
final candidate with a `--split test` run compared against the suite's last
history row. Accept only if the report's paired-by-case delta is positive and
not marked `(n.s.)`. Never read `test` cases while editing (leakage).

## Two modes

- **Directed** (the main new capability): user gives a target skill *and* a
  direction — a concrete goal the skill should get better at. Optimization
  is scored against that direction.
- **General audit**: no direction given. Falls back to the existing
  CLAUDE.md rubric — Trigger Clarity (0–5) + Body Quality (0–5), threshold
  ≥8/10 — the same check `claude-maxer`'s `skill-audit` work type has been
  running ad hoc. This mode skips probe generation (the rubric is already a
  holistic score) and goes straight to bounded-edit + validation-gate.

Ask which skill and which mode if not stated. For "audit all skills," loop
general-audit mode once per skill in `registry.yaml`.

## The loop (directed mode)

### 0. Setup
- Read the target skill's `SKILL.md` + `metadata.yaml`.
- Turn the user's direction into 2–4 concrete, checkable criteria (e.g. "does
  not trigger on plain coding questions", "output includes X", "triggers
  within the first turn on Haiku-class prompts"). Confirm them with the user
  if the direction is vague enough that criteria are ambiguous.
- Create a run log dir: `.claude/skillopt-runs/<skill>-<timestamp>/`.
- Score the **baseline**: current SKILL.md against both the direction
  criteria and the general Trigger Clarity/Body Quality rubric (the general
  score must never regress below 8/10 — directed optimization is not
  allowed to trade away trigger reliability).

### 1. Rollout — build a probe set
Generate 6 short scenarios (prompts a user might realistically send), split:
- 2–3 **positive**: should trigger the skill and exercise the direction.
- 1–2 **negative**: adjacent/near-miss topics that should *not* trigger it
  (checks for new false positives introduced by the edit).
- 1–2 **regression**: an existing documented behavior of this skill that
  must keep working (pull from the skill's own body, or from CLAUDE.md notes
  about it if any exist).

Split 4 into a train set (used for reflection) and 2 into a held-out set
(touched only by the validation gate, never by reflection).

For each train probe, judge inline: would this description (as a
system-reminder trigger hint) cause a model to call `Skill(...)` here, and if
so, does the current body produce output meeting the relevant criteria?
Record a pass/fail + one-line reason per probe — this is the "trajectory."

### 2. Reflection — propose bounded edits
Separate train-probe failures from successes.
- **Failures** → what's missing or wrong in the trigger description or body?
  Propose corrective edits.
- **Successes** → what must be preserved? Flag these as constraints so later
  edits don't regress them.

Each proposed edit is one of `ADD` / `DELETE` / `REPLACE`, one line of
rationale each. If this is round 2+, also read the run dir's
`rejected-edits.md` buffer and `meta-notes.md` (step 5) first; do not
re-propose anything already rejected there — treat it as evidence of a
direction that doesn't work.

**Aggregate** before selecting (the paper's merge stage): collapse edits
that say the same thing into one, keeping the best wording, and record a
**support count** — how many train probes each edit would fix. Resolve
contradicting edits to one. No two surviving edits may touch the same text
region, so the gate can attribute a score change to them.

### 3. Bounded edit budget
Cap edits applied this round: **3 on round 1, 2 on round 2+** (this session's
equivalent of the paper's cosine-decayed textual learning rate — start
looser, tighten as the skill stabilizes). Rank aggregated edits by the
paper's criteria, in order: (1) systematic impact — higher support count
wins over a one-probe fix; (2) complementarity — fills a gap rather than
restating the body; (3) generality — a principle over a probe-specific
patch; (4) actionability — concrete over vague. Apply only the top-ranked
ones within budget to a candidate `SKILL.md`. Do not do a full rewrite —
bounded, localized edits only, so later rounds can still tell what helped.

### 4. Validation gate — measured trigger + fresh eyes
Two checks, both required:
- **Trigger**: run the 2 held-out probes (plus any negative probes) through
  the automated `claude -p --output-format stream-json` method above against
  the candidate SKILL.md, and record TRIGGERED/SKIPPED per probe. This
  replaces guessing at trigger behavior — a subagent's opinion of a
  description is not evidence of what a model actually does with it.
- **Body quality**: spawn a `general-purpose` subagent with **only**: the
  candidate SKILL.md, the 2 held-out probes, the direction criteria, and the
  general rubric. It has no memory of why the edit was made. Ask it whether
  body output would satisfy the held-out probes' criteria. Foreground this
  call — the loop can't continue without the score.

Score the gate **soft**, not pass/fail: for each held-out probe, the
fraction of direction criteria met (plus 1/0 for the trigger outcome), summed
over probes. With only 2 held-out probes a hard all-or-nothing score almost
never moves, so good edits get rejected as ties — the paper's `soft` gate
metric exists for exactly this small-selection-set case. Score the current
baseline the same way on the same probes.

Accept the candidate only if **both**:
- its soft direction score is strictly better than the current baseline's
  (ties rejected), and
- general rubric stays ≥8/10.

**Accepted**: overwrite the live `skills/<name>/SKILL.md` (plain tracked
file — no install step needed, symlinks resolve immediately). This candidate
becomes the new baseline for the next round.

**Rejected**: append the rejected edits + score delta to
`.claude/skillopt-runs/<skill>-<timestamp>/rejected-edits.md`. Do not retry
the same direction next round.

### 5. Round boundary — slow update + meta notes
Per-round edits only see this round's probes and can quietly undo an
earlier win. After each round that will be followed by another one, before
starting it (paper's epoch-boundary mechanisms, which it runs from epoch 2;
here rounds are few, so run it from the end of round 1):
- **Longitudinal comparison**: judge the 4 train probes under the SKILL.md
  this round started from and the one it ended with, and bucket each as
  *regressed*, *persistent failure*, *improved*, or *stable success*. Skip
  this if the round was rejected (nothing changed). Train probes only —
  held-out probes stay reserved for the gate.
- **Slow update**: turn regressions into must-preserve constraints and
  persistent failures into the top reflection target for the next round.
  If this implies a SKILL.md change, it is an ordinary candidate edit —
  it counts against the budget and goes through the step-4 gate.
- **Meta notes** (every boundary, rejected rounds included): overwrite
  `meta-notes.md` in the run dir with a few optimizer-side lessons for *this* skill — which kinds of edits helped,
  which were too vague or brittle, what level of abstraction worked.
  Revise the previous notes rather than appending; this is advice to the
  next reflection step, never text for the SKILL.md.

### 6. Repeat or stop
Default max rounds: **2**, hard cap **4**. Stop early if a round is rejected
twice in a row, or the user says stop. Do not keep spending rounds chasing
marginal gains — this is a conversational loop, not an unattended job.

### 7. Report
Print: baseline score → final score, edits applied (with rationale), edits
rejected (with reason), and the run log path. The final score is measured
on the same held-out probes the gate selected on, so it is optimistic —
say so, and point to `skill-bench`'s `--split test` for an unbiased number
(the paper keeps a separate test split for this reason). Leave the SKILL.md
change as an uncommitted working-tree diff — this skill never commits or opens a PR on
its own; that's the user's call, same as everywhere else in this repo.

## Defaults

| Parameter                  | Default              |
| --------------------------- | --------------------- |
| Rounds (epochs)             | 2 (max 4)             |
| Probe set size              | 6 (4 train / 2 held-out) |
| Edit budget                 | 3 round 1, 2 round 2+ |
| Validation gate             | soft score, strictly greater; ties rejected |
| General-rubric floor        | ≥8/10, always enforced |
| Validator                   | fresh `general-purpose` subagent, foreground |
| Round boundary              | longitudinal compare + `meta-notes.md` |

## Relationship to claude-maxer's skill-audit

`claude-maxer`'s unattended loop has been running the general-audit rubric
by hand (per CLAUDE.md's SkillOpt section) as one of its random work types.
General-audit mode here is that same rubric, now invokable on demand instead
of only when the random picker lands on it — `claude-maxer` can keep doing
its own thing, or call this skill for the audit step; either is fine.

## Guardrails

- Never expand scope mid-run — if the user's direction turns out to need a
  new skill entirely (not an edit to an existing one), stop and say so
  rather than forcing it through the edit loop.
- Never skip the validation gate to save time. An edit that "looks obviously
  right" still goes through it — the paper's ablations are explicit that
  removing the gate lets harmful proposals accumulate.
- Probe batches burn the 5h usage window fast — write the run log
  incrementally as probes complete, not only at the end, so a session-limit
  cutoff mid-run still leaves a usable report.
- `skills/obsidian-rag/` has no `SKILL.md` and isn't in `registry.yaml` —
  never target it.
