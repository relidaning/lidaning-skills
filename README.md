# Lidaning Skills

Personal skills for Claude Code, Codex, and OpenCode. Each skill is a directory with a `SKILL.md`
file — the standard [Agent Skills](https://agentskills.io) format.

## Available skills

| Skill | Scope | Description |
|---|---|---|
| `guardails` | global | Requires explicit permission before accessing, using, changing, or sharing private information and credentials. Instruction-based; requires the agent to load the skill. |
| `english-practice` | project | Always responds in English; corrects grammar, word choice, phrasing. |
| `memory-orchestrate` | project | Project memory: session log, core concepts, user-stated memories. |
| `learning-instruct` | project | Structured learning tutor with goal setting, teaching steps, and quizzes. |
| `model-switch` | project | Route Claude Code requests to DeepSeek, GLM, Kimi, or OpenRouter. |
| `obsidian-local` | project | Local Obsidian vault via REST API MCP — search, read, create, update notes. |
| `rag-chroma` | project | General-purpose RAG: ingest docs/URLs/PDFs, embed, store, retrieve. |
| `sub-maxer` | project | Documents/manages the keep-alive pings + opportunistic-work loop for Pro/Max limits. |
| `nextcloud` | project | Work with files in the self-hosted Nextcloud via MCP (WebDAV): list, read, upload, download, move, copy, delete, search. |
| `skill-bench` | project | Benchmark a skill: frozen, versioned trigger + behavior suites; headless trials; F1, rubric scores, pass@k, CIs, run history. |
| `git-rules` | global | Personal git/GitHub rules: delete a branch once its PR is merged, repo settings, session notes. New rules are added here instead of the global CLAUDE.md. |
| `project-rules` | global | Portable configuration and a technology map for projects with executable scripts/services. Load before applicable engineering work. |

## Quick start

```bash
# Interactive checkbox UI — toggle skills on/off (requires gum)
ldn

# Plain list with install status
ldn list

# Or use install.sh directly
./install.sh english-practice --project
./install.sh --remove english-practice --project

# Codex, or Claude Code and Codex together
./install.sh english-practice --project --agent codex
./install.sh git-rules --global --codex
./install.sh english-practice --project --agent both
./install.sh --remove english-practice --project --agent codex
ldn --agent codex
ldn --global --agent codex                 # manage user skills across projects
ldn list --global --agent codex
ldn list --agent codex
ldn mcp inject --agent codex
node cli.js add english-practice --project --agent codex

# OpenCode instead of (or as well as) Claude Code
./install.sh english-practice --project --opencode      # same as --agent opencode
./install.sh english-practice --global --agent all      # all three agents
ldn -agent opencode                                      # checkbox UI for .opencode/skills/
ldn list -agent opencode                                 # (no -agent = Claude Code layout)
```

## How it works

`install.sh`, `ldn`, and the Node CLI use the same installer. They link the
complete skill folder, including scripts, references, assets, and metadata.
Changes in this checkout are immediately available through the links. Existing
Markdown-only installs are migrated on reinstall; directories containing local
files are preserved and reported as conflicts.

The default target remains Claude Code. Use `--agent codex` (or `--codex`),
`--agent both` for Claude Code + Codex, or `--agent all` for all three targets.
`install.sh` and the Node CLI also accept `LDN_AGENT`; `ldn` uses its explicit
agent flag. Project installs are relative to the directory you run the command
from, so you can invoke `/path/to/lidaning-skills/install.sh` from another repo.

Codex uses `.agents/skills` for project skills and `~/.agents/skills` for user
skills, following the [official skill discovery paths](https://learn.chatgpt.com/docs/build-skills).
Its MCP servers go into `.codex/config.toml` for a project or
`${CODEX_HOME:-~/.codex}/config.toml` globally. MCP registration requires Python
3.11+ and preserves unrelated TOML settings and comments. Server definitions
are kept in marked installer-owned blocks; a conflicting manually configured
server is reported rather than overwritten. Credential references such as
`${NEXTCLOUD_PASSWORD}` become environment forwarding rules, so export them
before starting Codex. Project MCP settings require a trusted project. See the
[official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

With `--agent opencode` the links go to `.opencode/skills/<name>/` or
`~/.config/opencode/skills/<name>/` instead, and a skill's `mcp.json` is
converted into OpenCode's format (`mcp.servers` in `opencode.json[c]`, local
servers as a command array with `{env:VAR}` references, HTTP ones as
`"type": "remote"`). OpenCode also reads `.claude/skills/` for compatibility,
so installing a skill for both agents in the same scope can list it twice there.

Edit `SKILL.md` directly — changes are available through the links. Restart
the agent if an update does not appear.

Invoke a skill with `/skill-name` in Claude Code or `$skill-name` in Codex
(`/skills` also lists them). Both can select skills from their descriptions.

## Scope

| Agent | `--global` | `--project` |
|---|---|---|
| `claude` (default) | `~/.claude/skills/<name>/` | `.claude/skills/<name>/` |
| `codex` | `~/.agents/skills/<name>/` | `.agents/skills/<name>/` |
| `opencode` | `${XDG_CONFIG_HOME:-~/.config}/opencode/skills/<name>/` | `.opencode/skills/<name>/` |

## Agent compatibility

Shared skills use the same source files for every agent. Read
[AGENTS.md](AGENTS.md) for tool-name and project-memory conventions when moving
between agents. Local vault locations and existing `.claude/state` files are
shared application data; installing for Codex does not migrate that data.

`sub-maxer` defaults to Claude Code; its cron runner also supports
`--agent codex` for Codex quota checks and unattended execution. See its
[Codex setup](skills/sub-maxer/SKILL.md#codex-scheduler-opt-in) before enrolling
the separate Codex cron block. `model-switch` manages Claude Code itself. `skill-bench`
runs headless `claude -p` trials and requires Claude Code; it does not benchmark
Codex. Installing these in Codex makes their instructions available for managing
those Claude tools, without converting their runtimes. `skillopt` can use the
current agent for its in-session workflow; its headless benchmark integration
still requires Claude Code. Claude lifecycle hooks are not installed by this
installer and are not assumed to run in Codex.

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
description: What this skill does and when the agent should use it.
---

## Instructions

...
```

The `description` is how the agent decides when to auto-invoke. Write it with
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
# Restart the agent if changes do not appear.
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
    ├── memory-orchestrate/
    ├── learning-instruct/
    ├── model-switch/
    ├── obsidian-local/
    └── rag-chroma/
```
