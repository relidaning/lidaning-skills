#!/usr/bin/env python3
"""Read/write the undone-task queue in the Obsidian vault's Tasks note.

This is a library + CLI only -- it owns no schedule. claude-maxer drives it
(`pick` -> do the work -> `mark`); see SKILL.md.

Vault binding: the note is `Tasks.md` at the vault root, reachable over the
Obsidian Local REST API. Override with VAULT_TASKS_PATH if it ever moves.

What counts as a task
---------------------
A list item (`- ...`, `* ...`, `1. ...`) that is not already `- [x]`, or a
standalone prose paragraph (the note's original format, before mark_done
started rewriting handled lines as `- [x] ...`).

A bare prose line directly under a list item is a *continuation* of that
item, not a task of its own -- long entries get soft-wrapped onto a second
physical line when typed in Obsidian. Treating one as a task is actively
harmful: it hands half a sentence to the worker as the whole job (an entry
about the claude-maxer skill got picked up as work scoped to a different
repo), and marking it splits the user's single item into two.

Talks to the REST API directly over HTTP rather than through the obsidian
MCP tools, so it works from an unattended context with no MCP session.
"""
import os
import re
import sys
import urllib.request

TASKS_PATH = os.environ.get("VAULT_TASKS_PATH", "Tasks.md")
DEFAULT_URL = "http://127.0.0.1:27123"


def _url():
    # OBSIDIAN_MCP_URL carries a trailing slash; naive appending yields a
    # `//vault/...` path the REST API 404s on.
    base = (os.environ.get("OBSIDIAN_MCP_URL") or DEFAULT_URL).rstrip("/")
    return f"{base}/vault/{TASKS_PATH}"


def _request(method, extra_headers=None, body=None):
    req = urllib.request.Request(_url(), method=method, data=body)
    req.add_header("Authorization", f"Bearer {os.environ['OBSIDIAN_MCP_TOKEN']}")
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    # Bypass the proxy: 127.0.0.1 traffic would otherwise be swallowed by
    # http_proxy/https_proxy, which cron-side callers must set.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=15) as resp:
        return resp.read()


def get_content():
    return _request("GET").decode("utf-8")


def put_content(text):
    _request("PUT", {"Content-Type": "text/markdown"}, text.encode("utf-8"))


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
        print("usage: vault_tasks.py pick|list|mark <text>", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "pick":
        sys.exit(cmd_pick())
    elif sys.argv[1] == "list":
        sys.exit(cmd_list())
    elif sys.argv[1] == "mark" and len(sys.argv) >= 3:
        sys.exit(cmd_mark(sys.argv[2]))
    else:
        print("unknown command", file=sys.stderr)
        sys.exit(2)
