#!/usr/bin/env python3
"""
claude-maxer engine. It reads its settings and task list from SKILL.md (next
to this file) on every run, so editing the skill changes what runs. This file
holds only the mechanics a model can't be trusted with: reading usage, timing
against the 5h reset, never opening an off-schedule window, and writing to the
vault.

Commands (cron runs them through run_maxer_work.sh, which sets HOME/PATH/proxy):

  tick    What cron runs, every 10 min. Follows the real reset time instead
          of fixed hours: calls `run` once per window when it is within
          RUN_LEAD_MIN of its reset, and `open` once per pin hour
          (OPEN_HOURS) when no window is open. Every other tick exits
          without writing anything.
  open    Start a 5h window with a one-word Haiku ping. If a window is still
          open and resets within 20 min, wait for the reset and ping right
          after it. If it resets later than that, do nothing.
  run     Fill the window that is open right now. Work comes from the
          tasks-queue skill when it can be read: an undone vault Tasks.md
          item first (one at a time, committed to master in its repo), then
          one news batch if today hasn't had one, then optimize tasks (one
          app under /data/apps each, delivered as a PR), then more news. The
          queue decides that order (`tasks_queue.py next`); this file only
          decides whether there is quota and whether a task fits. SKILL.md's own tasks are the default, used
          only when the queue can't be read. Start tasks in batches until 5h
          reaches the target, 7d reaches today's budget ceiling, or
          the reset is less than 10 min away. Never runs when no window is
          open, because the first request would open one at the wrong time.
          Running tasks are killed 2 min before the reset for the same
          reason.
  status  Show usage and what `run` would do now.
  off     Pause: scheduled open/run do nothing (logged as skips) until `on`,
          or until --until (2h, 3d, 30m, HH:MM, YYYY-MM-DD, "YYYY-MM-DD HH:MM").
          A run already in progress stops starting new tasks.
  on      Resume.
  weekly off|on
          Ignore / respect the weekly (7d) limit. Off: runs skip today's
          weekly-budget ceiling and fill each window to the 5h target, so the
          week can run out early. Takes --until like `off`.

Vault output (written only when tasks run), under the vault root:
  claude-maxer/news/YYYY-MM-DD.md   one "## HH:MM · Task" section per task
  claude-maxer/log/YYYY-MM-DD.md    one block per run, one line per task
  claude-maxer/optimize/<app>.md    one dated report per optimize task
Checks, skips and pings go only to ~/.claude/state/claude-maxer.log.jsonl.

Usage: maxer.py tick | run|open|status [--dry-run] | off [--until WHEN] | on
               | weekly off [--until WHEN] | weekly on
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_PATH = os.path.join(SKILL_DIR, "SKILL.md")

STATE_DIR = os.path.expanduser("~/.claude/state")
SNAPSHOT_PATH = os.path.join(STATE_DIR, "usage_snapshot.json")
LOG_PATH = os.path.join(STATE_DIR, "claude-maxer.log.jsonl")
ROTATION_PATH = os.path.join(STATE_DIR, "claude-maxer-rotation.json")
BUDGET_PATH = os.path.join(STATE_DIR, "claude-maxer-day.json")
PAUSE_PATH = os.path.join(STATE_DIR, "claude-maxer-off.json")  # present = paused
WEEKLY_OFF_PATH = os.path.join(STATE_DIR, "claude-maxer-weekly-off.json")  # present = ignore 7d
WORK_DIR = os.path.join(STATE_DIR, "claude-maxer-work")  # neutral cwd: no repo CLAUDE.md
RUN_LOCK = "/tmp/claude-maxer-run.lock"
TICK_LOCK = "/tmp/claude-maxer-tick.lock"
TICK_PATH = os.path.join(STATE_DIR, "claude-maxer-tick.json")  # window/pin a tick already handled
# Shared with the */15 fetch cron: fetch_usage_oauth.py rotates a single-use
# OAuth refresh token, so two fetchers must never overlap.
FETCH_LOCK = "/tmp/claude-usage-fetch.lock"

# Fixed safety mechanics — deliberately not in SKILL.md.
STOP_MARGIN_MIN = 10       # stop starting tasks this close to the reset
KILL_MARGIN_S = 120        # hard-kill running tasks this long before the reset
SNAPSHOT_MAX_AGE_S = 20 * 60
OPEN_WAIT_MAX_S = 20 * 60  # opener waits for a reset at most this long
OPEN_HOURS = (3, 8, 13, 18, 23)  # tick opens a window only during these hours
RUN_LEAD_MIN = 60          # tick starts `run` this long before the window resets
SAME_RESET_S = 300         # resets_at jitters between fetches; this close = same window
DEFAULT_TASK_PCT = 4.0     # first guess at 5h% per task; replaced by measurement
PING_MODEL = "claude-haiku-4-5-20251001"

# Fallbacks if SKILL.md's settings block lacks a key. Each key can also be
# overridden by env MAXER_<KEY> (for manual tests).
DEFAULTS = {
    "target_5h": 95.0,
    "overshoot": 3.0,
    "weekly_target": 95.0,
    "concurrency": 3,
    "model": "claude-opus-5-5",
    "budget_usd": "5",
    "task_timeout_min": 25,
}
CFG = dict(DEFAULTS)
TASKS = []  # [(slug, title, prompt)], loaded from SKILL.md

# The task queue (tasks-queue skill) outranks SKILL.md's own tasks: tier 1 is
# the vault's Tasks.md, tier 2 its news tasks. SKILL.md's tasks are the
# default, used only when the queue can't be read.
QUEUE_SCRIPT = os.path.join(SKILL_DIR, "..", "tasks-queue", "tasks_queue.py")
QUEUE_TIMEOUT_S = 90         # the vault container has hung before; never wait on it long
VAULT_TASK_ROOT = "/data/apps"  # repos a vault task may target
VAULT_FAILS_PATH = os.path.join(STATE_DIR, "claude-maxer-vault-fails.json")
MAX_VAULT_ATTEMPTS = 2       # then skip that task until the user edits it
DEFAULT_VAULT_PCT = 10.0     # first guess at 5h% per vault task; replaced by measurement
DEFAULT_OPT_PCT = 10.0       # same, per optimize task

VAULT_ROOT = os.environ.get("OBSIDIAN_VAULT_PATH", "/data/nextcloud_client/obsidian/lidaning")


# ── SKILL.md: settings + tasks ─────────────────────────────────────────────

class SkillError(Exception):
    pass


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def load_skill(path=SKILL_PATH):
    """Parse the ```maxer-settings block and the `## Tasks` section."""
    with open(path) as f:
        text = f.read()

    cfg = dict(DEFAULTS)
    m = re.search(r"```maxer-settings\n(.*?)```", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (s.strip() for s in line.split(":", 1))
            if k in DEFAULTS:
                cfg[k] = v
    for k in DEFAULTS:
        if f"MAXER_{k.upper()}" in os.environ:
            cfg[k] = os.environ[f"MAXER_{k.upper()}"]
    try:
        for k, d in DEFAULTS.items():
            cfg[k] = type(d)(cfg[k])
    except ValueError as e:
        raise SkillError(f"bad value in maxer-settings: {e}")

    m = re.search(r"^## Tasks[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        raise SkillError("SKILL.md has no '## Tasks' section")
    tasks = []
    for block in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        title, body = title.strip(), body.strip()
        if title and body:
            tasks.append((slugify(title), title, body))
    if not tasks:
        raise SkillError("the '## Tasks' section has no '### Title' + prompt entries")
    return cfg, tasks


def use_skill():
    global CFG, TASKS
    CFG, TASKS = load_skill()


# ── small helpers ──────────────────────────────────────────────────────────

def log(status, **fields):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps({"ts": time.time(), "status": status, **fields}) + "\n")
    print(f"[{datetime.now():%H:%M:%S}] {status} {json.dumps(fields, ensure_ascii=False)}")


def hm(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def refresh_snapshot():
    """Fetch fresh usage under the shared fetch lock. Best-effort."""
    with open(FETCH_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            subprocess.run(
                [sys.executable, os.path.join(SKILL_DIR, "fetch_usage_oauth.py")],
                capture_output=True, text=True, timeout=90,
            )
        except subprocess.TimeoutExpired:
            pass


def read_usage():
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    rl = snap.get("rate_limits", {})
    five, seven = rl.get("five_hour") or {}, rl.get("seven_day") or {}
    return {
        "five_pct": five.get("used_percentage"),
        "five_reset": five.get("resets_at"),
        "seven_pct": seven.get("used_percentage"),
        "seven_reset": seven.get("resets_at"),
        "age": time.time() - snap.get("cached_at", 0),
    }


def fresh_usage():
    refresh_snapshot()
    return read_usage()


def window_open(u, now):
    return bool(u["five_reset"]) and u["five_reset"] > now


def day_budget(u, now, persist=True):
    """Today's 7d ceiling. Once per day (and again if a new week starts), what
    is left of the week up to weekly_target is split evenly over the days
    left until the weekly reset; today may spend one share. Earlier heavy use
    shrinks the share but never blocks a day outright. Returns a dict:
    seven_start, budget (pp), ceiling (%), new (first computed now)."""
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    try:
        with open(BUDGET_PATH) as f:
            b = json.load(f)
        if b.get("date") == today and abs((b.get("seven_reset") or 0)
                                          - (u["seven_reset"] or 0)) < SAME_RESET_S:
            return dict(b, new=False)
    except (OSError, ValueError):
        pass
    tgt, seven = CFG["weekly_target"], u["seven_pct"] or 0
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0).timestamp()
    days_left = ((u["seven_reset"] or now + 86400) - midnight) / 86400
    budget = max(0.0, tgt - seven) / max(days_left, 1.0)
    b = {"date": today, "seven_reset": u["seven_reset"], "seven_start": seven,
         "days_left": round(days_left, 2), "budget": round(budget, 1),
         "ceiling": round(min(tgt, seven + budget), 1)}
    if persist:
        with open(BUDGET_PATH, "w") as f:
            json.dump(b, f)
    return dict(b, new=True)


def switch_state(path, now, on_cmd, what):
    """'<what> since …, until …' if the switch file at `path` is set, else
    None. An expired --until clears the switch."""
    try:
        with open(path) as f:
            p = json.load(f)
    except (OSError, ValueError):
        return None
    until = p.get("until")
    if until and until <= now:
        os.remove(path)
        log("switch_expired", switch=os.path.basename(path))
        return None
    since = datetime.fromtimestamp(p.get("since", now)).strftime("%m-%d %H:%M")
    end = datetime.fromtimestamp(until).strftime("%m-%d %H:%M") if until else f"`{on_cmd}`"
    return f"{what} since {since}, until {end}"


def paused(now):
    """Reason string if the off switch is set, else None."""
    return switch_state(PAUSE_PATH, now, "maxer.py on", "switched off")


def weekly_ignored(now):
    """Reason string if the weekly limit is switched off, else None."""
    return switch_state(WEEKLY_OFF_PATH, now, "maxer.py weekly on", "weekly limit ignored")


def parse_until(s, now):
    m = re.fullmatch(r"(\d+)\s*([mhd])", s.strip())
    if m:
        return now + int(m[1]) * {"m": 60, "h": 3600, "d": 86400}[m[2]]
    base = datetime.fromtimestamp(now)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    try:
        t = datetime.strptime(s, "%H:%M")
    except ValueError:
        raise SystemExit(f"can't parse --until {s!r}: use 2h, 3d, 30m, HH:MM, YYYY-MM-DD "
                         f"or 'YYYY-MM-DD HH:MM'")
    ts = base.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0).timestamp()
    return ts if ts > now else ts + 86400  # next occurrence


def set_switch(path, until, event):
    now = time.time()
    end = parse_until(until, now) if until else None
    if end is not None and end <= now:
        raise SystemExit("--until is in the past")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"since": now, "until": end}, f)
    log(event, until=end)
    return end


