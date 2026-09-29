#!/usr/bin/env node
// mcpvault's own entrypoint (dist/server.js), with one addition: the path
// filter also hides the vault folders listed in EXCLUDED_DIRS_FILE. mcpvault
// routes every tool (read, write, search, list, tags, links) through this
// filter but has no CLI option for extra patterns, hence this wrapper. It is
// copied into mcpvault's dist/ at build time so its imports resolve there.
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { createServer } from "./src/createServer.js";
import { PathFilter } from "./src/pathfilter.js";
import { parseCliArgs } from "./src/cli.js";
import { createWriteStream, existsSync, readFileSync, statSync } from "fs";
import { join, posix, resolve } from "path";

const FILE = process.env.EXCLUDED_DIRS_FILE || "/config/excluded-dirs";
// supergateway runs with --logLevel none (at info it logs every message body,
// i.e. full note text), which also drops this process's stderr. Write straight
// to the container's log (PID 1's stderr) instead.
let logStream = null;
try { logStream = createWriteStream("/proc/1/fd/2", { flags: "a" }); } catch { /* fall back */ }
const log = (msg) => (logStream ? logStream.write(`[mcpvault] ${msg}\n`) : console.error(msg));
const RECHECK_MS = 2000;
const { vaultPathArg, readOnly } = parseCliArgs(process.argv.slice(2));
const vaultPath = resolve(vaultPathArg || process.cwd());
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));

class ExcludingPathFilter extends PathFilter {
  constructor() {
    super();
    this.basePatterns = [...this.ignoredPatterns];
    this.checkedAt = 0;
    this.mtime = null;
    this.failed = false;
    this.reload();
  }

  reload() {
    const now = Date.now();
    if (now - this.checkedAt < RECHECK_MS) return;
    this.checkedAt = now;
    let mtime;
    try { mtime = statSync(FILE).mtimeMs; } catch { mtime = -1; }
    if (mtime === this.mtime) return;
    this.mtime = mtime;
    try {
      const dirs = readFileSync(FILE, "utf-8").split("\n")
        .map((l) => l.replace(/#.*/, "").trim().replace(/^\/+|\/+$/g, ""))
        .filter(Boolean);
      this.ignoredPatterns = [...this.basePatterns, ...dirs.flatMap((d) => [d, `${d}/**`])];
      this.failed = false;
      log(`excluded folders: ${dirs.join(", ") || "(none)"}`);
      for (const d of dirs) {
        if (!existsSync(join(vaultPath, d))) {
          log(`warning: excluded folder not in the vault (renamed or moved?): ${d}`);
        }
      }
    } catch (e) {
      // Fail closed: without the list, expose nothing rather than everything.
      this.failed = true;
      log(`error: can't read ${FILE} (${e.message}); denying all paths`);
    }
  }

  isIgnoredPath(normalizedPath) {
    this.reload();
    // Resolve "." and ".." first: "0_dev/../0_lidaning/x.md" names a file in an
    // excluded folder, and the file system resolves it that way when reading.
    const clean = posix.normalize(normalizedPath).replace(/^\/+/, "");
    if (clean === ".." || clean.startsWith("../")) return true;
    return this.failed || super.isIgnoredPath(clean) || super.isIgnoredPath(normalizedPath);
  }
}

const pathFilter = new ExcludingPathFilter();
const serverHandle = serveStdio(
  () => createServer(vaultPath, { version, readOnly, pathFilter }),
  { onerror: (error) => console.error(error) },
);

let isShuttingDown = false;
async function shutdown() {
  if (isShuttingDown) return;
  isShuttingDown = true;
  try { await serverHandle.close(); } catch { /* exit regardless */ }
  process.exit(0);
}
process.stdin.on("end", shutdown);
process.stdin.on("close", shutdown);
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
