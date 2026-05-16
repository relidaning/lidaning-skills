#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');
const yaml = require('js-yaml');

const REPO_ROOT = __dirname;
const REGISTRY_FILE = path.join(REPO_ROOT, 'registry.yaml');
const SKILLS_DIR = path.join(REPO_ROOT, 'skills');
const GLOBAL_SKILLS = path.join(os.homedir(), '.claude', 'skills');
const PROJECT_SKILLS = path.join(process.cwd(), '.claude', 'skills');

// ANSI escape codes (no extra dependency)
const C = { reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m', green: '\x1b[32m', yellow: '\x1b[33m', red: '\x1b[31m', cyan: '\x1b[36m' };

const pkg = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf8'));

function usage() {
  console.log(`${C.bold}lidaning-skills${C.reset} ${C.dim}v${pkg.version}${C.reset} — manage your Claude Code skills

${C.bold}Usage:${C.reset}
  lidaning-skills [command] [options]

${C.bold}Commands:${C.reset}
  ${C.cyan}list, ls${C.reset}              List all available skills
  ${C.cyan}add <name...>${C.reset}         Install skill(s)
  ${C.cyan}remove, rm <name...>${C.reset}   Uninstall skill(s)

${C.bold}Options:${C.reset}
  -g, --global              Install to ~/.claude/skills/ (all projects)
  -p, --project             Install to ./.claude/skills/ (current project)
  -v, --version             Show version
  -h, --help                Show this help

${C.bold}Examples:${C.reset}
  lidaning-skills ls
  lidaning-skills add english-practice --global
  lidaning-skills add coding-orchestrate --project
  lidaning-skills add foo bar --global

If no scope flag is given, the default from the skill's metadata.yaml is used.`);
  process.exit(0);
}

function loadRegistry() {
  const raw = yaml.load(fs.readFileSync(REGISTRY_FILE, 'utf8'));
  return raw.skills || raw;
}

function skillPath(name) {
  const reg = loadRegistry();
  for (const s of reg) {
    if (s.name === name) return s.path;
  }
  return null;
}

function loadMetadata(name) {
  const sp = skillPath(name);
  if (!sp) return null;
  const metaFile = path.join(REPO_ROOT, sp, 'metadata.yaml');
  if (!fs.existsSync(metaFile)) return null;
  return yaml.load(fs.readFileSync(metaFile, 'utf8'));
}

function resolveScope(name, flagScope) {
  if (flagScope) return flagScope;
  const meta = loadMetadata(name);
  return meta ? meta.scope : 'global';
}

function installDir(scope) {
  return scope === 'global' ? GLOBAL_SKILLS : PROJECT_SKILLS;
}

// --- list ---

function cmdList() {
  const reg = loadRegistry();
  console.log(`${C.bold}Available skills:${C.reset}\n`);
  for (const s of reg) {
    const meta = loadMetadata(s.name);
    const scope = meta ? meta.scope : '?';
    const desc = meta ? String(meta.description).replace(/\s+/g, ' ').trim() : '(no description)';
    const scopeTag = scope === 'global' ? `${C.cyan}[global]${C.reset}` : `${C.yellow}[project]${C.reset}`;
    console.log(`  ${C.bold}${s.name.padEnd(25)}${C.reset} ${scopeTag}  ${C.dim}${desc}${C.reset}`);
  }
  console.log(`\n${C.dim}Repo: ${REPO_ROOT}${C.reset}`);
}

// --- add ---

function cmdAdd(name, flagScope) {
  const sp = skillPath(name);
  if (!sp) {
    console.error(`${C.red}Error:${C.reset} Skill '${name}' not found. Run ${C.bold}lidaning-skills ls${C.reset} to see available skills.`);
    process.exit(1);
  }

  const skillDir = path.join(REPO_ROOT, sp);
  const skillMd = path.join(skillDir, 'SKILL.md');
  if (!fs.existsSync(skillMd)) {
    console.error(`${C.red}Error:${C.reset} No SKILL.md found in ${skillDir}`);
    process.exit(1);
  }

  const scope = resolveScope(name, flagScope);
  const targetDir = path.join(installDir(scope), name);
  const scopeTag = scope === 'global' ? `${C.cyan}global${C.reset}` : `${C.yellow}project${C.reset}`;

  fs.mkdirSync(targetDir, { recursive: true });

  // Symlink SKILL.md
  const realSkillMd = fs.realpathSync(skillMd);
  const linkPath = path.join(targetDir, 'SKILL.md');
  if (fs.existsSync(linkPath)) fs.unlinkSync(linkPath);
  fs.symlinkSync(realSkillMd, linkPath);

  // Symlink supporting .md files (metadata.yaml, sessions.md, etc.)
  let count = 0;
  for (const f of fs.readdirSync(skillDir)) {
    if (!f.endsWith('.md') || f === 'SKILL.md') continue;
    const real = fs.realpathSync(path.join(skillDir, f));
    const dest = path.join(targetDir, f);
    if (fs.existsSync(dest)) fs.unlinkSync(dest);
    fs.symlinkSync(real, dest);
    count++;
  }

  console.log(`${C.green}Installed${C.reset} ${C.bold}${name}${C.reset} → ${targetDir} ${C.dim}[${scopeTag}${C.dim}]${C.reset} (SKILL.md + ${count} support files)`);
}

// --- remove ---

function cmdRemove(name, flagScope) {
  const sp = skillPath(name);
  if (!sp) {
    console.error(`${C.red}Error:${C.reset} Skill '${name}' not found.`);
    process.exit(1);
  }

  const scope = resolveScope(name, flagScope);
  const targetDir = path.join(installDir(scope), name);

  if (!fs.existsSync(targetDir)) {
    console.log(`${C.yellow}Not installed:${C.reset} ${targetDir}`);
    return;
  }

  fs.rmSync(targetDir, { recursive: true, force: true });
  console.log(`${C.green}Removed${C.reset} ${targetDir}`);
}

// --- main ---

function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    cmdList();
    process.exit(0);
  }

  const cmd = args[0];

  // Meta flags (no command context needed)
  if (cmd === '--help' || cmd === '-h') usage();
  if (cmd === '--version' || cmd === '-v') {
    console.log(`lidaning-skills v${pkg.version}`);
    process.exit(0);
  }

  // Parse names and flags from remaining args
  const rest = args.slice(1);
  let flagScope = null;
  const names = [];

  for (const a of rest) {
    if (a === '-g' || a === '--global') {
      flagScope = 'global';
    } else if (a === '-p' || a === '--project') {
      flagScope = 'project';
    } else if (a.startsWith('-')) {
      console.error(`${C.red}Unknown flag:${C.reset} ${a}`);
      console.error(`Run ${C.bold}lidaning-skills --help${C.reset} for usage.`);
      process.exit(1);
    } else {
      names.push(a);
    }
  }

  // Normalize command aliases
  const aliases = { ls: 'list', rm: 'remove' };
  const cmdNorm = aliases[cmd] || cmd;

  switch (cmdNorm) {
    case 'list':
      cmdList();
      break;
    case 'add':
      if (names.length === 0) {
        console.error(`${C.red}Error:${C.reset} 'add' requires at least one skill name.`);
        process.exit(1);
      }
      for (const n of names) cmdAdd(n, flagScope);
      break;
    case 'remove':
      if (names.length === 0) {
        console.error(`${C.red}Error:${C.reset} 'remove' requires at least one skill name.`);
        process.exit(1);
      }
      for (const n of names) cmdRemove(n, flagScope);
      break;
    default:
      console.error(`${C.red}Unknown command:${C.reset} ${cmd}`);
      console.error(`Run ${C.bold}lidaning-skills --help${C.reset} for usage.`);
      process.exit(1);
  }
}

main();
