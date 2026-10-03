# Lifecycle/Event Projections — Local Read-Only Fleet Waves

Use this reference when a Fleet/Supervisor plan adds an append-only event log and derives lifecycle/checkpoint events without changing the existing runtime state machine.

## Boundary

Keep these seams separate:

```text
existing lifecycle/checkpoint state
        → explicit recorder/projection
        → bounded append-only EventLog
        → later read-only diagnostics/replay
```

The recorder is an integration seam, not a replacement for lifecycle or checkpoint persistence. The first wave should not add CLI, orchestrator, provider, network, subprocess, dispatch, or automatic retry behavior.

## E1: Event envelope and log

A reusable `FleetEvent` should be:

- immutable, versioned, and canonically serializable;
- identified by event ID plus aggregate/ordering key;
- protected by deterministic checksum/fingerprint rules;
- append-only with explicit sequence/ownership/epoch semantics;
- replayable idempotently;
- bounded before serialization (never materialize an unbounded iterator first);
- safe against secrets, prompts/CoT, filesystem paths, URLs, PIDs, handles, and unbounded nested mappings;
- resistant to duplicate sequence collisions, symlink/path traversal, and absent-store side effects.

## E2: Lifecycle/checkpoint recorder

Record only explicit transitions and commits, for example:

- `lifecycle.transition` with bounded IDs, old/new states, reason, actor/source, and deterministic timestamp;
- `checkpoint.committed` with checkpoint identity, owner/epoch, sequence, and a bounded summary/digest.

Do not mutate `TaskLifecycle` or `Checkpoint` from the recorder. Do not persist raw outputs, evidence bodies, reports, blockers, prompts, secrets, or arbitrary metadata. A checkpoint event is a projection of a successful commit, not a substitute for the checkpoint store.

## RED/GREEN and adversarial review matrix

Focused tests should cover:

1. valid envelope/log append and deterministic JSON/checksum;
2. replay/idempotency and duplicate collision rejection;
3. owner/epoch and ordering/sequence invariants;
4. invalid states, IDs, reasons, timestamps, and statuses;
5. hostile iterators/mappings and `MAX_ITEMS + 1` bounds;
6. secret/path/URL/PID/handle redaction or rejection;
7. symlink and missing-store behavior;
8. lifecycle transition projection;
9. checkpoint commit projection and raw-data exclusion;
10. read-only/no-provider/no-network/no-process/no-dispatch invariants.

## Closeout labels

Report these separately:

- **implemented:** event envelope/log and recorder exist;
- **verified:** focused/full tests and static checks ran on the current workspace;
- **reviewed:** fresh-eyes/adversarial findings were resolved;
- **deferred:** diagnostics, CLI, orchestrator, live workers, brokers, providers, and deployment;
- **blocked:** any missing decision or required runtime capability.

## E3–E5: Diagnostics, facade, and CLI

Derive diagnostics from bounded replay rather than exposing event payloads directly. The report should contain only fixed taxonomy/status fields, counts, sequence range/gaps, and detached task-state summaries. Treat duplicate/non-monotonic sequences, malformed/inconsistent transitions, hostile mutated mappings, stale ownership, and tampered checksums as first-class adversarial cases.

Expose the report through a thin Supervisor facade before adding CLI. The facade must prove dispatch-count, event bytes/mtime, filesystem, lifecycle, checkpoint, and legacy STATE invariance. Then expose a separate read-only CLI command when the source is keyed by `run_id`: dispatch it before feature discovery, do not instantiate legacy state, accept explicit store/run/owner/limit arguments, emit exact stable JSON from `to_dict()`, and provide bounded deterministic text plus shell completions. Validate the real subprocess entrypoint, missing-store no-mkdir, invalid-argument fail-closed behavior, parser compatibility, and secret/path/raw-payload non-leakage. If a shell runtime is unavailable, record that exact limitation rather than claiming completion validation.

## E6: Reconcile existing durable sources before adding an index

Before creating a new event index or persistence authority, inspect existing run storage. If a `FleetRunStore` already persists snapshots, event sequence, events, checksum, locks, and generation/CAS, prefer a read-only reconciliation adapter over a second index. Accept already-constructed store/log instances; do not instantiate replacement stores merely to inspect a missing run, because constructors may create directories.

A reconciliation report should be frozen, bounded, detached, JSON-safe, and expose only identity/status/generation/count/sequence and a fixed reason taxonomy. Compare run identity, snapshot event sequence, event-log count/last sequence, and only owner contexts that share the same namespace. Never compare unrelated owner identifiers or export raw owner/payload data. Distinguish all four source states explicitly:

```text
both absent                         → unknown
snapshot only                       → degraded / missing_event_log
existing empty log only             → degraded / missing_store_snapshot
existing empty snapshot + log       → consistent
```

`replay()` returning an empty tuple is ambiguous: it can mean missing log or an existing empty `events.jsonl`. Use safe read-only metadata (`lstat`, regular-file and symlink checks) on the supplied log path to classify presence without following or writing it. Preserve bytes, size, and mtime in tests. Treat corrupted snapshots/logs as fail-closed errors, not as empty sources.

A green reconciliation test is not enough: independently probe matching/divergent/empty/missing/corrupt/symlink cases, run the full suite, and have fresh-eyes review verify no mkdir, write, second index, broker, provider, network, or process side effects. Keep E6 separate from the later decision to expose reconciliation through Supervisor/CLI.

## E7–E8: Facade before CLI

Add reconciliation to `FleetSupervisor` as a thin delegation over the reconciliation function before adding a command. Test exact direct/facade report equivalence (and exception equivalence), frozen/detached output, dispatch count, source bytes/mtime, no `STATE`, and no filesystem creation. Only after that gate, add a dedicated read-only CLI command with explicit run-store/event-root/run-id/limit inputs. The CLI should reuse the facade, preserve stable JSON/text contracts, dispatch before legacy feature discovery when keyed by `run_id`, and never invent a second persistence source of truth.

For strict CLI read-only behavior, preflight every existing path component with `lstat` before constructing a store whose constructor may create roots/locks. Reject root/nested symlinks and non-directory roots. If a root is absent, do not construct the store and do not try to compensate with `unlink`/`rmdir` cleanup; use a no-write report helper instead. Probe race-created content, bytes/mtime invariance, empty-vs-absent logs, and the real CLI entrypoint. A missing `events.jsonl` and an existing zero-byte log are distinct facts.

## E9: Pure readiness composition

Compose a readiness view only from already-materialized immutable reports; the compositor itself must not read filesystem, provider, network, process, or legacy state. A minimal safe shape is:

```text
SupervisorDiagnosis + EventDiagnosticsReport + RunEventReconciliationReport
                                  ↓
                             ReadinessView
```

Use explicit precedence:

```text
blocked / failed / human intervention
  > degraded / slow
  > suspected / unknown
  > ready
```

Validate the allowed status enum for each component and the coherence of `status`, `reasons`, and `present_components`; reject arbitrary combinations rather than trusting a public dataclass constructor. Export only fixed reason codes such as `supervisor_blocked`, `source_degraded`, and `missing_or_unknown_source`. Do not export raw diagnosis reasons, proposals, payloads, owners, or task IDs. Keep the module import graph pure when practical: use `TYPE_CHECKING` annotations and lazy runtime imports so importing the compositor does not initialize Supervisor/run-store dependencies. Test all precedence combinations, hostile collections, frozen/detached JSON, import isolation, and non-leakage before exposing readiness through another facade or CLI.

A high test count or clean focused slice does not imply the whole Fleet roadmap is complete. The next safe wave is usually read-only Supervisor diagnostics built from query/replay.
