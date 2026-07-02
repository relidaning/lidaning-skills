#!/usr/bin/env bash
set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "$0")" && pwd)"
REGISTRY="$SKILLS_DIR/registry.yaml"

# Claude Code skill paths
GLOBAL_SKILLS="$HOME/.claude/skills"
PROJECT_SKILLS=".claude/skills"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; }

usage() {
  cat <<EOF
Usage: install.sh <skill-name...> [--global|--project] [--remove] [--list] [--installed]

  --global      Install to ~/.claude/skills/ (personal, all projects)
  --project     Install to .claude/skills/ (this repo only)
  --remove      Uninstall the skill
  --list        List all available skills
  --installed   Show install status of each skill (global/project)

Examples:
  install.sh english-practice --global
  install.sh coding-orchestrate --project
  install.sh --remove english-practice --global
  install.sh --list
  install.sh --installed
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

list_installed() {
  echo "Skill install status:"
  echo ""
  printf "  %-25s %-10s %-10s\n" "SKILL" "GLOBAL" "PROJECT"
  while IFS= read -r line; do
    if [[ "$line" =~ ^\ *-\ name: ]]; then
      local name="${line#*: }"
      read -r path_line
      local global_status="-"
      local project_status="-"
      [[ -e "$GLOBAL_SKILLS/$name/SKILL.md" ]] && global_status="installed"
      [[ -e "$PROJECT_SKILLS/$name/SKILL.md" ]] && project_status="installed"
      printf "  %-25s %-10s %-10s\n" "$name" "$global_status" "$project_status"
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

install_skill() {
  local name="$1"
  local scope_override="${2:-}"

  local skill_dir="$SKILLS_DIR/$(skill_path "$name")"
  if [[ ! -d "$skill_dir" ]]; then
    err "Skill '$name' not found. Run --list to see available skills."
    exit 1
  fi

  local scope="${scope_override:-$(skill_scope "$skill_dir")}"

  local install_dir
  if [[ "$scope" == "global" ]]; then
    install_dir="$GLOBAL_SKILLS"
  else
    install_dir="$PROJECT_SKILLS"
  fi

  # Claude Code skills are directories: skills/<name>/SKILL.md
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

  log "Linked $name -> $link_dir/"

  # Register MCP server if skill ships one
  if [[ -f "$skill_dir/mcp.json" ]]; then
    merge_mcp_config "$skill_dir/mcp.json" "$scope"
    log "Registered MCP server(s) from $name"
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
  local install_dir
  if [[ "$scope" == "global" ]]; then
    install_dir="$GLOBAL_SKILLS"
  else
    install_dir="$PROJECT_SKILLS"
  fi

  local link_dir="$install_dir/${name}"
  if [[ -d "$link_dir" ]]; then
    rm -rf "$link_dir"
    log "Removed $link_dir"
  else
    warn "Not installed: $link_dir"
  fi

  # Deregister MCP server if skill ships one
  if [[ -f "$skill_dir/mcp.json" ]]; then
    remove_mcp_config "$skill_dir/mcp.json" "$scope"
    log "Removed MCP server(s) from $name"
  fi
}

# --- main ---

SCOPE=""
REMOVE=false
SKILLS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)   SCOPE="global"; shift ;;
    --project)  SCOPE="project"; shift ;;
    --remove)   REMOVE=true; shift ;;
    --list)     list_skills; exit 0 ;;
    --installed) list_installed; exit 0 ;;
    -h|--help)  usage ;;
    *)          SKILLS+=("$1"); shift ;;
  esac
done

if [[ ${#SKILLS[@]} -eq 0 ]]; then
  usage
fi

for skill in "${SKILLS[@]}"; do
  if $REMOVE; then
    remove_skill "$skill" "$SCOPE"
  else
    install_skill "$skill" "$SCOPE"
  fi
done
