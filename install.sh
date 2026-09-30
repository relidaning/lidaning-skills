#!/usr/bin/env bash
set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REGISTRY="$SKILLS_DIR/registry.yaml"

# Skill paths per coding agent. OpenCode (v2) scans <config dir>/skills for
# both its global config dir and the project's .opencode/ dir; it also reads
# .claude/skills for compatibility, but installing into its own dir keeps it
# working when that compatibility layer is turned off.
GLOBAL_SKILLS="$HOME/.claude/skills"
PROJECT_SKILLS=".claude/skills"
OPENCODE_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
OC_GLOBAL_SKILLS="$OPENCODE_CONFIG/skills"
OC_PROJECT_SKILLS=".opencode/skills"

# Which agent(s) to install for: claude, opencode, or all
AGENT="${LDN_AGENT:-claude}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }

usage() {
  cat <<EOF
Usage: install.sh <skill-name...> [--global|--project] [--agent A] [--remove] [--list] [--installed]

  --global      Install to the agent's global skills dir (all projects)
  --project     Install to the agent's project skills dir (this repo only)
  --agent A     claude (default), opencode, or all; also settable via LDN_AGENT
  --opencode    Shorthand for --agent opencode
  --mcp-only    Only register the skills' MCP servers (used by `ldn mcp inject`)
  --remove      Uninstall the skill
  --list        List all available skills
  --installed   Show install status of each skill (global/project)

Examples:
  install.sh english-practice --global
  install.sh memory-orchestrate --project
  install.sh --remove english-practice --global
  install.sh english-practice --project --agent opencode
  install.sh --list
  install.sh --installed

Skill dirs:
  claude    global ~/.claude/skills/            project .claude/skills/
  opencode  global ~/.config/opencode/skills/   project .opencode/skills/

MCP servers (skills that ship mcp.json):
  claude    global ~/.claude/settings.json      project .mcp.json + .claude/settings.local.json
  opencode  global ~/.config/opencode/opencode.json[c]   project opencode.json[c]
EOF
  exit 0
}

skill_path() {
  local name="$1"
  grep -A1 "name: $name$" "$REGISTRY" | grep 'path:' | sed 's/.*path: //'
}

trim() {
  # Trims leading/trailing whitespace without xargs, which chokes on
  # unmatched quotes (e.g. an apostrophe in a description field).
  awk '{$1=$1};1'
}

meta_field() {
  local skill_dir="$1"
  local field="$2"
  awk -v f="$field" '
    $0 ~ "^"f":" {
      if ($0 ~ ">$") { in_fold=1; next }
      sub("^"f": *", ""); print; exit
    }
    in_fold && /^[a-z]/  { exit }
    in_fold && /^  /     { sub("^  ", ""); printf "%s ", $0 }
    in_fold && /^[^ ]/  { exit }
    END { if (in_fold) printf "\n" }
  ' "$skill_dir/metadata.yaml" | trim
}

skill_scope() {
  local skill_dir="$1"
  meta_field "$skill_dir" "scope" | trim
}

list_skills() {
  echo "Available skills:"
  echo ""
  while IFS= read -r line; do
    if [[ "$line" =~ ^\ *-\ name: ]]; then
      local name="${line#*: }"
      read -r path_line
      local skill_dir="$SKILLS_DIR/${path_line#*: }"
      local scope=$(skill_scope "$skill_dir")
      local desc=$(meta_field "$skill_dir" "description" | trim)
      printf "  %-25s %-10s %s\n" "$name" "[$scope]" "$desc"
    fi
  done < "$REGISTRY"
}

agents() {
  case "$AGENT" in
    claude|opencode) echo "$AGENT" ;;
    all)             echo "claude opencode" ;;
    *) err "Unknown agent '$AGENT' (expected claude, opencode or all)" >&2; exit 1 ;;
  esac
}

skills_root() {
  local agent="$1" scope="$2"
  case "$agent:$scope" in
    claude:global)    echo "$GLOBAL_SKILLS" ;;
    claude:*)         echo "$PROJECT_SKILLS" ;;
    opencode:global)  echo "$OC_GLOBAL_SKILLS" ;;
    opencode:*)       echo "$OC_PROJECT_SKILLS" ;;
  esac
}

