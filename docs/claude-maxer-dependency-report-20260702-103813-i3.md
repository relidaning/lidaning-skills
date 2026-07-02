# Dependency Audit Report

- **Generated:** 2026-07-02 10:38 CST (claude-maxer, iteration 3)
- **Scope:** All Node subprojects under `skills/` with a `package.json`
- **Prior report:** none found — this is the baseline report

## Subprojects scanned

| Subproject | package.json | Notes |
| --- | --- | --- |
| `skills/model-switch` | yes | `node_modules` present, scanned below |
| `skills/rag-chroma` | no | Docker/Python-based (ChromaDB + MCP), no Node deps |

## skills/model-switch

### `npm outdated`

| Package | Current | Wanted | Latest |
| --- | --- | --- | --- |
| `@hono/node-server` | 2.0.3 | 2.0.6 | 2.0.6 |
| `@types/node` | 25.9.1 | 25.9.4 | 26.1.0 |
| `hono` | 4.12.22 | 4.12.27 | 4.12.27 |
| `tsx` | 4.22.3 | 4.22.4 | 4.22.4 |

### `npm audit`

2 vulnerabilities (1 low, 1 high):

- **hono <=4.12.24 — HIGH**
  - Path traversal in `serve-static` on Windows via encoded backslash (`%5C`) — [GHSA-wwfh-h76j-fc44](https://github.com/advisories/GHSA-wwfh-h76j-fc44)
  - AWS Lambda adapter merges multiple `Set-Cookie` headers, dropping cookies on ALB/Lattice — [GHSA-j6c9-x7qj-28xf](https://github.com/advisories/GHSA-j6c9-x7qj-28xf)
  - CORS middleware reflects any Origin with credentials when `origin` defaults to wildcard — [GHSA-88fw-hqm2-52qc](https://github.com/advisories/GHSA-88fw-hqm2-52qc)
  - Body Limit middleware bypassable on AWS Lambda via understated `Content-Length` — [GHSA-rv63-4mwf-qqc2](https://github.com/advisories/GHSA-rv63-4mwf-qqc2)
  - Lambda@Edge adapter keeps only the last value of a repeated request header — [GHSA-wgpf-jwqj-8h8p](https://github.com/advisories/GHSA-wgpf-jwqj-8h8p)
  - Fixed in `hono` 4.12.27 (already the "Wanted"/"Latest" version above)
- **esbuild 0.27.3 - 0.28.0 — LOW**
  - Allows arbitrary file read when running the dev server on Windows — [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr)
  - Transitive dependency (via `tsx`); fix available via `npm audit fix`

Both issues are resolved by `npm audit fix` (no `--force` needed), which lands on `hono@4.12.27` — already within the existing `^4.12.22` semver range.

## Recommendation

Bump `hono` to pull in the HIGH-severity fix (`npm update hono` or `npm audit fix` is sufficient, no major-version jump required). This report is read-only per policy — no upgrade was performed.
