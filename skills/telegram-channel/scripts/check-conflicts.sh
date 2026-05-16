#!/bin/bash
# Stop any running Telegram channel pollers (from --channels plugin).
# Run this before starting the telegram-channel skill to release the
# getUpdates connection so fetch.sh can take over.

set -euo pipefail

echo "Looking for processes holding Telegram getUpdates..."

# Find bun processes running the telegram plugin
found=false
while IFS= read -r line; do
  pid=$(echo "$line" | awk '{print $1}')
  cmd=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
  echo "  Found: PID $pid — $cmd"
  found=true
done < <(ps aux | grep -E 'bun.*telegram|telegram.*bun' | grep -v grep || true)

# Also find claude processes with --channels
while IFS= read -r line; do
  pid=$(echo "$line" | awk '{print $2}')
  args=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
  if echo "$args" | grep -qE '\-\-channels|\-\-dangerously-load-development-channels'; then
    echo "  Claude PID $pid using --channels flag"
    found=true
  fi
done < <(ps aux | grep 'claude' | grep -v grep || true)

if ! $found; then
  echo "No conflicting pollers found. You're good to go."
  exit 0
fi

echo ""
echo "These processes are holding the getUpdates connection."
echo "To use telegram-channel skill, close those Claude sessions"
echo "and restart WITHOUT the --channels flag."
echo ""
echo "The MCP tools (reply, react, edit_message) work through the"
echo "regular plugin loader — --channels is NOT needed for them."