def clear_switch(path, event):
    if os.path.exists(path):
        os.remove(path)
        log(event)
        return True
    return False


def cmd_off(until):
    end = set_switch(PAUSE_PATH, until, "off")
    print(f"claude-maxer is OFF until {datetime.fromtimestamp(end):%Y-%m-%d %H:%M}" if end
          else "claude-maxer is OFF until `maxer.py on`")
    return 0


def cmd_on():
    print("claude-maxer is ON" if clear_switch(PAUSE_PATH, "on")
          else "claude-maxer was already on")
    return 0


def cmd_weekly(state, until):
    """`weekly off`: runs ignore the 7d limit (today's weekly-budget ceiling)
    and fill every window to the 5h target. `weekly on`: respect it again."""
    if state == "off":
        end = set_switch(WEEKLY_OFF_PATH, until, "weekly_off")
        print("weekly limit is IGNORED " + (f"until {datetime.fromtimestamp(end):%Y-%m-%d %H:%M}"
                                            if end else "until `maxer.py weekly on`"))
    else:
        if until:
            raise SystemExit("--until goes with `weekly off`")
        print("weekly limit is RESPECTED again" if clear_switch(WEEKLY_OFF_PATH, "weekly_on")
              else "weekly limit was already respected")
    return 0


def gate(u, now):
    """(ok, reason) for starting more work right now."""
    off = paused(now)
    if off:
        return False, off
    if u["age"] > SNAPSHOT_MAX_AGE_S:
        return False, f"usage snapshot is {int(u['age'] / 60)} min old"
    if not window_open(u, now):
        return False, "no 5h window open (starting work now would open an off-schedule window)"
    left_min = (u["five_reset"] - now) / 60
    if left_min <= STOP_MARGIN_MIN:
        return False, f"window resets {hm(u['five_reset'])}, only {left_min:.0f} min left"
    if u["five_pct"] is not None and u["five_pct"] >= CFG["target_5h"]:
        return False, f"5h at {u['five_pct']}%, target {CFG['target_5h']:.0f}% reached"
    ceiling = day_budget(u, now)["ceiling"]
    if weekly_ignored(now):
        return True, "ok"
    if u["seven_pct"] is not None and u["seven_pct"] >= ceiling:
        return False, f"7d at {u['seven_pct']}%, today's weekly-budget ceiling is {ceiling}%"
    return True, "ok"


