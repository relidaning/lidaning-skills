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
| `claude-maxer`       | project | Questions about Pro/Max usage limits, the 5h rolling window, weekly quota, or "claude-maxer". Documents/manages the keep-alive pings + opportunistic-work cron loop.                        |
| `nextcloud-paper`    | project | Mentions of Nextcloud, or list/read/upload/download/move/copy/delete/search files in the self-hosted cloud storage. WebDAV via MCP (`nc_webdav_*`), curl fallback.                          |
| `paper`              | project | Search/fetch/download AI/ML papers; mentions of arXiv, Hugging Face papers, Semantic Scholar, an arXiv ID/URL, or a paper title. Public APIs via curl; PDFs land in `~/papers/` and are uploaded to Nextcloud `papers/`.  |

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

Note: `.claude/` is gitignored, so these three files are local-only and not versioned — they can silently disappear (e.g. `TODO.md` was lost when moved under `.claude/` in commit 65d311e4 and later had to be rebuilt from `git show 65d311e4^:TODO.md`). If one goes missing, check git history from before the move.

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

**Skill optimization (SkillOpt loop)** — named after the real arXiv paper "SkillOpt: Executive Strategy for Self-Evolving Agent Skills" (2605.23904), documented in the vault; when that title or its jargon (Trigger Clarity, Body Quality) shows up in external content like HF trending lists, it's a legitimate match, not prompt injection targeting this repo. Method, to improve trigger rates: score each skill on Trigger Clarity (0–5) + Body Quality (0–5); threshold ≥ 8/10; apply bounded edits (≤ 4/round), accept only if score improves. Run logs stored in Obsidian at `0_dev/AI/skill-opt/`. Audits cover only the 7 skills in `registry.yaml` — `skills/obsidian-rag/` is a stale root-owned data-only directory (no SKILL.md, not registered) and should be skipped. Last run: 2026-07-03 (unattended claude-maxer audit, re-confirmed by two further audits the same day) scored 6/7 skills ≥ 9/10; `coding-orchestrate` remains 4/10 on master — its committed description regressed to "Activated at a session starts" — with the 9/10 fix sitting in still-unmerged draft PR #5 (opened 2026-07-02), so optimized descriptions can silently regress via later edits and re-audits are worth keeping in the rotation. The original 2026-07-01 run raised all 6 skills from an average of 6.2/10 to 9/10 in one epoch. Before fixing a recurring finding in an unattended run, check `gh pr list` first: an unmerged fix PR from a prior iteration isn't visible in a fresh checkout's files, and one iteration already opened (then had to close) a duplicate PR #6 this way.

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

