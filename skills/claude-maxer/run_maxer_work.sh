#!/usr/bin/env bash
# claude-maxer: opportunistic long-term work, fired by local crontab 1h
# before each cloud keep-alive ping. Loops through work items — checking the
# cached usage gate before each one — until usage says skip, or a safety
# valve trips.
#
# Usage observability: fetch_usage_oauth.py (api.anthropic.com/api/oauth/
# usage with the Claude Code OAuth token) refreshes the usage snapshot
# before each iteration's gate check, so the loop CAN see its own
# consumption. The token rotates automatically whenever `claude` runs —
# including this loop's own `claude -p` calls — so it stays fresh in
# practice. If the fetch fails anyway (expired token, network), the loop
# falls back to the old behavior: the snapshot stays frozen at whatever the
# last interactive statusLine render cached, and the safety valves below
# are the real backstop.
#
# Usage: run_maxer_work.sh [--dry-run]

set -euo pipefail

# cron on this box doesn't set $HOME at all. Must be set before PATH below,
# which also depends on $HOME.
export HOME="/home/shake"

# cron runs with a minimal PATH (just /usr/bin:/bin etc.) that doesn't
# include claude, git, gh, npm, or node — all of which the headless session
# needs (claude itself, plus git/gh/npm as tools it shells out to for the
# branch+PR/dep-audit work). Prepend the same dirs the interactive shell uses.
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.nvm/versions/node/v24.15.0/bin:$HOME/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

# Root cause of every real cron failure so far ("403 Failed to authenticate"):
# this network reaches api.anthropic.com only via a local proxy
# (v2rayN/xray listening on 127.0.0.1:10808 — confirmed with `ss -tlnp`), set
# via http_proxy/https_proxy in the interactive shell's env. Cron doesn't
# inherit shell env at all, so requests went out unproxied and got a 403
# instead of a network error. Reproduced by clearing env entirely
# (`env -i ... claude -p`) — identical error; adding these two vars back
# fixed it. If the proxy client/port ever changes, update this.
export http_proxy="http://127.0.0.1:10808"
export https_proxy="http://127.0.0.1:10808"

REPO_DIR="/data/apps/lidaning-skills"
SKILL_DIR="$REPO_DIR/skills/claude-maxer"
LOG_FILE="$HOME/.claude/state/claude-maxer.log.jsonl"
# Read by fetch_usage_oauth.py --vault-log so the vault's usage note says
# what each quota jump bought, instead of just how big it was.
ACTIVITY_FILE="$HOME/.claude/state/maxer_activity.json"
MODEL="claude-sonnet-5"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Truncate once per whole loop run (not per iteration — each iteration below
# appends, so this file covers every iteration of the current run only).
: > /tmp/claude-maxer-last-run.log

# Safety valves — real usage % can't be observed per-iteration (see above),
# so these bound the loop instead of a token/cost figure. Next cron fire is
# 5h after this one; MAX_MINUTES leaves headroom before then.
#
# All four are env-overridable so a human can run one bounded iteration by
# hand to test a change without spending a whole window on it, e.g.
#   MAX_ITERATIONS=1 MAXER_BUDGET_USD=1 MAXER_FORCE_TYPE=news-digest ./run_maxer_work.sh
# Cron sets none of them and gets the defaults.
MAX_ITERATIONS="${MAX_ITERATIONS:-8}"
MAX_MINUTES="${MAX_MINUTES:-50}"
BUDGET_USD="${MAXER_BUDGET_USD:-3}"
# Forcing a type bypasses the weighted draw AND its daily cap — it is a
# testing hook, so it must be able to re-run a type that already hit its cap.
FORCE_TYPE="${MAXER_FORCE_TYPE:-}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  # $1=status $2=work_type $3=detail
  python3 -c "
import json, sys, time
print(json.dumps({'ts': time.time(), 'status': sys.argv[1], 'work_type': sys.argv[2], 'detail': sys.argv[3]}))
" "$1" "$2" "$3" >> "$LOG_FILE"
}

record_activity() {
  # $1=note — one short phrase for the vault usage note's trailing comment.
  python3 -c "
import json, sys, time
json.dump({'ts': time.time(), 'model': sys.argv[1], 'note': sys.argv[2]}, open(sys.argv[3], 'w'))
" "$MODEL" "$1" "$ACTIVITY_FILE"
}

# Times this work type already produced output today, from the run log.
ran_today() {
  python3 -c "
import datetime, json, sys
want, path = sys.argv[1], sys.argv[2]
today, n = datetime.date.today(), 0
try:
    with open(path) as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if (e.get('status') == 'ran' and e.get('work_type') == want
                    and datetime.date.fromtimestamp(e['ts']) == today):
                n += 1
except FileNotFoundError:
    pass
print(n)
" "$1" "$LOG_FILE"
}

