# PD Fleet → Hermes Adapter v0 — Specification

## Goal

Create a versioned, local-only contract for translating a Fleet task/run envelope into a controlled runtime adapter, with a deterministic fake delegate suitable for offline verification and no live Hermes/provider effects.

## Requirements

### R1 — Boundary ownership

- PD remains the decision and human-delivery authority.
- Fleet may request an adapter operation only for an already admitted local task.
- Hermes remains the authority for concrete runtime/session/provider capability.
- The adapter cannot approve gates, alter scope, merge, release, or declare production readiness.

### R2 — Identity and lineage

Every operation carries or resolves the complete lineage:

`mission_id → mission_run_id → lane_id → attempt_id → session_handle_id`

Owner scope and run identity must be validated on every operation. A fallback creates a new attempt and replaces the active opaque session correlation without replacing the lane.

### R3 — Lifecycle

The contract uses these states:

```text
queued → preparing → ready → running →
  succeeded | failed | timed_out | cancelling
cancelling → cancelled | failed | timed_out
```

`cleaned` is never a lifecycle state. It is an orthogonal cleanup marker applied by `cleanup` after a terminal result and cannot rewrite that result.

- `prepare` cannot produce provider/tool dispatch.
- `execute` is the sole dispatch boundary.
- `observe` cannot mutate lifecycle state.
- `cancelled` requires a fake termination confirmation.
- timeout is distinct from cancellation.
- cleanup is idempotent and independently evidenced.

### R4 — Idempotency and replay

- Every mutating operation has an idempotency key and request fingerprint.
- Same key + same fingerprint replays the existing bounded result.
- Same key + different fingerprint returns a stable conflict.
- Replay never increments dispatch count, attempts, or cleanup count unexpectedly.
- Event sequence is monotonic; observe supports a bounded cursor and deterministic replay.

### R5 — Bounded public data

The public contract may expose only bounded IDs, status, timestamps, counters, error category, provider/model labels when already authorized, and evidence references. It must reject or redact:

- prompts and chain-of-thought;
- credentials, tokens, secrets and raw environment;
- native Hermes handles, PIDs, commands and absolute paths;
- unbounded raw outputs;
- control characters/newlines in IDs;
- oversized goals, handoffs, event payloads or metadata.

Redaction happens before canonicalization, hashing, persistence, or evidence generation.

### R6 — Fake delegate safety

The fake runtime is deterministic and local. It records `dispatch_count`, but its dispatch method must not call Hermes, a provider, network, subprocess, gateway, MCP, Discord, or filesystem outside the test workspace. The canonical no-dispatch assertion is `dispatch_count == 0` for `prepare` and `dispatch_count == 1` only for the explicitly invoked fake `execute` path.

### R7 — Workspace and cleanup

Use an opaque workspace identifier and a non-sensitive root reference. Absolute paths stay implementation/test-plane-only. Cleanup is idempotent and verified for success, failure, timeout, and cancellation. The fake `prepare` transition is atomic: it exposes no partial-preparation state; recovery of partially-created real workspaces is explicitly deferred to the future real adapter scope.

### R8 — Compatibility

Existing Fleet V2 local lifecycle, reports, gates, and local example remain unchanged unless a RED test demonstrates a contract defect. No live adapter is added as a side effect of this wave.

## Acceptance criteria

1. A machine-readable or otherwise parseable contract exists for every operation and entity.
2. A fake adapter can prove prepare/no-dispatch, execute/result normalization, observe/read-only, cancel confirmation, handoff bounds, replay idempotency, and cleanup.
3. Negative tests cover ownership/lineage mismatch, stale handle, idempotency conflict, oversized input, forbidden fields, invalid transition, and terminal replay.
4. Independent verification can reproduce all claims from the shared worktree.
5. No provider, network, subprocess, credential, gateway, OMH, or live Hermes path is reachable from the fake verification wave.
6. Documentation labels all results `local_fake_only` and does not imply runtime or release readiness.

## Explicitly deferred

Real Hermes adapter, live delegate invocation, provider routing, credential handling, subprocess cancellation, production sandboxing, deployment, operational observability, and OMH integration require a later scope change.
