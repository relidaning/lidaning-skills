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
Usage: install.sh <skill-name...> [--global|--project] [--remove] [--list]

  --global      Install to ~/.claude/skills/ (personal, all projects)
  --project     Install to .claude/skills/ (this repo only)
  --remove      Uninstall the skill
  --list        List all available skills

Examples:
  install.sh english-practice --global
  install.sh coding-orchestrate --project
  install.sh --remove english-practice --global
  install.sh --list
EOF
  exit 0
}

skill_path() {
  local name="$1"
  grep -A1 "name: $name$" "$REGISTRY" | grep 'path:' | sed 's/.*path: //'
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
  ' "$skill_dir/metadata.yaml" | xargs
}

skill_scope() {
  local skill_dir="$1"
  meta_field "$skill_dir" "scope" | xargs
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
      local desc=$(meta_field "$skill_dir" "description" | xargs)
      printf "  %-25s %-10s %s\n" "$name" "[$scope]" "$desc"
    fi
  done < "$REGISTRY"
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
