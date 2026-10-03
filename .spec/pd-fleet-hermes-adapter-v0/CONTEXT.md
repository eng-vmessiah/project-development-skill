# Context — PD Fleet → Hermes Adapter v0

## Provenance

The preceding local plan closed at `LOCAL_VERIFIED` after H04/H05/H06/R06 hardening. Its `STATE.md` explicitly deferred the Hermes adapter. Vitor then selected the separately authorized continuation: open a new scope and plan the adapter slice.

## Architectural boundary

```text
PD Core
  → owns SPEC/PLAN, gates, evidence, and delivery decisions
PD Fleet
  → owns local task lifecycle, lease, report, and adapter envelope
Adapter seam
  → translates bounded Fleet context to a runtime contract
Hermes Runtime Host
  → owns concrete sessions, delegate_task, providers, tools, credentials, policy
Fake Hermes delegate
  → local deterministic test double; dispatch_count must remain zero
```

## Canonical identity

`Mission → MissionRun → Lane → Attempt → SessionHandle → WorkspaceDescriptor → Events/Artifacts`

A `Lane` remains stable across retries. An `Attempt` and opaque `SessionHandle` may be replaced by fallback/retry. Native Hermes handles, prompts, credentials, PIDs, commands, environment, and absolute paths never cross the adapter/API boundary.

## Contract direction

The v0 seam is:

```text
prepare(ContextPackage, MissionPlanSnapshot, WorkspaceDescriptor) → opaque SessionHandle
execute(SessionHandle, bounded input) → bounded ExecutionResult
observe(SessionHandle, cursor?) → bounded HarnessEvent[]
cancel(SessionHandle, idempotency key) → CancellationResult
handoff(SessionHandle) → bounded HandoffArtifact
```

`prepare` is non-dispatching. `execute` is the only dispatch boundary. `observe` is read-only. `cancel` records `cancelling` before confirmed termination permits `cancelled`. `handoff` is bounded and resumable without private session context.

## G0.1 repository seam inventory

The repository already contains two distinct runtime-related surfaces:

| Surface | Location | Current responsibility | v0 decision |
|---|---|---|---|
| Passive Fleet contracts | `scripts/pd_fleet/contracts.py`, `models.py` | versioned JSON-safe plan/output normalization, canonicalization, redaction, V2 hash | reuse as an input/evidence boundary; do not change in G0 |
| Fleet task lifecycle | `scripts/pd_fleet/lifecycle.py`, `run_store.py`, `scheduler.py` | `pending → ready → running → completed/failed/blocked/skipped`, attempts, leases, generation | remains authoritative for Fleet task state; adapter lifecycle is mapped, not substituted |
| Declarative runtime envelope | `scripts/pd_fleet/runtime_adapter.py` | `RuntimeTaskEnvelope`, `RuntimeResult`, data-only builders, optional injected runner | existing low-level compatibility seam; v0 fake lifecycle must not call it during G3 |
| Named runtime adapters | `scripts/pd_fleet/runtime_adapters.py` | provider-specific templates/output parsing and explicit runner injection | explicitly out of reach for fake-only v0; no factory/provider activation |
| Provider routing/dispatch | `scripts/pd_fleet/provider_routing.py`, `provider_dispatch.py` | provider selection and dispatch audit contracts | not reachable from v0 fake; future adapter scope only |
| Sandbox/provider modules | `sandbox.py`, `provider.py`, `provider_readiness.py`, `provider.py` | runtime capability and execution-plane concerns | forbidden from fake v0 imports/calls |

### v0 ownership and compatibility decision

The new v0 adapter is an **orchestration lifecycle seam**, not a replacement for `runtime_adapter.py` or `runtime_adapters.py`. It will use its own fake-only contract module and tests. Any later real adapter may translate from the v0 contract to the existing declarative envelope, but that translation is deferred and cannot be imported or invoked by the fake verification wave.

### Canonical lineage mapping

For the local Fleet run, the mapping is:

```text
Fleet plan → run_id → task_id/lane_id → attempt number + lease generation → opaque session_handle_id
```

- `run_id` is the `mission_run_id` equivalent for this local slice.
- `task_id` is the stable `lane_id` equivalent; the task identity survives retries.
- `attempt` is the replaceable `attempt_id` component; v0 uses a bounded opaque attempt identifier derived from the claimed task/run state, not a provider handle.
- `lease generation` is the fencing input for every mutating adapter operation.
- `session_handle_id` is an opaque fake-only correlation; it is never a native Hermes handle.
- `workspace_id` is required in the descriptor and bound to the same run/task/attempt; its root reference is test-plane-only and never public.
- events/artifacts carry `run_id`, `task_id`, `attempt_id`, sequence, and evidence reference; they are not identity substitutes.

Every mutating operation must carry the complete lineage plus owner and expected generation, or fail closed. `observe` accepts an opaque handle and cursor only after the handle's stored lineage is resolved and matched.

### Normative contract format

The contract will be versioned JSON fixtures (`pd-fleet-hermes-adapter:v0`) validated by a small local Python validator using the repository's existing canonical JSON/redaction helpers. JSON Schema is not assumed as a dependency. Every entity/operation fixture declares required fields, rejected fields, enum values, bounds, and expected stable error code. The fixture bundle is the review artifact; Python fake implementation follows only after G1/G2.

### Lifecycle and operation decisions

- Adapter states are `queued`, `preparing`, `ready`, `running`, terminal result state, and `cleaning/cleaned` as an orthogonal cleanup marker; `terminal` is not a persisted enum.
- `prepare`, `execute`, `cancel`, `handoff`, and `cleanup` are mutating/idempotent operations. `observe` is read-only and cursor-scoped.
- `prepare` reserves a handle but never dispatches. `execute` requires `ready` and atomically fences owner/generation before the fake dispatch counter changes.
- `cancel` is allowed before dispatch and while running; one idempotency winner records `cancelling`. `cancelled` requires fake termination confirmation; otherwise the result is `failed` or `timed_out`, never falsely cancelled.
- Cleanup is a separate idempotent operation/marker and cannot rewrite the original terminal result.

### Bounds and stable error taxonomy for G0 fixtures

Initial v0 limits are explicit and byte-based: IDs/owner fields 128 bytes, lineage object depth 4, metadata 16 keys with 256-byte keys and 4096 bytes total scalar content, execute input 8192 bytes, handoff 8192 bytes, single event 4096 bytes, event stream 64 events, and evidence references 128 bytes each. Oversize, cycles, non-finite numbers, control characters, unknown fields, and hostile mappings are rejected fail-closed.

Stable error codes required in fixtures: `invalid_lineage`, `owner_mismatch`, `stale_generation`, `stale_handle`, `invalid_transition`, `idempotency_conflict`, `replay_in_progress`, `input_too_large`, `forbidden_field`, `invalid_cursor`, `cancel_not_confirmed`, `cleanup_failed`, `dispatch_not_allowed`, and `unknown_field`.

Unknowns are now narrowed to fixture review details only. Any unresolved item remains `HOLD` and cannot be silently decided by implementation.
