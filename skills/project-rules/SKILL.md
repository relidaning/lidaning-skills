---
name: project-rules
description: >
  Apply the user's project engineering rules whenever creating, editing,
  reviewing, optimizing, or configuring a project with executable scripts,
  services, build commands, or automation. Reorganize existing files during
  project-wide optimization, keep project directories coherent, centralize
  portable configuration, require daily application logs and corresponding
  metric visualizations, and make technology choices and replacement boundaries
  visible. Applies across projects.
---

# Project rules

These are standing rules for work on executable projects, including skills
with scripts. Apply them to the project being worked on; global installation
does not authorize a sweep of other projects or changes to running services.
Respect explicit user instructions and project-specific constraints.

## Scope of application

- A request to optimize a project or apply these rules across a project includes
  its existing file organization, portable configuration and technology map.
  Inspect and address all three; configuration work alone is not completion.
  Carry out needed file moves and reference updates within that project rather
  than stopping at a proposed directory tree or organizing only newly added files.
- For a specific bug, feature or configuration-only request, apply the rules to
  the affected area without expanding into a project-wide reorganization. A
  review-only request produces findings rather than file changes.

## Coherent project layout

- Inspect the existing tree and framework conventions before choosing locations.
  Give each kind of file a clear home, reuse established directories, and avoid
  parallel folders serving the same purpose. Scale the layout to the project;
  do not create empty directories or split a small app into unnecessary layers.
  For a single app, put implementation directly in `src/`; do not add a
  project-named wrapper such as `src/<project>/` merely for organization.
  Keep an extra package layer only when a concrete framework, import or build
  requirement needs it, and explain that requirement.
- Keep the root focused on entrypoints, manifests/lockfiles, essential project
  guidance and configuration required there by tooling. Put implementation,
  support scripts, deployment assets and detailed documentation in purposeful
  directories. These are defaults to adapt, not a mandatory scaffold:

  | Content | Default home and boundary |
  | --- | --- |
  | Application code | `src/` for a single app; `backend/` and `frontend/` for separate services, or an established `apps/` and `packages/` workspace. Follow each component's native source layout. |
  | Maintenance and automation | `scripts/`; reserve `bin/` for user-facing commands. Keep scripts specific to a component with that component. |
  | Docker and deployment | `docker/` or `deploy/` for shared Dockerfiles, Compose files and deployment assets; component Dockerfiles may live with their service. Keep root files when tooling expects them. |
  | Database definitions | `db/` for migrations, schemas and seed definitions, or the framework's established equivalent. Keep these versioned and separate from mutable database storage. |
  | Runtime data | Configured storage outside source directories: Docker named volumes or a dedicated ignored directory such as `var/` or `data/`. Include databases, uploads, caches and local dumps; keep intentional test fixtures with tests. |
  | Log files | Required `<app-root>/logs/YYYY-MM-DD.log` for application, training and diagnostic logs; ignore `logs/` in version control and keep it separate from `data/` and source code. Persist container logs to this host location. Database journals and broker transaction logs remain with their data storage. |
  | Documentation | `docs/` for detailed guides and architecture; keep a concise root `README.md` linking to them and retain agent/tool entrypoints where discovery requires them. |
  | Tests and static assets | Follow the framework's test and asset conventions; use colocated tests or `tests/`, and established `public/` or `assets/` locations. |

- Document the chosen layout and important entrypoints briefly in the existing
  README or architecture guide. Make source, configuration, deployment assets
  and persistent data locations easy to distinguish, including host/container
  mount mappings. Keep a single authoritative copy of each file.
- For an existing project, inventory existing source files, scripts, deployment
  assets, database definitions/storage and documentation within the scope.
  Identify misplaced files and overlapping directories, choose their intended
  homes, then move and consolidate them. An existing location alone does not
  justify keeping scattered files. Retain coherent framework layouts and files
  with concrete tooling or compatibility requirements; do not force cosmetic
  moves when the current structure already serves its purpose.
- Before moving files, check imports, launch/build scripts, CI, Docker build
  contexts, COPY paths, bind mounts and
  documentation links; update affected references together. Preserve public
  entrypoints when needed, and validate affected commands from their documented
  working directories. Do not move live database files or volumes as incidental
  cleanup; treat storage relocation as an explicit data migration.

## Required application logging

- Every runnable or executable app project must have a working logging
  mechanism, including CLI tools, scripts, scheduled jobs and services. When
  creating or changing an executable app, inspect its logging and add or repair
  it if missing. A review-only request reports gaps without modifying files.
- Write logs to `<app-root>/logs/YYYY-MM-DD.log` (for example,
  `logs/2026-11-13.log`). Resolve the app root independently of the caller's
  working directory. Create `logs/` automatically, append without truncating
  earlier runs, and switch to the new date's file across midnight in long-running
  processes. Use one documented timezone for filenames and entry timestamps.
- Reuse the app's native logging facilities and wire them into its executable
  entrypoints. Include timestamps, severity and useful operation context; capture
  lifecycle events, important outcomes and errors with diagnostic details.
  Preserve CLI output and exit codes. Console-only logging is insufficient;
  never record credentials, tokens or other sensitive payloads.
- Keep log levels and retention settings in the existing configuration system.
  Ignore generated `logs/` files in version control. For containers, mount the
  log directory persistently so files appear at the host app root's `logs/`;
  document the mapping. For browser or restricted runtimes without filesystem
  access, use a host/backend logging sink that writes this path and explain any
  platform blocker rather than claiming console output satisfies the rule.
