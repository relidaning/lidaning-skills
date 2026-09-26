#!/usr/bin/env python3
"""skill-bench harness: frozen, versioned benchmark suites for Claude Code skills.

Stdlib only. Each target skill gets a suite under suites/<skill>/:

    suite.json     manifest (version, frozen cases hash, defaults, thresholds)
    cases.jsonl    one case per line (trigger or behavior), each with a split
    CARD.md        benchmark card: what is measured, how the data was built
    fixtures/      optional files referenced from prompts as {fixtures}/...
    history.jsonl  one summary line per run (the leaderboard)

Subcommands:
    init <skill>                scaffold an empty suite for a registered skill
    validate <skill>            schema + balance + hash checks (run before freeze/run)
    freeze <skill> [--bump P]   record the cases hash; bump version if cases changed
    run <skill> [options]       execute trials with `claude -p`, score, write report
    report <run_dir>            re-render report.md from a run's results.json
    history <skill>             print the leaderboard for a suite
    viz [--out F]               bake all suites/runs into one HTML dashboard

Every trial is one headless `claude -p` session in the repo root (the skill's
real environment) with write-capable tools disallowed. Trigger = a `Skill` tool
call whose `skill` input names the target. Behavior = deterministic checks
(gates) + a blind LLM judge scoring a binary rubric.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SUITES = HERE / "suites"
RUNS = REPO / ".claude" / "skill-bench-runs"
REGISTRY = REPO / "registry.yaml"

SCHEMA_VERSION = 1
# How the no-skill arm removes the target. "deny-target" = --disallowedTools
# Skill(<target>) (other skills still load). Runs before 2026-09-26 used
# "no-skill-tool" (the whole Skill tool disabled); their uplift isn't comparable.
BASELINE_MODE = "deny-target"
SAFE_DISALLOWED = [
    "Bash",
    "Edit",
    "Write",
    "NotebookEdit",
    "Task",
    "Agent",
    "mcp__obsidian__vault_write",
    "mcp__obsidian__vault_append",
    "mcp__obsidian__vault_patch",
    "mcp__obsidian__vault_delete",
    "mcp__nextcloud__nc_webdav_write_file",
    "mcp__nextcloud__nc_webdav_delete_resource",
    "mcp__nextcloud__nc_webdav_move_resource",
    "mcp__nextcloud__nc_webdav_copy_resource",
    "mcp__rag__rag_ingest",
    "mcp__rag__rag_load",
    "mcp__rag__rag_remove",
    "mcp__rag__rag_clear",
]
TRIGGER_CATEGORIES = {
    "positive": {
        "explicit",
        "paraphrase",
        "implicit",
        "multilingual",
        "noisy",
        "embedded",
    },
    "negative": {"near-miss", "other-skill", "off-topic", "keyword-trap"},
}
CHECK_KINDS = {
    "regex",
    "not_regex",
    "min_words",
    "max_words",
    "max_chars",
    "tool_called",
    "tool_not_called",
    "skill_called",
    "skill_not_called",
}
# Blocks other always-on skills add to every reply; stripped before checks/judge
# so they don't count toward length caps or match content regexes.
DEFAULT_STRIP = r"(?s)=== English Practice ===.*?=== English Practice ===\s*"
# Rough per-trial USD used only for --dry-run estimates when no history exists.
COST_GUESS = {"haiku": 0.05, "sonnet": 0.15, "opus": 0.40, "fable": 0.60}
JUDGE_SYSTEM = (
    "You are a strict, impartial benchmark grader. You grade one AI assistant "
    "transcript against a fixed checklist. For each criterion decide met=true "
    "only if the transcript clearly satisfies it; when in doubt, met=false. "
    "Quote short evidence. Do not reward length or politeness. Output ONLY a JSON "
    "object, no prose, no code fences."
)


# ----------------------------------------------------------------------------
# helpers


def die(msg: str, code: int = 1) -> None:
    print(f"[skill-bench] error: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str) -> None:
    print(f"[skill-bench] {msg}", file=sys.stderr, flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def registered_skills() -> list[str]:
    if not REGISTRY.exists():
        return []
    return re.findall(r"^\s*-\s*name:\s*(\S+)", REGISTRY.read_text(), re.M)


def skill_dir(skill: str) -> Path:
    return REPO / "skills" / skill


def suite_dir(skill: str) -> Path:
    return SUITES / skill


def load_suite(skill: str) -> tuple[dict, list[dict]]:
    d = suite_dir(skill)
    if not (d / "suite.json").exists():
        die(f"no suite for '{skill}' — run: bench.py init {skill}")
    suite = json.loads((d / "suite.json").read_text())
    cases = []
    for i, line in enumerate((d / "cases.jsonl").read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            die(f"cases.jsonl line {i}: {e}")
    return suite, cases


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except Exception:
        return ""


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_mean_ci(
    xs: list[float], iters: int = 2000, seed: int = 0
) -> tuple[float, float]:
    if not xs:
        return (float("nan"), float("nan"))
    if len(xs) == 1:
        return (xs[0], xs[0])
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(rng.choice(xs) for _ in range(n)) / n for _ in range(iters))
    return (means[int(0.025 * iters)], means[int(0.975 * iters) - 1])


def case_wilson(k: int, n: int, n_cases: int) -> tuple[float, float]:
    """Wilson CI for a trial-level rate k/n, with the sample size shrunk to the
    number of distinct cases (worst-case design effect for correlated trials)."""
    if n == 0 or n_cases == 0:
        return (float("nan"), float("nan"))
    p = k / n
    return wilson(round(p * n_cases), n_cases) if n_cases < n else wilson(k, n)


def cases_to_certify(max_rate: float) -> int:
    """Smallest n where 0 failures out of n gives a Wilson upper bound ≤ max_rate."""
    n = 1
    while wilson(0, n)[1] > max_rate and n < 10000:
        n += 1
    return n


def cluster_bootstrap(groups: list, stat, iters: int = 2000, seed: int = 0):
    """95% CI for stat(list of groups), resampling whole cases. The k trials of one
    case are correlated (same prompt), so resampling trials independently — as a
    plain Wilson interval over trials does — makes intervals too narrow."""
    nan = (float("nan"), float("nan"))
    if len(groups) < 2:
        return nan
    rng = random.Random(seed)
    vals = []
    for _ in range(iters):
        v = stat([rng.choice(groups) for _ in groups])
        if v is not None and not math.isnan(v):
            vals.append(v)
    if len(vals) < iters // 2:
        return nan
    vals.sort()
    return (vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1])


def trigger_f1(trials: list[dict]) -> float:
    tp = sum(r["label"] == "positive" and r["triggered"] for r in trials)
    fn = sum(r["label"] == "positive" and not r["triggered"] for r in trials)
    fp = sum(r["label"] == "negative" and r["triggered"] for r in trials)
    if not tp:
        return 0.0 if tp + fn else float("nan")
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    return 2 * prec * rec / (prec + rec)


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def paired_delta(a: dict, b: dict) -> dict | None:
    """Mean of per-case (a − b) over cases present in both, with a case-bootstrap
    CI. a/b map case id → list of per-trial values. significant = CI excludes 0."""
    shared = sorted(set(a) & set(b))
    if not shared:
        return None
    diffs = [mean(a[c]) - mean(b[c]) for c in shared]
    lo, hi = cluster_bootstrap(diffs, mean)
    return {
        "delta": mean(diffs),
        "ci": (lo, hi),
        "n_cases": len(shared),
        "significant": not math.isnan(lo) and (lo > 0 or hi < 0),
    }


def fmt_delta(d: dict | None) -> str:
    if not d:
        return "—"
    lo, hi = d["ci"]
    ci = "" if math.isnan(lo) else f" [{lo * 100:+.0f}, {hi * 100:+.0f}]"
    return f"{d['delta'] * 100:+.1f}%{ci}{'' if d['significant'] else ' (n.s.)'}"


def fmt(x, pct: bool = True, nd: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x * 100:.{nd}f}%" if pct else f"{x:.{nd}f}"


def fmt_ci(ci) -> str:
    lo, hi = ci
    if lo is None or math.isnan(lo) or lo == hi:  # degenerate: every resample identical
        return ""
    return f" [{lo * 100:.0f}–{hi * 100:.0f}]"


# ----------------------------------------------------------------------------
# init / validate / freeze


def cmd_init(a) -> None:
    skill = a.skill
    if (
        skill not in registered_skills()
        and not (skill_dir(skill) / "SKILL.md").exists()
    ):
        die(f"'{skill}' is not in registry.yaml and has no skills/{skill}/SKILL.md")
    d = suite_dir(skill)
    if (d / "suite.json").exists() and not a.force:
        die(f"suite already exists at {d} (use --force to overwrite the manifest)")
    d.mkdir(parents=True, exist_ok=True)
    (d / "fixtures").mkdir(exist_ok=True)
    suite = {
        "schema_version": SCHEMA_VERSION,
        "suite": skill,
        "target_skill": skill,
        "version": "0.1.0",
        "frozen": False,
        "cases_sha256": "",
        "created": dt.date.today().isoformat(),
        "skill_sha256_at_creation": sha256_file(skill_dir(skill) / "SKILL.md"),
        "trigger_policy": "conditional",
        "defaults": {
            "models": ["sonnet"],
            "k": 2,
            "split": "test",
            "jobs": 4,
            "timeout_s": 300,
            "judge_model": "sonnet",
            "pass_threshold": 0.75,
        },
        "thresholds": {
            "trigger_f1": 0.85,
            "false_positive_rate": 0.10,
            "behavior_pass_rate": 0.70,
        },
        "disallowed_tools": SAFE_DISALLOWED,
        "reply_strip_regex": [DEFAULT_STRIP],
        "notes": "",
    }
    (d / "suite.json").write_text(json.dumps(suite, indent=2) + "\n")
    if not (d / "cases.jsonl").exists() or a.force:
        (d / "cases.jsonl").write_text("")
    if not (d / "CARD.md").exists():
        (d / "CARD.md").write_text(
            (HERE / "CARD.template.md").read_text().replace("{{skill}}", skill)
        )
    print(d)


def validate(skill: str, quiet: bool = False, ignore_hash: bool = False) -> list[str]:
    suite, cases = load_suite(skill)
    errs, warns = [], []
    for key in ("suite", "target_skill", "version", "defaults", "thresholds"):
        if key not in suite:
            errs.append(f"suite.json missing '{key}'")
    policy = suite.get("trigger_policy", "conditional")
    if policy not in ("conditional", "always"):
        errs.append("trigger_policy must be 'conditional' or 'always'")
    seen, prompts = set(), {}
    for c in cases:
        cid = c.get("id", "<no id>")
        if cid in seen:
            errs.append(f"duplicate id {cid}")
        seen.add(cid)
        if c.get("split") not in ("dev", "test"):
            errs.append(f"{cid}: split must be dev|test")
        p = (c.get("prompt") or "").strip()
        if not p:
            errs.append(f"{cid}: empty prompt")
        if not c.get("claim"):
            warns.append(
                f"{cid}: no 'claim' — every case should cite a capability-spec claim in CARD.md"
            )
        norm = re.sub(r"\W+", " ", p.lower()).strip()
        if norm in prompts:
            errs.append(
                f"{cid}: duplicate prompt of {prompts[norm]} (leakage across splits?)"
            )
        prompts[norm] = cid
        t = c.get("type")
        if t == "trigger":
            lab, cat = c.get("label"), c.get("category")
            if lab not in ("positive", "negative"):
                errs.append(f"{cid}: trigger label must be positive|negative")
            elif cat not in TRIGGER_CATEGORIES[lab]:
                errs.append(
                    f"{cid}: category '{cat}' invalid for {lab} "
                    f"(allowed: {sorted(TRIGGER_CATEGORIES[lab])})"
                )
            if policy == "always" and lab == "negative":
                errs.append(f"{cid}: trigger_policy=always admits no negative cases")
            if not c.get("rationale"):
                warns.append(f"{cid}: no rationale for the label")
        elif t == "behavior":
            checks, rubric = c.get("checks", []), c.get("rubric", [])
            if not checks and not rubric:
                errs.append(f"{cid}: behavior case needs checks and/or rubric")
            for ch in checks:
                if ch.get("kind") not in CHECK_KINDS:
                    errs.append(f"{cid}: unknown check kind {ch.get('kind')}")
                if ch.get("kind") in ("regex", "not_regex"):
                    try:
                        re.compile(ch.get("pattern", ""))
                    except re.error as e:
                        errs.append(f"{cid}: bad regex {ch.get('pattern')!r}: {e}")
            ids = [r.get("id") for r in rubric]
            if len(ids) != len(set(ids)) or any(not i for i in ids):
                errs.append(f"{cid}: rubric items need unique ids")
            for r in rubric:
                if not r.get("criterion"):
                    errs.append(f"{cid}: rubric item {r.get('id')} has no criterion")
        else:
            errs.append(f"{cid}: type must be trigger|behavior")
        if "{fixtures}" in p:
            for ref in re.findall(r"\{fixtures\}/([\w./-]+)", p):
                if not (suite_dir(skill) / "fixtures" / ref).exists():
                    errs.append(f"{cid}: missing fixture {ref}")
    declared = card_claims(skill)
    # balance / coverage
    for split in ("dev", "test"):
        trig = [
            c for c in cases if c.get("type") == "trigger" and c.get("split") == split
        ]
        beh = [
            c for c in cases if c.get("type") == "behavior" and c.get("split") == split
        ]
        pos = sum(c.get("label") == "positive" for c in trig)
        neg = len(trig) - pos
        if split == "test":
            if pos < 6:
                warns.append(
                    f"test split has only {pos} positive trigger cases (want >= 6)"
                )
            if policy == "conditional" and neg < 6:
                warns.append(
                    f"test split has only {neg} negative trigger cases (want >= 6)"
                )
            wants_beh = not declared or any(c.startswith("B") for c in declared)
            if len(beh) < 3 and wants_beh:
                warns.append(
                    f"test split has only {len(beh)} behavior cases (want >= 3)"
                )
        if not trig and not beh:
            warns.append(f"{split} split is empty")
    # claim coverage against the CARD's capability spec
    if declared:
        cited = {cl for c in cases for cl in claims_of(c)}
        for cl in sorted(cited - set(declared)):
            warns.append(f"cases cite claim {cl}, which CARD.md's capability spec doesn't define")
        test_cited = {cl for c in cases if c.get("split") == "test" for cl in claims_of(c)}
        gaps = [cl for cl in declared if cl not in test_cited]
        if gaps:
            warns.append(
                f"claims with no test-split case (coverage gaps — list them in the CARD): "
                f"{', '.join(gaps)}"
            )
    elif cases:
        warns.append("CARD.md declares no **T1**/**N1**/**B1**-style claims in a capability-spec section")
    # freeze integrity
    cur = sha256_file(suite_dir(skill) / "cases.jsonl")
    if suite.get("frozen") and not ignore_hash and suite.get("cases_sha256") != cur:
        errs.append(
            "cases.jsonl changed since freeze — revert it or run `freeze --bump` "
            "(results from different case sets are not comparable)"
        )
    if not quiet:
        for w in warns:
            print(f"WARN  {w}")
        for e in errs:
            print(f"ERROR {e}")
        n_t = sum(c.get("type") == "trigger" for c in cases)
        print(
            f"{skill}: {len(cases)} cases ({n_t} trigger, {len(cases) - n_t} behavior), "
            f"v{suite.get('version')}, frozen={suite.get('frozen')}, "
            f"{len(errs)} error(s), {len(warns)} warning(s)"
        )
    return errs


def cmd_validate(a) -> None:
    if validate(a.skill):
        sys.exit(1)


def cmd_freeze(a) -> None:
    d = suite_dir(a.skill)
    suite, _ = load_suite(a.skill)
    cur = sha256_file(d / "cases.jsonl")
    prev = suite.get("cases_sha256") or ""
    if suite.get("frozen") and prev == cur and not a.bump:
        print(f"{a.skill} v{suite['version']} already frozen (cases_sha256={cur[:12]})")
        return
    if validate(a.skill, ignore_hash=True):
        die("fix validation errors before freezing")
    if prev and prev != cur and not a.bump:
        die(
            "cases changed since the last freeze; pass --bump major|minor|patch "
            "(major: labels/cases changed meaning; minor: cases added; patch: typo fixes)"
        )
    if not prev:
        suite["version"] = "1.0.0"
    elif a.bump:
        major, minor, patch = (int(x) for x in suite["version"].split("."))
        suite["version"] = {
            "major": f"{major + 1}.0.0",
            "minor": f"{major}.{minor + 1}.0",
            "patch": f"{major}.{minor}.{patch + 1}",
        }[a.bump]
    suite.update(
        frozen=True,
        cases_sha256=cur,
        frozen_at=dt.datetime.now().isoformat(timespec="seconds"),
    )
    (d / "suite.json").write_text(json.dumps(suite, indent=2) + "\n")
    print(f"frozen {a.skill} v{suite['version']} cases_sha256={cur[:12]}")


# ----------------------------------------------------------------------------
# running trials


def child_env() -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if not (k == "CLAUDECODE" or k.startswith("CLAUDE_CODE_"))
    }
    env["NODE_USE_ENV_PROXY"] = "1"
    return env


def claude_bin() -> str:
    return shutil.which("claude") or str(Path.home() / ".local/bin/claude")


def parse_stream(raw: str, target: str) -> dict:
    out = {
        "skills_loaded": None,
        "tool_calls": [],
        "skill_calls": [],
        "text": "",
        "cost_usd": 0.0,
        "duration_ms": None,
        "num_turns": None,
        "is_error": False,
        "subtype": None,
        "model": None,
    }
    last_text = []
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "system" and e.get("subtype") == "init":
            out["skills_loaded"] = e.get("skills") or []
            out["model"] = e.get("model")
        elif t == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    out["tool_calls"].append({"name": b.get("name"), "input": inp})
                    if b.get("name") == "Skill":
                        out["skill_calls"].append(str(inp.get("skill", "")))
                elif b.get("type") == "text":
                    last_text.append(b.get("text", ""))
        elif t == "result":
            out["cost_usd"] = e.get("total_cost_usd") or 0.0
            out["duration_ms"] = e.get("duration_ms")
            out["num_turns"] = e.get("num_turns")
            out["is_error"] = bool(e.get("is_error"))
            out["subtype"] = e.get("subtype")
            if isinstance(e.get("result"), str):
                out["text"] = e["result"]
    if not out["text"]:
        out["text"] = "\n".join(last_text)

    def is_target(s: str) -> bool:
        return s == target or s.endswith(":" + target)

    out["triggered"] = any(is_target(s) for s in out["skill_calls"])
    names = [c["name"] for c in out["tool_calls"]]
    first = next(
        (
            i
            for i, c in enumerate(out["tool_calls"])
            if c["name"] == "Skill" and is_target(str(c["input"].get("skill", "")))
        ),
        None,
    )
    out["trigger_index"] = first
    # "before work" = the target fired before any non-Skill tool call
    out["trigger_before_work"] = first is not None and all(
        n == "Skill" for n in names[:first]
    )
    out["target_loaded"] = out["skills_loaded"] is None or any(
        is_target(s) for s in out["skills_loaded"]
    )
    return out


RATE_LIMIT_RE = re.compile(
    r"usage limit|rate limit|session limit|weekly limit|hit your .*limit|\b429\b|limit reached|requires usage credits",
    re.I,
)
# Server-side blips worth a retry rather than an abort (checked before RATE_LIMIT_RE).
TRANSIENT_RE = re.compile(
    r"overloaded|\b529\b|\b50[023]\b|internal server error|ECONNRESET|socket hang up|fetch failed",
    re.I,
)
TRANSIENT_RETRIES = 2
TRANSIENT_BACKOFF_S = 20


def run_claude(
    prompt: str,
    model: str,
    disallowed: list[str],
    timeout_s: int,
    cwd: Path,
    extra: list[str] | None = None,
) -> tuple[str, str, int]:
    cmd = [
        claude_bin(),
        "-p",
        "--model",
        model,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        *(extra or []),
    ]
    if disallowed:
        cmd += ["--disallowedTools", *disallowed]
    try:
        p = subprocess.run(
            cmd,
            input=prompt,
            cwd=cwd,
            env=child_env(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        so = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return so, "TIMEOUT", -9


def eval_checks(checks: list[dict], tr: dict, target: str) -> list[dict]:
    text = tr["text"] or ""
    words = len(re.findall(r"\S+", text))
    res = []
    for ch in checks:
        k = ch["kind"]
        flags = re.I if "i" in ch.get("flags", "") else 0
        flags |= re.S if "s" in ch.get("flags", "") else 0
        flags |= re.M if "m" in ch.get("flags", "") else 0
        ok = False
        if k == "regex":
            ok = re.search(ch["pattern"], text, flags) is not None
        elif k == "not_regex":
            ok = re.search(ch["pattern"], text, flags) is None
        elif k == "min_words":
            ok = words >= ch["n"]
        elif k == "max_words":
            ok = words <= ch["n"]
        elif k == "max_chars":
            ok = len(text) <= ch["n"]
        elif k in ("tool_called", "tool_not_called"):
            pat = (
                re.compile(ch.get("input_regex", ""), re.I)
                if ch.get("input_regex")
                else None
            )
            hit = any(
                c["name"] == ch["name"]
                and (
                    pat is None
                    or pat.search(json.dumps(c["input"], ensure_ascii=False))
                )
                for c in tr["tool_calls"]
            )
            ok = hit if k == "tool_called" else not hit
        elif k in ("skill_called", "skill_not_called"):
            name = ch.get("name", target)
            hit = any(s == name or s.endswith(":" + name) for s in tr["skill_calls"])
            ok = hit if k == "skill_called" else not hit
        res.append(
            {
                "kind": k,
                "desc": ch.get("desc")
                or ch.get("pattern")
                or ch.get("name")
                or str(ch.get("n", "")),
                "pass": ok,
            }
        )
    return res


def trace_summary(tr: dict, limit: int = 40) -> str:
    lines = []
    for c in tr["tool_calls"][:limit]:
        inp = json.dumps(c["input"], ensure_ascii=False)
        lines.append(f"- {c['name']}({inp[:200]}{'…' if len(inp) > 200 else ''})")
    if len(tr["tool_calls"]) > limit:
        lines.append(f"- … {len(tr['tool_calls']) - limit} more")
    return "\n".join(lines) or "(no tool calls)"


def judge(
    case: dict,
    tr: dict,
    judge_model: str,
    timeout_s: int,
    work: Path,
    raw_path: Path | None = None,
) -> dict:
    """Grade one reply against the case's binary rubric. The judge's raw stream is
    kept next to the trial's (raw_path) so a disputed grade can be audited, and its
    cost is returned so run totals aren't understated."""
    rubric = case.get("rubric", [])
    if not rubric:
        return {"score": 1.0, "criteria": [], "error": None, "cost_usd": 0.0}
    crit = "\n".join(f"- id={r['id']}: {r['criterion']}" for r in rubric)
    ref = case.get("reference")
    prompt = (
        f"{JUDGE_SYSTEM}\n\n## User request given to the assistant\n{case['prompt']}\n\n"
        + (
            f"## Grader-only reference notes (not shown to the assistant)\n{ref}\n\n"
            if ref
            else ""
        )
        + f"## Tool calls the assistant made\n{trace_summary(tr)}\n\n"
        f"## Assistant's final reply\n<<<\n{(tr['text'] or '')[:14000]}\n>>>\n\n"
        f"## Checklist\n{crit}\n\n"
        'Return exactly: {"criteria":[{"id":"<id>","met":true|false,"evidence":"<short quote or reason>"}]}'
    )
    last_err, cost, raws = None, 0.0, []
    for _ in range(2):
        so, se, rc = run_claude(
            prompt,
            judge_model,
            [],
            timeout_s,
            work,
            extra=["--tools", "", "--system-prompt", JUDGE_SYSTEM],
        )
        raws.append(so + (f"\n//STDERR {se}" if se else ""))
        if raw_path:
            raw_path.write_text("\n//ATTEMPT\n".join(raws))
        js = parse_stream(so, "__none__")
        cost += js["cost_usd"] or 0.0
        jt = js["text"]
        m = re.search(r"\{.*\}", jt or "", re.S)
        if not m:
            last_err = f"judge returned no JSON (rc={rc}): {(jt or se)[:200]}"
            continue
        try:
            data = json.loads(m.group(0))
            got = {str(x.get("id")): x for x in data.get("criteria", [])}
            items, tot, num = [], 0.0, 0.0
            for r in rubric:
                w = float(r.get("weight", 1))
                g = got.get(str(r["id"]), {})
                met = bool(g.get("met"))
                items.append(
                    {
                        "id": r["id"],
                        "met": met,
                        "evidence": str(g.get("evidence", ""))[:300],
                    }
                )
                tot += w
                num += w * met
            missing = [r["id"] for r in rubric if str(r["id"]) not in got]
            return {
                "score": num / tot if tot else 1.0,
                "criteria": items,
                "error": f"judge omitted {missing}" if missing else None,
                "cost_usd": cost,
            }
        except Exception as e:  # noqa: BLE001
            last_err = f"judge JSON parse failed: {e}"
    return {"score": None, "criteria": [], "error": last_err, "cost_usd": cost}


