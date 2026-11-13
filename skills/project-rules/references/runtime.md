# Runtime efficiency, memory and recovery

Read for project-wide optimization or when the requested change involves runtime
behavior. Inspect applicable concerns; do not add infrastructure merely to
complete a checklist. Use synthetic or explicitly authorized workloads and data.

## Measure before tuning

- Define a representative workload and the desired outcome: latency,
  throughput, peak memory, startup cost or resource consumption. Record baseline,
  workload size, environment and measurement method. Compare changes under the
  same conditions and report tradeoffs, including correctness and complexity.
- Trace the critical path and use the stack's existing profiler or diagnostics
  to locate time in CPU work, allocations, I/O, queries, serialization, locks or
  external waits. Static analysis can identify candidates; label them as
  hypotheses until measured. Do not infer speedups from shorter code.
- Address demonstrated causes such as repeated work, N+1 queries, unnecessary
  transfers or unbounded parallelism before introducing caches or new services.
  For each cache define key semantics, freshness/invalidation, size limits and
  behavior on misses or failure. Bound queues, batches and concurrency, and
  propagate backpressure or an explicit overload response.

## Analyze runtime memory

- Distinguish process RSS, managed heap, native allocations, GPU memory and
  container limits as applicable. Observe idle baseline, peak during work and
  retained memory after repeated equivalent workloads. A high RSS reading alone
  does not establish a leak; allocator behavior and intentional caches matter.
- Use allocation profiles or heap snapshots when authorized and needed. Compare
  retained objects and ownership paths across runs; inspect unbounded caches,
  queues, subscriptions, listeners, tasks, tensors and resource handles. Treat
  dumps as potentially sensitive data; avoid persisting raw payloads in reports.
- Give resources explicit owners and cleanup on success, errors and cancellation.
  Prefer bounded retention, streaming, pagination or batching where workload
  size warrants it; account for ordering, consistency and partial results.
  Do not force garbage collection as a substitute for correcting retention.
- Validate with representative repeated runs and increasing input sizes. Report
  peak and retained memory alongside throughput/latency so a memory reduction
  does not conceal an unacceptable slowdown. If profiling is unavailable, state
  that limit and distinguish implemented bounds from measured improvements.

## Recover without corrupting state

- Identify credible failures at affected boundaries: timeout, dependency outage,
  process interruption, malformed input, resource exhaustion and partial writes.
  Define what the caller observes, what state may have changed and how execution
  safely resumes. Preserve failure signals; do not convert errors into success.
- Set deadlines and bounded retries only for transient failures. Use backoff
  and jitter where suitable, honor cancellation and avoid retry multiplication
  across layers. Retry side effects only with a verified idempotency mechanism
  or reconciliation; a timeout does not prove the remote operation failed.
- Use the existing transaction model for atomic local updates. For multi-step
  work, choose checkpoints, durable job state, atomic file replacement or
  compensation according to the actual consistency needs. Define checkpoint
  validity and duplicate handling; avoid claiming exactly-once behavior without
  an end-to-end guarantee.
- Where relevant, drain in-flight work on shutdown within a bound, release
  resources and leave restartable state. Define readiness separately from
  liveness. Add circuit breaking, degraded modes or dead-letter handling only
  when the workload needs them; make degraded results visible to consumers.
- For changes affecting persistent formats, define compatibility, migration
  validation and rollback limits. A code rollback does not undo a destructive
  data migration. Do not perform live migrations or restarts as incidental
  validation.

## Verify failure behavior and operational evidence

Use isolated fault injection at the relevant boundary: a deterministic timeout,
dependency error, cancellation, interruption or duplicate delivery. Check final
state, surfaced errors, bounded attempts, released resources and successful
resume where supported. Choose cases justified by the implementation rather
than requiring every failure scenario for every edit.

Integrate useful measurements with the skill's existing logging and visualization
rules. Correlate operations and attempts without double-counting; record retry
counts, queue depth, memory, recovery duration or saturation only when measured.
Keep metric label cardinality bounded. Document recovery commands and their
preconditions in the existing runbook when operators need manual intervention.
