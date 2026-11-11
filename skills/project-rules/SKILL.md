---
name: project-rules
description: >
  Apply the user's project engineering rules whenever creating, editing,
  reviewing, optimizing, or configuring a project with executable scripts,
  services, build commands, or automation. Reorganize existing files during
  project-wide optimization, keep project directories coherent, centralize
  portable configuration, and make technology choices and replacement boundaries
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
  | Log files | Ignored project-root `logs/` for application, training and diagnostic logs, separate from `data/` and source code. Make the path configurable and use a persistent container mount when file logging is enabled. Database journals and broker transaction logs remain with their data storage. |
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
