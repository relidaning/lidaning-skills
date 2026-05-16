# Sessions

## 2026-05-16 — Create learning-instruct skill

### Goal
Build a structured learning tutor skill that takes a user's goal, researches
and decomposes it, teaches step by step, and evaluates mastery.

### What we did
- Created skills/learning-instruct/ with SKILL.md, metadata.yaml
- Designed 4-phase workflow: Goal → Compose → Teach → Evaluate
- Created supporting files: goal.md, compositions.md, steps.md
- Registered in registry.yaml and installed with --project
- Updated CLAUDE.md skills table
- Updated SESSION.md

### Current state
Skill installed and ready. No active learning track yet — GOAL.md will be
created on first invocation.

### Decisions
- `.learning-instruct/` directory at project root (dot-prefix, like `.claude/`)
- 3–8 compositions per topic (from research-backed sources)
- Mastery-based progression — don't advance until user demonstrates understanding
- Evaluation scores: mastered / proficient / needs work (not numeric)
- Project-scoped — tied to the repo, not global

## 2026-05-16 — Add MEMORIES.md to coding-orchestrate

### Goal
Add a fourth managed file (MEMORIES.md) to coding-orchestrate for recording
things the user explicitly asks to remember.

### What we did
- Created memories.md supporting file in skill directory
- Updated SKILL.md to include MEMORIES.md as a fourth managed file
- Updated metadata.yaml description
- Updated CLAUDE.md references
- Updated SESSION.md with this entry

### Current state
MEMORIES.md integrated into coding-orchestrate. No MEMORIES.md file at
project root yet — it gets created on first memory entry.

### Decisions
- Explicit requests only — don't infer memories from conversation
- Same pattern as other managed files: supporting .md in skill dir, actual
  file at project root, linked from SKILL.md
- MEMORIES.md is project-scoped (not Claude auto-memory) — for explicit
  "remember this" requests from the user

## 2026-05-15 — Build lidaning-skills set

### Goal
Create a reusable personal skills set for Claude Code — English practice and
coding orchestration.

### What we did
- Designed skill architecture: canonical SKILL.md + metadata.yaml + install.sh
- Created english-practice skill (global, corrects non-native English)
- Created coding-orchestrate skill (project, sessions/TODOs/README management)
- Built install.sh with symlink-based installation
- Iterated on English practice format — emoji-based correction blocks
- Learned Claude Code conventions: uppercase SKILL.md, directory structure,
  description-based auto-invocation, live reload
- Refactored to Claude Code-only (dropped multi-agent targets/)
- Added supporting files to coding-orchestrate (sessions.md, todos.md, readme.md)
- Renamed skill.md → SKILL.md in source to match Claude Code convention
- Set up .lidaning/ tracking for this project

### Current state
Both skills installed and working. English practice active this session.
Coding-orchestrate just invoked, tracking files being created.

### Decisions
- Symlinks over copies — single source of truth, live edits
- SKILL.md uppercase — matches Claude Code convention
- metadata.yaml separate from SKILL.md — install.sh metadata, not agent-facing
- Supporting files as separate .md files in skill directory — follows official
  Claude Code pattern, loaded on demand via relative links
- Dropped multi-agent support for now — focus on Claude Code first
- Dropped CLAUDE.md concatenation — skills work via description-based
  auto-invocation, not forced injection

## 2026-05-16 — Telegram channel workaround skill

### Goal
The native `--channels plugin:telegram@claude-plugins-official` has a
known bug (GitHub #36503) where inbound notifications are silently
dropped. Build a skill that polls the Telegram Bot API directly and
routes messages into Claude for response.

### What we did
- Created telegram-channel skill under skills/telegram-channel/
- Built fetch.sh — polls getUpdates with access control from access.json,
  appends new DMs as JSONL to a queue file
- Built drain.sh — atomically drains the queue for processing
- Built check-conflicts.sh — diagnoses getUpdates conflicts from
  other --channels sessions
- Added retry logic for 409 Conflict when another poller is active
- Key design choice: user must NOT use --channels flag (it holds the
  getUpdates connection); MCP tools load fine through enabledPlugins
- Fixed set -e footgun: conditional at end of script tripped exit 1
- Installed skill into project
- Tested: fetch.sh successfully polls getUpdates when bun process
  holding the connection is killed

### Current state
fetch.sh verified working. End-to-end test (inbound message → queue →
Claude reply via MCP) pending — needs fresh Claude session without
--channels so MCP tools are available alongside our getUpdates polling.

### Decisions
- Polling over webhook: no public URL available, getUpdates is simpler
- fetch.sh uses deleteWebhook then getUpdates — cleanest handoff
- drain.sh for atomic queue ops — prevents message loss on concurrent writes
- 5s long-poll timeout — balances latency vs. blocking manual invocations
- Project-scoped (not global) — tied to this bot token / access config
- No persistent daemon — fetch.sh called on each skill invocation; pair
  with /loop for continuous mode
