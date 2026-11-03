# Repository guidance

This repository distributes Agent Skills for Claude Code, Codex, and OpenCode.
`registry.yaml` indexes `skills/<name>/SKILL.md`; `metadata.yaml` supplies the
default installation scope. Keep a single skill source for all agents.

`install.sh` is the installation implementation. `bin/ldn` supplies the
interactive UI, and `cli.js` is the npm CLI. Both delegate installation and MCP
registration to `install.sh`. Claude remains the default; `--agent codex`
selects Codex, `both` selects Claude and Codex, and `all` includes OpenCode.

Install complete skill folders as symlinks so relative resources work. For
Codex, use `.agents/skills` (project) and `~/.agents/skills` (user). MCP config
belongs in `.codex/config.toml` or `${CODEX_HOME:-~/.codex}/config.toml`.
`scripts/codex_mcp.py` maintains marked blocks, validates TOML, and preserves
unrelated configuration. Never persist expanded credentials into that file.

Run `python3 -m unittest discover -s tests -v` for installer integration checks,
`bash -n install.sh bin/ldn`, and `node --check cli.js` after installer changes.
Tests must use temporary homes/projects, without invoking paid agent sessions,
starting services, or touching the live vault.

# Cross-agent conventions

Use the current agent's available file, shell, web, MCP, and question tools.
Names such as Read, Bash, WebFetch, AskUserQuestion, and Skill refer to Claude
Code tools; they are not required tool names in Codex. In Codex, load a skill
by reading its advertised SKILL.md, and use `$skill-name` for explicit mention.
Discover MCP tools by server and capability rather than assuming an exact
Claude tool prefix.

Resolve helper scripts relative to the loaded skill's source directory.
Existing machine-specific vault/service paths remain deployment settings.
Existing `.claude/state` data and `.claude/MEMORIES.md` are shared legacy data;
do not migrate or duplicate them just because the caller is Codex.

For project memory use AGENTS.md in Codex and CLAUDE.md in Claude Code. Where a
project already has a single established concepts file, continue using it and
reference it from the other entrypoint rather than maintaining duplicate
concepts. In this repository, historical concepts remain in CLAUDE.md; consult
its Key Concepts section when relevant. SESSION.md remains shared history.

`sub-maxer` defaults to Claude Code and has an explicit `--agent codex`
backend for Codex quota reads and execution; keep provider state independent.
`model-switch` and the `skill-bench` trial runner operate on Claude Code.
Do not present them as native Codex model routing or benchmarking. Claude SessionEnd hooks are
optional Claude-only integrations, not a Codex persistence mechanism.
