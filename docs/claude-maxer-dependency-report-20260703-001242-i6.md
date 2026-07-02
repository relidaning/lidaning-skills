# Dependency Audit Report

- **Generated:** 2026-07-03 00:12 CST (claude-maxer, iteration 6)
- **Scope:** All Node subprojects under `skills/` with a `package.json`
- **Prior report:** [claude-maxer-dependency-report-20260702-103813-i3.md](claude-maxer-dependency-report-20260702-103813-i3.md) (2026-07-02, iteration 3)

## Subprojects scanned

| Subproject | package.json | Notes |
| --- | --- | --- |
| `skills/model-switch` | yes | `node_modules` present, scanned below |
| `skills/rag-chroma` | no | Docker/Python-based (ChromaDB + MCP), no Node deps |

## skills/model-switch

### `npm outdated`

| Package | Current | Wanted | Latest | Latest at prior report |
| --- | --- | --- | --- | --- |
| `@hono/node-server` | 2.0.3 | 2.0.8 | **2.0.8** | 2.0.6 |
| `@types/node` | 25.9.1 | 25.9.4 | 26.1.0 | 26.1.0 (unchanged) |
| `hono` | 4.12.22 | 4.12.27 | 4.12.27 (unchanged) | 4.12.27 |
| `tsx` | 4.22.3 | 4.22.5 | **4.22.5** | 4.22.4 |

Two packages have newer upstream releases since the last report: `@hono/node-server` (2.0.6 → 2.0.8) and `tsx` (4.22.4 → 4.22.5). No release notes were reviewed (read-only audit); nothing indicates a security fix in either bump.

### `npm audit`

Same 2 vulnerabilities as the prior report (1 low, 1 high) — no new advisories:

- **hono <=4.12.24 — HIGH** (fixed in 4.12.27, already within the `^4.12.22` semver range)
  - Path traversal in `serve-static` on Windows via encoded backslash (`%5C`) — [GHSA-wwfh-h76j-fc44](https://github.com/advisories/GHSA-wwfh-h76j-fc44)
  - AWS Lambda adapter merges multiple `Set-Cookie` headers, dropping cookies on ALB/Lattice — [GHSA-j6c9-x7qj-28xf](https://github.com/advisories/GHSA-j6c9-x7qj-28xf)
  - CORS middleware reflects any Origin with credentials when `origin` defaults to wildcard — [GHSA-88fw-hqm2-52qc](https://github.com/advisories/GHSA-88fw-hqm2-52qc)
  - Body Limit middleware bypassable on AWS Lambda via understated `Content-Length` — [GHSA-rv63-4mwf-qqc2](https://github.com/advisories/GHSA-rv63-4mwf-qqc2)
  - Lambda@Edge adapter keeps only the last value of a repeated request header — [GHSA-wgpf-jwqj-8h8p](https://github.com/advisories/GHSA-wgpf-jwqj-8h8p)
- **esbuild 0.27.3 - 0.28.0 — LOW** (transitive, via `tsx`)
  - Allows arbitrary file read when running the dev server on Windows — [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr)

Both remain fixable via `npm audit fix` (no `--force` needed) — unchanged from the prior report; the fix has still not been applied.

## Recommendation

Unchanged from the prior report: bump `hono` to pull in the HIGH-severity fix (`npm update hono` or `npm audit fix` is sufficient). Additionally, `@hono/node-server` and `tsx` now have newer patch releases available (2.0.8 and 4.22.5 respectively) with no known security content. This report is read-only per policy — no upgrade was performed.
