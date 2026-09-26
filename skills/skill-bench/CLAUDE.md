# CLAUDE.md — skill-bench

Benchmarks a registered skill with frozen, versioned suites run as headless `claude -p` trials. `bench.py` is stdlib-only Python; `SKILL.md` tells the model when to build a suite and when to just run one. Measures only — fixes go to `skillopt`.

## Key concepts

**A suite exists iff `suites/<skill>/suite.json` exists.** Nothing is recorded in `registry.yaml`; the registry only confirms the target is a real skill. A suite folder holds `suite.json` (version, `frozen`, `cases_sha256`, defaults, thresholds, `disallowed_tools`, `reply_strip_regex`), `cases.jsonl`, `CARD.md` (capability spec + audit + coverage), optional `fixtures/`, and `history.jsonl`. Run artifacts go to the repo's `.claude/skill-bench-runs/<skill>/<run_id>/` (gitignored).

**Every case cites a capability-spec claim** (`T1`, `B2`, … in CARD.md), which `validate` warns about if missing. Cases are split `dev`/`test`, and scores come from `test`. Fixtures are synthetic files with known ground truth, not real repo files.

**Blind label audit before freezing.** A fresh subagent labels the trigger prompts without seeing the labels, reading only the target's SKILL.md and the other skills' descriptions. Ambiguous cases are replaced, not argued over. Then `freeze` records the cases hash. If the hash changes later, you need `freeze --bump major|minor|patch`, because results from different case sets aren't comparable.

**Test-split contamination is recorded, not hidden.** If a SKILL.md edit was driven by a test-split miss (e.g. `sb-t-003`, "test skill english-practice"), note it in the CARD and add fresh held-out cases in the next minor version.

**skill-bench's own suite is trigger-only.** Trials run with `Bash`/`Edit`/`Write` disallowed for safety, and skill-bench's behavior needs Bash. Real suite runs validate that behavior instead.

**Always-on skills pollute replies.** `DEFAULT_STRIP` removes the `=== English Practice ===` block before checks and judging, so it doesn't count toward word caps or match content regexes. Suites can override this with `reply_strip_regex`.

**Runs cut off by usage limits must not look like passes.** Rate-limit and session-limit text (`RATE_LIMIT_RE`, which also covers judge errors) stops the run. A run with errored or missing trials gets the verdict **INCOMPLETE** and is not added to history. Finish it with `run <skill> --resume <run_dir>`, which re-runs only failed or missing trials and requires the same suite hash. `report` recomputes metrics from the stored trials and refreshes that run's history row, so logic fixes apply to old runs retroactively. A first-attempt background run can exit with code -1 because of a session restart and still have written complete results, so check the run dir before rerunning.

**Uplift compares against a no-skill baseline under the same gates** (`--baseline`). An early version reported +20.8% for `context-summarize` because gates were applied differently; after the fix it was +0.8%, i.e. noise. Uplift is now paired by case with a case-bootstrap CI (that +0.8% is [-27, +30], n.s.), and per-case discrimination flags behavior cases the baseline passes just as well (3/5 there).

**The baseline denies only the target skill** (`--disallowedTools Skill(<target>)`, `BASELINE_MODE = "deny-target"`). The original baseline disabled the whole `Skill` tool, which also removed english-practice. Because CLAUDE.md mandates that skill every turn, baseline replies opened by apologizing for not being able to call it, and the judge docked them for it (seen 2026-09-26 in `cs-b-007` no-skill: "adds a preamble about failing to call Skill(english-practice)"). The deny rule was verified live: english-practice loads, and the target call returns "Skill execution blocked by permission rules". In the baseline arm, `activation_rate` therefore means "tried to call the blocked skill". History rows carry `baseline_mode`. Older rows are `no-skill-tool` and their uplift isn't comparable.

**CIs are case-level, never trial-level.** The k trials of one prompt are near copies, so recall/FPR use Wilson with n = distinct cases, and F1/score/uplift use a bootstrap that resamples whole cases. Counting trials as independent made intervals look ~2× tighter than they were. With every case correct, a bootstrap interval collapses to a point. Those are hidden rather than printed as "[100–100]". A PASS whose CI still crosses a threshold gets a "too few cases to certify" warning (zero misses needs ≥22 positives for F1 0.85 and ≥35 negatives for FPR 10%).

**Warnings qualify a verdict without changing it.** `summary.by_model[m].warnings` (report's "Read before trusting the verdict", the dashboard's amber box) covers non-significant uplift, non-discriminating cases, uncertifiable thresholds, and saturation. Thresholds alone decide PASS/FAIL, so history stays comparable.

**`--resume` replays the original run's config** (models, k, split, `--only`, `case_ids`, `--baseline`) from its manifest. Earlier it used the current flags, which could mix models or drop baseline trials. History is upserted per run_id, so a resumed run replaces its row instead of duplicating it. Transient API errors (`TRANSIENT_RE`: overloaded/5xx) retry twice with backoff. Only `RATE_LIMIT_RE` aborts.

**Judge cost and output are recorded.** `judge_cost_usd` per trial is folded into run cost (it used to be dropped), and each judge stream is saved as `raw/<trial>__judge.jsonl` for auditing disputed grades. `--dry-run` estimates from observed per-trial costs in past runs of the suite when there are any.

**Run `python3 skills/skill-bench/selftest.py` after any `bench.py` change.** It's offline (~2s, no API calls). It copies the harness, registry and the context-summarize suite into a temp repo, puts a fake `claude` first on `PATH`, and drives real `bench.py` commands through transient retries, rate-limit abort, resume (config inheritance + history dedup), the baseline deny rule, judge cost/raw capture, same-second run-dir collisions, `report` and `viz`. A mutation check confirmed it catches regressions: reverting the baseline and history fixes produced 5 failures. It also found a real bug on its first runs: run ids have one-second resolution, so back-to-back runs shared a directory and mixed trials. Run dirs now get a `-2`, `-3` suffix on collision.

**`viz` is a static snapshot.** It bakes all suites, runs, and history into `.claude/skill-bench-runs/dashboard.html`. A published artifact can't read local data, so rerun `viz` and republish after new runs.
