#!/usr/bin/env python3
"""
claude-maxer web usage fetcher (FALLBACK — superseded by fetch_usage_oauth.py).

Cloudflare's human-verification loop blocks the --login flow (observed
2026-07-03), and the OAuth usage endpoint turned out to provide the same
data with no browser at all. Kept only in case that endpoint goes away.

Opens https://claude.ai/new#settings/usage with Playwright (persistent
profile, so login survives across runs) and extracts the Current session
(5h) and Weekly (7d) usage limits. Writes them to
~/.claude/state/usage_snapshot.json in the exact shape check_usage.py /
statusline.py already use — this is the headless-safe replacement for the
"snapshot only refreshes during interactive sessions" limitation.

Data sources, in order of preference:
 1. Network capture — claude.ai fetches a JSON usage payload when the
    settings/usage view opens; we listen for any JSON response whose URL
    mentions usage/rate_limit and mine it for utilization + reset fields.
 2. DOM scrape — regex over the rendered settings page text ("Current
    session ... X% ... Resets ...", weekly section) as fallback.

First-time setup (needs a display; do it once):
    python3 fetch_usage_web.py --login
Log in to claude.ai in the opened window, then close it (or Ctrl-C here).
After that, unattended runs work headlessly:
    python3 fetch_usage_web.py [--debug] [--no-write]

Proxy: claude.ai is only reachable through the local proxy on this box.
Uses $https_proxy if set, else defaults to http://127.0.0.1:10808.

Exit codes: 0 = snapshot written (or --no-write with data found),
2 = not logged in (run --login), 1 = anything else.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

PROFILE_DIR = os.path.expanduser("~/.claude/state/claude-web-profile")
SNAPSHOT_PATH = os.path.expanduser("~/.claude/state/usage_snapshot.json")
USAGE_URL = "https://claude.ai/new#settings/usage"
DEFAULT_PROXY = "http://127.0.0.1:10808"

# claude.ai API responses worth mining for usage numbers.
CAPTURE_URL_RE = re.compile(r"usage|rate_limit|overage|quota", re.I)


def log(msg):
    print(msg, file=sys.stderr)


def parse_iso(ts):
    """ISO-8601 string or epoch number -> epoch seconds, else None."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # Heuristic: ms vs s
        return ts / 1000 if ts > 4e10 else ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def find_windows_in_json(obj, out):
    """Recursively mine a captured JSON payload for 5h/7d usage windows.

    Handles both the statusline-style shape ({"five_hour": {...}}) and the
    claude.ai web shape (objects carrying utilization/used percentage plus a
    resets_at/reset time, keyed or labeled with session/weekly wording).
    """
    if isinstance(obj, dict):
        for key in ("five_hour", "seven_day"):
            win = obj.get(key)
            if isinstance(win, dict):
                pct = win.get("used_percentage", win.get("utilization"))
                if pct is not None:
                    out[key] = {
                        "used_percentage": round(float(pct)),
                        "resets_at": parse_iso(win.get("resets_at") or win.get("reset_at")),
                    }
        # Generic shape: {"utilization": 33, "resets_at": ...} under a key
        # that tells us which window it is.
        for k, v in obj.items():
            if isinstance(v, dict):
                pct = v.get("utilization", v.get("used_percentage"))
                reset = v.get("resets_at") or v.get("reset_at") or v.get("resets")
                if pct is not None and reset is not None:
                    kl = k.lower()
                    if re.search(r"five|5.?h|session", kl):
                        out.setdefault("five_hour", {
                            "used_percentage": round(float(pct)),
                            "resets_at": parse_iso(reset),
                        })
                    elif re.search(r"seven|7.?d|week", kl):
                        out.setdefault("seven_day", {
                            "used_percentage": round(float(pct)),
                            "resets_at": parse_iso(reset),
                        })
            find_windows_in_json(v, out)
    elif isinstance(obj, list):
        for item in obj:
            find_windows_in_json(item, out)


def scrape_dom_text(text):
    """Fallback: pull percentages out of the rendered settings page text.

    Expected wording (en): a "Current session" block and a weekly block,
    each with an "N% used" figure. Reset times in the DOM are humanized
    ("Resets 3:00 PM"), too fuzzy to convert reliably — left as None.
    """
    out = {}
    session = re.search(r"Current session.{0,300}?(\d{1,3})\s*%", text, re.S | re.I)
    weekly = re.search(r"(?:Weekly|Current week|All models).{0,300}?(\d{1,3})\s*%", text, re.S | re.I)
    if session:
        out["five_hour"] = {"used_percentage": int(session.group(1)), "resets_at": None}
    if weekly:
        out["seven_day"] = {"used_percentage": int(weekly.group(1)), "resets_at": None}
    return out