install_status() {
  # Distinguishes not-installed from a dangling symlink (e.g. after the
  # source skill dir was renamed/moved), which -e alone can't do since it
  # follows symlinks and reports false for both cases.
  local link="$1"
  if [[ -L "$link" ]]; then
    if [[ -e "$link" ]]; then
      echo "installed"
    else
      echo "broken"
    fi
  elif [[ -e "$link" ]]; then
    echo "installed"
  else
    echo "-"
  fi
}

list_installed() {
  echo "Skill install status:"
  echo ""
  printf "  %-25s %-10s %-10s %-10s %-10s\n" "SKILL" "GLOBAL" "PROJECT" "OC-GLOBAL" "OC-PROJECT"
  while IFS= read -r line; do
    if [[ "$line" =~ ^\ *-\ name: ]]; then
      local name="${line#*: }"
      read -r path_line
      printf "  %-25s %-10s %-10s %-10s %-10s\n" "$name" \
        "$(install_status "$GLOBAL_SKILLS/$name/SKILL.md")" \
        "$(install_status "$PROJECT_SKILLS/$name/SKILL.md")" \
        "$(install_status "$OC_GLOBAL_SKILLS/$name/SKILL.md")" \
        "$(install_status "$OC_PROJECT_SKILLS/$name/SKILL.md")"
    fi
  done < "$REGISTRY"
}

# For project scope, MCP servers are defined in .mcp.json (committable) and
# opted-in via enabledMcpjsonServers in settings.local.json (per-user).
# For global scope, mcpServers in ~/.claude/settings.json is used directly.

merge_mcp_config() {
  local mcp_json="$1"
  local scope="$2"
  if [[ "$scope" == "global" ]]; then
    local settings="$HOME/.claude/settings.json"
    mkdir -p "$(dirname "$settings")"
    python3 - "$settings" "$mcp_json" <<'PYEOF'
import json, sys, os
settings_file, mcp_file = sys.argv[1], sys.argv[2]
settings = json.load(open(settings_file)) if os.path.exists(settings_file) else {}
mcp = json.load(open(mcp_file))
settings.setdefault("mcpServers", {}).update(mcp)
json.dump(settings, open(settings_file, "w"), indent=2)
PYEOF
  else
    # Project scope: write server definitions to .mcp.json, enable in settings.local.json
    local mcp_file=".mcp.json"
    local local_settings=".claude/settings.local.json"
    mkdir -p ".claude"
    python3 - "$mcp_file" "$local_settings" "$mcp_json" <<'PYEOF'
import json, sys, os
mcp_file, local_settings_file, skill_mcp_file = sys.argv[1], sys.argv[2], sys.argv[3]
skill_mcp = json.load(open(skill_mcp_file))
# Merge into .mcp.json
mcp = json.load(open(mcp_file)) if os.path.exists(mcp_file) else {"mcpServers": {}}
mcp.setdefault("mcpServers", {}).update(skill_mcp)
json.dump(mcp, open(mcp_file, "w"), indent=2)
# Add server names to enabledMcpjsonServers in settings.local.json
local_settings = json.load(open(local_settings_file)) if os.path.exists(local_settings_file) else {}
enabled = local_settings.setdefault("enabledMcpjsonServers", [])
for key in skill_mcp:
    if key not in enabled:
        enabled.append(key)
json.dump(local_settings, open(local_settings_file, "w"), indent=2)
PYEOF
  fi
}

