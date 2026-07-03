#!/usr/bin/env bash
# claude-maxer: opportunistic long-term work, fired by local crontab 1h
# before each cloud keep-alive ping. Loops through work items — checking the
# cached usage gate before each one — until usage says skip, or a safety
# valve trips.
#
# Real per-iteration 5h/7d usage % is NOT observable here: that data only
# ever comes from the interactive statusLine hook (see statusline.py), which
# never fires in headless `claude -p` mode. So the cached snapshot stays
# frozen for the whole loop unless something else (an interactive session)
# updates it concurrently. The loop still re-checks it every iteration in
# case that happens, but the real backstops are the safety valves below.
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
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Truncate once per whole loop run (not per iteration — each iteration below
# appends, so this file covers every iteration of the current run only).
: > /tmp/claude-maxer-last-run.log

# Safety valves — real usage % can't be observed per-iteration (see above),
# so these bound the loop instead of a token/cost figure. Next cron fire is
# 5h after this one; MAX_MINUTES leaves headroom before then.
MAX_ITERATIONS=8
MAX_MINUTES=50

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  # $1=status $2=work_type $3=detail
  python3 -c "
import json, sys, time
print(json.dumps({'ts': time.time(), 'status': sys.argv[1], 'work_type': sys.argv[2], 'detail': sys.argv[3]}))
" "$1" "$2" "$3" >> "$LOG_FILE"
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
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Fetch https://huggingface.co/papers/trending, pick 2-3 trending papers not already covered in a note from earlier today, and for each fetch its abstract/summary content (via WebFetch on the paper page — do not attempt to download raw PDFs). Write a concise summary (what problem it solves, key idea, why it is notable) for each paper. Use the obsidian-local skill to create one note in the vault under a papers/digest folder consistent with this vault'"'"'s existing conventions (look at how skill-opt logs are organized under 0_dev/AI/ for the pattern), dated today, containing the summaries and links back to the paper pages. This does not touch the git repo, so no branch or PR is needed.'
      ;;
    news-digest)
      echo 'You are running unattended as part of the claude-maxer scheduled routine (iteration '"$2"' of this run). Fetch https://hacker-news.firebaseio.com/v0/topstories.json, take the first 10 story ids, fetch each via https://hacker-news.firebaseio.com/v0/item/{id}.json, and pick the 3 most interesting ones by score/discussion volume that are not already covered in a note from earlier today. For each: fetch the linked article via WebFetch (skip Ask HN/Show HN self-posts with no external link, or fall back to just the HN discussion) and write a concise summary (what it is, why it is notable, key discussion point from the top comments if relevant). Use the obsidian-local skill to create one note in the vault under a news/digest folder consistent with this vault'"'"'s existing conventions (look at how papers/digest notes are organized for the pattern), dated today, containing the summaries and links back to both the article and the HN discussion thread. This does not touch the git repo, so no branch or PR is needed.'
      ;;
  esac
}

TYPES=(skill-audit todo-triage dep-audit papers-digest news-digest)
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

  set +e
  CHECK_OUTPUT="$(python3 "$SKILL_DIR/check_usage.py")"
  CHECK_STATUS=$?
  set -e
  echo "[iter $ITER] $CHECK_OUTPUT"

  if [[ $CHECK_STATUS -ne 0 ]]; then
    log "skipped" "none" "$CHECK_OUTPUT"
    break
  fi

  WORK_TYPE="${TYPES[$RANDOM % ${#TYPES[@]}]}"
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
  RESULT_JSON="$(claude -p "$PROMPT" --model claude-sonnet-5 --output-format json --max-budget-usd 3 --dangerously-skip-permissions 2>>"$OUT_FILE")"
  CALL_STATUS=$?
  set -e
  echo "$RESULT_JSON" >> "$OUT_FILE"

  if [[ $CALL_STATUS -eq 0 ]]; then
    COST="$(echo "$RESULT_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total_cost_usd', 0))" 2>/dev/null || echo 0)"
    TOTAL_COST="$(python3 -c "print($TOTAL_COST + $COST)" 2>/dev/null || echo "$TOTAL_COST")"
    log "ran" "$WORK_TYPE" "iter=$ITER cost_usd=$COST cumulative_usd=$TOTAL_COST"
  else
    log "failed" "$WORK_TYPE" "iter=$ITER see $OUT_FILE"
  fi
done

echo "claude-maxer run finished: $((ITER - 1)) iteration(s), cumulative cost \$${TOTAL_COST}"
