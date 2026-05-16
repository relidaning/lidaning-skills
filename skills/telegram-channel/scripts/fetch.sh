#!/bin/bash
# Fetch new Telegram messages and append them to the queue file.
# Safe to call repeatedly — each message is queued exactly once.
# Drops any existing webhook/long-poll so we can get a clean connection.

set -euo pipefail

CHANNEL_DIR="$HOME/.claude/channels/telegram"
TOKEN_FILE="$CHANNEL_DIR/.env"
STATE_FILE="$CHANNEL_DIR/update_state"
QUEUE_FILE="$CHANNEL_DIR/queue.jsonl"
ACCESS_FILE="$CHANNEL_DIR/access.json"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "ERROR: Telegram bot token not found at $TOKEN_FILE" >&2
  echo "Run the telegram:configure skill first." >&2
  exit 1
fi

source "$TOKEN_FILE"

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN is empty" >&2
  exit 1
fi

API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

# Release any webhook so we can use getUpdates (webhooks and getUpdates are
# mutually exclusive). This does NOT drop active getUpdates connections — those
# are held by other MCP plugin instances and must be stopped separately.
curl -s --max-time 5 "${API}/deleteWebhook?drop_pending_updates=false" >/dev/null 2>&1 || true

# Determine DM policy and allowed users
ALLOW_ALL=true
ALLOW_FROM=""
if [ -f "$ACCESS_FILE" ]; then
  policy=$(jq -r '.dmPolicy // "open"' "$ACCESS_FILE")
  if [ "$policy" = "allowlist" ]; then
    ALLOW_ALL=false
    ALLOW_FROM=$(jq -r '.allowFrom[]? // empty' "$ACCESS_FILE")
  fi
fi

is_allowed() {
  local user_id="$1"
  if $ALLOW_ALL; then
    return 0
  fi
  for allowed in $ALLOW_FROM; do
    if [ "$user_id" = "$allowed" ]; then
      return 0
    fi
  done
  return 1
}

# Read last processed update_id
last_id=0
[ -f "$STATE_FILE" ] && last_id=$(cat "$STATE_FILE")

offset=$((last_id + 1))

# Fetch updates with long-poll timeout (retry on 409 Conflict from other pollers)
POLL_TIMEOUT="${TELEGRAM_POLL_TIMEOUT:-5}"
response=""
for attempt in 1 2 3; do
  response=$(curl -s --max-time $((POLL_TIMEOUT + 5)) \
    "${API}/getUpdates?offset=${offset}&timeout=${POLL_TIMEOUT}" 2>/dev/null || true)
  if [ -z "$response" ]; then
    exit 0
  fi
  # If another getUpdates is active (e.g. from --channels plugin), wait and retry
  if echo "$response" | jq -e '(.error_code == 409)' >/dev/null 2>&1; then
    [ $attempt -lt 3 ] && sleep 3
    continue
  fi
  break
done

if [ -z "$response" ]; then
  exit 0
fi

if ! echo "$response" | jq -e '.ok' >/dev/null 2>&1; then
  echo "ERROR: Telegram API error: $(echo "$response" | jq -r '.description // "unknown"')" >&2
  exit 1
fi

# Extract text messages, filter by access, append to queue
new_count=0
while IFS= read -r msg; do
  chat_id=$(echo "$msg" | jq -r '.message.chat.id | tostring')
  user_id=$(echo "$msg" | jq -r '.message.from.id | tostring')
  message_id=$(echo "$msg" | jq -r '.message.message_id | tostring')
  text=$(echo "$msg" | jq -r '.message.text // empty')
  date=$(echo "$msg" | jq -r '.message.date')

  [ -z "$text" ] && continue

  if ! is_allowed "$user_id"; then
    continue
  fi

  jq -nc --arg chat_id "$chat_id" \
         --arg message_id "$message_id" \
         --arg user "$user_id" \
         --arg text "$text" \
         --arg ts "$(date -d "@$date" -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{chat_id: $chat_id, message_id: $message_id, user: $user, text: $text, ts: $ts}' \
    >> "$QUEUE_FILE"

  new_count=$((new_count + 1))
done < <(echo "$response" | jq -c '.result[] | select(.message != null)')

max_id=$(echo "$response" | jq -r '.result[-1].update_id // empty')
if [ -n "$max_id" ]; then
  echo "$max_id" > "$STATE_FILE"
fi

if [ "$new_count" -gt 0 ]; then
  echo "Queued $new_count new message(s)" >&2
fi
