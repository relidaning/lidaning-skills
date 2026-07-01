# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Personal Claude Code skills repo. Each skill in `skills/<name>/` is a standalone
[Agent Skills](https://agentskills.io) directory with a `SKILL.md` entrypoint.
`install.sh` symlinks skills into `~/.claude/skills/` or `.claude/skills/` so
Claude Code discovers them. `registry.yaml` indexes all skills.

## Skills

These skills auto-invoke — you don't need `/slash` commands:

| Skill                | Scope   | Auto-trigger                                                                                                                                                                                |
| -------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `english-practice`   | project | **Every user message, regardless of language.** Always respond in English. Check grammar, phrasing, word choice before responding.                                                          |
| `coding-orchestrate` | project | New task, "what's next?", design decisions, session end (update SESSION.md).                                                                                                                |
| `learning-instruct`  | project | User wants to learn something, asks for a study plan, or types `/learning-instruct`.                                                                                                        |
| `obsidian-local`     | project | Local Obsidian vault via REST API MCP. Search, read, create, update, revise, delete notes.                                                                                                  |
| `rag-chroma`         | project | General-purpose RAG. Ingest documents (md, URLs, PDFs, Excel, Word), embed, store. Agent decides when to retrieve. Requires `docker compose -f skills/rag-chroma/docker-compose.yml up -d`. |

## Adding a skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and markdown body.
2. Add `metadata.yaml` with `name`, `description`, `scope`, `tags`.
3. Register in `registry.yaml`: `- name: <name>` / `path: skills/<name>`.
4. Install: `./install.sh <name> --global` or `--project`.

Skill frontmatter reference: `how-to-use-skills-in-claude-code.md`.

## Session tracking

The `coding-orchestrate` skill manages four files. Three live under `.claude/` to keep the project root clean; `README.md` stays at the root by convention:

- **`.claude/SESSION.md`** — per-session logs with goals, what was done, current state, decisions
- **`.claude/TODO.md`** — discovered tasks, format `- [ ] item`
- **`.claude/MEMORIES.md`** — things the user explicitly asked to remember
- **`README.md`** — kept current with project concepts and features

These are skill-managed, not hand-edited. When in doubt, invoke `/coding-orchestrate`.

## Key Concepts

**Skills are markdown, not executables** — a skill file instructs Claude but cannot self-execute on install. It cannot automatically write config files or start services when `install.sh` runs.

**Each skill has two files with different consumers:**
- `SKILL.md` — consumed by Claude Code at runtime. The YAML frontmatter `description` becomes the **trigger hint** shown in `<system-reminder>`, controlling when the model activates the skill. The markdown body is the instruction set injected into context.
- `metadata.yaml` — consumed by `install.sh` (bash). Contains `scope` (project/global), `name`, `description`, `tags`. Used to determine install target and for `--list` display. `install.sh` can't reliably parse SKILL.md frontmatter (folded YAML mixed with markdown), hence the separate file.

**SKILL.md `description` is a trigger hint, not a human label** — write it as activation criteria for the model (e.g., "Always activate for every user message"). A description that is too narrow (e.g., "When user sends a request in English") will suppress skill activation for other inputs.

**"Activate when…" beats "Use when…"** — empirically confirmed via SkillOpt scoring (2026-07-01). Descriptions with no trigger criteria or passive "Use when" buried at the end score 1–3/5 trigger clarity; imperative-first "Activate when…" scores 5/5. Common failure patterns:
- **No trigger criteria at all** (worst): scored 4/10 total — add "Activate when…" at the front.
- **Passive "Use when" at end**: scored 7/10 — move criteria to front, rewrite as imperative.
- **Correction-type skills**: add a "skip if already correct" rule in the body to avoid noise.

**Skill trigger priority stack** (strongest → weakest):
1. **CLAUDE.md** — always loaded; hard rule the model must follow
2. **Explicit `/skill-name` command** — user-invoked, no ambiguity
3. **`system-reminder` description** (from `SKILL.md` frontmatter) — hint the model reads each turn to decide whether to call `Skill(...)`
4. **Model default behavior** — what happens without any instructions

CLAUDE.md and the `system-reminder` description should reinforce each other, not conflict. When they disagree, CLAUDE.md wins.

**Model reliability gap** — even when both CLAUDE.md and `system-reminder` signal activation, the model can silently skip calling `Skill(...)` on the first response. Mitigation: write descriptions as imperative commands ("Always activate for every user message") rather than conditional triggers ("When user sends X").

**Skill optimization (SkillOpt loop)** — to improve trigger rates: score each skill on Trigger Clarity (0–5) + Body Quality (0–5); threshold ≥ 8/10; apply bounded edits (≤ 4/round), accept only if score improves. Run logs stored in Obsidian at `0_dev/AI/skill-opt/`. Last run: 2026-07-01, all 6 skills reached 9/10 from an average of 6.2/10 in one epoch.

**MCP server config lives in `settings.json`**, under the `mcpServers` key:

- `~/.claude/settings.json` (global) — available in every project and session; right for general-purpose servers (RAG, Obsidian).
- `.claude/settings.json` (project) — only that repo; extends/overrides global; right for repo-specific servers (e.g. a project database MCP).

**To auto-wire an MCP server on skill install**, extend `install.sh` to write the `mcpServers` entry into the appropriate `settings.json` after symlinking the skill.

**`update-config` skill** can edit `settings.json` interactively (permissions, hooks, env vars, `mcpServers`); invoke it when you need Claude to add or modify a config entry.

**Enabling project-level MCP servers requires two files in the cwd**, not just `settings.json`:

- `.mcp.json` — server definitions (name, command, args, env)
- `.claude/settings.local.json` — `{ "enabledMcpjsonServers": ["server-name", ...] }` so Claude Code actually loads them in that project
- `install.sh`'s `merge_mcp_config` handles writing both; `ldn`'s "inject MCP" option calls it. Syncing to `~/.config/claude-code/mcp.json` is **not** the right mechanism.

**`ldn` manages project-scoped skills, not global** — when you run `ldn` from any project directory, it installs/removes skills into `cwd/.claude/skills/` via `--project`. Pre-selection checks only the cwd, so globally-installed skills (in `~/.claude/skills/`) do not appear pre-checked. Each project gets its own independent set.

**`ldn` "inject MCP" option** — selecting it in the `gum choose` UI calls `install.sh`'s `merge_mcp_config` for every skill that ships an `mcp.json`, writing server definitions and `enabledMcpjsonServers` into the cwd. The item is pre-checked when `.mcp.json` already exists in the cwd.

**Installed SKILL.md files are symlinks** — `install.sh` symlinks the repo's skill directory, not copies. Editing `skills/<name>/SKILL.md` in the repo takes effect immediately in the installed skill; no re-install needed. Confirmed: `~/.claude/skills/<name>` and `.claude/skills/<name>` both resolve back to the repo path.
