#!/usr/bin/env python3
"""
claude-maxer usage gate.

Reads the usage snapshot cached by ~/.claude/scripts/statusline.py (updated
on every statusLine render during an interactive session on this machine —
there is no API/tool that exposes Claude Pro/Max 5h/7d usage directly, so
this cache is the only source of truth available).

The snapshot is used regardless of age — headless work (this script's own
caller included) never refreshes it, so gating on staleness would make a
loop stop after ~30 minutes no matter what. The cached percentage is treated
as still valid until something actually pushes it over the threshold.

Exit 0 = safe to proceed with long-term work. Exit 1 = skip this slot.
Always prints one line explaining the decision.
"""
import json
import os
import sys
import time

SNAPSHOT_PATH = os.path.expanduser("~/.claude/state/usage_snapshot.json")
SKIP_THRESHOLD_PCT = 95


def main():
    if not os.path.exists(SNAPSHOT_PATH):
        print("SKIP: no usage snapshot found yet (no interactive session has run on this machine)")
        return 1

    try:
        with open(SNAPSHOT_PATH) as f:
            snapshot = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"SKIP: usage snapshot unreadable ({e})")
        return 1

    age = time.time() - snapshot.get("cached_at", 0)
    rate_limits = snapshot.get("rate_limits", {})
    for key, label in [("five_hour", "5h"), ("seven_day", "7d")]:
        pct = (rate_limits.get(key) or {}).get("used_percentage")
        if pct is None:
            continue
        if pct >= SKIP_THRESHOLD_PCT:
            print(f"SKIP: {label} usage at {pct}% (>= {SKIP_THRESHOLD_PCT}% threshold)")
            return 1

    five_h = (rate_limits.get("five_hour") or {}).get("used_percentage", "?")
    seven_d = (rate_limits.get("seven_day") or {}).get("used_percentage", "?")
    print(f"PROCEED: 5h={five_h}% 7d={seven_d}% (snapshot {int(age)}s old)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