def write_snapshot(windows):
    """Merge into usage_snapshot.json, keeping fields we couldn't fetch."""
    existing = {}
    try:
        with open(SNAPSHOT_PATH) as f:
            existing = json.load(f).get("rate_limits", {})
    except (OSError, json.JSONDecodeError):
        pass
    merged = dict(existing)
    for key, win in windows.items():
        if win.get("resets_at") is None and isinstance(existing.get(key), dict):
            # DOM scrape has no epoch reset time; keep the old one.
            win = {**win, "resets_at": existing[key].get("resets_at")}
        merged[key] = win
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    tmp = SNAPSHOT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"rate_limits": merged, "cached_at": time.time(), "source": "web"}, f)
    os.replace(tmp, SNAPSHOT_PATH)
    return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--login", action="store_true",
                    help="open a visible browser to log in to claude.ai once")
    ap.add_argument("--debug", action="store_true",
                    help="dump captured API payloads + page text to stderr")
    ap.add_argument("--no-write", action="store_true",
                    help="print what would be written, don't touch the snapshot")
    ap.add_argument("--timeout", type=int, default=45,
                    help="seconds to wait for usage data (default 45)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy") or DEFAULT_PROXY
    captured = []  # (url, parsed-json)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=not args.login,
            proxy={"server": proxy},
            viewport={"width": 1280, "height": 900},
            # A real-browser UA avoids Cloudflare treating headless Chromium
            # as a bot on claude.ai.
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            if not CAPTURE_URL_RE.search(resp.url):
                return
            try:
                if "json" in (resp.headers.get("content-type") or ""):
                    captured.append((resp.url, resp.json()))
            except Exception:
                pass

        page.on("response", on_response)

        try:
            page.goto(USAGE_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            log(f"ERROR: navigation failed ({e}); proxy={proxy}")
            ctx.close()
            return 1

        if args.login:
            log("Browser open — log in to claude.ai, wait for the usage page, "
                "then close the window.")
            try:
                page.wait_for_event("close", timeout=600_000)
            except Exception:
                pass
            ctx.close()
            log("Login profile saved. Headless runs should work now.")
            return 0

        # Give the SPA time to auth-redirect and fire its usage requests.
        windows = {}
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            page.wait_for_timeout(1500)
            url = page.url
            if "login" in url or "/magic-link" in url or "auth" in url.split("claude.ai")[-1][:8]:
                log("NOT_LOGGED_IN: session expired or never created. Run: "
                    f"python3 {os.path.abspath(__file__)} --login")
                ctx.close()
                return 2
            for _, payload in captured:
                find_windows_in_json(payload, windows)
            if "five_hour" in windows and "seven_day" in windows:
                break

        body_text = ""
        try:
            body_text = page.inner_text("body", timeout=5_000)
        except Exception:
            pass

        if args.debug:
            for url, payload in captured:
                log(f"--- captured {url}\n{json.dumps(payload, indent=2)[:4000]}")
            log(f"--- page url: {page.url}\n--- page text:\n{body_text[:4000]}")

        ctx.close()

    # Login screens render text too — don't let the DOM fallback misread one.
    if re.search(r"log in|sign in|continue with google", body_text[:2000], re.I) and not windows:
        log("NOT_LOGGED_IN: landed on the login page. Run: "
            f"python3 {os.path.abspath(__file__)} --login")
        return 2

    if not windows:
        windows = scrape_dom_text(body_text)
    else:
        # Fill any window the API capture missed from the DOM.
        for k, v in scrape_dom_text(body_text).items():
            windows.setdefault(k, v)

    if not windows:
        log("ERROR: no usage data found (API capture and DOM scrape both empty). "
            "Re-run with --debug to inspect.")
        return 1

    if args.no_write:
        print(json.dumps({"rate_limits": windows}, indent=2))
        return 0

    merged = write_snapshot(windows)
    summary = " ".join(
        f"{lbl}={merged.get(key, {}).get('used_percentage', '?')}%"
        for key, lbl in [("five_hour", "5h"), ("seven_day", "7d")]
    )
    print(f"OK: snapshot updated from web — {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
