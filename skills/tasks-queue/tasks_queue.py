#!/usr/bin/env python3
"""Read/write the undone-task queue in the Obsidian vault's Tasks note.

This is a library + CLI only -- it owns no schedule. Callers run
`pick` -> do the work -> `mark`; see SKILL.md.

Vault binding: the note is `Tasks.md` at the vault root, reached through the
headless obsidian-vault MCP container (obsidian-local/scripts/vault_mcp.py), so
the Obsidian app need not run. Override with TASKS_QUEUE_PATH if it ever moves.

What counts as a task
---------------------
A list item (`- ...`, `* ...`, `1. ...`) that is not already `- [x]`, or a
standalone prose paragraph (the note's original format, before mark_done
started rewriting handled lines as `- [x] ...`).

A bare prose line directly under a list item is a *continuation* of that
item, not a task of its own -- long entries get soft-wrapped onto a second
physical line when typed in Obsidian. Treating one as a task is actively
harmful: it hands half a sentence to the worker as the whole job (an entry
about one repo got picked up as work scoped to a different repo), and
marking it splits the user's single item into two.

Calls the container over HTTP itself rather than through Claude's MCP tools,
so it works from an unattended context with no MCP session.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "obsidian-local", "scripts"))
from vault_mcp import read_note, write_note  # noqa: E402

TASKS_PATH = os.environ.get("TASKS_QUEUE_PATH", "Tasks.md")
# Test seam: a local file instead of the vault (skill-bench world cases).
TASKS_FILE = os.environ.get("TASKS_QUEUE_FILE")
_frontmatter = {}  # kept from the last read so a rewrite doesn't drop it


def get_content():
    global _frontmatter
    if TASKS_FILE:
        with open(TASKS_FILE) as f:
            text = f.read()
        m = re.match(r"(?s)(---\n.*?\n---\n)(.*)", text)
        _frontmatter, body = (m.group(1), m.group(2)) if m else ("", text)
        return body
    _frontmatter, body = read_note(TASKS_PATH)
    return body


def put_content(text):
    if TASKS_FILE:
        with open(TASKS_FILE, "w") as f:
            f.write(_frontmatter + text)
        return
    write_note(TASKS_PATH, text, frontmatter=_frontmatter)


def is_done(line):
    return re.match(r"^\s*-\s*\[[xX]\]", line) is not None


def is_list_item(line):
    return re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line) is not None


def undone_tasks(content):
    """Yield (line_index, line) for each undone task, in file order."""
    for i, line, kind in classify(content):
        if kind == "task":
            yield i, line


def classify(content):
    """Yield (line_index, line, kind) for every non-blank, non-heading line.

    kind is "task", "done", or "continuation".
    """
    prev_is_list_item = False
    for i, line in enumerate(content.splitlines()):
        s = line.strip()
        if not s or s.startswith("#"):
            prev_is_list_item = False
            continue
        if is_list_item(line):
            prev_is_list_item = True
            yield i, line, "done" if is_done(line) else "task"
            continue
        if prev_is_list_item:
            # Wrapped continuation of the item above, not a task. Callers
            # surface these: the rule is right for soft-wrapped entries but
            # would silently swallow a genuine bare-prose task typed under a
            # list item, so it must never fail invisibly.
            yield i, line, "continuation"
            continue
        yield i, line, "task"


def task_text(line):
    """The task's prose, with any list marker and checkbox stripped.

    `pick` emits this rather than the raw line: the text becomes the whole
    brief handed to the worker, and `- [ ] ` in the middle of a prompt is
    markup noise the worker has to see past. `mark` compares on this form
    too, so it accepts either the raw line or the cleaned text.
    """
    s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line.strip())
    return re.sub(r"^\[[ xX]?\]\s*", "", s).strip()


def mark_done(line):
    s = line.rstrip("\n")
    m = re.match(r"^(\s*-\s*\[)\s?(\])(.*)$", s)
    if m:
        return f"{m.group(1)}x{m.group(2)}{m.group(3)}"
    return f"- [x] {s.strip()}"


def cmd_pick():
    for _, line in undone_tasks(get_content()):
        print(task_text(line))
        return 0
    return 1


def cmd_list():
    content = get_content()
    found = False
    for i, line in undone_tasks(content):
        print(f"{i + 1}\t{task_text(line)}")
        found = True
    skipped = [(i, l) for i, l, k in classify(content) if k == "continuation"]
    if skipped:
        print(
            f"note: {len(skipped)} line(s) read as continuation text of the item "
            f"above, not as tasks. If one is meant to be its own task, give it a "
            f"'- ' prefix:",
            file=sys.stderr,
        )
        for i, line in skipped:
            print(f"  line {i + 1}: {line.strip()[:70]}", file=sys.stderr)
    return 0 if found else 1


SKILL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")


def news_tasks(path=SKILL_PATH):
    """The lower-priority tier: `### Title` + prompt entries under SKILL.md's
    `## News tasks` section. Read from the skill file, not the vault, so it
    works even when the vault container is down."""
    with open(path) as f:
        text = f.read()
    m = re.search(r"^## News tasks[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    tasks = []
    if m:
        for block in re.split(r"^### ", m.group(1), flags=re.M)[1:]:
            title, _, body = block.partition("\n")
            if title.strip() and body.strip():
                tasks.append({"title": title.strip(), "prompt": body.strip()})
    return tasks


def cmd_news():
    tasks = news_tasks()
    print(json.dumps(tasks, ensure_ascii=False, indent=1))
    return 0 if tasks else 1


# ── optimize tier ──────────────────────────────────────────────────────────
# One app under APPS_ROOT per task, least recently visited first. The worker
# classifies the app on its first visit; "skip" (toy, learning, data-only,
# abandoned) is remembered and never revisited. Delete an app's entry in the
# state file to have it reconsidered.

APPS_ROOT = os.environ.get("TASKS_QUEUE_APPS_ROOT", "/data/apps")
OPTIMIZE_STATE = os.path.expanduser(
    os.environ.get("TASKS_QUEUE_OPTIMIZE_STATE", "~/.claude/state/tasks-queue-optimize.json"))
# Never handed out: the repo hosting this queue and the engine that drains
# it -- an unattended worker rewriting its own scheduler mid-run is unsafe.
OPTIMIZE_EXCLUDE = {"lidaning-skills"}


def read_optimize_state():
    try:
        with open(OPTIMIZE_STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_optimize_state(state):
    os.makedirs(os.path.dirname(OPTIMIZE_STATE), exist_ok=True)
    tmp = OPTIMIZE_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, OPTIMIZE_STATE)


def optimize_prompt(path=SKILL_PATH):
    """The worker brief: the ```optimize-prompt block under SKILL.md's
    `## Optimize tasks`. Its {placeholders} are filled in by optimize_task."""
    with open(path) as f:
        text = f.read()
    m = re.search(r"^## Optimize tasks.*?^```optimize-prompt\n(.*?)^```", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def next_app(state=None):
    """(name, path) of the next app to optimize, or None. Git repos only: the
    result has to land as a reviewable commit, so a non-git directory is
    recorded as skipped without spending a session on it."""
    state = read_optimize_state() if state is None else state
    candidates = []
    for name in sorted(os.listdir(APPS_ROOT)):
        full = os.path.join(APPS_ROOT, name)
        if name.startswith(".") or name in OPTIMIZE_EXCLUDE or not os.path.isdir(full):
            continue
        entry = state.get(name, {})
        if entry.get("status") == "skip":
            continue
        if not os.path.isdir(os.path.join(full, ".git")):
            state[name] = {"status": "skip", "reason": "not a git repo", "ts": 0}
            write_optimize_state(state)
            continue
        candidates.append((entry.get("ts", 0), name, full))
    if not candidates:
        return None
    _, name, full = min(candidates)  # never visited (ts 0) first, then oldest
    return name, full


# PRs go only to repos owned by this GitHub account. Anything else (a fork
# whose origin is upstream, like jellyfin-web) keeps its work on a local
# branch: a PR there would land in someone else's public project.
GITHUB_OWNER = os.environ.get("TASKS_QUEUE_GITHUB_OWNER", "relidaning")
WORKTREE_ROOT = os.path.expanduser("~/.claude/state/claude-maxer-work/worktrees")


def _git(path, *args):
    import subprocess
    p = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=30)
    return p.stdout.strip() if p.returncode == 0 else ""


