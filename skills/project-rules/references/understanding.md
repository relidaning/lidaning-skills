# Understand a project through behavior

Use this workflow for onboarding, explanations and unfamiliar or cross-component
changes. Scale discovery to the question. Maintain a compact working model;
publish it in established project docs only when requested or durably useful.

## Frame the question and find the active system

- Identify the user's goal, the project's users, its observable inputs and
  outputs, and the behavior relevant to the request. Separate current behavior
  from desired behavior. If purpose is undocumented, infer it from entrypoints
  and examples and label the inference.
- Read applicable agent guidance and the established concepts/architecture file.
  Discover manifests, workspace boundaries, launch commands, CI and deployment
  definitions with file listings and targeted `rg` searches. Exclude generated,
  vendored and runtime data by default; inspect ignored source only when a
  concrete reference requires it. Discovery does not authorize secret or live
  data inspection.
- Distinguish source from generated artifacts, libraries from runnable services,
  and development/test startup from deployed startup. Follow wrappers to their
  implementation. In a monorepo, locate the owning package and its shared
  dependencies before expanding to other applications.
- Treat docs and remembered facts as navigation hints until checked. Code
  establishes implemented behavior; tests describe expectations for the cases
  they cover; launch/configuration files select runtime wiring. None alone
  proves what a live deployment runs. Report conflicts with concrete paths.

## Trace a representative behavior end to end

Start from a command, route, UI action, event or scheduled job relevant to the
request. Search its symbol and registrations, then follow the path to its result:

`input → dispatch → validation/auth → domain decision → state/external effect → output`

- Record actual file paths and symbols at important handoffs. Explain why each
  component exists and what it owns, rather than listing filenames. Follow
  middleware, dependency injection, plugin registration and configuration when
  imports alone do not reveal the active implementation.
- Follow data as well as calls: input shape and units, transformations, schemas,
  storage ownership, transaction boundaries, caches and externally visible
  outputs. Distinguish authoritative state from derived or cached copies.
- Follow asynchronous handoffs through producer, message/job contract, consumer
  and completion/failure reporting. Identify ordering, duplicate delivery,
  retries, cancellation and idempotency only where relevant to the behavior.
- Inspect a relevant failure path alongside the success path: rejection,
  dependency error, partial write or timeout. Identify where errors become an
  exit code, response or retry, and what state may already have changed.
- Trace configuration from declaration through precedence and loading to the
  consuming code. A setting's presence does not prove it affects this path.
  Separate environment-specific wiring from architectural requirements.

## Test the model and locate the impact

- State the behavior or invariant to preserve and the proposed change in
  observable terms. Locate its owning module, direct callers, downstream
  consumers, tests and public contracts. Search schema/configuration references
  as well as function calls; include build/deploy paths for structural changes.
- Track important claims as **observed** (source path/symbol), **inferred**
  (evidence plus reasoning), or **unknown** (specific missing evidence). Inspect
  a counterexample or alternate caller when a claim such as “all writes use this
  validator” determines correctness. A search with no matches is not proof of
  absence in a dynamically registered system.
- Use existing focused tests or an isolated reproduction when execution would
  resolve a material ambiguity. Inspect commands before running them; use
  temporary state and substitute external dependencies. Do not start paid agent
  sessions, live services or migrations for discovery. If execution is
  unavailable, distinguish source inspection from runtime verification.
- Prioritize unknowns that could change the implementation, compatibility or
  validation plan. Investigate those next. Keep unrelated gaps out of scope;
  ask only when a necessary answer cannot be obtained from authorized sources.

## Stop at a useful level of confidence

For a change, discovery is sufficient when the agent can explain the relevant
entrypoint-to-effect path, owner, preserved contract, affected consumers and
appropriate validation, with no unresolved assumption that could materially
change the approach. For an explanation, stop when the requested behavior is
supported and its limitations are clear. Do not require full-repository coverage.

For broad onboarding, sample the primary user flows and relevant background
flows across major component boundaries; explicitly identify untraced areas.
A representative trace does not establish that every execution path behaves
the same way.

Present the useful model, scaled to the request:

- Purpose and principal behaviors.
- Component responsibilities, entrypoints and dependency direction.
- A concrete execution/data trace with source anchors.
- State ownership, important contracts and operational wiring.
- Change impact and validation, or unresolved questions for an explanation.

A small component table or flow diagram can help broad work; a local fix may
need only a few sentences. Avoid mandatory reports for every edit. Persist only
stable navigation, invariants and reasons in the established concepts file;
link authoritative sources instead of duplicating implementations. Update that
model after changes, remove invalidated claims and record verification limits.
