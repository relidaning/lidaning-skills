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
| `english-practice` | project | **Every user message, regardless of language.** Always respond in English. Check grammar, phrasing, word choice before responding. |
| `coding-orchestrate` | project | New task, "what's next?", design decisions, session end (update SESSION.md). |
| `learning-instruct` | project | User wants to learn something, asks for a study plan, or types `/learning-instruct`. |
| `obsidian-local` | project | Local Obsidian vault via REST API MCP. Search, read, create, update, revise, delete notes. |
| `rag-chroma` | project | General-purpose RAG. Ingest documents (md, URLs, PDFs, Excel, Word), embed, store. Agent decides when to retrieve. Requires `docker compose -f skills/rag-chroma/docker-compose.yml up -d`. |

## Adding a skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and markdown body.
2. Add `metadata.yaml` with `name`, `description`, `scope`, `tags`.
3. Register in `registry.yaml`: `- name: <name>` / `path: skills/<name>`.
4. Install: `./install.sh <name> --global` or `--project`.

Skill frontmatter reference: `how-to-use-skills-in-claude-code.md`.

## Session tracking

The `coding-orchestrate` skill manages four files at repo root:
- **SESSION.md** — per-session logs with goals, what was done, current state, decisions
- **TODO.md** — discovered tasks, format `- [ ] item`
- **MEMORIES.md** — things the user explicitly asked to remember
- **README.md** — kept current with project concepts and features

These are skill-managed, not hand-edited. When in doubt, invoke `/coding-orchestrate`.
