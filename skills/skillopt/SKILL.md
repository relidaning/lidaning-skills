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
the ones that measurably help. The paper's demo (`/data/apps/myai/demo/skillopt/`)
trains against a scoreable HR-compliance benchmark with a separate optimizer
LLM and dozens of API rollouts per step. We don't have that — no automated
verifier exists for "does this skill trigger well" — so this version scales
the same mechanics down to fit inside a conversation, with Claude playing
optimizer, and a **fresh-context subagent** playing the held-out validator
(same fresh-eyes principle as `/code-review`'s verify pass, standing in for
the paper's separate optimizer-vs-target-model split).

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
`rejected-edits.md` buffer first and do not re-propose anything already
rejected there — treat it as evidence of a direction that doesn't work.

### 3. Bounded edit budget
Cap edits applied this round: **3 on round 1, 2 on round 2+** (this session's
equivalent of the paper's cosine-decayed textual learning rate — start
looser, tighten as the skill stabilizes). Rank proposed edits by expected
impact on the direction criteria, apply only the top-ranked ones within
budget to a candidate `SKILL.md`. Do not do a full rewrite — bounded,
localized edits only, so later rounds can still tell what helped.

### 4. Validation gate — fresh eyes required
Spawn a `general-purpose` subagent with **only**: the candidate SKILL.md, the
2 held-out probes, the direction criteria, and the general rubric. It has no
memory of why the edit was made. Ask it to score the candidate the same way
a model deciding whether to call `Skill()` would, plus whether body output
would satisfy the held-out probes. Foreground this call — the loop can't
continue without the score.

Accept the candidate only if **both**:
- direction score is strictly better than baseline (ties rejected), and
- general rubric stays ≥8/10.

**Accepted**: overwrite the live `skills/<name>/SKILL.md` (plain tracked
file — no install step needed, symlinks resolve immediately). This candidate
becomes the new baseline for the next round.

**Rejected**: append the rejected edits + score delta to
`.claude/skillopt-runs/<skill>-<timestamp>/rejected-edits.md`. Do not retry
the same direction next round.

### 5. Repeat or stop
Default max rounds: **2**, hard cap **4**. Stop early if a round is rejected
twice in a row, or the user says stop. Do not keep spending rounds chasing
marginal gains — this is a conversational loop, not an unattended job.

### 6. Report
Print: baseline score → final score, edits applied (with rationale), edits
rejected (with reason), and the run log path. Leave the SKILL.md change as
an uncommitted working-tree diff — this skill never commits or opens a PR on
its own; that's the user's call, same as everywhere else in this repo.

## Defaults

| Parameter                  | Default              |
| --------------------------- | --------------------- |
| Rounds (epochs)             | 2 (max 4)             |
| Probe set size              | 6 (4 train / 2 held-out) |
| Edit budget                 | 3 round 1, 2 round 2+ |
| Validation gate             | strictly greater; ties rejected |
| General-rubric floor        | ≥8/10, always enforced |
| Validator                   | fresh `general-purpose` subagent, foreground |

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
- `skills/obsidian-rag/` has no `SKILL.md` and isn't in `registry.yaml` —
  never target it.
