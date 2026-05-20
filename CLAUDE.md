# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Personal Claude Code skills repo. Each skill in `skills/<name>/` is a standalone
[Agent Skills](https://agentskills.io) directory with a `SKILL.md` entrypoint.
`install.sh` symlinks skills into `~/.claude/skills/` or `.claude/skills/` so
Claude Code discovers them. `registry.yaml` indexes all skills.

No build step, no lint, no tests. The repo is pure markdown + bash scripts.

## Skills

These skills auto-invoke — you don't need `/slash` commands:

| Skill | Scope | Auto-trigger |
|---|---|---|
| `english-practice` | global | **Every user message in English.** Check grammar, phrasing, word choice before responding. |
| `coding-orchestrate` | project | New task, "what's next?", design decisions, session end (update SESSION.md). |
| `telegram-channel` | project | Process Telegram inbound queue via `/loop telegram-channel`. |
| `learning-instruct` | project | User wants to learn something, asks for a study plan, or types `/learning-instruct`. |

## Adding a skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and markdown body.
2. Add `metadata.yaml` with `name`, `description`, `scope`, `tags`.
3. Register in `registry.yaml`: `- name: <name>` / `path: skills/<name>`.
4. Install: `./install.sh <name> --global` or `--project`.

Skill frontmatter reference: `how-to-use-skills-in-claude-code.md`.

## telegram-channel architecture

This skill bypasses the broken native `notifications/claude/channel` path. Instead of
relying on the MCP server's internal poller to deliver inbound messages, it polls
the Bot API directly:

- `scripts/fetch.sh` — calls `getUpdates`, filters by `access.json` allowlist, appends
  new DMs as JSONL to `~/.claude/channels/telegram/queue.jsonl`
- `scripts/drain.sh` — atomically moves the queue file and prints contents for processing
- `scripts/check-conflicts.sh` — diagnoses other processes holding the getUpdates connection

**Conflict constraint:** Telegram allows only one `getUpdates` consumer per bot token.
The MCP server's internal `bot.start()` holds this connection. To use `telegram-channel`,
the MCP server's poller must be stopped — but the MCP tools (`reply`, `react`, etc.)
live in the same process. This is an unresolved tension (TODO.md).

## Session tracking

The `coding-orchestrate` skill manages four files at repo root:
- **SESSION.md** — per-session logs with goals, what was done, current state, decisions
- **TODO.md** — discovered tasks, format `- [ ] item`
- **MEMORIES.md** — things the user explicitly asked to remember
- **README.md** — kept current with project concepts and features

These are skill-managed, not hand-edited. When in doubt, invoke `/coding-orchestrate`.