remove_mcp_config() {
  local mcp_json="$1"
  local scope="$2"
  if [[ "$scope" == "global" ]]; then
    local settings="$HOME/.claude/settings.json"
    [[ -f "$settings" ]] || return 0
    python3 - "$settings" "$mcp_json" <<'PYEOF'
import json, sys, os
settings_file, mcp_file = sys.argv[1], sys.argv[2]
settings = json.load(open(settings_file))
mcp = json.load(open(mcp_file))
servers = settings.get("mcpServers", {})
for key in mcp:
    servers.pop(key, None)
if servers:
    settings["mcpServers"] = servers
else:
    settings.pop("mcpServers", None)
json.dump(settings, open(settings_file, "w"), indent=2)
PYEOF
  else
    local mcp_file=".mcp.json"
    local local_settings=".claude/settings.local.json"
    python3 - "$mcp_file" "$local_settings" "$mcp_json" <<'PYEOF'
import json, sys, os
mcp_file, local_settings_file, skill_mcp_file = sys.argv[1], sys.argv[2], sys.argv[3]
skill_mcp = json.load(open(skill_mcp_file))
# Remove from .mcp.json
if os.path.exists(mcp_file):
    mcp = json.load(open(mcp_file))
    servers = mcp.get("mcpServers", {})
    for key in skill_mcp:
        servers.pop(key, None)
    if servers:
        mcp["mcpServers"] = servers
    else:
        mcp.pop("mcpServers", None)
    json.dump(mcp, open(mcp_file, "w"), indent=2)
# Remove from enabledMcpjsonServers in settings.local.json
if os.path.exists(local_settings_file):
    local_settings = json.load(open(local_settings_file))
    enabled = local_settings.get("enabledMcpjsonServers", [])
    local_settings["enabledMcpjsonServers"] = [k for k in enabled if k not in skill_mcp]
    if not local_settings["enabledMcpjsonServers"]:
        del local_settings["enabledMcpjsonServers"]
    json.dump(local_settings, open(local_settings_file, "w"), indent=2)
PYEOF
  fi
}

# OpenCode keeps MCP servers in opencode.json[c] under mcp.servers, in its own
# shape: local servers take a command array + "environment", remote ones
# "type": "remote", and env references are {env:VAR} instead of ${VAR}.
# One helper handles add and remove; the file may be JSONC, so comments are
# stripped on read (and are not preserved on write).

opencode_mcp() {
  local action="$1" mcp_json="$2" scope="$3"
  local base
  if [[ "$scope" == "global" ]]; then base="$OPENCODE_CONFIG/opencode"; else base="opencode"; fi
  local cfg="$base.json"
  [[ -f "$base.jsonc" ]] && cfg="$base.jsonc"
  [[ "$action" == "remove" && ! -f "$cfg" ]] && return 0
  mkdir -p "$(dirname "$cfg")"
  python3 - "$action" "$cfg" "$mcp_json" <<'PYEOF'
import json, os, re, sys
action, cfg_file, skill_mcp_file = sys.argv[1:4]

def load_jsonc(path):
    if not os.path.exists(path):
        return {"$schema": "https://opencode.ai/config.json"}
    text = open(path).read()
    # Drop // and /* */ comments outside strings, then trailing commas.
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                  lambda m: m.group(0) if m.group(0).startswith('"') else "",
                  text, flags=re.S)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return json.loads(text) if text.strip() else {}

def env_ref(v):
    return re.sub(r'\$\{(\w+)\}', r'{env:\1}', v) if isinstance(v, str) else v

def convert(entry):
    if "command" in entry:
        out = {"type": "local", "command": [entry["command"], *entry.get("args", [])]}
        if entry.get("env"):
            out["environment"] = {k: env_ref(v) for k, v in entry["env"].items()}
    else:
        out = {"type": "remote", "url": env_ref(entry["url"])}
        if entry.get("headers"):
            out["headers"] = {k: env_ref(v) for k, v in entry["headers"].items()}
    return out

cfg = load_jsonc(cfg_file)
skill_mcp = json.load(open(skill_mcp_file))
servers = cfg.setdefault("mcp", {}).setdefault("servers", {})
for name, entry in skill_mcp.items():
    if action == "add":
        servers[name] = convert(entry)
    else:
        servers.pop(name, None)
if not servers:
    cfg["mcp"].pop("servers")
    if not cfg["mcp"]:
        cfg.pop("mcp")
with open(cfg_file, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PYEOF
}

