#!/usr/bin/env python3
"""Offline regression test for bench.py — no API calls, no usage window.

Copies the harness, registry.yaml and the context-summarize suite into a temp
repo, puts a fake `claude` first on PATH, and drives real `bench.py` commands
through the failure paths that matter: transient retries, rate-limit abort,
resume (config inheritance + history dedup), baseline deny rule, judge cost
and raw-output capture. Run after any bench.py change:

    python3 skills/skill-bench/selftest.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TARGET = "context-summarize"

FAKE = r'''#!/usr/bin/env python3
import sys, json, os, re, hashlib
args = sys.argv[1:]
prompt = sys.stdin.read()
model = args[args.index("--model") + 1]
mode = os.environ.get("FAKE_MODE", "ok")
state = os.environ["FAKE_STATE"]
judge = "--tools" in args
def emit(*evs):
    for e in evs: print(json.dumps(e))
dis = args[args.index("--disallowedTools") + 1:] if "--disallowedTools" in args else []
allowed = args[args.index("--allowedTools") + 1:args.index("--disallowedTools")] if "--allowedTools" in args else []
perm = args[args.index("--permission-mode") + 1] if "--permission-mode" in args else None
with open(os.path.join(state, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"judge": judge, "model": model, "disallowed": dis, "allowed": allowed,
                         "perm": perm, "cwd": os.getcwd(), "world_file": os.environ.get("WORLD_FILE"),
                         "prompt": prompt}) + "\n")
key = hashlib.md5((prompt + str(judge)).encode()).hexdigest()
try:  # atomic "first time this prompt is seen"
    os.close(os.open(os.path.join(state, key), os.O_CREAT | os.O_EXCL)); first = True
except FileExistsError:
    first = False
if not judge and mode == "transient_once" and first:
    emit({"type": "result", "is_error": True, "result": "API Error: 529 overloaded_error", "total_cost_usd": 0}); sys.exit(1)
if not judge and mode == "ratelimit" and "tl;dr" in prompt:
    emit({"type": "result", "is_error": True, "result": "You've hit your usage limit", "total_cost_usd": 0}); sys.exit(1)
if not judge and mode == "hard_fail_once" and "tl;dr README" in prompt and first:
    emit({"type": "result", "is_error": True, "result": "some permanent error", "total_cost_usd": 0}); sys.exit(1)
if judge:
    ids = re.findall(r"- id=(\S+):", prompt)
    emit({"type": "result", "is_error": False, "total_cost_usd": 0.01,
          "result": json.dumps({"criteria": [{"id": i, "met": True, "evidence": "x"} for i in ids]})})
    sys.exit(0)
if "WORLDTEST" in prompt:  # a world case: act on the sandboxed state like a script would
    if "MARKDONE" in prompt:
        with open(os.environ["WORLD_FILE"], "a") as fh:
            fh.write("- [x] done\n")
    reply = "Next up: fix the upload test."
    emit({"type": "system", "subtype": "init", "model": "fake-" + model, "skills": ["context-summarize", "english-practice"]})
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "context-summarize"}},
          {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "python3 q.py next"}}, {"type": "text", "text": reply}]}})
    if "MARKDONE" in prompt:
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1",
              "content": "Permission to use Bash has been denied because Claude Code is running in don't ask mode."}]}})
    emit({"type": "result", "result": reply, "total_cost_usd": 0.1, "duration_ms": 1000, "num_turns": 2, "is_error": False})
    sys.exit(0)
emit({"type": "system", "subtype": "init", "model": "fake-" + model, "skills": ["context-summarize", "english-practice"]})
denied = "Skill" in dis or "Skill(context-summarize)" in dis
fire = not denied and re.search(r"summar|tl;dr|gist|recap|short version|boil|highlights|catch me up|what do i need|总结", prompt, re.I)
content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "context-summarize"}}] if fire else []
emit({"type": "assistant", "message": {"content": content + [{"type": "text", "text": "Postgres chosen. owner Li."}]}})
emit({"type": "result", "result": "Postgres chosen. owner Li.", "total_cost_usd": 0.1, "duration_ms": 1000, "num_turns": 1, "is_error": False})
'''

failures: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="skill-bench-selftest-"))
    repo, fake, state = tmp / "repo", tmp / "bin", tmp / "state"
    (repo / "skills").mkdir(parents=True)
    fake.mkdir()
    shutil.copy(REPO / "registry.yaml", repo)
    shutil.copytree(REPO / "skills" / TARGET, repo / "skills" / TARGET)
    shutil.copytree(
        HERE,
        repo / "skills" / "skill-bench",
        ignore=shutil.ignore_patterns("history.jsonl", "__pycache__", ".claude"),
    )
    bench = repo / "skills" / "skill-bench" / "bench.py"
    bench.write_text(
        bench.read_text().replace("TRANSIENT_BACKOFF_S = 20", "TRANSIENT_BACKOFF_S = 0")
    )
    (fake / "claude").write_text(FAKE)
    (fake / "claude").chmod(0o755)
    runs = repo / ".claude" / "skill-bench-runs" / TARGET
    hist = repo / "skills" / "skill-bench" / "suites" / TARGET / "history.jsonl"

    def run(mode: str, *args: str) -> subprocess.CompletedProcess:
        if state.exists():
            shutil.rmtree(state)
        state.mkdir()
        env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "FAKE_MODE": mode, "FAKE_STATE": str(state)}
        return subprocess.run(
            [sys.executable, str(bench), *args], cwd=repo, env=env, capture_output=True, text=True, timeout=600
        )

    def latest() -> Path:
        return max((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime_ns)

    def results(rd: Path) -> dict:
        return json.loads((rd / "results.json").read_text())

    def hist_rows() -> list[dict]:
        return [json.loads(x) for x in hist.read_text().splitlines()] if hist.exists() else []

    def calls() -> list[dict]:
        return [json.loads(x) for x in (state / "calls.jsonl").read_text().splitlines()]

    try:
        print("validate")
        p = run("ok", "validate", TARGET)
        check(p.returncode == 0, "real suite validates with 0 errors")

        print("full run with transient 529s + baseline, non-default model")
        p = run("transient_once", "run", TARGET, "--baseline", "--model", "haiku")
        check(p.returncode == 0, f"run exits 0 (stderr tail: {p.stderr[-200:]!r})")
        check("retrying" in p.stderr, "transient errors are retried")
        rd = latest()
        o = results(rd)
        s = o["summary"]["by_model"]["haiku"]
        check(s["n_error"] == 0 and s["verdict"] != "INCOMPLETE", "retries recover every trial")
        check({r["model"] for r in o["trials"]} == {"haiku"}, "all trials on the requested model")
        n_judge = sum(1 for r in o["trials"] if r.get("judge_cost_usd"))
        check(n_judge > 0 and abs(s["judge_cost_usd"] - 0.01 * n_judge) < 1e-6, "judge cost recorded")
        check(abs(s["cost_usd"] - (0.1 * len(o["trials"]) + 0.01 * n_judge)) < 1e-6, "run cost includes judge cost")
        check(len(list((rd / "raw").glob("*__judge.jsonl"))) == n_judge, "judge raw output saved per behavior trial")
        base = [c for c in calls() if not c["judge"] and "Skill(context-summarize)" in c["disallowed"]]
        check(bool(base) and all("Skill" not in c["disallowed"] for c in base), "baseline denies only the target skill")
        check(o["manifest"]["baseline_mode"] == "deny-target", "manifest records baseline_mode")
        check("uplift" in s and "paired" in s["uplift"] and "discrimination" in s, "paired uplift + discrimination computed")
        check(isinstance(s.get("warnings"), list) and "headroom" in s, "warnings + headroom computed")
        check(len(hist_rows()) == 1 and hist_rows()[0]["model"] == "haiku", "complete run enters history once")
        rep = (rd / "report.md").read_text()
        check("## By claim" in rep and "Discrimination" in rep, "report has claim + discrimination sections")

        print("rate-limit abort, then resume without repeating flags")
        p = run("ratelimit", "run", TARGET, "--only", "trigger", "--model", "opus")
        rd = latest()
        o = results(rd)
        check(o["manifest"]["aborted_rate_limit"], "rate limit aborts the run")
        check(o["summary"]["by_model"]["opus"]["verdict"] == "INCOMPLETE", "aborted run is INCOMPLETE")
        check(len(hist_rows()) == 1, "aborted run kept out of history")
        p = run("ok", "run", TARGET, "--resume", str(rd))
        o = results(rd)
        check(p.returncode == 0, "resume exits 0")
        check({r["model"] for r in o["trials"]} == {"opus"}, "resume keeps the original model (not the default)")
        check({r["type"] for r in o["trials"]} == {"trigger"}, "resume keeps --only trigger")
        check(all(r["status"] == "ok" for r in o["trials"]), "resume completes every trial")

        print("resume of a run already in history (errors under the 10% bar)")
        before = len(hist_rows())
        p = run("hard_fail_once", "run", TARGET, "--model", "sonnet")
        rd = latest()
        check(len(hist_rows()) == before + 1, "run with a few errors enters history")
        p = run("ok", "run", TARGET, "--resume", str(rd))
        rows = [r for r in hist_rows() if r["run_id"] == rd.name]
        check(len(rows) == 1 and rows[0]["errors"] == 0, "resume replaces the history row, no duplicate")

        print("same-second runs get distinct run dirs")
        run("ok", "run", TARGET, "--only", "trigger", "--split", "dev", "-k", "1")
        run("ok", "run", TARGET, "--only", "trigger", "--split", "dev", "-k", "1")
        dirs = sorted(p.name for p in runs.iterdir())
        check(len(dirs) == len(set(dirs)) and all(
            len(results(runs / d)["trials"]) == results(runs / d)["manifest"]["n_trials"] for d in dirs
        ), "no run dir holds another run's trials")

        print("report re-render + dashboard")
        p = run("ok", "report", str(rd))
        check(p.returncode == 0 and len([r for r in hist_rows() if r["run_id"] == rd.name]) == 1, "report upserts history")
        p = run("ok", "viz")
        check(p.returncode == 0 and "/*__DATA__*/" not in Path(p.stdout.strip()).read_text(), "viz bakes data")

        print("world cases: sandbox, env, state + decision checks")
        sd = repo / "skills" / "skill-bench" / "suites" / TARGET
        (sd / "worlds" / "w").mkdir(parents=True)
        (sd / "worlds" / "w" / "Tasks.md").write_text("- fix the upload test\n- write docs\n")
        sj = json.loads((sd / "suite.json").read_text())
        sj["frozen"] = False
        sj["sandbox"] = {"allowed_tools": ["Bash(python3 *q.py*)"]}
        (sd / "suite.json").write_text(json.dumps(sj))
        base = {"split": "dev", "type": "behavior", "claim": "B1", "world": "w",
                "env": {"WORLD_FILE": "{world}/Tasks.md"}}
        wcases = [
            {**base, "id": "w-1", "prompt": "WORLDTEST what next? tasks in {world}",
             "checks": [{"kind": "decision", "pattern": "upload test", "reject": ["write docs"]},
                        {"kind": "file_unchanged", "path": "Tasks.md"},
                        {"kind": "tool_called", "name": "Bash", "input_regex": "q\\.py next"}]},
            {**base, "id": "w-2", "prompt": "WORLDTEST MARKDONE mark it",
             "checks": [{"kind": "file_regex", "path": "Tasks.md", "pattern": "\\[x\\] done"},
                        {"kind": "file_unchanged", "path": "Tasks.md", "desc": "must not edit"}]},
        ]
        bad = {"split": "dev", "type": "behavior", "claim": "B1", "id": "w-bad", "prompt": "no world here",
               "checks": [{"kind": "file_exists", "path": "x"}]}
        cf_ = sd / "cases.jsonl"
        orig = cf_.read_text()
        cf_.write_text(orig + json.dumps(bad) + "\n")
        p = run("ok", "validate", TARGET)
        check(p.returncode != 0 and "needs the case to have a 'world'" in p.stdout, "state check without a world is rejected")
        cf_.write_text(orig + "".join(json.dumps(c) + "\n" for c in wcases))
        p = run("ok", "validate", TARGET)
        check(p.returncode == 0, f"world cases validate (out: {p.stdout[-300:]!r})")
        p = run("ok", "run", TARGET, "--allow-unfrozen", "--case", "w-1", "--case", "w-2", "--split", "dev", "-k", "1", "--baseline")
        check(p.returncode == 0, f"world run exits 0 (stderr tail: {p.stderr[-300:]!r})")
        rd = latest()
        tr = {(r["case_id"], r["cond"]): r for r in results(rd)["trials"]}
        wc = [c for c in calls() if "WORLDTEST" in c["prompt"]]
        check(len(wc) == 4 and all(c["perm"] == "dontAsk" for c in wc), "world trials run in dontAsk mode")
        check(all("Read(./**)" in c["allowed"] and "Read" not in c["allowed"] and "Bash(python3 *q.py*)" in c["allowed"] for c in wc), "allowlist = base + suite sandbox tools")
        check(all("Bash" not in c["disallowed"] for c in wc), "an allowlisted tool is dropped from the blanket deny list")
        check(any("Skill(context-summarize)" in c["disallowed"] for c in wc), "baseline still denies the target in a world")
        check(all(not c["cwd"].startswith(str(repo)) for c in wc), "world cwd is outside the repo")
        check(all(c["world_file"] and c["world_file"].startswith(c["cwd"]) and "{world}" not in c["prompt"] for c in wc),
              "{world} expands to the trial's own copy in env and prompt")
        check(len({c["cwd"] for c in wc}) == 4, "every trial gets a fresh world")
        check(all(not Path(c["cwd"]).exists() for c in wc), "temp worlds are cleaned up")
        w1, w2 = tr[("w-1", "skill")], tr[("w-2", "skill")]
        check(w1["gates_pass"] and w1["world_changed"] == [], "decision + file_unchanged + tool input pass on an untouched world")
        g2 = {g["desc"]: g["pass"] for g in w2["checks"]}
        check(w2["world_changed"] == ["Tasks.md"] and g2.get("must not edit") is False
              and g2.get("Tasks.md \\[x\\] done") is True, "state checks see the trial's edits")
        check(w2["denied"] and "q.py next" in w2["denied"][0] and not w1["denied"], "sandbox denials recorded per trial")
        check(any("sandbox denials (w-2)" in w for w in results(rd)["summary"]["by_model"]["sonnet"]["warnings"]),
              "report warns that w-2 hit sandbox denials")
        check((rd / "worlds" / "w-2__sonnet__skill__t1" / "Tasks.md").read_text().endswith("[x] done\n"),
              "world end state archived next to the transcript")
        check(not (rd / "worlds" / "w-2__sonnet__skill__t1" / ".claude").exists(), "archived world excludes symlinked skills")
    finally:
        if failures:
            print(f"\nkept temp repo for inspection: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'FAILED' if failures else 'PASSED'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
