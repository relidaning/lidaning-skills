---
name: skill-bench
description: >
  Activate when the user wants a skill measured, tested, evaluated, or
  benchmarked — "benchmark my X skill", "test skill X", "eval X", "how about
  my skill X", "how good is X", "is X any good", "does X trigger reliably",
  "score X on Haiku", "rerun the X benchmark", "compare X before/after my
  edit" — or invokes /skill-bench. "test skill X" always means benchmark X,
  even when X is an always-on skill like english-practice: just calling X is
  not a test of it. Runs a standard benchmark: builds a
  versioned, frozen dataset (trigger + behavior cases, dev/test split) and a
  scoring method for the target skill if none exists yet, executes it with
  headless `claude -p` trials, and reports precision/recall/F1, rubric
  scores, pass@k, confidence intervals, and deltas against earlier runs. Do
  not answer "how good is my skill" by reading SKILL.md and giving an
  opinion; measure it. For *changing* a skill toward a goal use skillopt
  instead (skillopt may consume this skill's suites).
---

# skill-bench

A benchmark harness for this repo's skills. Output is numbers you can compare
across runs, not an opinion. It follows standard benchmark practice:

| Practice | How it's done here |
|---|---|
| Fixed, versioned dataset | `suites/<skill>/cases.jsonl`, frozen by sha256 in `suite.json`, semver on change |
| Held-out test split | `dev` for iterating, `test` for scoring; the history only records `test` runs |
| Documented construction | `CARD.md` (a benchmark card: capability spec, coverage, label agreement) |
| Label quality | independent subagent label audit before freezing; disputed cases dropped |
| Deterministic metrics first | trigger = exact `Skill` tool call in stream-json; behavior gates = regex/tool checks |
| Model-graded metrics second | blind LLM judge on a **binary** checklist rubric (no 1–10 Likert) |
| Repeated trials | k trials per case → pass@k, pass^k, flaky-case list, run-to-run consistency |
| Uncertainty | 95% CIs at the case level (k trials of one prompt aren't independent): case-Wilson for recall/FPR, case bootstrap for F1, scores, uplift |
| Controls | optional no-skill baseline (only the target denied via `Skill(<target>)`; other skills still load) → uplift, paired by case, with a significance flag |
| Benchmark self-checks | per-case discrimination vs baseline, headroom/saturation, "too few cases to certify", claim coverage |
| Reproducibility | each run records suite version, cases hash, SKILL.md hash, git commit, model, k |
| Leaderboard | `suites/<skill>/history.jsonl`; comparisons refuse mismatched case sets |

Everything lives in `skills/skill-bench/`. The harness is `bench.py` (stdlib
Python, no install). Run it from the repo root as
`python3 skills/skill-bench/bench.py …`.

## Step 0 — resolve the target

Map the user's phrasing to a skill name in `registry.yaml` ("my summarize
skill" → `context-summarize`). If it's ambiguous, ask. If the user named
something that isn't a skill here, say so and stop. Default model is `sonnet`.
If the user names a model ("on Haiku"), pass `--model haiku`. Pass `--model`
more than once to compare models.

Then check `skills/skill-bench/suites/<skill>/suite.json`:
- **Exists and frozen**: go to Step 4 (run).
- **Missing**: build the suite first (Steps 1–3). Tell the user in one line
  that no benchmark exists yet and you're building one. Don't ask permission;
  building the suite is part of the request.
- **Exists but unfrozen**: someone started building it. Finish Steps 1–3.

## Step 1 — capability spec

`python3 skills/skill-bench/bench.py init <skill>` scaffolds the suite dir.
Then read the target's `SKILL.md`, `metadata.yaml`, any helper files it
references, and CLAUDE.md's notes about it. Write the **capability spec** into
`CARD.md`: a numbered list of every testable claim the skill makes:

- **T-claims**: when it should trigger (each phrase family in the description)
- **N-claims**: when it must not trigger (explicit exclusions, plus adjacent
  skills that own nearby territory; check the other descriptions in
  `registry.yaml` for overlap)
- **B-claims**: behavior rules, including output shape, required steps,
  format, length limits, and safety rules ("never writes files", "asks before
  deleting")

Every case must cite the claim it tests (`"claim": "T2"`). A claim with no
case is a coverage gap. Note it in the CARD.

If the skill fires on every message (like `english-practice`), set
`"trigger_policy": "always"` in `suite.json`. The suite then has no negative
trigger cases, and precision is trivially 1.

## Step 2 — generate cases

Write `suites/<skill>/cases.jsonl`, one JSON object per line.

**Trigger cases** (minimum: ≥ 24 total; ≥ 8 positive and ≥ 8 negative in `test`).
That minimum catches gross failures but can't *certify* the thresholds: with
zero misses, a 95% CI only clears F1 0.85 at ≥ 22 distinct positive cases and
FPR 10% at ≥ 35 distinct negative cases. The report says when a PASS rests on
too few cases. Grow toward those sizes when the user will act on the verdict.

```json
{"id":"cs-t-001","split":"test","type":"trigger","label":"positive","category":"paraphrase","claim":"T1","prompt":"can you give me the gist of README.md?","rationale":"'gist' is listed in the description's cue words"}
```

Positive categories: `explicit` (uses the description's own words),
`paraphrase` (same intent, none of the cue words), `implicit` (need is clear,
task is never named), `multilingual` (the user sometimes writes Chinese),
`noisy` (typos, casual grammar), `embedded` (the request is inside a longer
message about something else).
Negative categories: `near-miss` (shares vocabulary, different intent),
`other-skill` (belongs to a neighboring skill), `keyword-trap` (contains a cue
word used in a non-triggering sense), `off-topic`.

Prompts must be what this user would actually type: short, lowercase-casual,
and grounded in this repo's real files and projects (`README.md`,
`registry.yaml`, `/data/apps/myfollows`, the Obsidian vault). Don't write
generic textbook prompts. A prompt must be answerable without side effects,
because trials run with write tools disabled. Don't make up file paths.
Either reference real files, or add a fixture under `suites/<skill>/fixtures/`
and refer to it as `{fixtures}/name.md`.

**Behavior cases** (target: ≥ 6 total, ≥ 4 in `test`, one per major B-claim):

```json
{"id":"cs-b-001","split":"test","type":"behavior","claim":"B2","prompt":"tl;dr {fixtures}/meeting.md",
 "checks":[{"kind":"skill_called"},{"kind":"max_words","n":180},{"kind":"tool_not_called","name":"Write"},
           {"kind":"regex","pattern":"postgres","flags":"i","desc":"keeps the key decision"}],
 "rubric":[{"id":"r1","criterion":"States that the team chose Postgres over Mongo"},
           {"id":"r2","criterion":"Does not invent facts absent from the source"}],
 "reference":"Source decides Postgres; owner Li; deadline Oct 3.","pass_threshold":0.75}
```

- `checks` are hard gates evaluated by code. If any gate fails, the trial
  scores 0. Kinds: `regex`, `not_regex` (on the final reply; `flags` from
  `ims`), `min_words`, `max_words`, `max_chars`, `tool_called` /
  `tool_not_called` (`name`, optional `input_regex`), `skill_called` /
  `skill_not_called` (`name` defaults to the target). Use checks for anything
  code can verify; don't hand it to the judge.
- `rubric`: 2–5 **binary, observable** criteria the judge marks met/not met.
  Write each one as a fact about the reply ("lists exactly three bullets",
  "names the file it read"). Avoid vague quality words ("is helpful", "is
  well written"). Every case needs at least one criterion that a plausible
  *wrong* answer fails. `reference` is ground truth shown only to the judge.
- Score = weighted fraction of criteria met. Pass = gates pass and score ≥
  `pass_threshold` (suite default 0.75).
- **Aim each behavior case at something the model would get wrong without
  the skill**: a skill-specific rule, format, or safety behavior, not generic
  competence. A case that the no-skill baseline passes just as well measures
  the model, not the skill. The report flags these as "no discrimination".
  context-summarize v1.0.0 had 3/5 such cases, and that's why its uplift was
  indistinguishable from zero.
- A case may cite several claims: `"claim": "B1,B3"`.

**World cases** (decision and tool-calling skills). First place the skill on
three axes: *input* (prompt, or prompt + world state), *output* (text,
decision, or actions), *grader* (code check, state check, or judge). If the
skill decides from state (usage numbers, a task list) or acts through its
scripts, a prompt-only case can only quiz it on its docs. Give it a **world**
instead:

```json
{"id":"tq-b-001","split":"test","type":"behavior","claim":"B1","world":"two-undone",
 "env":{"TASKS_QUEUE_FILE":"{world}/Tasks.md"},
 "prompt":"what should claude work on next?",
 "checks":[{"kind":"tool_called","name":"Bash","input_regex":"tasks_queue\\.py"},
           {"kind":"decision","pattern":"(?i)upload test","reject":["(?i)write the docs"]},
           {"kind":"file_unchanged","path":"Tasks.md"}],
 "rubric":[...]}
```

- `world` names a folder `suites/<skill>/worlds/<name>/`. Each trial gets a
  fresh copy in a temp dir **outside the repo** (so the repo's
  `settings.local.json` allow rules don't apply), with the repo's installed
  skills and `CLAUDE.md` symlinked in. The end state is archived to the run's
  `worlds/<trial>/`.
- `env` is injected into the trial, and `{world}` expands to that trial's copy
  (in `env` and `prompt`; `{repo}` expands to the repo root). This is the
  **test seam**: the skill's scripts must read their state from an env var
  (e.g. `TASKS_QUEUE_FILE`) so the trial never touches the real vault, usage
  endpoint or crontab. If the skill has no seam, adding one is part of
  building the suite. Say so, and keep it a small, default-off change.
- World trials run under `--permission-mode dontAsk` with an **allowlist**:
  `Read`, `Glob`, `Grep`, `Skill`, plus `suite.json` → `sandbox.allowed_tools`
  and the case's `allowed_tools` (e.g. `"Bash(python3 *tasks_queue.py*)"`).
  Everything else is denied without a prompt. Allowlist only the commands the
  skill documents.
- Extra check kinds: `decision` (`pattern` must match the final reply, none of
  `reject` may), and state checks on the world after the run: `file_regex`,
  `file_not_regex`, `file_exists`, `file_absent`, `file_unchanged` (`path`
  relative to the world). Prefer these to the judge. The judge also sees which
  world files changed.
- Write one world per **side of each decision boundary** (e.g. one undone
  task vs. none; a done-only list; a wrapped continuation line), not random
  states. The right answer follows from the rule, so it's a `decision` check,
  not a rubric item.

**Splits**: put about one third in `dev` and two thirds in `test`, stratified
so every category appears in `test`. No near-duplicate prompts across splits.
`validate` rejects exact duplicates.

## Step 3 — label audit, then freeze

1. `python3 skills/skill-bench/bench.py validate <skill>`. Fix every ERROR.
   Fix balance WARNs where you can. `validate` also checks that cases cite
   claims the CARD's capability spec defines (`**T1**`, `**B2**`, …) and lists
   claims with no `test` case. Cover them, or name them as gaps in the CARD.
2. **Independent label audit.** Spawn one `general-purpose` subagent in the
   foreground. Give it **only** the target's SKILL.md frontmatter description
   and body, the other registered skills' descriptions, and the trigger
   prompts with ids, **without labels**. Ask it to label each prompt
   positive/negative with one line of reasoning. Also give it the behavior
   cases with their rubrics, and ask it to flag any criterion that is
   ambiguous or that a correct answer could fail.
3. Compare. For every trigger case where the auditor disagrees, either drop it
   or rewrite it until the intent is unambiguous. Ambiguous cases measure
   noise. Fix or drop any rubric criterion the auditor flagged. Record the
   agreement rate (`n agreed / n`) and what you changed in `CARD.md`.
4. Fill in the CARD's coverage table. Then run
   `python3 skills/skill-bench/bench.py freeze <skill>`, which records the
   hash and sets version 1.0.0.

After this, **do not edit `cases.jsonl` to make a skill look better.** Changing
cases requires `freeze --bump` (major: labels changed meaning; minor: cases
added; patch: typo fixes), and results across versions are marked not
comparable.

## Step 4 — run

```bash
python3 skills/skill-bench/bench.py run <skill> --dry-run      # trial count + cost estimate
python3 skills/skill-bench/bench.py run <skill> [--model haiku] [--model sonnet] [-k 3] [--baseline]
```

- Defaults come from `suite.json` (`split=test`, `k=2`, `jobs=4`).
- Use `--baseline` on the first run of a new suite, and whenever the user asks
  whether the skill "helps" or is "worth it". It reruns behavior cases with
  only the target denied (`--disallowedTools Skill(<target>)`), so always-on
  skills like english-practice still load in both arms. Runs before
  2026-09-26 disabled the whole Skill tool (`baseline_mode: no-skill-tool` in
  history). Don't compare their uplift with newer runs.
- Run it in the background (`run_in_background`). A full suite takes minutes.
  Trials are appended to `trials.jsonl` as they finish, so a usage-limit
  cutoff still leaves partial data. The harness detects rate-limit errors and
  stops early instead of burning the rest of the window.
- Check the 5h window first if the run is large (> ~60 trials): read
  `~/.claude/state/usage_snapshot.json` (claude-maxer keeps it fresh). If
  `rate_limits.five_hour.used_percentage` is ≥ 80, tell the user and offer a smaller run
  (`--only trigger`, `-k 1`, or `--split dev`).
- Trials run in the repo root with write-capable tools disallowed (list in
  `suite.json` → `disallowed_tools`). Only loosen that list if the user
  explicitly asks and the skill's side effects are safe. Afterward the
  harness diffs `git status`. If the report says the repo changed during the
  run, check `ListAgents` for another session before blaming a probe, then
  inspect the diff.
- Replies are scored after stripping `suite.json` → `reply_strip_regex`
  matches. By default that's the `english-practice` block, which fires on
  every turn here and would otherwise count toward word caps and regexes. Add
  patterns for any other always-on skill whose output lands in replies.
- If a run is cut off (usage limit, session restart), finish it with
  `run <skill> --resume <run_dir>`. It reuses that run's models, k, split,
  `--only`/`--case` and `--baseline` (don't repeat them), re-executes only
  failed or missing trials, requires the same suite and SKILL.md hashes, and
  replaces the run's history row instead of adding a second one.
- Transient API errors (overloaded/5xx) are retried twice with backoff. Only
  usage/rate limits abort the run.
- Smoke tests while building a suite: `--allow-unfrozen --split dev -k 1`.
  These never enter history.

Results go to `.claude/skill-bench-runs/<skill>/<run-id>/`: `manifest.json`,
`trials.jsonl`, `results.json`, `report.md`, and `raw/` transcripts. Frozen,
full runs also append one row per model to `suites/<skill>/history.jsonl`.

## Step 5 — report to the user

Read `report.md` and give the user:

1. **Headline**: one line per model, with verdict (PASS/FAIL against
   `suite.json` thresholds), composite, trigger F1 / precision / recall / FPR,
   behavior score, pass rate, uplift with its CI if the baseline ran, and cost
   (judge calls included).
   Then relay every line of the report's **"Read before trusting the
   verdict"** block. These don't change the verdict, but they qualify it:
   uplift not significant (`n.s.`), behavior cases with no discrimination, a
   suite too small to certify its thresholds, or a saturated suite that can't
   show improvement. A PASS with any of these is "passes, but the benchmark
   can't vouch for it yet". Say so in those words, and name the fix (more
   cases, more discriminating behavior cases, `freeze --bump minor`).
2. **Where it breaks**: the categories with the lowest fire rate or highest
   FPR, the consistently-wrong cases (quote the prompts), the claims marked ⚠
   in the **By claim** table (say it as "the skill breaks promise B3: …"),
   and the most-missed rubric criteria. For one or two failures, open the raw transcript and say
   *why* it failed (skill never called, called but ignored a rule, judge
   disagreed, etc.). Name the transcript path. If you suspect the judge, read
   its raw output next to the trial (`raw/<trial>__judge.jsonl`).
3. **Change since last run**, if the report has a comparison. Say explicitly
   whether SKILL.md changed between the runs. If it didn't, the delta is
   noise, whatever its size. Otherwise use the report's **paired by case**
   deltas (same cases, both runs, case-bootstrap CI). A delta marked `(n.s.)`
   is not an improvement or a regression, however large it looks.
4. The report path. For a visual view, run `bench.py viz`. It bakes every
   suite, run and history row into `.claude/skill-bench-runs/dashboard.html`,
   which opens locally in any browser and can be republished as an artifact.
   It's a static snapshot, so rerun `viz` after new runs.

Don't round away bad news. If the benchmark itself looks broken (e.g. every
trial errored, or the target never loaded), say so. Don't report numbers from
a broken run.

Don't fix the skill as part of this request. If the results suggest a fix,
offer to run `skillopt` with the failing categories as its direction, using
this suite's `dev` split for reflection and `test` as the held-out gate.

## Other commands

- `bench.py history <skill>` prints the leaderboard for "how has X trended".
- `bench.py report <run_dir>` re-renders a report after harness changes.
- `python3 skills/skill-bench/selftest.py` is an offline regression test of the
  harness (fake `claude`, ~2s, no usage). Run it after editing `bench.py`.
- To extend a suite (the user found a new failure mode): add cases, re-audit
  only the new ones, then `freeze --bump minor`.

## Guardrails

- Never report scores from an unfrozen suite as the benchmark result. Label
  them "smoke test".
- Never look at `test` cases while editing the target skill in the same
  session. That's leakage. Use `dev`.
- Probe runs burn the 5h window. Prefer `-k 2` on one model unless the user
  asks for more.
- `served_models` in the report shows the model that actually answered. If it
  differs from the one requested (e.g. a refusal fallback), say so.
