#!/bin/bash
# Atomically drain the message queue.
# Moves the queue file to a temp location, then outputs its contents.
# This prevents message loss if fetch.sh appends during processing.

set -euo pipefail

QUEUE_FILE="$HOME/.claude/channels/telegram/queue.jsonl"

if [ ! -f "$QUEUE_FILE" ] || [ ! -s "$QUEUE_FILE" ]; then
  exit 0
fi

# Atomic drain: mv then read from the moved copy
tmpfile=$(mktemp)
mv "$QUEUE_FILE" "$tmpfile"
cat "$tmpfile"
rm -f "$tmpfile"
