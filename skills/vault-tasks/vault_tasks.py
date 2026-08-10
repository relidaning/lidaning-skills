#!/usr/bin/env python3
"""Pick the next undone task from the vault's Tasks.md, or mark one done.

Undone = any non-empty, non-heading line that doesn't already start with
"- [x]" (case-insensitive). Plain prose lines (the file's current format)
count as undone; "- [ ] ..." checkbox lines do too, for forward
compatibility if tasks get added in that format later.

Talks to the Obsidian Local REST API directly over HTTP (not the MCP tool)
so it works unattended from cron.
"""
import os
import re
import sys
import urllib.request

TASKS_PATH = "Tasks.md"


def _url():
    base = os.environ["OBSIDIAN_MCP_URL"].rstrip("/")
    return f"{base}/vault/{TASKS_PATH}"


def _request(method, extra_headers=None, body=None):
    req = urllib.request.Request(_url(), method=method, data=body)
    req.add_header("Authorization", f"Bearer {os.environ['OBSIDIAN_MCP_TOKEN']}")
    for k, v in (extra_headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def get_content():
    return _request("GET").decode("utf-8")


def put_content(text):
    _request("PUT", {"Content-Type": "text/markdown"}, text.encode("utf-8"))


def is_done(line):
    return re.match(r"^\s*-\s*\[[xX]\]", line) is not None


def is_task_line(line):
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    return not is_done(line)


def mark_done(line):
    s = line.rstrip("\n")
    m = re.match(r"^(\s*-\s*\[)\s?(\])(.*)$", s)
    if m:
        return f"{m.group(1)}x{m.group(2)}{m.group(3)}"
    return f"- [x] {s.strip()}"


def cmd_pick():
    for line in get_content().splitlines():
        if is_task_line(line):
            print(line.strip())
            return 0
    return 1


def cmd_mark(target):
    lines = get_content().splitlines()
    for i, line in enumerate(lines):
        if is_task_line(line) and line.strip() == target.strip():
            lines[i] = mark_done(line)
            put_content("\n".join(lines) + "\n")
            return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: vault_tasks.py pick|mark <text>", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "pick":
        sys.exit(cmd_pick())
    elif sys.argv[1] == "mark" and len(sys.argv) >= 3:
        sys.exit(cmd_mark(sys.argv[2]))
    else:
        print("unknown command", file=sys.stderr)
        sys.exit(2)
