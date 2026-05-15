# How to Use Skills in Claude Code

Based on [Claude Code skills documentation](https://code.claude.com/docs/en/skills).
Skills follow the [Agent Skills](https://agentskills.io) open standard.

## What a skill is

A skill is a directory with a `SKILL.md` file. Claude Code discovers it,
lists it in `/skills`, and loads its content when invoked. A skill's body
costs no tokens until it's used — unlike CLAUDE.md which loads every session.

Create a skill when:
- You keep pasting the same instructions or checklist into chat
- A section of CLAUDE.md has grown into a procedure
- You want reference material available on demand without the token cost of
  always loading it

## Where skills live

| Location | Path | Applies to |
|---|---|---|
| Personal | `~/.claude/skills/<name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<name>/SKILL.md` | This project only |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | Where plugin is enabled |

Personal overrides project. Plugin skills use a `plugin-name:skill-name`
namespace and never conflict.

## File format

```markdown
---
name: my-skill
description: What this skill does and when Claude should use it
---

Your instructions here.
```

- **YAML frontmatter** between `---` markers — configures behavior
- **Markdown body** — the instructions Claude follows when the skill runs

The directory name becomes the command name (`/my-skill`). The `name` field
overrides it if set.

## Frontmatter reference

All fields are optional. Only `description` is recommended.

| Field | Description |
|---|---|
| `name` | Display name. Defaults to directory name. Lowercase, hyphens, max 64 chars. |
| `description` | **Recommended.** What the skill does and when to use it. Claude matches on this to auto-invoke. Truncated at 1,536 chars in listings. |
| `when_to_use` | Extra trigger phrases. Appended to description. |
| `disable-model-invocation` | Set `true` to prevent Claude from auto-invoking. Only you can trigger it with `/name`. Use for deploy, commit, etc. |
| `user-invocable` | Set `false` to hide from the `/` menu. Only Claude can invoke. Use for background reference. |
| `allowed-tools` | Tools Claude can use without asking during this skill. e.g. `Bash(git *)`. |
| `context` | Set `fork` to run in an isolated subagent. |
| `agent` | Subagent type when `context: fork`. e.g. `Explore`, `Plan`. |
| `model` | Model override while skill is active. |
| `paths` | Glob patterns limiting when the skill activates. |

## Who can invoke a skill

| Configuration | You can invoke | Claude can invoke |
|---|---|---|
| (default) | Yes | Yes |
| `disable-model-invocation: true` | Yes | No |
| `user-invocable: false` | No | Yes |

- **`disable-model-invocation: true`** — for side-effect workflows you control:
  `/deploy`, `/commit`, `/send-slack-message`
- **`user-invocable: false`** — for background knowledge that isn't an action:
  legacy system context, internal jargon reference

## How auto-invocation works

When `disable-model-invocation` is not set, Claude sees the skill's `description`
and `when_to_use` in context. If your message matches, Claude invokes the skill
via the Skill tool. Write the description with the exact phrases users would say:

```yaml
# Good
description: Summarize uncommitted changes and flag risks. Use when the user
asks what changed, wants a commit message, or asks to review their diff.

# Weak
description: A git diff skill
```

## Skill lifecycle

1. **Listed** — skill name and description are always in context so Claude knows
   what's available. Descriptions may be truncated if you have many skills.
2. **Invoked** — the full `SKILL.md` content enters the conversation.
3. **Persists** — content stays in context across turns for the rest of the
   session. Claude Code does not re-read the file.
4. **Compaction** — if the conversation is summarized, the most recent 5,000
   tokens of each invoked skill are carried forward (25,000 token combined
   budget). Re-invoke if the skill seems to lose influence.

## Live change detection

Claude Code watches `~/.claude/skills/` and `.claude/skills/` for file changes.
**Adding, editing, or removing a skill takes effect within the current session
without restarting.** Creating a brand-new top-level skills directory requires
a restart so the new directory can be watched.

## Dynamic context injection

Use `` !`command` `` to run a shell command before the skill content is sent to
Claude. The output replaces the placeholder:

```markdown
## Current changes
!`git diff HEAD`
```

For multi-line commands, use a fenced `` ```! `` block:

````markdown
```!
node --version
npm --version
```
````

Claude only sees the output, not the command.

## Arguments

```yaml
---
name: fix-issue
description: Fix a GitHub issue by number
---

Fix GitHub issue $ARGUMENTS following our coding standards.
```

`/fix-issue 123` → "Fix GitHub issue 123 following our coding standards..."

- `$ARGUMENTS` — all arguments as typed
- `$0`, `$1` — positional arguments
- `${CLAUDE_SKILL_DIR}` — path to the skill's directory

## Subagent skills

Add `context: fork` to run a skill in an isolated subagent:

```yaml
---
name: deep-research
description: Research a topic thoroughly
context: fork
agent: Explore
---

Research $ARGUMENTS:
1. Find relevant files
2. Read and analyze
3. Summarize with file references
```

The skill content becomes the subagent's prompt. It won't have access to
conversation history.

## Skills vs CLAUDE.md

| | CLAUDE.md | Skill |
|---|---|---|
| **When loaded** | Every session, automatically | When invoked (by you or Claude) |
| **Token cost** | Always paid | Only when used |
| **Best for** | Facts, conventions, always-on behaviors | Procedures, checklists, on-demand reference |
| **Invocation** | Automatic | `/name` or auto-matched via description |

A common pattern: keep CLAUDE.md for standing instructions, move multi-step
procedures into skills.

## Supporting files

A skill directory can contain reference files, templates, and scripts:

```
my-skill/
├── SKILL.md           # Required entrypoint
├── reference.md       # Detailed docs (loaded on demand)
├── template.md        # Template for Claude to fill in
└── scripts/
    └── validate.sh    # Script Claude can execute
```

Reference them from SKILL.md so Claude knows when to load them.

## Troubleshooting

**Skill not triggering:**
1. Check the `description` includes keywords users would say
2. Verify it appears in `/skills`
3. Try invoking directly with `/skill-name`

**Skill triggers too often:**
1. Make the `description` more specific
2. Add `disable-model-invocation: true`

**Skill seems to stop working mid-session:**
The content may have been trimmed during compaction. Re-invoke with `/skill-name`.
