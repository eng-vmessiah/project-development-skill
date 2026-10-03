# PD Fleet → Hermes Adapter v0 — Normative Contract

**Schema family:** `pd-fleet-hermes-adapter:v0`
**Format:** deterministic local JSON contract fixtures
**Status:** `passed_local_fake_only` / `NOT_READY_RUNTIME`
**Execution mode:** `local_fake_only`

This document is normative for the G1 review. It defines the contract before any fake runtime implementation. It does not authorize Hermes/provider execution.

## 1.1 Wire requests, wire results, and review fixtures

The bundle has three separate layers:

1. **Wire request:** the operation object validated by `contracts/schema.json`. It contains only fields that cross the adapter boundary and rejects unknown fields.
2. **Wire result/entity:** the result object validated by `contracts/result-schema.json`. It contains only bounded public output and rejects unknown fields.
3. **Review fixture:** a local scenario artifact containing a request projection plus expected assertions, hostile test inputs, or simulated outcomes. Fixture metadata is never sent across the adapter boundary.

The request and result schemas are intentionally flat per operation. Review fixtures must validate their request projection against the request schema and validate returned entities against the result schema; scenario controls such as `cancel_confirmation`, `cleanup_attempt`, `forbidden_fields`, and `attempted_artifact` are not wire request fields.

## 1.2 Semantic validator rules

JSON Schema expresses structure and portable bounds. The local validator additionally enforces UTF-8 byte limits, recursive control-character rejection, cycle/non-finite-number rejection, canonical lineage/workspace equality, stored owner/generation/handle fencing, redaction before canonicalization, and the fingerprint domain algorithm. These are semantic checks, not claims that JSON Schema alone can prove them.


### Required shared fields

| Field | Type | Bound | Rule |
|---|---|---:|---|
| `schema_version` | string | — | exactly `pd-fleet-hermes-adapter:v0` |
| `operation` | enum | — | one of the six operation names |
| `lineage` | object | depth 4 | complete identity object |
| `owner` | string | 128 UTF-8 bytes | safe ID, non-empty |
| `expected_generation` | integer | non-negative | CAS/fencing value |
| `idempotency_key` | string | 128 UTF-8 bytes | required for mutating operations |
| `request_fingerprint` | string | 128 UTF-8 bytes | `sha256:` + deterministic digest |

### Lineage

```json
{
  "run_id": "run-001",
  "task_id": "task-001",
  "attempt_id": "attempt-001",
  "session_handle_id": "handle-001",
  "workspace_id": "ws-001"
}
```

All five keys are required in operation requests. `session_handle_id` may be `null` only for `prepare`; all later operations require the opaque handle. The values are safe IDs, except `null` where explicitly allowed. The handle is never a native Hermes object, PID, path, command, or credential.

The adapter must resolve the stored lineage and compare every supplied component, owner, and expected generation before mutating state. Any mismatch fails closed and leaves counters, state, events, attempts, and cleanup markers unchanged.

## 2. Operation schemas

### `prepare`

Required: shared envelope, `workspace`.

```json
{
  "operation": "prepare",
  "lineage": {"session_handle_id": null, "...": "..."},
  "workspace": {
    "workspace_id": "ws-001",
    "root_ref": "test-root-001",
    "isolation": "dedicated",
    "cleanup_policy": "always"
  }
}
```

Allowed states: `queued → preparing → ready` or `preparing → failed/cancelling`.

Invariant: `dispatch_count_delta == 0`; no runtime/provider/import/capability side effect.

### `execute`

Required: shared envelope, non-null handle, `input`.

```json
{"input": {"goal_ref": "goal-001", "payload": "bounded test input"}}
```

Allowed only from `ready`; owner and generation are fenced before fake dispatch. In G2+ fake implementation, exactly one successful non-replay execution increments `dispatch_count` by one. Real execution is forbidden by this scope.

### `observe`

Required: `schema_version`, `operation`, complete lineage, `cursor`.

No owner mutation, idempotency key, or dispatch. Cursor is an opaque bounded ID or `null`. Observe is read-only and returns at most 64 events, strictly increasing sequence, with no gaps unless `gap_detected` is explicitly returned.

### `cancel`

Required: shared envelope, non-null handle, `cancel_reason`.

```json
{"cancel_reason": "operator_requested"}
```

Allowed from `queued`, `preparing`, `ready`, and `running`. First accepted request transitions to `cancelling`. `cancelled` is legal only with `cancel_confirmed: true`; otherwise the terminal result is `failed` or `timed_out` with `cancel_not_confirmed`.

Concurrent cancellation uses the first atomic idempotency reservation as the winner; same-key replay returns the winner's bounded result, and a different key returns the current state without a second transition.

### `handoff`

Required: shared envelope, non-null handle, `handoff_reason`.

Returns a bounded `HandoffArtifact` containing only lineage references, status, evidence references, next action, and version. It must not contain prompts, chain-of-thought, raw output, credentials, PIDs, commands, absolute paths, or native handles.

### `cleanup`

