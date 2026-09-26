# Benchmark card: `skill-bench`

**Trigger-only suite.** skill-bench's behavior needs Bash, which trials disallow for safety. Its behavior is validated by real suite runs (e.g. `context-summarize`).

## Capability spec

- **T1**: fires when the user wants one skill measured, tested, evaluated, benchmarked, or compared before and after an edit. Includes the user's own phrasings: "benchmark my X skill", "how about my skill X", "test skill X".
- **N1**: doesn't fire for _changing_ a skill toward a goal, or for a general audit. Those belong to skillopt.
- **N2**: doesn't fire for code or model benchmarks, unit tests, skill authoring, or questions about what a skill does.

## Label audit

Blind subagent audit: **18/19 agreed.** `sb-t-010` ("score nextcloud-paper for me") was AMBIGUOUS, because "score" appears in both the skill-bench and skillopt descriptions. It was replaced with "how good is my paper-fetch skill, measured?" before freezing.
The auditor also noted that the global `anthropic-skills:skill-creator` description claims "benchmark skill performance". It competes on the positives by design, and this suite measures how often it wins.

## Coverage

| Category     | Label    | dev | test |
| ------------ | -------- | --- | ---- |
| explicit     | positive | 1   | 3    |
| paraphrase   | positive | 1   | 2    |
| implicit     | positive | 0   | 1    |
| multilingual | positive | 0   | 1    |
| noisy        | positive | 0   | 1    |
| other-skill  | negative | 1   | 2    |
| keyword-trap | negative | 1   | 2    |
| near-miss    | negative | 0   | 2    |
| off-topic    | negative | 0   | 1    |

## Contamination note

The first v1.0.0 run (2026-09-24, cut off by the usage limit) showed `sb-t-003` ("test skill english-practice") misfiring consistently: the model called english-practice itself as the "test". The SKILL.md description was then edited to say "test skill X" always means benchmark X. That edit was informed by a **test-split** case. Treat the next `sb-t-003` result as optimistic, and add fresh held-out "test skill <always-on skill>" cases in v1.1.0 to measure it cleanly.