# Weighted pick, skipping anything that has hit its daily cap.
pick_work_type() {
  local pool=() t cap
  for t in "${TYPES[@]}"; do
    (( ${WEIGHTS[$t]} == 0 )) && continue   # weight 0 = disabled
    cap="${DAILY_CAP[$t]:-0}"
    if (( cap > 0 )) && (( $(ran_today "$t") >= cap )); then
      continue
    fi
    for ((i = 0; i < ${WEIGHTS[$t]}; i++)); do pool+=("$t"); done
  done
  (( ${#pool[@]} == 0 )) && return 1
  printf '%s\n' "${pool[$RANDOM % ${#pool[@]}]}"
}

build_prompt() {
  case "$1" in
    skill-audit)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Run a SkillOpt-style quality pass: for each skill under skills/*, score Trigger Clarity (0-5) and Body Quality (0-5) against the criteria already documented in this repo'"'"'s CLAUDE.md. For any skill scoring below 8/10 total, make at most 4 bounded edits to its SKILL.md to raise the score, then re-score to confirm the edit actually helped (revert if it did not). If every skill already scores >= 8/10, say so and do nothing else. If you made edits: create a new branch named claude-maxer/skill-audit-'"$3"', commit the changes with a message summarizing before/after scores, and open a draft PR via gh describing what changed and why. Do not push to master directly.'
      ;;
    todo-triage)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Read .claude/TODO.md. Pick 1-2 items that are small, unambiguous, and safe to implement without a product decision (skip anything vague, risky, or that touches secrets/credentials/deployment, and skip anything already addressed by an earlier iteration in this same run — check open branches/PRs named claude-maxer/todo-triage-* first). Implement them, run any existing lint/tests for the touched area, and check them off in TODO.md. If you find and implement at least one safe item: create a new branch named claude-maxer/todo-triage-'"$3"', commit, and open a draft PR via gh referencing which TODO items were addressed. If no safe item remains, say so and do nothing else. Do not push to master directly.'
      ;;
    dep-audit)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). For each Node subproject under skills/ that has a package.json (e.g. skills/model-switch, skills/rag-chroma), run `npm outdated` and `npm audit` (read-only, do not upgrade or auto-fix anything). Compare findings against the most recent report at docs/claude-maxer-dependency-report-*.md if one exists. Only if there is something new to report (newly outdated packages, new vulnerabilities) or no prior report exists: write/update a concise markdown report at docs/claude-maxer-dependency-report-'"$3"'.md, create a new branch named claude-maxer/dep-audit-'"$3"', commit it, and open a draft PR via gh with the summary in the PR description. If there is nothing new versus the last report, say so and do nothing else. Do not push to master directly, and never run npm install/update/audit fix.'
      ;;
    papers-digest)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Fetch https://huggingface.co/papers/trending, pick 2-3 trending papers, and for each fetch its abstract/summary content (via WebFetch on the paper page — do not attempt to download raw PDFs). Write a concise summary (what problem it solves, key idea, why it is notable) for each paper. Use the obsidian-local skill to write the note at exactly claude-maxer/digest/papers-'"$(date +%F)"'.md — that literal path, including the .md extension. FIRST read that note if it exists: if it does, pick only papers it does not already cover and APPEND them to it; never create a -2/-3 suffixed duplicate, and never write an extensionless file. Head the appended section with the current time only (e.g. "## 16:38"); never put an iteration number or fire label in a heading or in the prose — the note is per-day, not per-fire, and the label is wrong the moment another fire appends. If every trending paper is already covered, say so and write nothing. Link back to the paper pages. This does not touch the git repo, so no branch or PR is needed.'
      ;;
    news-digest)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Fetch https://hacker-news.firebaseio.com/v0/topstories.json, take the first 10 story ids, fetch each via https://hacker-news.firebaseio.com/v0/item/{id}.json, and pick the 3 most interesting ones by score/discussion volume. Note: fan-out loops over ids captured from a previous command must not use `for id in $ids` — the Bash tool runs zsh, which does not word-split unquoted parameter expansions, so that builds one URL containing spaces and every fetch comes back empty; use `${=ids}`, a zsh array, or do the fan-out in python3. For each story: fetch the linked article via WebFetch (skip Ask HN/Show HN self-posts with no external link, or fall back to just the HN discussion) and write a concise summary (what it is, why it is notable, key discussion point from the top comments if relevant). Use the obsidian-local skill to write the note at exactly claude-maxer/digest/news-'"$(date +%F)"'.md — that literal path, including the .md extension. FIRST read that note if it exists: if it does, pick only stories it does not already cover and APPEND them to it; never create a -2/-3 suffixed duplicate, and never write an extensionless file. Head the appended section with the current time only (e.g. "## 16:38"); never put an iteration number or fire label in a heading or in the prose — the note is per-day, not per-fire, and the label is wrong the moment another fire appends. If every top story is already covered, say so and write nothing. Link back to both the article and the HN discussion thread. This does not touch the git repo, so no branch or PR is needed.'
      ;;
  esac
}

TYPES=(skill-audit todo-triage dep-audit papers-digest news-digest)

# Work mix retuned 2026-08-11 from the vault's own record,
# claude-maxer/usage/2026-08-11.md: the 06:00 window went 27% -> 100% in
# roughly 40 minutes, and what the user could actually point at afterwards
# was a handful of digest notes — several of them same-day duplicates of
# each other, because uniform selection kept re-drawing the digest types and
# every fire re-derived the day's digest from scratch. Digests are cheap to
# produce and near-worthless on repeat, so they are now both down-weighted
# and hard-capped per day; repo work carries the load. The point was never to
# spend less quota — it is to stop paying digest prices for duplicate output.
#
# 2026-08-11, later the same day: both digests DISABLED outright (weight 0)
# at the user's request. Down-weighting was not enough — the output itself
# was judged not worth any quota, duplicate or not. They stay in TYPES and
# keep their prompts so MAXER_FORCE_TYPE can still run one by hand, and
# re-enabling is a one-character change. Weight 0 = never drawn.
declare -A WEIGHTS=(
  [skill-audit]=3 [todo-triage]=3 [dep-audit]=2 [papers-digest]=0 [news-digest]=0
)
# 0 = uncapped. Digests cap at one note per day each; the append-don't-
# duplicate instruction in build_prompt is the second half of this fix.
declare -A DAILY_CAP=(
  [skill-audit]=0 [todo-triage]=0 [dep-audit]=0 [papers-digest]=1 [news-digest]=1
)

START_TS=$(date +%s)
ITER=0
TOTAL_COST="0"

while true; do
  ITER=$((ITER + 1))

  if (( ITER > MAX_ITERATIONS )); then
    log "stopped" "none" "iteration cap reached ($MAX_ITERATIONS)"
    break
  fi
  ELAPSED=$(( $(date +%s) - START_TS ))
  if (( ELAPSED > MAX_MINUTES * 60 )); then
    log "stopped" "none" "wall-clock cap reached (${MAX_MINUTES}m)"
    break
  fi

  # Best-effort snapshot refresh from the OAuth usage endpoint (exit 2 =
  # token expired — any `claude` run refreshes it; anything nonzero = keep
  # the cached statusline snapshot).
  set +e
  FETCH_OUTPUT="$(timeout 60 python3 "$SKILL_DIR/fetch_usage_oauth.py" 2>&1 | tail -1)"
  FETCH_STATUS=$?
  set -e
  echo "[iter $ITER] usage-fetch exit=$FETCH_STATUS: $FETCH_OUTPUT"

  set +e
  CHECK_OUTPUT="$(python3 "$SKILL_DIR/check_usage.py")"
  CHECK_STATUS=$?
  set -e
  echo "[iter $ITER] $CHECK_OUTPUT"

  if [[ $CHECK_STATUS -ne 0 ]]; then
    log "skipped" "none" "$CHECK_OUTPUT"
    break
  fi

  if [[ -n "$FORCE_TYPE" ]]; then
    WORK_TYPE="$FORCE_TYPE"
  elif ! WORK_TYPE="$(pick_work_type)"; then
    log "stopped" "none" "every work type has hit its daily cap"
    break
  fi
  RUN_ID="$(date +%Y%m%d-%H%M%S)-i${ITER}"
  PROMPT="$(build_prompt "$WORK_TYPE" "$ITER" "$RUN_ID")"

  if $DRY_RUN; then
    echo "[dry-run iter $ITER] would run work_type=$WORK_TYPE"
    echo "$PROMPT"
    continue
  fi

  cd "$REPO_DIR"
  OUT_FILE="/tmp/claude-maxer-last-run.log"
  echo "=== iter $ITER ($WORK_TYPE) $(date -Iseconds) ===" >> "$OUT_FILE"
  set +e
  RESULT_JSON="$(claude -p "$PROMPT" --model "$MODEL" --output-format json --max-budget-usd "$BUDGET_USD" --dangerously-skip-permissions 2>>"$OUT_FILE")"
  CALL_STATUS=$?
  set -e
  echo "$RESULT_JSON" >> "$OUT_FILE"

  if [[ $CALL_STATUS -eq 0 ]]; then
    COST="$(echo "$RESULT_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total_cost_usd', 0))" 2>/dev/null || echo 0)"
    TOTAL_COST="$(python3 -c "print($TOTAL_COST + $COST)" 2>/dev/null || echo "$TOTAL_COST")"
    log "ran" "$WORK_TYPE" "iter=$ITER cost_usd=$COST cumulative_usd=$TOTAL_COST"
    # Round for the vault note only; the log keeps full precision.
    COST_FMT="$(printf '%.2f' "$COST" 2>/dev/null || echo "$COST")"
    record_activity "$WORK_TYPE (\$$COST_FMT)"
  else
    log "failed" "$WORK_TYPE" "iter=$ITER see $OUT_FILE"
    record_activity "$WORK_TYPE failed"
  fi
done

echo "claude-maxer run finished: $((ITER - 1)) iteration(s), cumulative cost \$${TOTAL_COST}"
