# Fleet Local Operations — Execution Plan

> **Authorized scope:** Fleet local/simulado only. No Hermes runtime, providers, network, credentials, subprocesses, push, merge, release or deployment.

## Outcome

Advance `fleet-local` from a serial simulated vertical slice to a bounded, capability-aware operational core. All claims remain local/simulated; no external-effect or exactly-once-live claim is permitted.

## Wave A — Effective adapter capability gate

**Goal:** a provider profile may select a route, but only an adapter that explicitly supports every requested capability may execute it.

1. Add strict adapter capability declaration and validation at the `RuntimeAdapter` boundary.
2. Block unsupported effective capabilities before runner/envelope/execution.
3. Emit stable `UNSUPPORTED_RUNTIME_CAPABILITY` semantics and a redacted Fleet `blocked` report.
4. Add RED-first tests for profile-vs-adapter mismatch, supported path, malformed declaration and no-effect blocking.

**Acceptance:** zero adapter/runner calls on denial; no provider/network/subprocess side effect; legacy supported behavior remains green.

**Status (verified):** completed in `e9d7e75` (`feat(pd-fleet): gate dispatch by effective adapter capability`); Fleet suite evidence: `1193 passed`.

## Wave B — Bounded parallel local execution

**Goal:** expose a bounded `--max-parallel` for `v2 run-local`, while preserving declarative waves, durable leases, deterministic commits/events and resume safety.

1. Red-first tests for CLI range `[1, 8]`, no store mutation on invalid values and propagation to scheduler/executor/orchestrator.
2. Enforce the minimum non-terminal declarative wave atomically inside scheduler selection.
3. Isolate the local simulated dispatcher per worker; persist only through the coordinator.
4. Correct reconciliation of a valid uncommitted lease after another lease in its batch commits.
5. Provide a wall-clock source to local scheduler and recover only expired leases; leave live leases untouched.
6. Prove real two-worker overlap, deterministic result/event ordering, wave barrier and partial-batch resume.

**Acceptance:** no task from a later declarative wave runs early; invalid bounds fail before store mutation; terminal tasks are never re-dispatched; local-only semantics are explicit.

**Status (verified):** completed in `568e6bd` (`feat(pd-fleet): add bounded parallel local execution`); fresh closeout evidence after Wave C: `1203 passed`, compileall, `git diff --check` and `v2_doc_paths.py` valid.

## Wave C — Retry/recovery evidence (after Wave B)

**Goal:** make the existing retry policy demonstrable and auditable through `v2 run-local` without creating a second fake runtime.

1. Add opt-in bounded deterministic simulated failures to the existing `SimulatedAdapter`.
2. Persist a bounded retry decision event before release/reclaim.
3. Apply injected backoff without real sleep.
4. Test retry allowlist/exhaustion, reload after persisted retry and no replay of completed work.
5. **Boundary:** this local slice is at-least-once for any future external effect; it must not claim exactly-once without a durable idempotency key/outbox or cooperative lease renewal. The SimulatedAdapter remains pure and side-effect-free.
6. **Audit proof:** retry decision is persisted before release; a recovery fixture may stop only after that durable decision and must resume deterministically.

**Known live follow-ups (not Wave C acceptance):** lease heartbeat, external-effect idempotency key/outbox, commit-pending recovery, and lease-token reconciliation independent of global generation.

**Status (verified):** completed locally in this commit (`feat(pd-fleet): add deterministic retry recovery fixtures`). Fixtures are closed (`success|retry-once|fail-always`); retry decisions are persisted before release; backoff is injected/no-op; allowlist, exhaustion/readiness and completed-run no-replay were verified with `1203 passed`. This remains local/simulated and does not change `NOT_READY_HERMES_SEAM`.

## Cross-wave gates

- Strict RED → GREEN tests for every production behavior.
- Focused suite after each task; full `tests/fleet`, compileall, diff-check and docs checker after each wave.
- Independent spec and quality reviews before commit.
- Update state/docs only with verified evidence; `fleet-hermes` remains `NOT_READY_HERMES_SEAM`.