def run_trial(
    job: dict, suite: dict, run_dir: Path, stop: threading.Event, judge_dir: Path
) -> dict:
    if stop.is_set():
        return {**job["meta"], "status": "skipped"}
    case, model, cond, t = job["case"], job["model"], job["cond"], job["trial"]
    target = suite["target_skill"]
    prompt = case["prompt"].replace("{fixtures}", str(suite_dir(target) / "fixtures"))
    disallowed = list(suite.get("disallowed_tools", SAFE_DISALLOWED))
    if cond == "no-skill":
        # Deny only the target. Disabling the whole Skill tool also removes
        # always-on skills (english-practice) whose absence the model then
        # narrates in its reply, and the judge penalizes the baseline for it.
        disallowed.append(f"Skill({target})")
    for attempt in range(TRANSIENT_RETRIES + 1):
        so, se, rc = run_claude(prompt, model, disallowed, job["timeout"], REPO)
        tr = parse_stream(so, target)
        failed = rc != -9 and (tr["is_error"] or (rc != 0 and not tr["text"]))
        msg = (tr["text"] or se or "")[:300]
        if not (failed and TRANSIENT_RE.search(msg) and not RATE_LIMIT_RE.search(msg)):
            break
        if attempt < TRANSIENT_RETRIES and not stop.is_set():
            log(f"{case['id']} {model} {cond} t{t}: transient error, retrying — {msg[:80]}")
            stop.wait(TRANSIENT_BACKOFF_S * (attempt + 1))
    raw_name = f"{case['id']}__{model}__{cond}__t{t}.jsonl"
    (run_dir / "raw" / raw_name).write_text(so + (f"\n//STDERR {se}" if se else ""))
    rec = {
        **job["meta"],
        "raw": f"raw/{raw_name}",
        "cost_usd": tr["cost_usd"],
        "duration_ms": tr["duration_ms"],
        "num_turns": tr["num_turns"],
        "served_model": tr["model"],
        "skill_calls": tr["skill_calls"],
        "triggered": tr["triggered"],
        "trigger_before_work": tr["trigger_before_work"],
        "tool_names": [c["name"] for c in tr["tool_calls"]],
    }
    if rc == -9:
        return {**rec, "status": "error", "error": "timeout"}
    if tr["is_error"] or (rc != 0 and not tr["text"]):
        msg = (tr["text"] or se or "")[:300]
        if RATE_LIMIT_RE.search(msg):
            stop.set()
            return {**rec, "status": "error", "error": f"rate-limited: {msg}"}
        return {**rec, "status": "error", "error": f"rc={rc}: {msg}"}
    if not tr["target_loaded"] and cond == "skill":
        return {
            **rec,
            "status": "invalid",
            "error": f"target skill '{target}' not loaded in session",
        }
    for pat in suite.get("reply_strip_regex", [DEFAULT_STRIP]):
        tr["text"] = re.sub(pat, "", tr["text"] or "").strip()
    rec["reply_excerpt"] = (tr["text"] or "")[:600]
    if case["type"] == "trigger":
        rec["status"] = "ok"
        rec["correct"] = rec["triggered"] == (case["label"] == "positive")
        return rec
    checks = eval_checks(case.get("checks", []), tr, target)
    j = judge(
        case,
        tr,
        suite["defaults"].get("judge_model", "sonnet"),
        job["timeout"],
        judge_dir,
        raw_path=run_dir / "raw" / raw_name.replace(".jsonl", "__judge.jsonl"),
    )
    rec.update({"checks": checks, "judge": j, "judge_cost_usd": j.get("cost_usd", 0.0)})
    if j["score"] is None:
        if RATE_LIMIT_RE.search(j["error"] or ""):
            stop.set()
        return {**rec, "status": "judge_error", "error": j["error"]}
    rec["status"] = "ok"
    return score_behavior(rec, case, suite)