install_skill() {
  local name="$1"
  local scope_override="${2:-}"
  local agent="$3"

  local skill_dir="$SKILLS_DIR/$(skill_path "$name")"
  if [[ ! -d "$skill_dir" ]]; then
    err "Skill '$name' not found. Run --list to see available skills."
    exit 1
  fi

  local scope="${scope_override:-$(skill_scope "$skill_dir")}"
  local install_dir=$(skills_root "$agent" "$scope")

  # --mcp-only (used by `ldn mcp inject`): register MCP servers, link nothing
  if $MCP_ONLY; then
    if [[ -f "$skill_dir/mcp.json" ]]; then
      if [[ "$agent" == "opencode" ]]; then
        opencode_mcp add "$skill_dir/mcp.json" "$scope"
      else
        merge_mcp_config "$skill_dir/mcp.json" "$scope"
      fi
      log "Registered MCP server(s) from $name [$agent]"
    fi
    return 0
  fi

  # Skills are directories (same layout for Claude Code and OpenCode): skills/<name>/SKILL.md
  # Symlink skill.md as SKILL.md, plus all supporting .md files
  local link_dir="$install_dir/${name}"
  mkdir -p "$link_dir"

  # Always symlink the main skill file
  if [[ ! -f "$skill_dir/SKILL.md" ]]; then
    err "No SKILL.md found in $skill_dir"
    exit 1
  fi
  ln -sf "$(realpath "$skill_dir/SKILL.md")" "$link_dir/SKILL.md"

  # Symlink supporting .md files (sessions.md, todos.md, etc.)
  for f in "$skill_dir"/*.md; do
    [[ -f "$f" ]] || continue
    local base=$(basename "$f")
    [[ "$base" == "SKILL.md" ]] && continue  # already linked above
    ln -sf "$(realpath "$f")" "$link_dir/$base"
  done

  log "Linked $name -> $link_dir/ [$agent]"

  # Register MCP server if skill ships one
  if [[ -f "$skill_dir/mcp.json" ]]; then
    if [[ "$agent" == "opencode" ]]; then
      opencode_mcp add "$skill_dir/mcp.json" "$scope"
    else
      merge_mcp_config "$skill_dir/mcp.json" "$scope"
    fi
    log "Registered MCP server(s) from $name [$agent]"
  fi
}

remove_skill() {
  local name="$1"
  local skill_dir="$SKILLS_DIR/$(skill_path "$name")"
  if [[ ! -d "$skill_dir" ]]; then
    err "Skill '$name' not found."
    exit 1
  fi

  local scope="${2:-$(skill_scope "$skill_dir")}"
  local agent="$3"
  local install_dir=$(skills_root "$agent" "$scope")

  local link_dir="$install_dir/${name}"
  if [[ -d "$link_dir" ]]; then
    rm -rf "$link_dir"
    log "Removed $link_dir"
  else
    warn "Not installed: $link_dir"
  fi

  # Deregister MCP server if skill ships one
  if [[ -f "$skill_dir/mcp.json" ]]; then
    if [[ "$agent" == "opencode" ]]; then
      opencode_mcp remove "$skill_dir/mcp.json" "$scope"
    else
      remove_mcp_config "$skill_dir/mcp.json" "$scope"
    fi
    log "Removed MCP server(s) from $name [$agent]"
  fi
}

# --- main ---

SCOPE=""
REMOVE=false
MCP_ONLY=false
SKILLS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)   SCOPE="global"; shift ;;
    --project)  SCOPE="project"; shift ;;
    --remove)   REMOVE=true; shift ;;
    --agent)    AGENT="${2:?--agent needs claude, opencode or all}"; shift 2 ;;
    --agent=*)  AGENT="${1#*=}"; shift ;;
    --opencode) AGENT="opencode"; shift ;;
    --mcp-only) MCP_ONLY=true; shift ;;
    --list)     list_skills; exit 0 ;;
    --installed) list_installed; exit 0 ;;
    -h|--help)  usage ;;
    *)          SKILLS+=("$1"); shift ;;
  esac
done

if [[ ${#SKILLS[@]} -eq 0 ]]; then
  usage
fi

AGENTS=$(agents) || exit 1

for agent in $AGENTS; do
  for skill in "${SKILLS[@]}"; do
    if $REMOVE; then
      remove_skill "$skill" "$SCOPE" "$agent"
    else
      install_skill "$skill" "$SCOPE" "$agent"
    fi
  done
done
