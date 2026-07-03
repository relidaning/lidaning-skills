# Lidaning Skills

Personal skills for Claude Code. Each skill is a directory with a `SKILL.md`
file — the standard [Agent Skills](https://agentskills.io) format.

## Available skills

| Skill | Scope | Description |
|---|---|---|
| `english-practice` | project | Always responds in English; corrects grammar, word choice, phrasing. |
| `coding-orchestrate` | project | Session tracking, TODO management, ADR records, history context. |
| `learning-instruct` | project | Structured learning tutor with goal setting, teaching steps, and quizzes. |
| `model-switch` | project | Route Claude Code requests to DeepSeek, GLM, Kimi, or OpenRouter. |
| `obsidian-local` | project | Local Obsidian vault via REST API MCP — search, read, create, update notes. |
| `rag-chroma` | project | General-purpose RAG: ingest docs/URLs/PDFs, embed, store, retrieve. |
| `claude-maxer` | project | Documents/manages the keep-alive pings + opportunistic-work loop for Pro/Max limits. |
| `nextcloud-paper` | project | Operate the self-hosted Nextcloud via MCP (WebDAV): list, read, write, move, search files. |

## Quick start

```bash
# Interactive checkbox UI — toggle skills on/off (requires gum)
ldn

# Plain list with install status
ldn list

# Remove installed skills
ldn rm

# Or use install.sh directly
./install.sh english-practice --project
./install.sh --remove english-practice --project
```

## How it works

`install.sh` (or `ldn`) creates a symlink in `.claude/skills/<name>/` (project)
or `~/.claude/skills/<name>/` (global). Claude Code discovers the directory
automatically.

Edit `SKILL.md` directly — changes take effect after a session restart.

Invoke a skill with `/skill-name`, or let Claude auto-invoke it when your
message matches the skill's `description`.

## Scope

| Flag | Installs to | Use for |
|---|---|---|
| `--global` | `~/.claude/skills/<name>/` | Personal skills you want everywhere |
| `--project` | `.claude/skills/<name>/` | Skills specific to one repo |

## Creating a skill

```
skills/<name>/
├── SKILL.md          # YAML frontmatter + markdown instructions
├── sessions.md       # Optional supporting files
├── todos.md
└── metadata.yaml     # name, description, scope, tags
```

**`SKILL.md`** — the agent-facing entrypoint (required):

```markdown
---
name: my-skill
description: What this skill does and when Claude should use it.
---

## Instructions

...
```

The `description` is how Claude decides when to auto-invoke. Write it with
the phrases users would say. See
[how-to-use-skills-in-claude-code.md](how-to-use-skills-in-claude-code.md)
for the full frontmatter reference.

**`metadata.yaml`** — used by `install.sh`:

```yaml
name: my-skill
description: What it does
scope: global
tags: [example]
```

Add an entry to `registry.yaml` and install.

## Editing a skill

```bash
vim skills/english-practice/SKILL.md
# Restart the Claude Code session to pick up changes.
```

## Directory structure

```
lidaning-skills/
├── README.md
├── registry.yaml
├── install.sh
├── bin/ldn                  # skill manager CLI
├── how-to-use-skills-in-claude-code.md
└── skills/
    ├── english-practice/
    ├── coding-orchestrate/
    ├── learning-instruct/
    ├── model-switch/
    ├── obsidian-local/
    └── rag-chroma/
```