Required: shared envelope, non-null handle, `cleanup_reason`.

Cleanup is an idempotent orthogonal marker: `not_cleaned → cleaning → cleaned`. It cannot rewrite the original terminal outcome. A failed cleanup preserves the original outcome, records `cleanup_failed`, and may retry under the same owner/generation without claiming `cleaned` prematurely.

## 3. Result schemas

### Result families

Each result family has its own closed schema in `contracts/result-schema.json`. `ExecutionResult` and `CleanupResult` use the common envelope fields; `HarnessEvent`, `HandoffArtifact`, and the bounded `ObserveResult` array have their own explicitly closed shapes.
### ExecutionResult

`status`: `succeeded|failed|timed_out|cancelled|blocked`.

Allowed fields: `status`, `error_code`, `output_ref`, `output_bytes`, `dispatch_count`, `attempt_id`, `session_handle_id`, `event_sequence`, `evidence_refs`. Raw output is forbidden.

### HarnessEvent

Required: `event_id`, `sequence`, `event_type`, `run_id`, `task_id`, `attempt_id`, `status`, `payload_ref`.

`payload_ref` is an evidence reference, never inline prompt/output/secret data. Sequence is monotonic per run/lane.

### CancellationResult

Required: `status`, `cancel_confirmed`, `termination_ref`, `event_sequence`.

`termination_ref` is an opaque evidence ID. `cancel_confirmed` must be `false` whenever the status is not `cancelled`.

### HandoffArtifact

Required: `artifact_id`, `artifact_version`, `lineage_ref`, `status`, `next_action`, `evidence_refs`. Maximum encoded size: 8192 bytes. No prompt, CoT, credential, PID, path, command, native handle, or raw result.

### CleanupResult

Required: `cleanup_marker`, `original_terminal_status`, `cleanup_confirmed`, `evidence_refs`. `cleanup_confirmed=true` is permitted only with marker `cleaned`.

## 4. Lifecycle matrix

| Current | Allowed next |
|---|---|
| `queued` | `preparing`, `cancelling` |
| `preparing` | `ready`, `failed`, `cancelling` |
| `ready` | `running`, `failed`, `cancelling` |
| `running` | `succeeded`, `failed`, `timed_out`, `cancelling` |
| `cancelling` | `cancelled`, `failed`, `timed_out` |
| terminal | no lifecycle transition; cleanup marker is separate |

Cleanup marker: `not_cleaned → cleaning → cleaned`. `cleanup_failed` never changes the original terminal status.

Fleet mapping: `succeeded → completed`; `failed/timed_out → failed` with reason; `cancelled → blocked` with reason; `queued/preparing/ready/running` map to same-named Fleet states where available.

## 5. Idempotency and fingerprint

- Scope: `(run_id, task_id, operation, idempotency_key)`.
- Fingerprint: SHA-256 over canonical UTF-8 JSON of the redacted request body, excluding `request_fingerprint` itself, with domain prefix `pd-fleet-hermes-adapter:v0\0request\0`.
- Same scope + same fingerprint: replay the original bounded result; no new mutation.
- Same scope + different fingerprint: `idempotency_conflict`; no mutation.
- Concurrent first use: one `reserved`, others receive `replay_in_progress`; exactly one may execute.
- Terminal replay records are retained for the scope's run; retention expiry must leave a tombstone and cannot permit key reuse.

## 6. Validation and error precedence

Validation is fail-closed and ordered:

1. envelope/schema version and unknown top-level fields;
2. type, UTF-8 byte, control-character, depth, cycle, and finite-number bounds;
3. forbidden fields and path/workspace safety;
4. complete lineage and owner/generation fencing;
5. lifecycle transition;
6. idempotency reservation/fingerprint;
7. operation-specific fields;
8. fake-only capability boundary.

Stable error codes: `unknown_field`, `input_too_large`, `forbidden_field`, `invalid_lineage`, `owner_mismatch`, `stale_generation`, `stale_handle`, `invalid_transition`, `idempotency_conflict`, `replay_in_progress`, `invalid_cursor`, `cancel_not_confirmed`, `cleanup_failed`, `dispatch_not_allowed`.

## 7. Redaction and canonicalization

The canonical pipeline is:

```text
untrusted input
→ structural validation
→ recursive redaction/rejection
→ canonical JSON (sorted keys, UTF-8, no NaN/Infinity)
→ fingerprint/hash
→ bounded persistence/evidence
```

Secrets, prompts, raw output, credentials, URLs, absolute paths, commands, PIDs, environments, and native handles are rejected at input boundaries or replaced before any hash/evidence operation. Raw sensitive values must never occur in request fingerprints, events, artifacts, errors, or stored snapshots.

## 8. Workspace safety

`root_ref` is an opaque test-plane reference matching `[a-z0-9][a-z0-9._-]{0,127}`. It cannot contain `/`, `\\`, `..`, URI schemes, drive prefixes, control characters, symlink markers, or absolute paths. `workspace_id` is bound to run/task/attempt and owner. The real root, if ever introduced in a later scope, remains execution-plane-only.