def repo_facts(path):
    """Base branch, GitHub slug and https remote of a repo. The remote is
    given as https even when origin is ssh: plain ssh doesn't go through
    this machine's proxy, https does (and gh supplies the credentials)."""
    base = _git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[-1]
    if not base:
        base = next((b for b in ("master", "main")
                     if _git(path, "rev-parse", "--verify", "--quiet", b)), "")
    url = _git(path, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", url)
    slug = f"{m[1]}/{m[2]}" if m else ""
    return {
        "base": base or "master",
        "repo": slug,
        "remote": f"https://github.com/{slug}.git" if slug else "",
        "pr": bool(m) and m[1].lower() == GITHUB_OWNER.lower(),
    }


def optimize_task():
    """{kind, app, path, base, branch, worktree, repo, remote, pr, prompt}
    for the next app, or None."""
    app = next_app()
    prompt = optimize_prompt()
    if not app or not prompt:
        return None
    name, full = app
    stamp = time.strftime("%Y%m%d-%H%M")
    t = {"kind": "optimize", "app": name, "path": full, **repo_facts(full),
         "branch": f"opt/{name}-{stamp}",
         "worktree": os.path.join(WORKTREE_ROOT, f"{name}-{stamp}")}
    if t["pr"]:
        pr_rule = (f"Push the branch with `git push {t['remote']} {t['branch']}` and open a "
                   f"PR with `gh pr create --repo {t['repo']} --base {t['base']} --head "
                   f"{t['branch']}`, the report as its body.")
    else:
        pr_rule = ("Do NOT push and do NOT open a PR: this repo's origin is not the user's "
                   f"own GitHub repo ({t['repo'] or 'no GitHub remote'}). Leave the commits on "
                   "the local branch.")
    fill = dict(t, pr_rule=pr_rule)
    t["prompt"] = re.sub(r"\{(\w+)\}", lambda m: str(fill.get(m[1], m[0])), prompt)
    return t


def cmd_optimize():
    t = optimize_task()
    if not t:
        return 1
    print(json.dumps(t, ensure_ascii=False))
    return 0


# ── the schedule ───────────────────────────────────────────────────────────
# `next` is the one place that decides what runs next. Callers only decide
# whether it fits: if a repo task (vault/optimize) is too big for what's left,
# they ask again with --small.

NEWS_DAY_PATH = os.path.expanduser(
    os.environ.get("TASKS_QUEUE_NEWS_DAY", "~/.claude/state/tasks-queue-news-day.json"))


def news_ran_today():
    try:
        with open(NEWS_DAY_PATH) as f:
            return json.load(f).get("date") == time.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return False


def cmd_news_ran():
    os.makedirs(os.path.dirname(NEWS_DAY_PATH), exist_ok=True)
    with open(NEWS_DAY_PATH, "w") as f:
        json.dump({"date": time.strftime("%Y-%m-%d")}, f)
    return 0


def next_task(skip=(), small=False):
    """1. an undone Tasks.md item, 2. today's first news batch, 3. an app to
    optimize, 4. news as filler. `skip`: vault task texts the caller won't
    run (already tried, or failed too often). `small`: only news fits."""
    if not small:
        try:
            for _, line in undone_tasks(get_content()):
                text = task_text(line)
                if text not in skip:
                    return {"kind": "vault", "text": text}
        except Exception as e:  # vault down: the other tiers still run
            print(f"note: Tasks.md unreadable ({e}); skipping tier 1", file=sys.stderr)
    if not news_ran_today():
        return {"kind": "news", "why": "daily"}
    if not small:
        t = optimize_task()
        if t:
            return t
    return {"kind": "news", "why": "filler"}


def cmd_next(args):
    skip, small, i = [], False, 0
    while i < len(args):
        if args[i] == "--small":
            small = True
        elif args[i] == "--skip" and i + 1 < len(args):
            i += 1
            skip.append(args[i])
        i += 1
    print(json.dumps(next_task(skip, small), ensure_ascii=False))
    return 0


def cmd_optimize_done(app, status, note=""):
    """Record a visit. status: skip | optimized | findings | failed."""
    state = read_optimize_state()
    entry = state.get(app, {})
    entry.update(status=status, reason=note[:200], ts=time.time(),
                 visits=entry.get("visits", 0) + 1)
    state[app] = entry
    write_optimize_state(state)
    return 0


def cmd_optimize_list():
    state = read_optimize_state()
    for name in sorted(state):
        e = state[name]
        print(f"{name}\t{e.get('status')}\tvisits={e.get('visits', 0)}\t{e.get('reason', '')}")
    return 0


def cmd_mark(target):
    lines = get_content().splitlines()
    for i, line in undone_tasks("\n".join(lines)):
        if task_text(line) == task_text(target):
            lines[i] = mark_done(line)
            put_content("\n".join(lines) + "\n")
            return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: tasks_queue.py next [--small] [--skip TEXT]...|news-ran|pick|list|"
              "mark <text>|news|optimize|optimize-done <app> <status> [note]|optimize-list",
              file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "next":
        sys.exit(cmd_next(sys.argv[2:]))
    elif sys.argv[1] == "news-ran":
        sys.exit(cmd_news_ran())
    elif sys.argv[1] == "pick":
        sys.exit(cmd_pick())
    elif sys.argv[1] == "list":
        sys.exit(cmd_list())
    elif sys.argv[1] == "news":
        sys.exit(cmd_news())
    elif sys.argv[1] == "optimize":
        sys.exit(cmd_optimize())
    elif sys.argv[1] == "optimize-list":
        sys.exit(cmd_optimize_list())
    elif sys.argv[1] == "optimize-done" and len(sys.argv) >= 4:
        sys.exit(cmd_optimize_done(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])))
    elif sys.argv[1] == "mark" and len(sys.argv) >= 3:
        sys.exit(cmd_mark(sys.argv[2]))
    else:
        print("unknown command", file=sys.stderr)
        sys.exit(2)