def score_behavior(rec: dict, case: dict, suite: dict) -> dict:
    """Combine gates + judge. In the no-skill baseline, skill-activation gates are
    skipped: the target is denied there by design, so they'd fail trivially
    and inflate uplift."""
    thr = case.get("pass_threshold", suite["defaults"].get("pass_threshold", 0.75))
    gates = [
        c
        for c in rec["checks"]
        if not (
            rec["cond"] == "no-skill"
            and c["kind"] in ("skill_called", "skill_not_called")
        )
    ]
    rec["gates_pass"] = all(c["pass"] for c in gates)
    js = rec["judge"]["score"]
    rec["score"] = js if rec["gates_pass"] else 0.0
    rec["pass"] = rec["gates_pass"] and js >= thr
    return rec


def observed_costs(skill: str) -> dict:
    """Mean USD per trial (trial + judge) by (model, type) from this suite's past
    runs, so --dry-run estimates reflect real spend instead of a flat guess."""
    acc: dict = {}
    for rp in (RUNS / skill).glob("*/results.json"):
        try:
            trials = json.loads(rp.read_text())["trials"]
        except Exception:  # noqa: BLE001
            continue
        for r in trials:
            if r.get("status") != "ok" or not r.get("cost_usd"):
                continue
            key = (r.get("model"), r.get("type"))
            s = acc.setdefault(key, [0.0, 0])
            s[0] += r["cost_usd"] + (r.get("judge_cost_usd") or 0)
            s[1] += 1
    return {key: tot / n for key, (tot, n) in acc.items() if n}