def next_tasks(n, tasks):
    """Round-robin through the news tasks across runs, by title, so
    editing the list doesn't reset or skip the rotation badly."""
    try:
        with open(ROTATION_PATH) as f:
            last = json.load(f).get("last")
    except (OSError, ValueError):
        last = None
    titles = [t[1] for t in tasks]
    idx = titles.index(last) + 1 if last in titles else 0
    picked = [tasks[(idx + i) % len(tasks)] for i in range(min(n, len(tasks)))]
    with open(ROTATION_PATH, "w") as f:
        json.dump({"last": picked[-1][1]}, f)
    return picked


# ── task queue ─────────────────────────────────────────────────────────────

def queue_call(*args):
    """(returncode, stdout) from tasks_queue.py, or None if it can't run."""
    try:
        p = subprocess.run([sys.executable, QUEUE_SCRIPT, *args], capture_output=True,
                           text=True, timeout=QUEUE_TIMEOUT_S)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def news_source():
    """(tasks, source): the queue's news tasks, or SKILL.md's defaults when
    the queue can't be read or lists none."""
    r = queue_call("news")
    if r and r[0] == 0:
        try:
            tasks = [(slugify(t["title"]), t["title"], t["prompt"]) for t in json.loads(r[1])]
            if tasks:
                return tasks, "tasks-queue"
        except (ValueError, KeyError, TypeError):
            pass
    return TASKS, "claude-maxer defaults"


