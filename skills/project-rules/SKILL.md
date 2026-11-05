---
name: project-rules
description: >
  Apply the user's project engineering rules whenever creating, editing,
  reviewing, or configuring a project with executable scripts, services,
  build commands, or automation. Centralize portable configuration and make
  technology choices and replacement boundaries visible. Applies across projects.
---

# Project rules

These are standing rules for work on executable projects, including skills
with scripts. Apply them to the project being worked on; global installation
does not authorize a sweep of other projects or changes to running services.
Respect explicit user instructions and project-specific constraints.

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

For new work, follow these rules as part of implementation. In an existing
project, bring touched settings under its configuration system; do a broader
extraction when requested. Update launch instructions and non-secret examples
with the same change. Validate real loading from another working directory,
override precedence, invalid configuration and affected behavior with isolated
tests. Do not start paid sessions, contact production dependencies, restart
services or migrate live data merely to test configuration.

Report what moved, where to edit it, what remains fixed and which checks ran.
Installing this skill makes it discoverable; a host's global instruction file
can require loading it for applicable work. Do not promise enforced execution
by agents or hosts that do not load skills.