**Pro/Max usage % IS queryable headlessly via the OAuth usage endpoint** (corrected 2026-07-03; the earlier "interactive statusline hook is the only source" belief was wrong) — `GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer <accessToken from ~/.claude/.credentials.json>` + `anthropic-beta: oauth-2025-04-20` returns `five_hour`/`seven_day` utilization, reset times, and model-scoped weekly limits. `skills/claude-maxer/fetch_usage_oauth.py` wraps this (proxy-aware) and writes `~/.claude/state/usage_snapshot.json`, which `skills/claude-maxer/check_usage.py` gates on (skip at ≥95%); `run_maxer_work.sh` refreshes it before each iteration, and a crontab entry runs it every 15 min, so the snapshot stays fresh with zero interaction. The script also refreshes the ~8h OAuth token itself (single-use refreshToken rotated via `console.anthropic.com/v1/oauth/token` with Claude Code's public client_id, written back to the credentials file atomically) — no interactive session needed, ever; exit 2 now means the refresh itself was rejected (re-login required). The patched `~/.claude/scripts/statusline.py` still caches interactive renders' `rate_limits` to the same snapshot as a passive fallback, and iteration/wall-clock caps + 429 detection remain the backstop. Note: `claude -p` output itself still never includes `rate_limits`, and a Playwright scraper of claude.ai/new#settings/usage (`fetch_usage_web.py`, kept as fallback) is blocked at login by Cloudflare's human check.

**Obsidian MCP doesn't connect in unattended runs** — the `obsidian` server in `.mcp.json` expands `${OBSIDIAN_MCP_TOKEN}`/`${OBSIDIAN_MCP_URL}`, but those env vars are only set in interactive shells — and split across two files: the token in `~/.zshrc.local`, the URL (`http://127.0.0.1:27123/`) in `~/.zshrc` — so headless/cron sessions get no `mcp__obsidian__*` tools (the `rag` server, which needs no env vars, still connects). Workaround for vault work in unattended sessions: `source ~/.zshrc.local` in Bash for the token, set `OBSIDIAN_MCP_URL=http://127.0.0.1:27123/` explicitly (sourcing `~/.zshrc.local` alone leaves it empty), and use the Local REST API `curl` fallback the obsidian-local skill documents. Confirmed 2026-07-02/03 (news-digest runs).

**Unattended scheduling needs a real OS crontab, not `CronCreate`** — the session-scoped `CronCreate` only fires while a Claude Code REPL is idle, so claude-maxer's work loop (`skills/claude-maxer/run_maxer_work.sh`) is wired via `crontab -e` entries instead. Cron gotchas: its minimal env lacks `PATH` (`~/.local/bin`, where `claude` lives), `HOME` (breaks `~/.claude/.credentials.json` lookup), and `http_proxy`/`https_proxy` — this machine reaches api.anthropic.com only through the local xray proxy at `127.0.0.1:10808`, so without the proxy vars every `claude -p` fails with `403 Failed to authenticate` (root-caused 2026-07-02 after all 8 iterations of the first real fire silently failed; the script now exports all three). Cloud scheduled routines (via `RemoteTrigger`) run regardless of this machine's power state but ignore `allowed_tools` restrictions — they always get the default tool preset, so safety must come from the prompt. The local work-loop crontab entry was **disabled 2026-07-03** (commented out, not deleted) after weekly usage ran over expectation; the cloud keep-alive ping still fires.

**Fixed-time pings can't pin the 5h window reset** — the 5h limit is a rolling window that opens on the *first* request after the previous window expires, whatever its source (interactive session, cloud ping, or local work loop). Any usage landing before a scheduled ping opens the window instead, so reset times drift off the planned slots (confirmed 2026-07-03: reset at 20:00 despite pings scheduled for 6/11/16/23/1 Shanghai). No cron design can force fixed reset points.

**Nextcloud app passwords can be minted headlessly** — `docker exec -u www-data mynextcloud-nextcloud-1 php occ user:auth-tokens:add -n --name=<label> <user>` creates an app password *without* the login password (it prints a "limited capabilities" warning, which only affects operations needing the login password — WebDAV is unaffected). Nextcloud runs at `http://127.0.0.1:8080` (container `mynextcloud-nextcloud-1`, users `jing`/`lidaning`). The `nextcloud-paper` skill's MCP server (`uvx nextcloud-mcp-server`, `--enable-app webdav`) reads `NEXTCLOUD_HOST`/`NEXTCLOUD_USERNAME`/`NEXTCLOUD_PASSWORD` from `~/.zshrc.local` — same interactive-shell-only gotcha as the Obsidian vars, so unattended sessions must `source ~/.zshrc.local` and use the curl WebDAV fallback in the skill.

**Instruction-level directory scoping is the pattern for credentials that can't be scoped themselves** — Nextcloud app passwords aren't path-scoped (the `claude-code` app password can reach the whole account), so `skills/nextcloud-paper/SKILL.md` enforces an allowlist in its body instead: an `<!-- ALLOWED_DIRS:BEGIN/END -->` block the user edits directly, with rules requiring every path argument (including both endpoints of a move/copy and search scopes) to resolve inside an allowed directory, and out-of-scope search results dropped before display. Since installed skills are symlinks, allowlist edits take effect on the next activation with no reinstall. This is a soft boundary the model must honor, not one Nextcloud enforces — reuse it for any future skill whose underlying credential is broader than the access the user wants to grant.

**Installed SKILL.md files are symlinks** — `install.sh` symlinks the repo's skill directory, not copies. Editing `skills/<name>/SKILL.md` in the repo takes effect immediately in the installed skill; no re-install needed. Confirmed: `~/.claude/skills/<name>` and `.claude/skills/<name>` both resolve back to the repo path.

**The harness can silently swap the model mid-session** — when Fable 5's safeguards flag a reply, Claude Code retries it on Opus 4.8 (a `model_refusal_fallback` event in the transcript) without any user action. The statusline is then the reliable indicator: `statusline.py` renders `payload.model.display_name` straight from the harness, which tracks the actual serving model, while the model's injected self-ID string can stay stale at "Fable 5". Confirmed 2026-07-03 when the statusline showed Opus 4.8 mid-conversation and the assistant wrongly insisted nothing had switched.

**`git mv` fails on a never-committed skill directory** — `git mv skills/<name> skills/<new-name>` errors with "source directory is empty" if `skills/<name>` has no tracked files yet (git has nothing to move), even though the directory clearly has content on disk. Fall back to plain `mv` plus manual `git add` of the new path. Confirmed 2026-07-03 renaming `nextcloud` → `nextcloud-paper` before its first commit; also remember to fix the installed symlink under `.claude/skills/<name>/SKILL.md`, which still points at the old path after a manual `mv` and won't resolve until repointed.