def read_fails():
    try:
        with open(VAULT_FAILS_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def next_work(skip=(), small=False):
    """The queue's next task ({kind: vault|news|optimize, ...}), or None if
    the queue can't be read. `skip`: vault tasks not to hand out."""
    args = ["next"] + (["--small"] if small else [])
    for t in skip:
        args += ["--skip", t]
    r = queue_call(*args)
    if not r or r[0] != 0:
        return None
    try:
        return json.loads(r[1])
    except ValueError:
        return None


def describe(task):
    if not task:
        return "queue unreadable (SKILL.md defaults would run)"
    if task["kind"] == "vault":
        return f"vault task: {task['text'][:80]}"
    if task["kind"] == "optimize":
        return (f"optimize {task['app']} → " + (f"PR to {task['repo']}" if task["pr"]
                                               else "local branch only, no PR"))
    return f"news ({task.get('why')})"


def pr_ok(url, repo):
    """True if `url` is a PR that exists in `repo` (owner/name)."""
    if not url.startswith(f"https://github.com/{repo}/pull/"):
        return False
    try:
        return subprocess.run(["gh", "pr", "view", url, "--json", "url"], capture_output=True,
                              timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def branch_ts(repo, branch):
    try:
        ts = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ct", branch],
                            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(ts or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


VAULT_PROMPT = """You are running unattended for claude-maxer. A task from the user's Obsidian \
vault Tasks.md reads:

"{task}"

Repos live under {root}. Work out which repo the task is about, cd into it, and implement \
the task: make the needed changes and run any existing lint/typecheck/build/test step for \
the touched area. Keep the change scoped to this task; no unrelated cleanup.

Before committing, check `git branch --show-current` and `git status`. Commit to master. \
If the repo is on another branch or has uncommitted work you didn't make, stop without \
committing. Do not push, and do not open a PR.

If the task is unclear, needs a decision from the user, or you can't tell which repo it \
means, change nothing and stop.

End your reply with exactly these two lines:
REPO: <absolute path of the repo, or none>
RESULT: done | skipped <one-line reason>"""


def last_commit_ts(repo):
    try:
        br = subprocess.run(["git", "-C", repo, "branch", "--show-current"],
                            capture_output=True, text=True, timeout=30).stdout.strip()
        ts = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ct"],
                            capture_output=True, text=True, timeout=30).stdout.strip()
        return br, float(ts or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, 0.0


def run_optimize_task(task, deadline):
    """Run one optimize task with full tools, cwd the app's repo. The worker
    edits only a fresh worktree and delivers a PR. File its report in the
    vault, record the outcome in the queue, and remove the worktree (the
    branch stays). "optimized" is believed only if the PR exists, or, where
    no PR is allowed, the branch got a new commit."""
    app, path = task["app"], task["path"]
    started = time.time()
    res = {"slug": "optimize", "title": f"optimize: {app}", "start": started,
           "items": 0, "cost": 0.0}
    cmd = ["claude", "-p", task["prompt"], "--model", CFG["model"], "--output-format", "json",
           "--max-budget-usd", CFG["budget_usd"], "--dangerously-skip-permissions"]
    timeout = max(60, min(CFG["task_timeout_min"] * 60, deadline - started))
    reply = ""
    try:
        p = subprocess.run(cmd, cwd=path, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        out = json.loads(p.stdout)
        res["cost"] = float(out.get("total_cost_usd") or 0)
        res["tokens"] = token_usage(out)
        reply = PRACTICE_BLOCK.sub("", out.get("result") or "").strip()
    except subprocess.TimeoutExpired:
        res["error"] = "killed before the window reset"
    except ValueError:
        res["error"] = "unparseable output"
    res["end"] = time.time()

    outcome = (re.findall(r"^APP:\s*(.+)$", reply, re.M) or [""])[-1].strip()
    pr = (re.findall(r"^PR:\s*(\S+)", reply, re.M) or ["none"])[-1]
    status, _, why = outcome.partition(" ")
    if res.get("error") or status not in ("skip", "optimized", "findings"):
        status, why = "failed", res.get("error") or "no APP line in the reply"
        res["error"] = why
    elif status == "optimized":
        if task.get("pr"):
            if pr_ok(pr, task["repo"]):
                why = pr
            else:
                status, why = "findings", f"claimed optimized, but no PR found ({pr})"
        elif branch_ts(path, task["branch"]) >= int(started):
            why = f"local branch {task['branch']} (no PR: origin is {task['repo'] or 'none'})"
        else:
            status, why = "findings", f"claimed optimized, but {task['branch']} has no new commit"
    res["outcome"] = f"{status} {why}".strip()
    queue_call("optimize-done", app, status, why)
    if os.path.isdir(task.get("worktree", "")):
        subprocess.run(["git", "-C", path, "worktree", "remove", "--force", task["worktree"]],
                       capture_output=True, timeout=60)
    subprocess.run(["git", "-C", path, "worktree", "prune"], capture_output=True, timeout=60)
    body = reply or f"_No report: {why}_"
    vault_append(f"claude-maxer/optimize/{app}.md",
                 f"\n## {datetime.fromtimestamp(started):%Y-%m-%d %H:%M} · {status}\n\n{body}\n",
                 heading=f"# Optimize — {app}\n\n`{path}` · one report per claude-maxer "
                         f"visit, newest last.\n")
    return res


def run_vault_task(text, deadline):
    """Run one vault task with full tools. Mark it done only if a new commit
    landed on master in the repo it names; otherwise count a failed attempt."""
    started = time.time()
    res = {"slug": "vault-task", "title": f"vault task: {text[:60]}", "start": started,
           "items": 0, "cost": 0.0}
    cmd = ["claude", "-p", VAULT_PROMPT.format(task=text, root=VAULT_TASK_ROOT),
           "--model", CFG["model"], "--output-format", "json",
           "--max-budget-usd", CFG["budget_usd"], "--dangerously-skip-permissions"]
    timeout = max(60, min(CFG["task_timeout_min"] * 60, deadline - started))
    try:
        p = subprocess.run(cmd, cwd=VAULT_TASK_ROOT, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        out = json.loads(p.stdout)
        res["cost"] = float(out.get("total_cost_usd") or 0)
        res["tokens"] = token_usage(out)
        reply = out.get("result") or ""
    except subprocess.TimeoutExpired:
        reply, res["error"] = "", "killed before the window reset"
    except ValueError:
        reply, res["error"] = "", "unparseable output"
    res["end"] = time.time()

    repo = (re.findall(r"^REPO:\s*(\S+)", reply, re.M) or ["none"])[-1]
    result = (re.findall(r"^RESULT:\s*(.+)$", reply, re.M) or [""])[-1].strip()
    if not res.get("error"):
        repo_ok = (repo.startswith(VAULT_TASK_ROOT + "/")
                   and os.path.isdir(os.path.join(repo, ".git")))
        br, ts = last_commit_ts(repo) if repo_ok else (None, 0.0)
        if result.startswith("done") and br == "master" and ts >= int(started):
            r = queue_call("mark", text)
            res["repo"] = repo
            if not r or r[0] != 0:
                res["error"] = f"committed in {repo} but marking the vault task failed"
        else:
            res["error"] = (result or "no RESULT line")[:120] + (
                "" if result.startswith("skipped") else f" (repo {repo}, no new master commit)")
    if res.get("error"):
        fails = read_fails()
        fails[text] = fails.get(text, 0) + 1
        with open(VAULT_FAILS_PATH, "w") as f:
            json.dump(fails, f, ensure_ascii=False)
        res["attempt"] = fails[text]
    return res


# ── vault ──────────────────────────────────────────────────────────────────
# Plain file appends into the vault folder rather than the obsidian-vault MCP
# container: on 2026-09-27 that container's sessions hung mid-run (healthz
# fine, every call timing out) and a finished digest was lost. The vault is a
# local folder that Nextcloud syncs, so a file write is all a note needs.

def note_path(day):
    return f"claude-maxer/news/{day}.md"


def covered_titles(path):
    """Titles already in today's note, so a later task doesn't repeat them."""
    try:
        with open(os.path.join(VAULT_ROOT, path)) as f:
            return re.findall(r"\*\*\[([^\]]+)\]\(", f.read())
    except OSError:
        return []


_vault_lock = threading.Lock()  # parallel tasks append to the same daily note


def vault_append(path, text, heading=None):
    full = os.path.join(VAULT_ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with _vault_lock, open(full, "a") as f:
        if heading and f.tell() == 0:
            text = heading + text
        f.write(text)


def log_note(day):
    return f"claude-maxer/log/{day}.md"


def vault_decision(now, u, line):
    """One line per scheduled decision in the vault log. On the day's first
    entry, the note heading and today's weekly budget go first."""
    day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    b = day_budget(u, now)
    head = ""
    if b["new"] or not os.path.exists(os.path.join(VAULT_ROOT, log_note(day))):
        head = (f"\n**Today's budget:** {b['budget']}pp of the weekly limit "
                f"(7d {b['seven_start']}% → ceiling {b['ceiling']}%, "
                f"{b['days_left']} days to the weekly reset)\n\n")
    vault_append(log_note(day), head + line + "\n",
                 heading=f"# claude-maxer log — {day}\n\nEvery scheduled open/run decision, "
                         f"and every task. News lands in claude-maxer/news/.\n")


# ── one task ───────────────────────────────────────────────────────────────

PRACTICE_BLOCK = re.compile(r"=== English Practice ===.*?=== English Practice ===\s*", re.S)
ENTRY = re.compile(r"^\s*\d+\.\s+\*\*\[.+?\]\(https?://", re.M)

# Appended to every SKILL.md task prompt: what the engine needs to parse,
# dedupe and store the reply. Task authors write only the *what*.
CONTRACT = (
    "\n\n---\nYou are running unattended. Your reply is saved verbatim into a notes vault, "
    "so reply with nothing except a numbered list: no preamble, no closing remarks, no "
    "English-practice block. You have only WebSearch and WebFetch. Run several different "
    "searches and open sources to confirm details. Only include an item if you actually saw "
    "its URL in a search result or opened it; never invent a URL, a date, or a detail.\n\n"
    "Format, exactly, one entry per item:\n"
    "1. **[Headline in your own words](https://source.url)** · Source · YYYY-MM-DD\n"
    "   One or two sentences: what it is and why it matters."
)


def list_only(text):
    """Keep the numbered entries and their indented continuation lines; drop
    any preamble before the list and any commentary after it."""
    kept, started = [], False
    for line in text.splitlines():
        if re.match(r"\s*\d+\.\s", line):
            started = True
        elif started and line.strip() and not line.startswith((" ", "\t")):
            break
        if started:
            kept.append(line)
    return "\n".join(kept).strip()


def build_prompt(task_prompt, already):
    skip = ""
    if already:
        skip = ("\n\nThese items are already in today's note. Do not repeat them, even "
                "from a different source:\n" + "\n".join(f"- {t}" for t in already))
    return task_prompt + CONTRACT + skip


TOKEN_KEYS = ("inputTokens", "cacheCreationInputTokens", "cacheReadInputTokens", "outputTokens")


def token_usage(out):
    """Tokens summed over every model the session used (modelUsage also
    covers subagent/helper models, which the top-level usage omits)."""
    tot = dict.fromkeys(TOKEN_KEYS, 0)
    for m in (out.get("modelUsage") or {}).values():
        for k in TOKEN_KEYS:
            tot[k] += int(m.get(k) or 0)
    return tot


def fmt_tokens(t):
    def n(x):
        return f"{x / 1e6:.1f}M" if x >= 1e6 else f"{x / 1e3:.0f}k" if x >= 1e4 \
            else f"{x / 1e3:.1f}k" if x >= 1e3 else str(x)
    if not t or not any(t.values()):
        return "tokens n/a"
    return (f"{n(t['inputTokens'])} in, {n(t['cacheCreationInputTokens'])} cache write, "
            f"{n(t['cacheReadInputTokens'])} cache read, {n(t['outputTokens'])} out")


def run_task(slug, title, prompt, day, deadline):
    path = note_path(day)
    cmd = [
        "claude", "-p", build_prompt(prompt, covered_titles(path)),
        "--model", CFG["model"],
        "--output-format", "json",
        "--max-budget-usd", CFG["budget_usd"],
        # Only web tools exist in the session: nothing to write with, no
        # Skill call for the global english-practice rule to spend turns on,
        # and --strict-mcp-config (with no config) loads no MCP servers.
        "--tools", "WebSearch,WebFetch",
        "--allowedTools", "WebSearch", "WebFetch",
        "--strict-mcp-config",
    ]
    started = time.time()
    timeout = max(60, min(CFG["task_timeout_min"] * 60, deadline - started))
    res = {"slug": slug, "title": title, "start": started, "items": 0, "cost": 0.0}
    try:
        p = subprocess.run(cmd, cwd=WORK_DIR, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        res.update(end=time.time(), error="killed before the window reset")
        return res
    res["end"] = time.time()
    try:
        out = json.loads(p.stdout)
    except ValueError:
        res["error"] = f"exit {p.returncode}, unparseable output"
        return res
    res["cost"] = float(out.get("total_cost_usd") or 0)
    res["tokens"] = token_usage(out)
    text = PRACTICE_BLOCK.sub("", out.get("result") or "").strip()
    entries = ENTRY.findall(text)
    if out.get("is_error") or not entries:
        res["error"] = (out.get("subtype") or "no linked entries in reply")[:120]
        return res
    heading = f"# News — {day}\n\nCollected by claude-maxer, one section per task.\n"
    try:
        vault_append(path, f"\n## {hm(started)} · {title}\n\n{list_only(text)}\n", heading=heading)
    except Exception as e:
        res["error"] = f"vault write failed: {e}"[:120]
        return res
    res["items"] = len(entries)
    return res


# ── commands ───────────────────────────────────────────────────────────────

def cmd_run(dry_run):
    lk = open(RUN_LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another run is in progress")
        return 0
    os.makedirs(WORK_DIR, exist_ok=True)

    u = fresh_usage()
    ok, why = gate(u, time.time())
    if not ok:
        log("skip", reason=why, five=u["five_pct"], seven=u["seven_pct"])
        if not dry_run:
            vault_decision(time.time(), u, f"- {hm(time.time())} run · skipped: {why} "
                                           f"(5h {u['five_pct']}%)")
        return 0
    if dry_run:
        print(f"DRY RUN: would start tasks — 5h {u['five_pct']}%, resets {hm(u['five_reset'])}, "
              f"7d {u['seven_pct']}% (today's ceiling {day_budget(u, time.time(), False)['ceiling']}%)")
        task = next_work(sorted(k for k, n in read_fails().items() if n >= MAX_VAULT_ATTEMPTS))
        news, src = news_source()
        print("queue's next task:", describe(task))
        print(f"news tasks ({src}):", [t[1] for t in news])
        if task and task["kind"] == "vault":
            print(VAULT_PROMPT.format(task=task["text"], root=VAULT_TASK_ROOT))
        elif task and task["kind"] == "optimize":
            print(task["prompt"][:1500])
        else:
            print(build_prompt(news[0][2], [])[:900])
        return 0

    day = datetime.now().strftime("%Y-%m-%d")
    note = log_note(day)
    reset = u["five_reset"]
    deadline = reset - KILL_MARGIN_S
    start_five = u["five_pct"]
    vault_decision(
        time.time(), u,
        f"\n### {hm(time.time())} run — window resets {hm(reset)}, "
        f"5h {u['five_pct']}%, 7d {u['seven_pct']}% (today's ceiling "
        f"{day_budget(u, time.time())['ceiling']}%"
        f"{', ignored: weekly switch is off' if weekly_ignored(time.time()) else ''}) · "
        f"[[claude-maxer/news/{day}|news {day}]]\n",
    )
    log("run_start", five=u["five_pct"], seven=u["seven_pct"], resets=reset)

    per_task, per_vault, per_opt = DEFAULT_TASK_PCT, DEFAULT_VAULT_PCT, DEFAULT_OPT_PCT
    total_cost, tasks_done = 0.0, 0
    total_tokens = dict.fromkeys(TOKEN_KEYS, 0)
    tried = set()
    news, src = news_source()
    vault_append(note, f"- news tasks from {src}\n")
    while True:
        ok, why = gate(u, time.time())
        if not ok:
            break
        # Never start a task expected to push 5h past target + overshoot:
        # 100% locks the user out until the reset.
        room = CFG["target_5h"] + CFG["overshoot"] - (u["five_pct"] or 0)
        before = u["five_pct"] or 0
        # The queue decides what's next; this loop only checks that it fits.
        skip = sorted(tried | {t for t, n in read_fails().items() if n >= MAX_VAULT_ATTEMPTS})
        task = next_work(skip)
        if task and ((task["kind"] == "vault" and room < per_vault)
                     or (task["kind"] == "optimize" and room < per_opt)):
            task = next_work(skip, small=True)
        task = task or {"kind": "news", "why": "queue unreadable"}
        vt = task.get("text") if task["kind"] == "vault" else None
        ot = task if task["kind"] == "optimize" else None
        if vt:
            tried.add(vt)  # one attempt per run; a failure retries next run
            results = [run_vault_task(vt, deadline)]
            u = fresh_usage()
            delta = (u["five_pct"] or 0) - before
            if delta > 0:
                per_vault = delta
        elif ot:
            results = [run_optimize_task(ot, deadline)]
            u = fresh_usage()
            delta = (u["five_pct"] or 0) - before
            if delta > 0 and not results[0].get("outcome", "").startswith("skip"):
                per_opt = delta  # a quick skip says nothing about a real visit's cost
        else:
            # News: today's first batch, or filler.
            n = min(CFG["concurrency"], int(room // max(per_task, 0.5)))
            if n < 1:
                why = f"5h at {u['five_pct']}%, one more task (~{per_task:.0f}pp) would overshoot"
                break
            batch = next_tasks(n, news)
            queue_call("news-ran")
            with ThreadPoolExecutor(max_workers=len(batch)) as ex:
                results = list(ex.map(lambda t: run_task(*t, day, deadline), batch))
            u = fresh_usage()
            delta = (u["five_pct"] or 0) - before
            if delta > 0:
                per_task = delta / len(batch)
        for r in results:
            total_cost += r["cost"]
            for k, v in r.get("tokens", {}).items():
                total_tokens[k] += v
            cost = f"${r['cost']:.2f} · {fmt_tokens(r.get('tokens'))}"
            if r.get("error"):
                tries = f" (attempt {r['attempt']}/{MAX_VAULT_ATTEMPTS})" if "attempt" in r else ""
                line = (f"- {hm(r['start'])}–{hm(r['end'])} · {r['title']} · failed{tries}: "
                        f"{r['error']} · {cost}\n")
            elif r["slug"] == "optimize":
                tasks_done += 1
                app = r["title"].split(": ", 1)[1]
                line = (f"- {hm(r['start'])}–{hm(r['end'])} · {r['title']} · {r['outcome']} · "
                        f"[[claude-maxer/optimize/{app}|report]] · {cost}\n")
            elif r["slug"] == "vault-task":
                tasks_done += 1
                line = (f"- {hm(r['start'])}–{hm(r['end'])} · {r['title']} · done, committed "
                        f"in {r['repo']}, checked off in Tasks.md · {cost}\n")
            else:
                tasks_done += 1
                line = (f"- {hm(r['start'])}–{hm(r['end'])} · {r['title']} · {r['items']} items "
                        f"· {cost}\n")
            vault_append(note, line)
            log("task", **r)
        vault_append(note, f"- 5h now {u['five_pct']}% (batch of {len(results)}: +{delta:.0f}pp)\n")

    vault_append(note, f"- stopped: {why}. {tasks_done} tasks, ${total_cost:.2f}, "
                           f"{fmt_tokens(total_tokens)}, 5h {start_five}% → {u['five_pct']}%\n")
    log("run_end", reason=why, tasks=tasks_done, cost=round(total_cost, 2), tokens=total_tokens,
        five_start=start_five, five_end=u["five_pct"])
    return 0


def ping():
    os.makedirs(WORK_DIR, exist_ok=True)
    p = subprocess.run(
        # --tools "" = no tools at all. Without it, the global CLAUDE.md sends
        # the model looking for a Skill call and a 1-turn cap fails the ping.
        ["claude", "-p", "Reply with the single word: ack", "--model", PING_MODEL,
         "--tools", "", "--strict-mcp-config", "--max-turns", "2"],
        cwd=WORK_DIR, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180,
    )
    return p.returncode


def cmd_open(dry_run):
    now = time.time()
    off = paused(now)
    if off:
        log("open_skip", reason=off)
        if not dry_run:
            vault_decision(now, read_usage(), f"- {hm(now)} open · skipped: {off}")
        return 0
    u = fresh_usage()
    if window_open(u, now):
        wait = u["five_reset"] - now
        if wait > OPEN_WAIT_MAX_S:
            why = f"a window is already open until {hm(u['five_reset'])}"
            log("open_skip", reason=why)
            if not dry_run:
                vault_decision(now, u, f"- {hm(now)} open · skipped: {why}")
            return 0
        if dry_run:
            print(f"DRY RUN: would wait {wait / 60:.1f} min for the {hm(u['five_reset'])} reset, then ping")
            return 0
        time.sleep(wait + 90)
    elif dry_run:
        print("DRY RUN: no window open, would ping now")
        return 0
    rc = ping()
    time.sleep(20)
    u = fresh_usage()
    log("opened" if rc == 0 else "open_failed", rc=rc, resets=u["five_reset"],
        resets_hm=hm(u["five_reset"]) if u["five_reset"] else None)
    t = time.time()
    if rc == 0:
        vault_decision(t, u, f"- {hm(t)} open · opened a window, resets "
                             f"{hm(u['five_reset']) if u['five_reset'] else '?'}")
    else:
        vault_decision(t, u, f"- {hm(t)} open · FAILED (claude exit {rc})")
    return 0 if rc == 0 else 1


def pin_slot(now):
    """Start of the pin hour `now` is in, or None. Windows are opened only
    here, so a window someone else opened off-pin doesn't make every later
    window drift with it."""
    d = datetime.fromtimestamp(now)
    if d.hour not in OPEN_HOURS:
        return None
    return d.replace(minute=0, second=0, microsecond=0).timestamp()


def cmd_tick():
    """Cron runs this every 10 min. `run` fires once per window, RUN_LEAD_MIN
    before its actual reset; `open` fires once per pin hour, only when no
    window is open. open/run log their own decisions (skips included), so a
    window or pin gets one vault line, not one per tick."""
    lk = open(TICK_LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0  # an earlier tick is still running or waiting on a reset
    try:
        with open(TICK_PATH) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}

    def save():
        with open(TICK_PATH, "w") as f:
            json.dump(st, f)

    now = time.time()
    u = read_usage()  # the */15 fetch keeps it fresh; open/run refresh again anyway
    if u["age"] > 10 * 60:
        u = fresh_usage()
    if window_open(u, now):
        reset = u["five_reset"]
        # +90s: cron starts a few seconds late and resets_at jitters
        if reset - now > RUN_LEAD_MIN * 60 + 90 or abs(st.get("ran_for", 0) - reset) < SAME_RESET_S:
            return 0
        st["ran_for"] = reset
        save()
        return cmd_run(False)
    slot = pin_slot(now)
    if slot is None or st.get("opened_for") == slot:
        return 0
    rc = cmd_open(False)
    if rc == 0:  # a failed ping retries on the next tick while the pin hour lasts
        st["opened_for"] = slot
        save()
    return rc


def cmd_status():
    u = fresh_usage()
    now = time.time()
    ok, why = gate(u, now)
    b = day_budget(u, now, persist=False)
    print(f"switch: {paused(now) or 'on'}")
    print(f"weekly limit: {weekly_ignored(now) or 'respected (today’s ceiling applies)'}")
    print(f"5h {u['five_pct']}%  resets {hm(u['five_reset']) if u['five_reset'] else '-'}"
          f"  | 7d {u['seven_pct']}%  today's budget {b['budget']}pp "
          f"(from {b['seven_start']}% → ceiling {b['ceiling']}%, {b['days_left']} days left)")
    news, src = news_source()
    task = next_work(sorted(k for k, n in read_fails().items() if n >= MAX_VAULT_ATTEMPTS))
    print(f"queue's next task: {describe(task)}")
    print(f"news tasks from {src}: {', '.join(t[1] for t in news)}")
    print(f"settings: {CFG}")
    print("run would start tasks now" if ok else f"run would skip: {why}")
    if window_open(u, now):
        print(f"tick: runs at ~{hm(u['five_reset'] - RUN_LEAD_MIN * 60)} "
              f"({RUN_LEAD_MIN} min before the {hm(u['five_reset'])} reset)")
    else:
        pins = ", ".join(f"{h:02d}" for h in OPEN_HOURS)
        print(f"tick: no window open; opens one in the next pin hour ({pins})")
    return 0


def main():
    ap = argparse.ArgumentParser(description="claude-maxer")
    ap.add_argument("command", choices=["tick", "run", "open", "status", "off", "on", "weekly"])
    ap.add_argument("state", nargs="?", choices=["on", "off"], help="with weekly")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--until", help="with off: 2h, 3d, 30m, HH:MM, YYYY-MM-DD, 'YYYY-MM-DD HH:MM'")
    a = ap.parse_args()
    if a.command == "off":
        return cmd_off(a.until)
    if a.command == "on":
        return cmd_on()
    if a.command == "weekly":
        if not a.state:
            ap.error("weekly needs on or off")
        return cmd_weekly(a.state, a.until)
    if a.command in ("tick", "run", "open", "status"):
        try:
            use_skill()
        except (OSError, SkillError) as e:
            # Don't guess at a half-parsed skill: log loudly and do nothing.
            log("skill_error", error=str(e))
            return 1
    if a.command == "tick":
        return cmd_tick()
    if a.command == "run":
        return cmd_run(a.dry_run)
    if a.command == "open":
        return cmd_open(a.dry_run)
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
