# Architecture discovery and code organization

Read for architectural, structural or reusable-component work. Scale the
analysis to the affected behavior; a small app need not adopt service layers.

## Build an evidence-based map

1. Use file discovery to locate manifests, entrypoints, relevant modules and
   tests. Exclude generated assets, vendored dependencies and build outputs.
   Respect private-data permissions; source discovery does not authorize reading
   credentials, production logs, databases or memory dumps.
2. Search for the user-visible behavior: a route, CLI command, UI action, event,
   job name or error. Follow one representative path from input to result,
   including persistence, external calls and asynchronous handoffs.
3. Identify component responsibilities, dependency direction, state ownership
   and interface boundaries. Inspect callers and consumers before changing a
   shared function or schema. Account for dynamic registration, plugins and
   configuration where static search alone cannot establish reachability.
4. Stop expanding when the affected path, relevant contracts and validation
   points are understood. State unresolved edges instead of inventing certainty.
   For broad work, record a compact component table or diagram in existing docs:
   responsibility, entrypoint, dependencies, owned data and public contract.

## Put logic where it belongs

- Organize around cohesive capabilities and ownership. Keep framework handlers
  focused on input translation, authorization and response handling; put domain
  rules in the owning module and infrastructure details behind appropriate
  boundaries. Follow established framework conventions where they already work.
- Extract logic when it has an independent rule, repeated use, separate testing
  need or a distinct reason to change. Separate deterministic decisions from
  database, network, filesystem and clock effects where this improves clarity.
  Pass required context explicitly rather than hiding it in mutable globals.
- Reuse an existing implementation when its semantics fit. Consolidate actual
  duplicate rules, preserving meaningful differences between callers. Similar
  syntax alone does not justify a shared abstraction. Keep domain-specific code
  with its domain; avoid a miscellaneous `utils` directory becoming its owner.
- Keep dependency direction explicit and avoid cycles. Introduce a narrow
  adapter or interface at a real variation or external boundary; do not create
  factories, repositories or plugin systems for hypothetical future needs.
- Move or extract code in behavior-preserving steps before changing its rules
  when that separation makes validation easier. Update imports and consumers
  together; preserve documented public entrypoints and compatibility as needed.

## Design usable contracts

- Give each interface a clear purpose and minimal surface. Define input/output
  shapes, validation, units, nullability, error behavior and compatibility needs.
  At stateful boundaries, define ownership, lifecycle and transaction scope.
- For asynchronous or remote operations, define cancellation, timeouts,
  concurrency and retry/idempotency semantics where applicable. Keep transport
  details out of reusable domain logic; translate errors at the boundary without
  losing diagnostic context.
- Depend on only the capabilities a consumer needs. Avoid leaking vendor types,
  database rows or mutable internal objects through public contracts unless that
  coupling is intentional and documented.
- Validate the behavior consumers rely on: domain invariants, boundary failures
  and a representative integrated path. Use characterization checks where
  existing behavior is unclear. Do not write tests that only mirror file layout
  or private helper structure.

## Keep knowledge navigable

Update the established project guide with paths and symbol names that help the
next agent locate code. Capture non-obvious invariants and decision reasons,
including deliberate coupling and replacement limits. Link authoritative source
files rather than copying implementations or dependency versions. Record the
scope and limitations of measurements; remove or correct stale claims when the
underlying code changes. Do not create a second architecture inventory when an
existing one can be extended.
