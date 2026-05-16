---
name: telegram-channel
description: >
  Process inbound Telegram messages when the native --channels plugin
  drops them. Polls the Bot API, reads queued DMs, and replies through
  the Telegram MCP tools. Use in a /loop for continuous processing.
---

## Overview

The native `--channels plugin:telegram@claude-plugins-official` has a
known bug where inbound `notifications/claude/channel` events are
silently dropped. This skill works around it by polling the Telegram
Bot API directly and routing messages into Claude for response.

Two pieces:
- `scripts/fetch.sh` — polls `getUpdates` and appends new DMs to a
  queue file.
- `scripts/drain.sh` — atomically drains the queue for processing.

## Prerequisite: no `--channels` flag

The `--channels` flag (or `--dangerously-load-development-channels`)
starts a getUpdates poller inside the MCP plugin. Telegram only allows
one active getUpdates per bot token, so this blocks fetch.sh.

**Solution:** run Claude WITHOUT the `--channels` flag. The MCP tools
(`reply`, `react`, `edit_message`, `download_attachment`) work through
the normal `enabledPlugins` mechanism — `--channels` is only needed for
the (broken) inbound notification path, which this skill replaces.

To check for conflicts:
```bash
bash skills/telegram-channel/scripts/check-conflicts.sh
```

## When invoked

Do all of these steps, in order:

### Step 1: Collect new messages

Run:
```bash
bash skills/telegram-channel/scripts/fetch.sh
```
This appends any new Telegram DMs to `~/.claude/channels/telegram/queue.jsonl`.

If fetch.sh reports a 409 Conflict error, another process is holding the
getUpdates connection. Run `check-conflicts.sh` for guidance.

### Step 2: Drain the queue atomically

Run:
```bash
bash skills/telegram-channel/scripts/drain.sh
```

This moves the queue file aside and prints its contents. If the output
is empty, there are no messages — stop here.

### Step 3: Reply to each message

For each line of output from Step 2 (each line is a JSON object):

1. Parse the fields: `chat_id`, `message_id`, `user`, `text`, `ts`
2. Think of a helpful reply to the user's message. You are acting as
   Claude, so respond naturally as yourself in the same language the
   user wrote in.
3. Reply using the MCP tool:
   ```
   mcp__plugin_telegram_telegram__reply
     chat_id: <chat_id>
     text: <your response>
     reply_to: <message_id>
   ```
   Always set `reply_to` to the `message_id` so the user sees your
   reply threaded under their message.

If a reply fails for any message, re-append that message's JSON line
to the queue file so it is retried next time:
```bash
echo '<json-line>' >> ~/.claude/channels/telegram/queue.jsonl
```

## Continuous mode with /loop

For real-time-ish processing, invoke this skill on a loop:
```
/loop 30s /telegram-channel
```
Every 30 seconds, fetch.sh polls the API (with a 5-second long-poll
timeout) and this skill processes whatever arrived. Worst-case latency
is ~35 seconds.

## Access control

`fetch.sh` respects the DM policy in
`~/.claude/channels/telegram/access.json`. If `dmPolicy` is
`"allowlist"`, only users listed in `allowFrom` are queued. Otherwise
all DMs are accepted.
