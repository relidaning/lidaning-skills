#!/usr/bin/env python3
"""
claude-maxer usage gate.

Reads the usage snapshot written by fetch_usage_oauth.py (or, as a passive
fallback, cached by ~/.claude/scripts/statusline.py during an interactive
session). Exit 0 = safe to proceed. Exit 1 = skip this slot. Always prints
one line explaining the decision.

Pacing (added 2026-08-11, replacing a flat 95% threshold)
--------------------------------------------------------
Fires are hourly, and the 5h ceiling ramps with how far into the current
window we are, so the loop paces itself instead of emptying the window in
one burst. The old flat gate let a single fire take 5h usage from 27% to
100% in ~40 minutes; everything after that skipped for four hours, and the
window's remaining capacity was spent before the user was even awake.

    elapsed in window   ceiling   effect
    hour 0              0%        steady — no unattended work at all
    hour 1              25%
    hour 2              50%
    hour 3              75%
    hour 4              95%

"Steady" in hour 0 is deliberate: right after a reset the whole window is
still available, and the user's own interactive work should get first claim
on it. The loop starts drawing only once an hour has passed.

Because the caller re-checks this gate before every iteration, the ceiling
also bounds a single fire: iterations keep running until usage crosses the
current hour's line, then the loop stops. That is what keeps one fire to
roughly one 25% step rather than the whole window.

7d stays a flat 95% — it spans a week, so an hourly ramp means nothing to
it; it is a hard backstop, not a pacer.
"""
import json
import os
import sys
import time

SNAPSHOT_PATH = os.path.expanduser("~/.claude/state/usage_snapshot.json")
SEVEN_DAY_SKIP_PCT = 95
WINDOW_HOURS = 5

# Ceiling per elapsed whole hour of the current 5h window. Edit this to
# repace the loop — it is the whole policy. Index = elapsed hour.
RAMP_BY_HOUR = [0, 25, 50, 75, 95]

# Used when the window's start can't be derived (no resets_at — the API
# omits it for a window with no usage yet). Without this the loop could
# deadlock: hour 0's ceiling is 0, so if a never-opened window also read as
# hour 0 nothing would ever run, and nothing would ever open the window.
# The first ramp step is small enough to be a safe bootstrap.
BOOTSTRAP_CEILING_PCT = RAMP_BY_HOUR[1]


def five_hour_ceiling(five, now):
    """(ceiling_pct, human_reason) for the current point in the window."""
    resets_at = five.get("resets_at")
    if not resets_at:
        return BOOTSTRAP_CEILING_PCT, "window start unknown, bootstrap ceiling"
    elapsed_h = (now - (resets_at - WINDOW_HOURS * 3600)) / 3600.0
    elapsed_h = max(elapsed_h, 0.0)
    hour = min(int(elapsed_h), len(RAMP_BY_HOUR) - 1)
    return RAMP_BY_HOUR[hour], f"hour {hour} of the 5h window"


def main():
    if not os.path.exists(SNAPSHOT_PATH):
        print("SKIP: no usage snapshot found yet")
        return 1
    try:
        with open(SNAPSHOT_PATH) as f:
            snapshot = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"SKIP: usage snapshot unreadable ({e})")
        return 1

    now = time.time()
    age = now - snapshot.get("cached_at", 0)
    rate_limits = snapshot.get("rate_limits", {})
    five = rate_limits.get("five_hour") or {}
    seven = rate_limits.get("seven_day") or {}
    five_pct = five.get("used_percentage")
    seven_pct = seven.get("used_percentage")

    # Age is deliberately not a gate: headless work never refreshes the
    # snapshot on its own, so skipping on staleness would stop every loop
    # after ~30 minutes. The caller refreshes it before each iteration.
    if seven_pct is not None and seven_pct >= SEVEN_DAY_SKIP_PCT:
        print(f"SKIP: 7d usage at {seven_pct}% (>= {SEVEN_DAY_SKIP_PCT}%)")
        return 1

    if five_pct is None:
        print(f"PROCEED: no 5h figure in snapshot, 7d={seven_pct}% "
              f"(snapshot {int(age)}s old)")
        return 0

    ceiling, why = five_hour_ceiling(five, now)
    if five_pct >= ceiling:
        print(f"SKIP: 5h usage at {five_pct}% (>= {ceiling}% ceiling — {why})")
        return 1

    print(f"PROCEED: 5h={five_pct}% of {ceiling}% ceiling ({why}) "
          f"7d={seven_pct}% (snapshot {int(age)}s old)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
