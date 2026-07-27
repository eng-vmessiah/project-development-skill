# Fleet hardening: contracts, reconciliation, and review loops

Reusable guidance extracted from a multi-wave Fleet orchestration hardening pass.

## Canonical identity across boundaries

- Preserve the original canonical V2 payload before converting it to runtime models.
- Runtime model expansion/defaults and alias conversion must never silently redefine identity.
- `plan_hash` must be computed by one shared canonical contract and compared at every durable boundary (orchestrator, run store, checkpoint, reconciliation).
- Add an integration test that hashes the raw V2 payload through the shared contract, persists it in the store-shaped envelope, then reconciles through the orchestrator.
- Test alias-shaped V2 input (`taskId`, `agentId`, dependency/path aliases) and assert runtime conversion does not change the raw hash.

## Strict reconciliation envelope

When an explicit V2 reconciliation context is supplied, fail closed unless the envelope contains and validates:

```text
plan_hash, run_id, owner, generation, checkpoint, leases, events
```

Validate relationships, not only field shapes:

- `lease.task_id` exists in the loaded plan;
- lease owner and generation equal the run owner/generation;
- lease ID is non-empty and correctly typed;
- checkpoint run ID/plan hash/generation match the run;
- checkpoint V2 has a complete sealed envelope and checksum;
- V1 checkpoints go through the real V1 validator, not a shallow fixture check;
- event sequence is monotonic in stored order (`[1, 2, ..., n]`), not merely a sorted set;
- orphan running tasks block before dispatch.

Activate V2 reconciliation explicitly. Do not infer it from ambiguous legacy `context` keys; preserve V1 callers.

## Fail-closed hostile-input probes

For each boundary, add regressions for:

- non-mapping inputs and non-string mapping keys;
- hostile `__str__` keys;
- cycles, callables, `NaN`, infinity, and unsupported objects;
- forged checksum, unknown nested fields, unknown task IDs;
- secrets, URLs, POSIX/Windows/UNC/WSL paths in diagnostics;
- mutation of both input and returned issues/events;
- zero adapter/dispatcher calls on every invalid case.

Normalize expected malformed-input errors to stable contract codes. Keep a separate sanitized code for internal canonicalization failures rather than swallowing all exceptions as one generic error.

## Fresh-eyes review protocol

A task is not PASS because focused/full tests are green. For each non-trivial wave:

1. Run targeted, related-boundary, full-suite, compile, and diff hygiene gates.
2. Dispatch independent spec, security/adversarial, and quality reviews.
3. Independently verify reviewer claims, test paths, file existence, and counts.
4. Fix confirmed findings, then rerun fresh reviews.
5. Distinguish findings in the current task's ownership from cross-module follow-ups; never silently expand ownership.
6. Record deferred provider/store/runtime findings explicitly in the plan.

A green phase can still be `PARTIAL` when provider enablement, native sandboxing, real CLI dispatch, human verification, or deployment/runtime integration is not exercised.

## Common residuals to probe in adjacent modules

- Provider boundaries: reject non-finite numbers, cycles, non-string keys, and inline textual secrets in metadata.
- Durable stores: reject unknown task IDs, malformed nested leases/events, non-finite lease durations, non-string event keys, and cyclic event payloads with stable store errors.
- Executors: do not treat a boolean capability flag as a sandbox; require an explicit trusted runner/capability and default-deny.

These adjacent findings may belong to later tasks, but they must be recorded rather than mistaken for a clean global PASS.
