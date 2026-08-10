# Dependency Audit Report

- **Generated:** 2026-08-11 02:30 CST (claude-maxer, iteration 1)
- **Scope:** All Node subprojects under `skills/` with a `package.json`
- **Prior report:** [claude-maxer-dependency-report-20260703-001242-i6.md](claude-maxer-dependency-report-20260703-001242-i6.md) (2026-07-03, iteration 6)

## Subprojects scanned

| Subproject | package.json | Notes |
| --- | --- | --- |
| `skills/model-switch` | yes | `node_modules` present, scanned below |
| `skills/rag-chroma` | no | Docker/Python-based (ChromaDB + MCP), no Node deps |

## skills/model-switch

### `npm outdated`

| Package | Current | Wanted | Latest | Latest at prior report |
| --- | --- | --- | --- | --- |
| `@hono/node-server` | 2.0.3 | 2.1.0 | **2.1.0** | 2.0.8 |
| `@types/node` | 25.9.1 | 25.9.5 | 26.2.0 | 26.1.0 |
| `hono` | 4.12.22 | 4.13.1 | **4.13.1** | 4.12.27 |
| `tsx` | 4.22.3 | 4.23.12 | **4.23.12** | 4.22.5 |
| `typescript` | 6.0.3 | 6.0.3 | 7.0.2 | (not reported as outdated) |

**Major changes since 2026-07-03:**
- `@hono/node-server` has jumped from 2.0.8 available to 2.1.0 (minor version bump)
- `hono` now offers 4.13.1 (jumped from 4.12.27)
- `tsx` now offers 4.23.12 (jumped from 4.22.5 — major version jump in "wanted")
- **`typescript` is now outdated** — version 7.0.2 available (was not reported as outdated in prior report; 6.0.3 may have been released since last scan)

### `npm audit`

**3 vulnerabilities total (1 low, 1 moderate, 1 high)** — increased from 2 vulnerabilities in the prior report:

- **@hono/node-server <=2.0.9 — MODERATE** 
  - Path traversal in `serve-static` on Windows via encoded backslash (`%5C`) — [GHSA-frvp-7c67-39w9](https://github.com/advisories/GHSA-frvp-7c67-39w9)
  - **NEW: Unauthenticated memory-leak DoS via aborted WebSocket handshake** — [GHSA-9mqv-5hh9-4cgg](https://github.com/advisories/GHSA-9mqv-5hh9-4cgg)

- **esbuild 0.27.3–0.28.0 — LOW** (transitive via `tsx`)
  - Arbitrary file read on Windows dev server — [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr)

- **hono <=4.12.33 — HIGH** (12 distinct advisories)
  - Previous report listed 5 advisories; current audit shows expanded list:
    - Body Limit Middleware bypass on AWS Lambda (`GHSA-rv63-4mwf-qqc2`)
    - Lambda@Edge adapter header loss (`GHSA-wgpf-jwqj-8h8p`)
    - CORS middleware origin reflection (`GHSA-88fw-hqm2-52qc`)
    - Path traversal in `serve-static` on Windows (`GHSA-wwfh-h76j-fc44`)
    - AWS Lambda `Set-Cookie` merge (`GHSA-j6c9-x7qj-28xf`)
    - **NEW: API Gateway v1 adapter header de-duplication** (`GHSA-xgm2-5f3f-mvvc`)
    - **NEW: JSX context not isolated per request** (`GHSA-hvrm-45r6-mjfj`)
    - **NEW: Server-Side XSS via JSX Escaping Bypass in cx()** (`GHSA-w62v-xxxg-mg59`)
    - **NEW: ReDoS in CORS middleware** (`GHSA-8j4g-w8fx-2239`)
    - **NEW: memo() retains SSR output across requests** (`GHSA-f23p-vx2j-j53r`)
    - **NEW: Proxy Helper header leak via Connection header** (`GHSA-79qm-7rj5-m7r9`)
    - **NEW: Algorithmic Complexity DoS in Language Middleware** (`GHSA-54fx-42gc-7vw4`)

All 3 vulnerabilities are fixable via `npm audit fix` (no `--force` needed).

## Recommendation

**Take action now** — this update has introduced 9 additional high-severity advisories in hono. The prior report (2026-07-03) recommended bumping `hono` to pull in fixes; that recommendation stands and is now more urgent:
- `npm audit fix` will resolve all 3 vulnerabilities
- `@hono/node-server` 2.1.0 and `tsx` 4.23.12 should also be updated as they include security and stability improvements
- `typescript` 7.0.2 can be reviewed separately for breaking changes before upgrading

This report is read-only per policy — no upgrade was performed.