def cmd_run(a) -> None:
    skill = a.skill
    suite, cases = load_suite(skill)
    errs = validate(skill, quiet=True)
    if errs:
        validate(skill)
        die("suite fails validation")
    if not suite.get("frozen") and not a.allow_unfrozen:
        die(
            "suite is not frozen — run `freeze` first (or --allow-unfrozen for a smoke test "
            "whose results will not enter history)"
        )
    dfl = suite["defaults"]
    old = None
    if a.resume:
        # A resume must re-create the original job set, not whatever the current
        # flags/defaults say — otherwise a haiku or --baseline run resumed without
        # repeating those flags silently mixes models or drops trials.
        old = json.loads((Path(a.resume).resolve() / "manifest.json").read_text())
        if old.get("partial") and old.get("case_ids") is None and old.get("only") is None:
            die("that run was a --case subset from an older harness; rerun it instead")
        a.model, a.k, a.split = old["models"], old["k"], old["split"]
        a.only, a.baseline, a.case = old.get("only"), old.get("baseline"), old.get("case_ids")
    models = a.model or dfl.get("models", ["sonnet"])
    k = a.k or dfl.get("k", 2)
    split = a.split or dfl.get("split", "test")
    sel = [c for c in cases if split == "all" or c["split"] == split]
    if a.only:
        sel = [c for c in sel if c["type"] == a.only]
    if a.case:
        unknown = sorted(set(a.case) - {c["id"] for c in sel})
        if unknown:
            die(f"--case ids not in the selected split/type: {', '.join(unknown)}")
        sel = [c for c in sel if c["id"] in a.case]
    if not sel:
        die("no cases selected")
    jobs = []
    for model in models:
        for c in sel:
            conds = ["skill"] + (
                ["no-skill"] if a.baseline and c["type"] == "behavior" else []
            )
            for cond in conds:
                for t in range(1, k + 1):
                    jobs.append(
                        {
                            "case": c,
                            "model": model,
                            "cond": cond,
                            "trial": t,
                            "timeout": a.timeout or dfl.get("timeout_s", 300),
                            "meta": {
                                "case_id": c["id"],
                                "type": c["type"],
                                "label": c.get("label"),
                                "category": c.get("category"),
                                "claim": c.get("claim"),
                                "model": model,
                                "cond": cond,
                                "trial": t,
                            },
                        }
                    )
    n_beh = sum(j["case"]["type"] == "behavior" for j in jobs)

    seen = observed_costs(skill)

    def guess(model: str, typ: str) -> float:
        if (model, typ) in seen:
            return seen[(model, typ)]
        g = next((v for key, v in COST_GUESS.items() if key in model), 0.15)
        return g * (1.3 if typ == "behavior" else 1.0)  # + judge call

    est = sum(guess(j["model"], j["case"]["type"]) for j in jobs)
    log(
        f"{skill} v{suite['version']}: {len(sel)} cases x {len(models)} model(s) x k={k}"
        f"{' + no-skill baseline' if a.baseline else ''} = {len(jobs)} trials "
        f"(+{n_beh} judge calls), est. ~${est:.2f}"
    )
    if a.dry_run:
        return
    kept: list[dict] = []
    if old:
        run_dir = Path(a.resume).resolve()
        if old["cases_sha256"] != sha256_file(suite_dir(skill) / "cases.jsonl"):
            die("suite cases changed since that run — cannot resume")
        if old["skill_sha256"] != sha256_file(skill_dir(skill) / "SKILL.md"):
            die(
                "SKILL.md changed since that run — resuming would mix two versions; start a new run"
            )
        prev = [
            json.loads(x)
            for x in (run_dir / "trials.jsonl").read_text().splitlines()
            if x.strip()
        ]
        kept = [r for r in prev if r.get("status") == "ok"]
        done = {(r["case_id"], r["model"], r["cond"], r["trial"]) for r in kept}
        jobs = [
            j
            for j in jobs
            if (j["case"]["id"], j["model"], j["cond"], j["trial"]) not in done
        ]
        (run_dir / "trials.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
        )
        run_id = old["run_id"]
        log(f"resuming {run_id}: {len(kept)} ok trials kept, {len(jobs)} to run")
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{skill}-{stamp}"
        # two runs started in the same second must not share (and mix) a run dir
        n = 1
        while True:
            try:
                (RUNS / skill / run_id).mkdir(parents=True)
                break
            except FileExistsError:
                n += 1
                run_id = f"{skill}-{stamp}-{n}"
        run_dir = RUNS / skill / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    judge_dir = Path(tempfile.mkdtemp(prefix="skill-bench-judge-"))
    git_before = git("status", "--porcelain")
    manifest = {
        "run_id": run_id,
        "started": dt.datetime.now().isoformat(timespec="seconds"),
        "suite": skill,
        "suite_version": suite["version"],
        "frozen": bool(suite.get("frozen")),
        "cases_sha256": sha256_file(suite_dir(skill) / "cases.jsonl"),
        "skill_sha256": sha256_file(skill_dir(skill) / "SKILL.md"),
        "skill_git_dirty": bool(git("status", "--porcelain", "--", f"skills/{skill}")),
        "git_commit": git("rev-parse", "--short", "HEAD"),
        "models": models,
        "k": k,
        "split": split,
        "only": a.only,
        "baseline": a.baseline,
        "baseline_mode": BASELINE_MODE if a.baseline else None,
        "judge_model": dfl.get("judge_model", "sonnet"),
        "trigger_policy": suite.get("trigger_policy", "conditional"),
        "thresholds": suite.get("thresholds", {}),
        "n_cases": len(sel),
        "n_trials": len(jobs),
        "partial": bool(a.case) or a.only is not None,
        "case_ids": sorted(a.case) if a.case else None,
        "expected_types": sorted({c["type"] for c in sel}),
    }
    if old:
        manifest["started"] = old["started"]
        manifest["resumed"] = dt.datetime.now().isoformat(timespec="seconds")
        manifest["n_trials"] = len(jobs) + len(kept)
    # written up front so a run killed mid-way can still be resumed
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    stop = threading.Event()
    results = list(kept)
    lock = threading.Lock()
    trials_path = run_dir / "trials.jsonl"
    with cf.ThreadPoolExecutor(max_workers=a.jobs or dfl.get("jobs", 4)) as ex:
        futs = {
            ex.submit(run_trial, j, suite, run_dir, stop, judge_dir): j for j in jobs
        }
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                # keep the job's meta so the failure is counted against its model
                r = {**futs[f]["meta"], "status": "error", "error": f"harness: {e}"}
            with lock:
                results.append(r)
                with trials_path.open("a") as fh:  # incremental: survives a cutoff
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            tag = r.get("status")
            if r.get("type") == "trigger" and tag == "ok":
                tag = "✓" if r["correct"] else "✗"
            elif r.get("type") == "behavior" and tag == "ok":
                tag = f"{'✓' if r['pass'] else '✗'} {r['score']:.2f}"
            log(
                f"[{i}/{len(jobs)}] {r.get('case_id')} {r.get('model')} {r.get('cond')} "
                f"t{r.get('trial')}: {tag}"
            )
    shutil.rmtree(judge_dir, ignore_errors=True)
    git_after = git("status", "--porcelain")
    manifest["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    manifest["aborted_rate_limit"] = stop.is_set()
    manifest["repo_changed_during_run"] = git_before != git_after
    if manifest["repo_changed_during_run"]:
        manifest["repo_diff"] = sorted(
            set(git_after.splitlines()) ^ set(git_before.splitlines())
        )
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    summary = aggregate(results, manifest)
    out = {"manifest": manifest, "summary": summary, "trials": results}
    (run_dir / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (run_dir / "report.md").write_text(render_report(out, suite, cases))
    complete = all(s["verdict"] != "INCOMPLETE" for s in summary["by_model"].values())
    if (
        manifest["frozen"]
        and not manifest["partial"]
        and not stop.is_set()
        and complete
    ):
        upsert_history(
            skill,
            manifest["run_id"],
            [history_row(manifest, m, s) for m, s in summary["by_model"].items()],
        )
    else:
        log("run not appended to history (unfrozen, partial, aborted, or incomplete)")
    print(run_dir / "report.md")


# ----------------------------------------------------------------------------
# aggregation


def aggregate(results: list[dict], man: dict) -> dict:
    by_model = {}
    for m in man["models"]:
        rs = [r for r in results if r.get("model") == m]
        ok = [r for r in rs if r.get("status") == "ok"]
        s = {
            "n_trials": len(rs),
            "n_ok": len(ok),
            "n_error": sum(r.get("status") in ("error", "judge_error") for r in rs),
            "n_invalid": sum(r.get("status") == "invalid" for r in rs),
            "n_skipped": sum(r.get("status") == "skipped" for r in rs),
            "cost_usd": round(
                sum((r.get("cost_usd") or 0) + (r.get("judge_cost_usd") or 0) for r in rs),
                4,
            ),
            "judge_cost_usd": round(sum(r.get("judge_cost_usd") or 0 for r in rs), 4),
            "mean_latency_s": None,
        }
        lat = [r["duration_ms"] / 1000 for r in rs if r.get("duration_ms")]
        if lat:
            s["mean_latency_s"] = round(sum(lat) / len(lat), 1)
        served = sorted({r.get("served_model") for r in rs if r.get("served_model")})
        s["served_models"] = served
        # --- trigger
        tr = [r for r in ok if r["type"] == "trigger"]
        if tr:
            tp = sum(r["label"] == "positive" and r["triggered"] for r in tr)
            fn = sum(r["label"] == "positive" and not r["triggered"] for r in tr)
            fp = sum(r["label"] == "negative" and r["triggered"] for r in tr)
            tn = sum(r["label"] == "negative" and not r["triggered"] for r in tr)
            prec = tp / (tp + fp) if tp + fp else float("nan")
            rec = tp / (tp + fn) if tp + fn else float("nan")
            f1 = (
                (2 * prec * rec / (prec + rec))
                if tp and not math.isnan(prec)
                else (0.0 if tp + fn else float("nan"))
            )
            cats = {}
            for r in tr:
                c = cats.setdefault(
                    r["category"], {"label": r["label"], "n": 0, "fired": 0}
                )
                c["n"] += 1
                c["fired"] += r["triggered"]
            per_case = {}
            for r in tr:
                pc = per_case.setdefault(
                    r["case_id"],
                    {
                        "label": r["label"],
                        "n": 0,
                        "fired": 0,
                        "category": r["category"],
                    },
                )
                pc["n"] += 1
                pc["fired"] += r["triggered"]
            flaky = sorted(
                cid for cid, v in per_case.items() if 0 < v["fired"] < v["n"]
            )
            wrong = sorted(
                cid
                for cid, v in per_case.items()
                if (v["fired"] == 0 and v["label"] == "positive")
                or (v["fired"] == v["n"] and v["label"] == "negative")
            )
            fired = [r for r in tr if r["label"] == "positive" and r["triggered"]]
            groups: dict = {}
            for r in tr:
                groups.setdefault(r["case_id"], []).append(r)
            n_pos = sum(g[0]["label"] == "positive" for g in groups.values())
            n_neg = len(groups) - n_pos
            s["trigger"] = {
                "f1_ci": cluster_bootstrap(
                    list(groups.values()), lambda gs: trigger_f1([r for g in gs for r in g])
                ),
                "tp": tp,
                "fn": fn,
                "fp": fp,
                "tn": tn,
                "precision": prec,
                "recall": rec,
                "f1": f1,
                # Wilson over *cases*, not trials: k trials of one prompt are near
                # copies, so counting them as independent overstates certainty.
                "recall_ci": case_wilson(tp, tp + fn, n_pos),
                "fpr": fp / (fp + tn) if fp + tn else float("nan"),
                "fpr_ci": case_wilson(fp, fp + tn, n_neg),
                "accuracy": (tp + tn) / len(tr),
                "before_work_rate": (
                    sum(r["trigger_before_work"] for r in fired) / len(fired)
                )
                if fired
                else float("nan"),
                "categories": cats,
                "per_case": per_case,
                "flaky_cases": flaky,
                "consistently_wrong": wrong,
                "consistency": 1 - len(flaky) / len(per_case)
                if per_case
                else float("nan"),
            }
        # --- behavior per condition
        for cond in ("skill", "no-skill"):
            bh = [r for r in ok if r["type"] == "behavior" and r["cond"] == cond]
            if not bh:
                continue
            scores = [r["score"] for r in bh]
            passes = sum(r["pass"] for r in bh)
            per_case = {}
            for r in bh:
                pc = per_case.setdefault(
                    r["case_id"], {"n": 0, "passes": 0, "scores": []}
                )
                pc["n"] += 1
                pc["passes"] += r["pass"]
                pc["scores"].append(r["score"])
            crit_miss, gate_fail = {}, {}
            for r in bh:
                for c in r["judge"]["criteria"]:
                    key = f"{r['case_id']}:{c['id']}"
                    crit_miss.setdefault(key, [0, 0])
                    crit_miss[key][1] += 1
                    crit_miss[key][0] += not c["met"]
                for g in r["checks"]:
                    key = f"{r['case_id']}:{g['kind']}:{g['desc']}"
                    gate_fail.setdefault(key, [0, 0])
                    gate_fail[key][1] += 1
                    gate_fail[key][0] += not g["pass"]
            s[f"behavior_{cond}"] = {
                "n": len(bh),
                "mean_score": sum(scores) / len(scores),
                "mean_score_ci": cluster_bootstrap(
                    [v["scores"] for v in per_case.values()],
                    lambda gs: mean(x for g in gs for x in g),
                ),
                "pass_rate": passes / len(bh),
                "pass_rate_ci": wilson(passes, len(bh)),
                "pass_at_k": sum(v["passes"] > 0 for v in per_case.values())
                / len(per_case),
                "pass_all_k": sum(v["passes"] == v["n"] for v in per_case.values())
                / len(per_case),
                "activation_rate": sum(r["triggered"] for r in bh) / len(bh),
                "per_case": per_case,
                "criterion_misses": {
                    k2: v
                    for k2, v in sorted(crit_miss.items(), key=lambda kv: -kv[1][0])
                    if v[0]
                },
                "gate_failures": {
                    k2: v
                    for k2, v in sorted(gate_fail.items(), key=lambda kv: -kv[1][0])
                    if v[0]
                },
            }
        b, nb = s.get("behavior_skill"), s.get("behavior_no-skill")
        if b and nb:
            sc = {c: v["scores"] for c, v in b["per_case"].items()}
            nsc = {c: v["scores"] for c, v in nb["per_case"].items()}
            paired = paired_delta(sc, nsc)
            s["uplift"] = {
                "mean_score": b["mean_score"] - nb["mean_score"],
                "pass_rate": b["pass_rate"] - nb["pass_rate"],
                "paired": paired,
            }
            # Item discrimination: a behavior case the no-skill baseline does just
            # as well on can't show what the skill adds — it measures the model.
            s["discrimination"] = {
                c: {
                    "skill": mean(sc[c]),
                    "baseline": mean(nsc[c]),
                    "delta": mean(sc[c]) - mean(nsc[c]),
                }
                for c in sorted(set(sc) & set(nsc))
            }
            s["non_discriminating"] = [
                c for c, v in s["discrimination"].items() if v["delta"] <= 0
            ]
        # Headroom: cases every trial got right can only catch regressions, never
        # show an improvement. A fully saturated suite needs harder cases.
        solved, total = 0, 0
        if "trigger" in s:
            for v in s["trigger"]["per_case"].values():
                total += 1
                want = v["label"] == "positive"
                solved += v["fired"] == (v["n"] if want else 0)
        if b:
            for v in b["per_case"].values():
                total += 1
                solved += v["passes"] == v["n"] and min(v["scores"]) >= 1.0
        s["headroom"] = {
            "solved_cases": solved,
            "n_cases": total,
            "saturated": bool(total) and solved == total,
        }
        parts = []
        if "trigger" in s and not math.isnan(s["trigger"]["f1"]):
            parts.append(s["trigger"]["f1"])
        if b:
            parts.append(b["mean_score"])
        s["composite"] = sum(parts) / len(parts) if parts else float("nan")
        th = man.get("thresholds", {})
        verdict = []
        if "trigger" in s:
            t = s["trigger"]
            if not math.isnan(t["f1"]) and t["f1"] < th.get("trigger_f1", 0.85):
                verdict.append(
                    f"trigger F1 {t['f1']:.2f} < {th.get('trigger_f1', 0.85)}"
                )
            if not math.isnan(t["fpr"]) and t["fpr"] > th.get(
                "false_positive_rate", 0.10
            ):
                verdict.append(
                    f"FPR {t['fpr']:.2f} > {th.get('false_positive_rate', 0.10)}"
                )
        if b and b["pass_rate"] < th.get("behavior_pass_rate", 0.70):
            verdict.append(
                f"behavior pass rate {b['pass_rate']:.2f} < {th.get('behavior_pass_rate', 0.70)}"
            )
        if s.get("uplift") and s["uplift"]["mean_score"] <= 0:
            verdict.append("no uplift over the no-skill baseline")
        bad = s["n_error"] + s["n_invalid"] + s["n_skipped"]
        missing = [
            c
            for c in man.get("expected_types", [])
            if (c == "trigger" and "trigger" not in s)
            or (c == "behavior" and "behavior_skill" not in s)
        ]
        if s["n_trials"] and (bad / s["n_trials"] > 0.10 or missing):
            s["verdict"] = "INCOMPLETE"
            verdict.insert(
                0,
                f"{bad}/{s['n_trials']} trials errored/invalid/skipped"
                + (f"; no completed {', '.join(missing)} trials" if missing else "")
                + " — rerun before trusting this",
            )
        else:
            s["verdict"] = "PASS" if not verdict else "FAIL"
        s["verdict_reasons"] = verdict
        # Not verdict-changing (thresholds decide that), but things a reader must
        # know before trusting a PASS.
        warn = []
        up = (s.get("uplift") or {}).get("paired")
        if up and up["delta"] > 0 and not up["significant"]:
            warn.append(
                f"uplift {fmt_delta(up)} is not distinguishable from zero — "
                "the skill's behavior benefit is unproven on this suite"
            )
        if s.get("non_discriminating"):
            warn.append(
                f"{len(s['non_discriminating'])}/{len(s['discrimination'])} behavior cases "
                "score as well without the skill (no discrimination): "
                + ", ".join(s["non_discriminating"])
            )
        t = s.get("trigger")
        if t and s["verdict"] == "PASS":
            fpr_hi = t["fpr_ci"][1]
            fpr_th = th.get("false_positive_rate", 0.10)
            if not math.isnan(fpr_hi) and fpr_hi > fpr_th:
                warn.append(
                    f"FPR passes on its point estimate, but its 95% CI reaches "
                    f"{fpr_hi:.0%} > {fpr_th:.0%}: too few negative cases to certify it "
                    f"(with zero misfires you'd need ≥{cases_to_certify(fpr_th)} distinct "
                    "negative cases)"
                )
            rec_lo = t["recall_ci"][0]
            if not math.isnan(rec_lo) and rec_lo < th.get("trigger_f1", 0.85):
                warn.append(
                    f"recall's 95% CI dips to {rec_lo:.0%}, below the F1 bar "
                    f"{th.get('trigger_f1', 0.85):.0%}: the positive set is too small to "
                    f"certify trigger reliability (≥{cases_to_certify(1 - th.get('trigger_f1', 0.85))} "
                    "distinct positive cases needed at zero misses)"
                )
        if s["headroom"]["saturated"]:
            warn.append(
                "suite is saturated — every case passed every trial, so it can catch "
                "regressions but can't show improvements; add harder cases (freeze --bump minor)"
            )
        s["warnings"] = warn
        by_model[m] = s
    return {"by_model": by_model}


def upsert_history(skill: str, run_id: str, fresh: list[dict]) -> None:
    """One row per (run, model): a resumed or re-rendered run replaces its rows in
    place instead of appending duplicates that would double-count it."""
    hist = suite_dir(skill) / "history.jsonl"
    rows = (
        [json.loads(x) for x in hist.read_text().splitlines() if x.strip()]
        if hist.exists()
        else []
    )
    out, placed = [], False
    for r in rows:
        if r["run_id"] == run_id:
            if not placed:
                out.extend(fresh)
                placed = True
            continue
        out.append(r)
    if not placed:
        out.extend(fresh)
    hist.write_text("".join(json.dumps(r) + "\n" for r in out))


def history_row(man: dict, model: str, s: dict) -> dict:
    t, b = s.get("trigger", {}), s.get("behavior_skill", {})
    up = (s.get("uplift") or {}).get("paired")

    def r(x):
        return (
            None
            if x is None or (isinstance(x, float) and math.isnan(x))
            else round(x, 4)
        )

    return {
        "run_id": man["run_id"],
        "date": man["started"][:10],
        "model": model,
        "suite_version": man["suite_version"],
        "cases_sha256": man["cases_sha256"][:12],
        "skill_sha256": man["skill_sha256"][:12],
        "skill_git_dirty": man["skill_git_dirty"],
        "git_commit": man["git_commit"],
        "split": man["split"],
        "k": man["k"],
        "trigger_f1": r(t.get("f1")),
        "precision": r(t.get("precision")),
        "recall": r(t.get("recall")),
        "fpr": r(t.get("fpr")),
        "behavior_mean": r(b.get("mean_score")),
        "behavior_pass_rate": r(b.get("pass_rate")),
        "uplift": r(s.get("uplift", {}).get("mean_score")),
        "baseline_mode": (man.get("baseline_mode") or "no-skill-tool")
        if man.get("baseline")
        else None,
        "uplift_ci": [r(x) for x in up["ci"]] if up else None,
        "uplift_significant": up["significant"] if up else None,
        "trigger_f1_ci": [r(x) for x in t["f1_ci"]]
        if t.get("f1_ci") and t["f1_ci"][0] != t["f1_ci"][1]
        else None,
        "solved_cases": s.get("headroom", {}).get("solved_cases"),
        "n_cases": s.get("headroom", {}).get("n_cases"),
        "composite": r(s.get("composite")),
        "verdict": s.get("verdict"),
        "cost_usd": s.get("cost_usd"),
        "errors": s.get("n_error"),
    }


# ----------------------------------------------------------------------------
# reporting


def case_values(s: dict) -> dict:
    """Per-case trial values for paired comparisons: trigger → 1/0 correct,
    behavior → score."""
    vals = {}
    for cid, v in (s.get("trigger") or {}).get("per_case", {}).items():
        hit = v["fired"] if v["label"] == "positive" else v["n"] - v["fired"]
        vals[("trigger", cid)] = [1.0] * hit + [0.0] * (v["n"] - hit)
    for cid, v in (s.get("behavior_skill") or {}).get("per_case", {}).items():
        vals[("behavior", cid)] = v["scores"]
    return vals


def compare_runs(man: dict, s: dict, prev_row: dict, model: str) -> dict:
    """Paired, case-level deltas against an earlier run on the same case set.
    History rows only hold aggregates, so this needs the earlier run's
    results.json; returns {} if it's gone."""
    rp = RUNS / man["suite"] / prev_row["run_id"] / "results.json"
    if not rp.exists():
        return {}
    try:
        ps = json.loads(rp.read_text())["summary"]["by_model"][model]
    except Exception:  # noqa: BLE001
        return {}
    cur, old = case_values(s), case_values(ps)
    out = {}
    for typ, label in (("trigger", "trigger accuracy"), ("behavior", "behavior score")):
        a = {k[1]: v for k, v in cur.items() if k[0] == typ}
        b = {k[1]: v for k, v in old.items() if k[0] == typ}
        d = paired_delta(a, b)
        if d:
            out[label] = d
    return out


def claims_of(c: dict) -> list[str]:
    """A case may cite several claims: "claim": "B1,B3"."""
    return [x.strip() for x in str(c.get("claim") or "").split(",") if x.strip()]


def card_claims(skill: str) -> list[str]:
    """Claim ids (T1, N2, B3, …) declared in the CARD's capability-spec section."""
    p = suite_dir(skill) / "CARD.md"
    if not p.exists():
        return []
    txt = p.read_text()
    m = re.search(r"^##[^\n]*capability spec[^\n]*\n(.*?)(?=^## |\Z)", txt, re.I | re.M | re.S)
    body = m.group(1) if m else txt
    return list(dict.fromkeys(re.findall(r"\*\*([TNB]\d+)\*\*", body)))


def claim_table(trials: list[dict], by_case: dict, skill: str) -> list[str]:
    """Results rolled up by capability-spec claim, so a failure reads as "the skill
    breaks promise B5", not just "case cs-b-003 failed"."""
    rows: dict = {}
    for r in trials:
        if r.get("status") != "ok" or r.get("cond") != "skill":
            continue
        ok = r["correct"] if r["type"] == "trigger" else r["pass"]
        for claim in claims_of(r if r.get("claim") else by_case.get(r["case_id"], {})):
            v = rows.setdefault((r.get("model"), claim), [0, 0, set()])
            v[0] += ok
            v[1] += 1
            v[2].add(r["case_id"])
    if not rows:
        return []
    declared = card_claims(skill)
    order = {c: i for i, c in enumerate(declared)}
    L = ["## By claim", "", "| Model | Claim | Correct/passed | Cases |", "|---|---|---|---|"]
    for (m, claim), (ok, n, cids) in sorted(
        rows.items(), key=lambda kv: (kv[0][0], order.get(kv[0][1], 999), kv[0][1])
    ):
        flag = "" if ok == n else " ⚠"
        L.append(f"| {m} | {claim} | {ok}/{n}{flag} | {len(cids)} |")
    untested = [c for c in declared if c not in {k[1] for k in rows}]
    L.append("")
    if untested:
        L += [f"Claims in CARD.md with no trials in this run: {', '.join(untested)}", ""]
    return L


def render_report(out: dict, suite: dict, cases: list[dict]) -> str:
    man, summ = out["manifest"], out["summary"]
    by_case = {c["id"]: c for c in cases}
    L = [
        f"# skill-bench: `{man['suite']}`",
        "",
        f"Run `{man['run_id']}` · suite v{man['suite_version']} "
        f"(cases `{man['cases_sha256'][:12]}`, {'frozen' if man['frozen'] else '**UNFROZEN — smoke test, not comparable**'}) · "
        f"SKILL.md `{man['skill_sha256'][:12]}`{' (uncommitted edits)' if man['skill_git_dirty'] else ''} · "
        f"commit `{man['git_commit']}` · split **{man['split']}** · k={man['k']} · judge {man['judge_model']}",
        "",
    ]
    if man.get("aborted_rate_limit"):
        L += [
            "> **Aborted early: rate/usage limit hit.** Metrics below cover only completed trials.",
            "",
        ]
    if man.get("repo_changed_during_run"):
        L += [
            "> **Repo working tree changed during the run** — a probe may have had side effects, "
            "or another session edited files. Inspect before trusting results: "
            + ", ".join(f"`{x}`" for x in man.get("repo_diff", [])[:10]),
            "",
        ]
    L += [
        "## Headline",
        "",
        "| Model | Verdict | Composite | Trigger F1 | Precision | Recall | FPR | Behavior score | Pass rate | Uplift | Cost | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m, s in summ["by_model"].items():
        t, b = s.get("trigger", {}), s.get("behavior_skill", {})
        up = s.get("uplift", {}).get("mean_score")
        if (s.get("uplift") or {}).get("paired"):
            up_s = fmt_delta(s["uplift"]["paired"])
        else:
            up_s = ("+" if up and up > 0 else "") + fmt(up) if up is not None else "—"
        L.append(
            f"| {m} | **{s['verdict']}** | {fmt(s['composite'])} | "
            f"{fmt(t.get('f1'))}{fmt_ci(t.get('f1_ci', (None, None)))} | "
            f"{fmt(t.get('precision'))} | {fmt(t.get('recall'))}{fmt_ci(t.get('recall_ci', (None, None)))} | "
            f"{fmt(t.get('fpr'))}{fmt_ci(t.get('fpr_ci', (None, None)))} | "
            f"{fmt(b.get('mean_score'))}{fmt_ci(b.get('mean_score_ci', (None, None)))} | "
            f"{fmt(b.get('pass_rate'))} | {up_s} | "
            f"${s['cost_usd']:.2f} | {s['n_error']}{'+' + str(s['n_invalid']) + ' invalid' if s['n_invalid'] else ''} |"
        )
    L += [
        "",
        "Composite = mean(trigger F1, behavior score). Brackets are 95% CIs: Wilson "
        "for per-trial rates; case-level bootstrap (the k trials of a case resampled "
        "together) for F1, scores and uplift. Uplift is paired by case; (n.s.) = its "
        "CI includes 0. Cost includes judge calls. Errors/invalid trials are excluded "
        "from metrics.",
        "",
    ]
    for m, s in summ["by_model"].items():
        L += [f"## {m}", ""]
        if s["verdict_reasons"]:
            L += ["Below threshold: " + "; ".join(s["verdict_reasons"]), ""]
        if s.get("warnings"):
            L += ["**Read before trusting the verdict:**", ""]
            L += [f"- {w}" for w in s["warnings"]]
            L.append("")
        hr = s.get("headroom")
        if hr and hr["n_cases"]:
            L += [
                f"Headroom: {hr['n_cases'] - hr['solved_cases']}/{hr['n_cases']} cases "
                "were missed at least once (cases solved every trial can't show an improvement).",
                "",
            ]
        if s.get("served_models"):
            L += [
                f"Served by: {', '.join(s['served_models'])} · mean latency {s['mean_latency_s']}s",
                "",
            ]
        t = s.get("trigger")
        if t:
            L += [
                "### Trigger",
                "",
                "| | fired | didn't fire |",
                "|---|---|---|",
                f"| should fire | TP {t['tp']} | FN {t['fn']} |",
                f"| shouldn't fire | FP {t['fp']} | TN {t['tn']} |",
                "",
                f"Accuracy {fmt(t['accuracy'])} · run-to-run consistency {fmt(t['consistency'])} · "
                f"fired before doing other work {fmt(t['before_work_rate'])} of true positives",
                "",
                "| Category | Label | Fire rate |",
                "|---|---|---|",
            ]
            for cat, v in sorted(
                t["categories"].items(), key=lambda kv: (kv[1]["label"], kv[0])
            ):
                L.append(
                    f"| {cat} | {v['label']} | {v['fired']}/{v['n']} ({fmt(v['fired'] / v['n'], nd=0)}) |"
                )
            L.append("")
            if t["consistently_wrong"]:
                L += ["**Consistently wrong** (every trial wrong):", ""]
                for cid in t["consistently_wrong"]:
                    c = by_case.get(cid, {})
                    L.append(
                        f"- `{cid}` ({c.get('label')}/{c.get('category')}): {c.get('prompt', '')[:140]!r}"
                    )
                L.append("")
            if t["flaky_cases"]:
                L += [
                    "**Flaky** (trials disagreed): "
                    + ", ".join(f"`{x}`" for x in t["flaky_cases"]),
                    "",
                ]
        for cond in ("skill", "no-skill"):
            b = s.get(f"behavior_{cond}")
            if not b:
                continue
            L += [
                f"### Behavior ({'with skill' if cond == 'skill' else 'no-skill baseline'})",
                "",
                f"Mean score {fmt(b['mean_score'])}{fmt_ci(b['mean_score_ci'])} · pass rate "
                f"{fmt(b['pass_rate'])}{fmt_ci(b['pass_rate_ci'])} · pass@k {fmt(b['pass_at_k'])} · "
                f"pass^k {fmt(b['pass_all_k'])} · "
                + (
                    f"skill activated in {fmt(b['activation_rate'])} of trials"
                    if cond == "skill"
                    else f"model tried to call the (blocked) skill in {fmt(b['activation_rate'])} of trials"
                ),
                "",
                "| Case | Passes | Scores |",
                "|---|---|---|",
            ]
            for cid, v in b["per_case"].items():
                L.append(
                    f"| `{cid}` | {v['passes']}/{v['n']} | {', '.join(f'{x:.2f}' for x in v['scores'])} |"
                )
            L.append("")
            if cond == "no-skill" and s.get("discrimination"):
                L += [
                    "Discrimination (mean score with skill vs without, per case):",
                    "",
                    "| Case | Skill | Baseline | Δ |",
                    "|---|---|---|---|",
                ]
                for cid, v in s["discrimination"].items():
                    flag = "" if v["delta"] > 0 else " ⚠ no discrimination"
                    L.append(
                        f"| `{cid}` | {v['skill']:.2f} | {v['baseline']:.2f} | "
                        f"{v['delta']:+.2f}{flag} |"
                    )
                L.append("")
            if cond == "skill":
                if b["gate_failures"]:
                    L += ["Failed hard checks:", ""]
                    L += [
                        f"- `{k2}` — {v[0]}/{v[1]}"
                        for k2, v in list(b["gate_failures"].items())[:15]
                    ]
                    L.append("")
                if b["criterion_misses"]:
                    L += ["Most-missed rubric criteria (judge):", ""]
                    for k2, v in list(b["criterion_misses"].items())[:15]:
                        cid, rid = k2.split(":", 1)
                        crit = next(
                            (
                                r["criterion"]
                                for r in by_case.get(cid, {}).get("rubric", [])
                                if str(r["id"]) == rid
                            ),
                            "",
                        )
                        L.append(f"- `{k2}` — missed {v[0]}/{v[1]}: {crit}")
                    L.append("")
    L += claim_table(out["trials"], by_case, man["suite"])
    bad = [r for r in out["trials"] if r.get("status") != "ok"]
    if bad:
        L += ["## Errors / invalid trials", ""]
        L += [
            f"- `{r.get('case_id')}` {r.get('model')} {r.get('cond')} t{r.get('trial')}: "
            f"{r.get('status')} — {' '.join(str(r.get('error')).split())[:200]}"
            for r in bad[:30]
        ]
        L.append("")
    L += ["## Failing trials", ""]
    fails = [
        r
        for r in out["trials"]
        if r.get("status") == "ok"
        and (
            (r["type"] == "trigger" and not r["correct"])
            or (r["type"] == "behavior" and not r["pass"])
        )
    ]
    if not fails:
        L.append("None.")
    for r in fails[:40]:
        L.append(
            f"- `{r['case_id']}` {r['model']} {r['cond']} t{r['trial']} → `{r['raw']}` "
            f"(skills called: {', '.join(r['skill_calls']) or 'none'})"
        )
    L += ["", "## Comparison with previous run", ""]
    hist = suite_dir(man["suite"]) / "history.jsonl"
    prev_rows = []
    if hist.exists():
        prev_rows = [json.loads(x) for x in hist.read_text().splitlines() if x.strip()]
    wrote = False
    for m, s in summ["by_model"].items():
        prev = [
            p
            for p in prev_rows
            if p["model"] == m
            and p["split"] == man["split"]
            and p["run_id"] < man["run_id"]  # earlier runs only, also on re-render
        ]
        if not prev:
            continue
        p = prev[-1]
        same = p["cases_sha256"] == man["cases_sha256"][:12]
        paired = compare_runs(man, s, p, m) if same else {}
        cur = history_row(man, m, s)
        deltas = []
        for key in (
            "trigger_f1",
            "fpr",
            "behavior_mean",
            "behavior_pass_rate",
            "composite",
        ):
            if cur.get(key) is not None and p.get(key) is not None:
                deltas.append(f"{key} {p[key]:.2f}→{cur[key]:.2f}")
        L.append(
            f"- **{m}** vs `{p['run_id']}`: "
            + ", ".join(deltas)
            + ("" if same else " — **different case set, not comparable**")
            + (
                " (SKILL.md unchanged — delta is run-to-run noise)"
                if p["skill_sha256"] == cur["skill_sha256"]
                else " (SKILL.md changed)"
            )
        )
        for label, d in paired.items():
            L.append(f"  - paired by case, {label}: {fmt_delta(d)} over {d['n_cases']} cases")
        wrote = True
    if not wrote:
        L.append("No earlier run with the same model and split.")
    L += [
        "",
        "## Caveats",
        "",
        "- The judge is a Claude model grading Claude output (self-preference bias possible); "
        "hard checks are the unbiased part of the behavior score.",
        "- Trials run in the real repo with the user's global CLAUDE.md and all installed skills — "
        "this measures the skill as actually deployed, not in isolation.",
        f"- With k={man['k']} trials per case, CIs are wide; treat differences inside them as noise.",
        "",
    ]
    return "\n".join(L)


def cmd_report(a) -> None:
    rd = Path(a.run_dir)
    out = json.loads((rd / "results.json").read_text())
    suite, cases = load_suite(out["manifest"]["suite"])
    if "expected_types" not in out["manifest"]:
        out["manifest"]["expected_types"] = sorted(
            {r["type"] for r in out["trials"] if r.get("type")}
        )
    by_id = {c["id"]: c for c in cases}
    for r in out["trials"]:
        if (
            r.get("status") == "ok"
            and r.get("type") == "behavior"
            and r["case_id"] in by_id
        ):
            score_behavior(r, by_id[r["case_id"]], suite)
    out["summary"] = aggregate(
        out["trials"], out["manifest"]
    )  # recompute with current logic
    (rd / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (rd / "report.md").write_text(render_report(out, suite, cases))
    hist = suite_dir(out["manifest"]["suite"]) / "history.jsonl"
    rid = out["manifest"]["run_id"]
    if hist.exists() and any(
        json.loads(x)["run_id"] == rid for x in hist.read_text().splitlines() if x.strip()
    ):
        upsert_history(
            out["manifest"]["suite"],
            rid,
            [
                history_row(out["manifest"], m, sm)
                for m, sm in out["summary"]["by_model"].items()
            ],
        )
    print(rd / "report.md")


def cmd_history(a) -> None:
    h = suite_dir(a.skill) / "history.jsonl"
    if not h.exists():
        die(f"no history for {a.skill}")
    rows = [json.loads(x) for x in h.read_text().splitlines() if x.strip()]
    cols = [
        "date",
        "model",
        "suite_version",
        "skill_sha256",
        "split",
        "k",
        "trigger_f1",
        "fpr",
        "behavior_mean",
        "uplift",
        "composite",
        "verdict",
        "cost_usd",
    ]
    print(" | ".join(cols))
    for r in rows:
        cells = ["—" if r.get(c) is None else str(r.get(c)) for c in cols]
        if r.get("uplift_significant") is False:
            cells[cols.index("uplift")] += " (n.s.)"
        print(" | ".join(cells))


def cmd_viz(a) -> None:
    """Bake every suite, its history, and its runs into one self-contained HTML page."""
    data = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "suites": {}}
    for d in sorted(p for p in SUITES.iterdir() if (p / "suite.json").exists()):
        suite, cases = load_suite(d.name)
        hist = d / "history.jsonl"
        runs = []
        for rd in sorted((RUNS / d.name).glob("*/results.json"), reverse=True):
            out = json.loads(rd.read_text())
            if not out["manifest"].get("frozen") and not a.include_smoke:
                continue
            for r in out["trials"]:
                r.pop("tool_names", None)
            runs.append(
                {
                    "manifest": out["manifest"],
                    "summary": out["summary"],
                    "trials": out["trials"],
                }
            )
        data["suites"][d.name] = {
            "suite": suite,
            "cases": cases,
            "runs": runs,
            "history": [
                json.loads(x) for x in hist.read_text().splitlines() if x.strip()
            ]
            if hist.exists()
            else [],
        }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "viz_template.html").read_text().replace("/*__DATA__*/null", blob)
    out = Path(a.out) if a.out else RUNS / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(out)


# ----------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("skill")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sp.add_parser("validate")
    p.add_argument("skill")
    p.set_defaults(fn=cmd_validate)
    p = sp.add_parser("freeze")
    p.add_argument("skill")
    p.add_argument("--bump", choices=["major", "minor", "patch"])
    p.set_defaults(fn=cmd_freeze)
    p = sp.add_parser("run")
    p.add_argument("skill")
    p.add_argument(
        "--model",
        action="append",
        help="repeatable; alias (haiku/sonnet/opus) or full id",
    )
    p.add_argument("-k", type=int, help="trials per case")
    p.add_argument("--split", choices=["dev", "test", "all"])
    p.add_argument("--only", choices=["trigger", "behavior"])
    p.add_argument(
        "--case", action="append", help="run only these case ids (partial run)"
    )
    p.add_argument(
        "--baseline",
        action="store_true",
        help="also run behavior cases with the target skill denied (no-skill baseline)",
    )
    p.add_argument("--jobs", type=int)
    p.add_argument("--timeout", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-unfrozen", action="store_true")
    p.add_argument(
        "--resume",
        metavar="RUN_DIR",
        help="re-execute only failed/missing trials of an earlier run",
    )
    p.set_defaults(fn=cmd_run)
    p = sp.add_parser("report")
    p.add_argument("run_dir")
    p.set_defaults(fn=cmd_report)
    p = sp.add_parser("history")
    p.add_argument("skill")
    p.set_defaults(fn=cmd_history)
    p = sp.add_parser("viz")
    p.add_argument(
        "--out",
        help="output HTML path (default .claude/skill-bench-runs/dashboard.html)",
    )
    p.add_argument(
        "--include-smoke",
        action="store_true",
        help="also show unfrozen smoke-test runs",
    )
    p.set_defaults(fn=cmd_viz)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
