#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const yaml = require('js-yaml');

const REPO_ROOT = __dirname;
const REGISTRY_FILE = path.join(REPO_ROOT, 'registry.yaml');
let agent = process.env.LDN_AGENT || 'claude';

// ANSI escape codes (no extra dependency)
const C = { reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m', green: '\x1b[32m', yellow: '\x1b[33m', red: '\x1b[31m', cyan: '\x1b[36m' };

const pkg = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf8'));

function usage() {
  console.log(`${C.bold}lidaning-skills${C.reset} ${C.dim}v${pkg.version}${C.reset} — manage your Claude Code, Codex, and OpenCode skills

${C.bold}Usage:${C.reset}
  lidaning-skills [command] [options]

${C.bold}Commands:${C.reset}
  ${C.cyan}list, ls${C.reset}              List all available skills
  ${C.cyan}add <name...>${C.reset}         Install skill(s)
  ${C.cyan}remove, rm <name...>${C.reset}   Uninstall skill(s)

${C.bold}Options:${C.reset}
  -g, --global              Install for all projects
  -p, --project             Install for the current project
  --agent <name>           claude (default), codex, both, opencode, or all
  --codex                  Shorthand for --agent codex
  -v, --version             Show version
  -h, --help                Show this help

${C.bold}Examples:${C.reset}
  lidaning-skills ls
  lidaning-skills add english-practice --global
  lidaning-skills add memory-orchestrate --project
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

// Keep paths, complete-package links and MCP handling in the shell installer.
function runInstaller(names, flagScope, remove = false) {
  const args = [...names, '--agent', agent];
  if (flagScope) args.push(`--${flagScope}`);
  if (remove) args.push('--remove');
  const result = spawnSync(path.join(REPO_ROOT, 'install.sh'), args, { stdio: 'inherit' });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status || 1);
}

// --- main ---

function main() {
  const args = [];
  const raw = process.argv.slice(2);
  for (let i = 0; i < raw.length; i++) {
    const arg = raw[i];
    if (arg === '--agent' || arg === '-a') {
      if (!raw[i + 1]) { console.error('--agent requires a value'); process.exit(1); }
      agent = raw[++i];
    } else if (arg.startsWith('--agent=')) {
      agent = arg.slice('--agent='.length);
    } else if (arg === '--codex') {
      agent = 'codex';
    } else { args.push(arg); }
  }
  if (!['claude', 'codex', 'both', 'opencode', 'all'].includes(agent)) {
    console.error(`Unknown agent: ${agent}`);
    process.exit(1);
  }

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
      runInstaller(names, flagScope);
      break;
    case 'remove':
      if (names.length === 0) {
        console.error(`${C.red}Error:${C.reset} 'remove' requires at least one skill name.`);
        process.exit(1);
      }
      runInstaller(names, flagScope, true);
      break;
    default:
      console.error(`${C.red}Unknown command:${C.reset} ${cmd}`);
      console.error(`Run ${C.bold}lidaning-skills --help${C.reset} for usage.`);
      process.exit(1);
  }
}

main();