- Validate with isolated temporary app roots: a normal run and an error produce
  useful entries at the required path, repeated runs append, launching from
  another working directory keeps the same destination, and long-running apps
  roll over by date. Check retention and concurrent writers where applicable;
  use a controlled clock rather than waiting overnight or starting live services.

## Required log-based visualization

- Every runnable or executable app with logging must provide useful
  visualizations derived from its `<app-root>/logs/YYYY-MM-DD.log` records.
  When creating or changing an executable app, inspect and add or repair this
  capability alongside its logging. Apply it within the current project;
  review-only requests report gaps without implementing them.
- Match the app's visual style, user-facing language, domain terminology and
  technology stack. Extend an existing chart page or module where available;
  for CLI tools and batch jobs, a terminal dashboard or generated HTML report
  may fit better than a new web service. Make the result reachable through a
  documented page, command or report path. Reuse suitable existing charting
  facilities rather than introducing a separate monitoring stack by default.
- Choose core metrics for the actual workload. Services should show request
  volume and QPS, error rate, and latency trends (including p50/p95 where useful).
  Jobs and scripts should show run counts, success/failure rate, duration and
  work throughput. Model workloads should show applicable inference latency,
  request/token throughput and failures; training/evaluation workloads should
  show recorded loss, quality metrics and progress. Include resource usage or
  cost only when measured or explicitly identified as an estimate.
- Make the logs sufficient to compute those metrics: use consistently parseable
  events with timestamps, operation/service/model identifiers, outcomes and
  durations or work counts as needed. Reuse the existing format or extend it
  compatibly. Distinguish one completed operation from its diagnostic messages
  and individual retry attempts to avoid double-counting. Do not infer request
  error rate from the proportion of log lines marked ERROR.
- Define metric units, time buckets, timezone and counting semantics. Compute
  QPS as request count divided by the bucket's duration in seconds, and error
  rate as failed operations divided by total eligible operations in the same
  window. Treat zero denominators and missing observations explicitly; show
  unavailable data rather than invented values. Note sampling, retention gaps
  and incomplete coverage that limit interpretation.
- Use time-series charts for trends and suitable summaries or breakdowns for
  failures and workload comparisons. Label axes and units, expose the selected
  time range and relevant service/model/run filters, and show empty/error states
  plus data freshness. Provide readable values alongside color distinctions.
  Choose live refresh for active monitoring or a dated snapshot for reports,
  according to the app's workflow.
- Read daily files across the selected range, including rollover. Handle partial
  or malformed records without crashing or silently misrepresenting coverage.
  Bound parsing and aggregation work as logs grow; keep refresh and range limits
  in the existing configuration. Keep raw logs and sensitive details out of
  public assets; use existing access controls for operational views.
- Validate aggregation against small, known log fixtures, covering success,
  failure, retries, empty windows and midnight boundaries. Check the resulting
  charts or reports display the expected values, filters, units and empty states.
  Document how to open or generate the visualization and which metrics it covers.

## Portable configuration

- Inspect launch scripts, manifests, containers and environment reads before
  changing configuration. Reuse the project's existing configuration system
  where it meets these rules; avoid adding a competing source of truth.
- Extract operational choices: service addresses/ports, providers/models,
  file/storage locations, timeouts, schedules, resource limits, feature flags
  and tuning parameters. Keep algorithm invariants, API bounds and protocol
  constants in code unless there is a real supported reason to vary them.
- Ship a versioned, human-readable configuration with safe defaults and
  comments. Settings must actually drive the executable entrypoints, not just
  describe them. Keep dependency versions in native manifests/lockfiles and
  deployment choices in deployment configuration; link these sources rather
  than copying their values into an inventory that will drift.
- Define precedence (normally environment > selected file > shipped defaults),
  load files relative to their source or an explicit path rather than the
  caller's working directory, and reject invalid values with setting names.
  Preserve existing environment overrides and default behavior during migration.
- Keep credentials out of tracked files and examples. Use environment variables
  or the existing secret manager, document required variable names, and ignore
  local overrides. Do not print resolved secrets during validation.
- Use relative paths or configurable deployment paths. Distinguish host paths,
  container paths and build-time settings. Every client, healthcheck and agent
  registration affected by an endpoint change must have an update path.

## Visible, replaceable technology

Maintain a compact technology map alongside the configuration (comments or a
linked reference are sufficient): role, current implementation, authoritative
manifest/configuration, and replacement contract. Distinguish a value change
from a rebuild, adapter/code change, or data migration. Never suggest that
changing a database name or model ID alone makes incompatible implementations
interchangeable. Preserve data and call out index rebuilds before applying them.

## Applying the rules

For new work, follow these rules as part of implementation. For project-wide
optimization, complete the existing-file organization pass as well as the
configuration and technology-map work. For narrower changes, bring touched
settings under the project's configuration system. Update launch instructions
and non-secret examples with the same change. Validate real loading from another
working directory, override precedence, invalid configuration and affected
behavior with isolated tests. Do not start paid sessions, contact production dependencies, restart
services or migrate live data merely to test configuration.

For layout changes, validate affected imports, builds, tests, script entrypoints
and deployment configuration using checks appropriate to the project. Search
for stale references to moved paths and inspect matches; keep only intentional
compatibility references or historical records. Check that runtime data remains
separate from versioned code and its configured paths still resolve.

Report concrete old-to-new paths, reference updates, where to edit configuration
and which checks ran. For project-wide optimization, explicitly report the
layout outcome: changes made, or why the inspected layout needs no changes.
Identify any deferred moves and the concrete blocker; do not present a
configuration-only result as a completed project-wide optimization while known
layout problems remain.

Installing this skill makes it discoverable; a host's global instruction file
can require loading it for applicable work. Do not promise enforced execution
by agents or hosts that do not load skills.
