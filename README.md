# Lidaning Skills

Personal skills for Claude Code. Each skill is a directory with a `SKILL.md`
file — the standard [Agent Skills](https://agentskills.io) format.

## Available skills

| Skill | Scope | Description |
|---|---|---|
| `english-practice` | global | Corrects non-native English expressions. Grammar, word choice, phrasing. |
| `coding-orchestrate` | project | Session tracking, TODO management, ADR records, history context. |

## Quick start

```bash
# List available skills
./install.sh --list

# Install a global skill (personal, all projects)
./install.sh english-practice --global

# Install a project skill (current repo only)
./install.sh coding-orchestrate --project

# Remove
./install.sh --remove english-practice --global
```

## How it works

`install.sh` creates a symlink:

```
~/.claude/skills/english-practice/SKILL.md
  → lidaning-skills/skills/english-practice/skill.md
```

Claude Code discovers it automatically. Edit `skill.md`, changes take effect
immediately — Claude Code watches skill directories for live changes.

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
# Done. Live reload picks it up — no restart, no rebuild.
```

## Directory structure

```
lidaning-skills/
├── README.md
├── registry.yaml
├── install.sh
├── how-to-use-skills-in-claude-code.md
└── skills/
    ├── english-practice/
    │   ├── SKILL.md
    │   └── metadata.yaml
    └── coding-orchestrate/
        ├── SKILL.md
        ├── sessions.md
        ├── todos.md
        ├── readme.md
        └── metadata.yaml
```
