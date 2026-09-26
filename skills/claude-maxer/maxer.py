#!/usr/bin/env python3
"""
claude-maxer: pin the 5h usage window to fixed times, then fill each window
to ~95% during its last hour with news-digest work written to the vault.

Window plan (all times machine-local, CST)
------------------------------------------
24h is not a multiple of 5h, so five back-to-back windows can't repeat on
the same clock times every day. The plan is four pinned windows plus one 4h
buffer:

    03:00-08:00   08:00-13:00   13:00-18:00   18:00-23:00   | 23:00-03:00 buffer

`open` (cron at 03/08/13/18) starts each window with a one-word Haiku ping.
If the previous window is still open because it started a few minutes late,
`open` waits for that reset and pings right after it. Nothing is pinged at
23:00. A window opened then would run until 04:00 and swallow the 03:00
window. The buffer is left for interactive use. If you work in it and open a
window yourself, the 03:00 pin is lost for that day, and the 08:00 pin
restores the schedule.

`run` (cron every 15 min) does nothing unless a window is open and resets in
10-65 minutes, so it acts once, in each window's last hour. Then it
starts digest tasks until one of these stops it:

  * 5h usage reaches TARGET_5H_PCT (95%)
  * 7d usage reaches its pace line (see weekly_line); the weekly cap is the
    real bound, since filling every window to 95% would spend the whole week
    in about three days
  * the window is within STOP_MARGIN_MIN of resetting. Every task is also
    killed before the reset: a request after the reset would open an
    off-schedule window and break the pin.

The window isn't tied to the clock plan, so a window you opened yourself
also gets filled in its last hour.

Vault output (only written when tasks actually run):
  claude-maxer/news/YYYY-MM-DD.md            the day's digests, one section per task
  claude-maxer/log/YYYY-MM-DD.md             one block per run, one line per task
Checks, skips and pings go only to ~/.claude/state/claude-maxer.log.jsonl.

Usage: maxer.py run [--dry-run] | open [--dry-run] | status
Cron runs these through run_maxer_work.sh, which sets HOME/PATH/proxy.
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

STATE_DIR = os.path.expanduser("~/.claude/state")
SNAPSHOT_PATH = os.path.join(STATE_DIR, "usage_snapshot.json")
LOG_PATH = os.path.join(STATE_DIR, "claude-maxer.log.jsonl")
ROTATION_PATH = os.path.join(STATE_DIR, "claude-maxer-rotation.json")
WORK_DIR = os.path.join(STATE_DIR, "claude-maxer-work")  # neutral cwd: no repo CLAUDE.md
RUN_LOCK = "/tmp/claude-maxer-run.lock"
# Shared with the */15 fetch cron: fetch_usage_oauth.py rotates a single-use
# OAuth refresh token, so two fetchers must never overlap.
FETCH_LOCK = "/tmp/claude-usage-fetch.lock"

TARGET_5H_PCT = float(os.environ.get("MAXER_TARGET_5H", 95))
WEEKLY_TARGET_PCT = float(os.environ.get("MAXER_WEEKLY_TARGET", 95))
WEEKLY_SLACK_PCT = float(os.environ.get("MAXER_WEEKLY_SLACK", 5))
ENTER_MAX_MIN = 65      # start only when the window resets within this many minutes...
STOP_MARGIN_MIN = 10    # ...and stop starting tasks this close to the reset
KILL_MARGIN_S = 120     # hard-kill running tasks this long before the reset
TASK_TIMEOUT_S = 25 * 60
OVERSHOOT_PCT = 3        # a batch may end at most this far above TARGET_5H_PCT
CONCURRENCY = int(os.environ.get("MAXER_CONCURRENCY", 3))
DEFAULT_TASK_PCT = 4.0  # first guess at 5h% per task; replaced by measurement
SNAPSHOT_MAX_AGE_S = 20 * 60
OPEN_WAIT_MAX_S = 20 * 60  # opener waits for a reset at most this long

MODEL = os.environ.get("MAXER_MODEL", "claude-opus-5-5")
PING_MODEL = "claude-haiku-4-5-20251001"
BUDGET_USD = os.environ.get("MAXER_BUDGET_USD", "5")

# (slug, note title, description for the prompt). Rotated across runs so
# every domain gets its turn; see next_domains().
DOMAINS = [
    ("ai", "AI", "AI and machine learning: model releases, research, AI companies, policy"),
    ("big-tech", "Big tech", "big tech: Apple, Google, Microsoft, Meta, Amazon, Nvidia, Tesla and peers: products, business, regulation"),
    ("world", "World", "breaking world news: politics, conflicts, disasters, major international events"),
    ("security", "Security", "cybersecurity: major breaches, actively exploited vulnerabilities, security research"),
    ("dev", "Dev & open source", "software development and open source: languages, frameworks, dev tools, notable releases"),
    ("science", "Science & space", "science and space: research breakthroughs, space missions, health and medicine"),
    ("markets", "Markets", "markets and economy: central banks, major market moves, macro data, big deals"),
    ("china-tech", "China tech", "China technology and economy: Chinese tech companies, AI labs, chips, policy"),
]


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
    """Returns dict with five_pct, five_reset, seven_pct, seven_reset, age."""
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


def weekly_line(u, now):
    """Highest 7d% allowed right now: the pace needed to land on
    WEEKLY_TARGET_PCT at the weekly reset, plus a little slack."""
    if not u["seven_reset"]:
        return WEEKLY_TARGET_PCT
    week = 7 * 86400
    elapsed = min(max(now - (u["seven_reset"] - week), 0), week) / week
    return min(WEEKLY_TARGET_PCT, WEEKLY_TARGET_PCT * elapsed + WEEKLY_SLACK_PCT)


def gate(u, now):
    """(ok, reason) for starting more work right now."""
    if u["age"] > SNAPSHOT_MAX_AGE_S:
        return False, f"usage snapshot is {int(u['age'] / 60)} min old"
    if not window_open(u, now):
        return False, "no 5h window open (starting work now would open an off-schedule window)"
    left_min = (u["five_reset"] - now) / 60
    if left_min > ENTER_MAX_MIN:
        return False, f"window resets {hm(u['five_reset'])}, {left_min:.0f} min away (not the last hour yet)"
    if left_min <= STOP_MARGIN_MIN:
        return False, f"window resets {hm(u['five_reset'])}, only {left_min:.0f} min left"
    if u["five_pct"] is not None and u["five_pct"] >= TARGET_5H_PCT:
        return False, f"5h at {u['five_pct']}%, target {TARGET_5H_PCT:.0f}% reached"
    line = weekly_line(u, now)
    if u["seven_pct"] is not None and u["seven_pct"] >= line:
        return False, f"7d at {u['seven_pct']}%, over its pace line {line:.0f}%"
    return True, "ok"


# ── rotation ───────────────────────────────────────────────────────────────

def next_domains(n):
    try:
        with open(ROTATION_PATH) as f:
            idx = json.load(f).get("next", 0)
    except (OSError, ValueError):
        idx = 0
    picked = [DOMAINS[(idx + i) % len(DOMAINS)] for i in range(n)]
    with open(ROTATION_PATH, "w") as f:
        json.dump({"next": (idx + n) % len(DOMAINS)}, f)
    return picked


# ── vault ──────────────────────────────────────────────────────────────
# Plain file appends into the vault folder rather than the obsidian-vault MCP
# container: on 2026-09-27 that container's sessions hung mid-run (healthz
# fine, every call timing out) and a finished digest was lost. The vault is a
# local folder that Nextcloud syncs, so a file write is all a note needs.

VAULT_ROOT = os.environ.get("OBSIDIAN_VAULT_PATH", "/data/nextcloud_client/obsidian/lidaning")


def note_path(day):
    return f"claude-maxer/news/{day}.md"


def covered_titles(path):
    """Titles already in today's note (any topic), so a later task doesn't
    repeat them."""
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


# ── the digest task ────────────────────────────────────────────────────────

PRACTICE_BLOCK = re.compile(r"=== English Practice ===.*?=== English Practice ===\s*", re.S)


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


def build_prompt(desc, already):
    skip = ""
    if already:
        skip = ("\n\nThese stories are already in today's note. Do not repeat them, "
                "even from a different outlet:\n" + "\n".join(f"- {t}" for t in already))
    return (
        "You are an unattended news collector. Your reply is saved verbatim into a notes "
        "vault, so reply with nothing except the list described below: no preamble, "
        "no closing remarks, no English-practice block.\n\n"
        f"Topic: {desc}.\n\n"
        "Find the 10 most important stories on this topic from the last 48 hours, newest "
        "first. Aim for all 10: run at least six different WebSearch queries (sub-topics, "
        "companies, regions) and open articles with WebFetch to confirm details. Prefer "
        "primary or reputable sources. Only include a story if you actually saw its URL in a "
        "search result or opened it; never invent a URL, a date, or a detail. List fewer "
        "than 10 only if searching really turns up nothing more.\n\n"
        "Format, exactly, one entry per story:\n"
        "1. **[Headline in your own words](https://source.url)** · Outlet · YYYY-MM-DD\n"
        "   One or two sentences: what happened and why it matters."
        f"{skip}"
    )


def run_task(slug, title, desc, day, deadline):
    path = note_path(day)
    already = covered_titles(path)
    cmd = [
        "claude", "-p", build_prompt(desc, already),
        "--model", MODEL,
        "--output-format", "json",
        "--max-budget-usd", BUDGET_USD,
        # Only web tools exist in the session: nothing to write with, no
        # Skill call for the global english-practice rule to spend turns on,
        # and --strict-mcp-config (with no config) loads no MCP servers.
        "--tools", "WebSearch,WebFetch",
        "--allowedTools", "WebSearch", "WebFetch",
        "--strict-mcp-config",
    ]
    started = time.time()
    timeout = max(60, min(TASK_TIMEOUT_S, deadline - started))
    res = {"slug": slug, "path": path, "start": started, "items": 0, "cost": 0.0}
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
    text = PRACTICE_BLOCK.sub("", out.get("result") or "").strip()
    entries = re.findall(r"^\s*\d+\.\s+\*\*\[.+?\]\(https?://", text, re.M)
    if out.get("is_error") or not entries:
        res["error"] = (out.get("subtype") or "no linked entries in reply")[:120]
        return res
    text = list_only(text)
    heading = f"# News — {day}\n\nCollected by claude-maxer, one section per topic run.\n"
    try:
        vault_append(path, f"\n## {hm(started)} · {title}\n\n{text}\n", heading=heading)
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
        return 0
    if dry_run:
        print(f"DRY RUN: would start tasks — 5h {u['five_pct']}%, resets {hm(u['five_reset'])}, "
              f"7d {u['seven_pct']}% (line {weekly_line(u, time.time()):.0f}%)")
        print("next domains:", [d[0] for d in DOMAINS])
        print(build_prompt(DOMAINS[0][2], [])[:900])
        return 0

    day = datetime.now().strftime("%Y-%m-%d")
    log_note = f"claude-maxer/log/{day}.md"
    reset = u["five_reset"]
    deadline = reset - KILL_MARGIN_S
    start_five = u["five_pct"]
    vault_append(
        log_note,
        f"\n### {hm(time.time())} run — window resets {hm(reset)}, "
        f"5h {u['five_pct']}%, 7d {u['seven_pct']}% (pace line {weekly_line(u, time.time()):.0f}%) "
        f"· [[claude-maxer/news/{day}|news {day}]]\n\n",
        heading=f"# claude-maxer log — {day}\n\nWritten only when claude-maxer runs tasks. "
                f"News lands in claude-maxer/news/.\n",
    )
    log("run_start", five=u["five_pct"], seven=u["seven_pct"], resets=reset)

    per_task = DEFAULT_TASK_PCT
    total_cost, tasks_done = 0.0, 0
    while True:
        now = time.time()
        ok, why = gate(u, now)
        if not ok:
            break
        # Never start a task expected to push 5h past the target plus a small
        # margin: 100% locks the user out until the reset.
        room = TARGET_5H_PCT + OVERSHOOT_PCT - (u["five_pct"] or 0)
        n = min(CONCURRENCY, int(room // max(per_task, 0.5)))
        if n < 1:
            why = f"5h at {u['five_pct']}%, one more task (~{per_task:.0f}pp) would overshoot"
            break
        batch = next_domains(n)
        before = u["five_pct"] or 0
        with ThreadPoolExecutor(max_workers=n) as ex:
            results = list(ex.map(lambda d: run_task(*d, day, deadline), batch))
        u = fresh_usage()
        delta = (u["five_pct"] or 0) - before
        if delta > 0:
            per_task = delta / n
        for r in results:
            total_cost += r["cost"]
            if r.get("error"):
                line = f"- {hm(r['start'])}–{hm(r['end'])} · {r['slug']} · failed: {r['error']} · ${r['cost']:.2f}\n"
            else:
                tasks_done += 1
                line = (f"- {hm(r['start'])}–{hm(r['end'])} · {r['slug']} · {r['items']} stories "
                        f"· ${r['cost']:.2f}\n")
            vault_append(log_note, line)
            log("task", **{k: v for k, v in r.items() if k != "path"})
        vault_append(log_note, f"- 5h now {u['five_pct']}% (batch of {n}: +{delta:.0f}pp)\n")

    vault_append(log_note, f"- stopped: {why}. {tasks_done} digests, ${total_cost:.2f}, "
                           f"5h {start_five}% → {u['five_pct']}%\n")
    log("run_end", reason=why, tasks=tasks_done, cost=round(total_cost, 2),
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
    u = fresh_usage()
    now = time.time()
    if window_open(u, now):
        wait = u["five_reset"] - now
        if wait > OPEN_WAIT_MAX_S:
            log("open_skip", reason=f"a window is already open until {hm(u['five_reset'])}")
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
    return 0 if rc == 0 else 1


def cmd_status():
    u = fresh_usage()
    now = time.time()
    ok, why = gate(u, now)
    print(f"5h {u['five_pct']}%  resets {hm(u['five_reset']) if u['five_reset'] else '-'}"
          f"  | 7d {u['seven_pct']}%  pace line {weekly_line(u, now):.0f}%")
    print("would run now" if ok else f"would skip: {why}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="claude-maxer")
    ap.add_argument("command", choices=["run", "open", "status"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.command == "run":
        return cmd_run(a.dry_run)
    if a.command == "open":
        return cmd_open(a.dry_run)
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
