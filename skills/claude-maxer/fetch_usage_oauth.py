#!/usr/bin/env python3
"""
claude-maxer OAuth usage fetcher (primary, headless-safe).

Queries https://api.anthropic.com/api/oauth/usage with the Claude Code
OAuth token from ~/.claude/.credentials.json — the same endpoint the CLI's
/usage screen uses. Returns real 5h + 7d utilization with reset times, no
browser, no login, no Cloudflare (discovered 2026-07-03; this obsoletes the
older belief that usage was only visible to the interactive statusLine
hook, and supersedes fetch_usage_web.py, which Cloudflare's human check
blocks anyway).

Writes ~/.claude/state/usage_snapshot.json in the exact shape
check_usage.py / statusline.py already use, tagged "source": "oauth-api".

Token freshness: fully self-sufficient. Access tokens live ~8h; when the
cached one is expired (or the API answers 401/403), this script refreshes
it with the refreshToken via the same public OAuth flow the CLI uses
(console.anthropic.com/v1/oauth/token, Claude Code's client_id) and writes
the rotated tokens back to the credentials file atomically — exactly what
Claude Code does on its own runs, so the two stay interchangeable. No
interactive session is ever required; a bare crontab entry can run this
forever.

Vault heartbeat: --vault-log appends one line per fetch to a daily note in
the Obsidian vault (0_dev/AI/claude-maxer/usage-log-YYYY-MM-DD.md) via the
Local REST API — a visible proof the background loop is alive. Token comes
from $OBSIDIAN_MCP_TOKEN or is parsed out of ~/.zshrc.local (cron has no
shell env). Vault errors (Obsidian closed, plugin off) only warn; the
snapshot fetch still succeeds.

Usage: fetch_usage_oauth.py [--no-write] [--raw] [--refresh] [--vault-log]
Exit codes: 0 = snapshot written (or data printed), 2 = auth problem
(unreadable credentials / refresh rejected), 1 = anything else.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
SNAPSHOT_PATH = os.path.expanduser("~/.claude/state/usage_snapshot.json")
USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
TOKEN_ENDPOINT = "https://console.anthropic.com/v1/oauth/token"
# Claude Code's public OAuth client id (same one the CLI itself sends).
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
DEFAULT_PROXY = "http://127.0.0.1:10808"
# Refresh when the token has less than this long to live. Kept small so a
# concurrently running interactive session (which also refreshes) rarely
# races us on the one-time-use refresh token.
EXPIRY_MARGIN_S = 120


def refresh_access_token(opener, creds):
    """Rotate the OAuth tokens in-place; returns the new access token.

    Persists rotated tokens back to CREDENTIALS_PATH immediately — the
    refresh token is single-use, so losing the new one would break every
    future refresh including Claude Code's own.
    """
    oauth = creds["claudeAiOauth"]
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": oauth["refreshToken"],
            "client_id": CLIENT_ID,
        }).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "claude-maxer/fetch_usage_oauth"},
    )
    with opener.open(req, timeout=30) as r:
        tok = json.load(r)
    oauth["accessToken"] = tok["access_token"]
    if tok.get("refresh_token"):
        oauth["refreshToken"] = tok["refresh_token"]
    oauth["expiresAt"] = int((time.time() + tok.get("expires_in", 28800)) * 1000)
    tmp = CREDENTIALS_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f)
    os.replace(tmp, CREDENTIALS_PATH)
    return oauth["accessToken"]


def iso_to_epoch(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _fmt_reset(epoch, long=False):
    if not epoch:
        return "?"
    return time.strftime("%m-%d %H:%M" if long else "%H:%M", time.localtime(epoch))


def vault_log(rate_limits, scoped):
    """Append a one-line usage entry to today's vault heartbeat note.

    Talks straight to Obsidian's Local REST API on localhost — deliberately
    bypasses the proxy (ProxyHandler({})), which would otherwise swallow
    127.0.0.1 traffic. Raises on failure; caller treats it as a warning.
    """
    token = os.environ.get("OBSIDIAN_MCP_TOKEN")
    if not token:
        # cron has no shell env; the token only lives in ~/.zshrc.local.
        with open(os.path.expanduser("~/.zshrc.local")) as f:
            for line in f:
                if "OBSIDIAN_MCP_TOKEN=" in line:
                    token = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not token:
        raise RuntimeError("no OBSIDIAN_MCP_TOKEN in env or ~/.zshrc.local")
    base = (os.environ.get("OBSIDIAN_MCP_URL") or "http://127.0.0.1:27123").rstrip("/")

    note_path = f"0_dev/AI/claude-maxer/usage-log-{time.strftime('%Y-%m-%d')}.md"
    url = f"{base}/vault/{urllib.request.quote(note_path)}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "text/markdown"}

    five = rate_limits.get("five_hour", {})
    seven = rate_limits.get("seven_day", {})
    line = (f"- {time.strftime('%H:%M')} — 5h **{five.get('used_percentage', '?')}%**"
            f" (resets {_fmt_reset(five.get('resets_at'))})"
            f" · 7d **{seven.get('used_percentage', '?')}%**"
            f" (resets {_fmt_reset(seven.get('resets_at'), long=True)})")
    line += "".join(f" · {s['model'] or s['kind']} 7d **{s['percent']}%**" for s in scoped)
    line += "\n"

    # New day = new note: give it a heading before the first entry.
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=10):
            exists = True
    except urllib.error.HTTPError as e:
        e.read()
        if e.code != 404:
            raise
        exists = False
    if not exists:
        line = (f"# claude-maxer usage log — {time.strftime('%Y-%m-%d')}\n\n"
                f"Appended by `fetch_usage_oauth.py --vault-log` "
                f"(cron, every 15 min).\n\n{line}")

    # POST /vault/<path> appends (Local REST API v4+), creating if missing.
    req = urllib.request.Request(url, data=line.encode(), headers=headers, method="POST")
    with opener.open(req, timeout=10) as r:
        r.read()
    return note_path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--no-write", action="store_true",
                    help="print parsed result, don't touch the snapshot")
    ap.add_argument("--raw", action="store_true",
                    help="dump the full API response to stderr")
    ap.add_argument("--refresh", action="store_true",
                    help="force an OAuth token refresh before fetching")
    ap.add_argument("--vault-log", action="store_true",
                    help="append this fetch to a daily Obsidian heartbeat note")
    args = ap.parse_args()

    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)
        token = creds.get("claudeAiOauth", {}).get("accessToken")
    except (OSError, json.JSONDecodeError) as e:
        print(f"AUTH: cannot read credentials ({e})", file=sys.stderr)
        return 2
    if not token:
        print("AUTH: no accessToken in credentials file", file=sys.stderr)
        return 2

    # api.anthropic.com is only reachable through the local proxy on this
    # box (same requirement as claude -p; see run_maxer_work.sh).
    proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy") or DEFAULT_PROXY
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))

    expires_at = creds["claudeAiOauth"].get("expiresAt", 0) / 1000
    if args.refresh or time.time() > expires_at - EXPIRY_MARGIN_S:
        try:
            token = refresh_access_token(opener, creds)
            print(f"refreshed OAuth token (new expiry in "
                  f"{(creds['claudeAiOauth']['expiresAt']/1000 - time.time())/3600:.1f}h)",
                  file=sys.stderr)
        except Exception as e:
            print(f"AUTH: token refresh failed ({e}) — falling back to the "
                  f"stored access token", file=sys.stderr)

    def get_usage(tok):
        req = urllib.request.Request(USAGE_ENDPOINT, headers={
            "Authorization": f"Bearer {tok}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "claude-maxer/fetch_usage_oauth",
        })
        with opener.open(req, timeout=30) as r:
            return json.load(r)

    try:
        try:
            data = get_usage(token)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403):
                raise
            # Stored token rejected — refresh once and retry.
            e.read()
            token = refresh_access_token(opener, creds)
            data = get_usage(token)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        if e.code in (401, 403):
            print(f"AUTH: HTTP {e.code} even after token refresh: {body}",
                  file=sys.stderr)
            return 2
        print(f"ERROR: HTTP {e.code} from usage endpoint: {body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: usage request failed ({e}); proxy={proxy}", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(data, indent=2), file=sys.stderr)

    rate_limits = {}
    for key in ("five_hour", "seven_day"):
        win = data.get(key) or {}
        if win.get("utilization") is None:
            continue
        rate_limits[key] = {
            "used_percentage": round(win["utilization"]),
            "resets_at": iso_to_epoch(win.get("resets_at")),
        }
    if not rate_limits:
        print("ERROR: response had no five_hour/seven_day utilization "
              "(schema change? re-run with --raw)", file=sys.stderr)
        return 1

    # Model-scoped weekly limits (e.g. per-model caps) ride along for
    # visibility; check_usage.py ignores them.
    scoped = [
        {"kind": lim.get("kind"), "percent": lim.get("percent"),
         "resets_at": iso_to_epoch(lim.get("resets_at")),
         "model": ((lim.get("scope") or {}).get("model") or {}).get("display_name")}
        for lim in (data.get("limits") or []) if lim.get("kind") == "weekly_scoped"
    ]

    if args.no_write:
        print(json.dumps({"rate_limits": rate_limits, "scoped_limits": scoped}, indent=2))
        return 0

    snapshot = {"rate_limits": rate_limits, "cached_at": time.time(),
                "source": "oauth-api"}
    if scoped:
        snapshot["scoped_limits"] = scoped
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    tmp = SNAPSHOT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snapshot, f)
    os.replace(tmp, SNAPSHOT_PATH)

    if args.vault_log:
        try:
            note = vault_log(rate_limits, scoped)
            print(f"vault heartbeat appended to {note}", file=sys.stderr)
        except Exception as e:
            # Obsidian closed / plugin off / token moved — never fail the fetch.
            print(f"WARN: vault log skipped ({e})", file=sys.stderr)

    parts = [f"{lbl}={rate_limits[key]['used_percentage']}%"
             for key, lbl in [("five_hour", "5h"), ("seven_day", "7d")]
             if key in rate_limits]
    parts += [f"{s['model'] or s['kind']}(7d)={s['percent']}%" for s in scoped]
    print("OK: snapshot updated from oauth api — " + " ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
