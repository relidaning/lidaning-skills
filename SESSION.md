# Sessions

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
