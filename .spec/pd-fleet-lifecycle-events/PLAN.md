# Plan — PD Fleet Lifecycle Events

**Branch:** `feat/pd-fleet-lifecycle-events`
**Gate:** local/in-process, TDD RED-GREEN, sem provider/network/process.

## E1 — Event envelope + append-only local log

- **Files:** `scripts/pd_fleet/events.py`, `tests/fleet/test_events.py`.
- **Depends:** closed Supervisor/Handoff slice; existing lifecycle/checkpoint contracts read-only.
- **Implementation:** immutable validated `FleetEvent`; `EventLog(root, run_id, owner_epoch)` with atomic append, canonical JSON, checksum, idempotent replay, query by `(ordering_key, sequence)`, bounded append/query and read-only replay.
- **Acceptance:** R1–R8; hostile payload/iterator/secret/path/numeric inputs reject; duplicate same event preserves bytes; conflicting identity rejects; missing log read has no mkdir side effect; concurrent same-event append produces one record; `git diff --check`, compileall, focused and full tests pass.
- **Forbidden:** `scripts/pd.py`, orchestrator, provider, network, subprocess, legacy STATE.
- **Status:** implemented + independently verified (`29 focused`, `778 full`, fresh-eyes R1–R8 pass).

## E1R — Adversarial hardening before E2

- **Files:** `scripts/pd_fleet/events.py`, `tests/fleet/test_events.py`.
- **Depends:** E1 fresh-eyes review.
- **Acceptance:** sensitive envelope fields reject `:`, `=` and prompt/PID/handle forms; custom mappings/iterables are bounded before full materialization; log reads enforce byte/line/event limits before allocation; ancestral symlinks and unsafe final paths fail closed; unknown persisted fields reject; focused adversarial and full verification pass.
- **Status:** implemented + independently verified; E1 review closed; E2 unblocked.

## E2 — Lifecycle/checkpoint event projection

- **Files:** `scripts/pd_fleet/lifecycle_events.py`, `tests/fleet/test_lifecycle_events.py`.
- **Depends:** E1/E1R closed.
- **Implementation:** `LifecycleEventRecorder` explicit seam over `EventLog`; records bounded lifecycle transition and checkpoint-commit events with stable event IDs, run/task/owner identity, reason/status summary and checkpoint digest/summary only.
- **Acceptance:** recording never mutates `TaskLifecycle`/`Checkpoint`; same projection replay is idempotent; stale owner/sequence fails closed; checkpoint payload excludes raw outputs/evidence/secrets and remains bounded; event query/replay recovers transitions and commits deterministically; no changes to `lifecycle.py`, `checkpoint.py`, `orchestrator.py`, `STATE` or CLI.
- **Status:** implemented + independently verified (`55 focused`, `804 full`, final review CLOSED / E3 UNBLOCKED).

## E3 — Supervisor read-only event diagnostics

- **Files:** `scripts/pd_fleet/event_diagnostics.py`, `tests/fleet/test_event_diagnostics.py`.
- **Depends:** E2/E2R closed.
- **Implementation:** bounded `EventDiagnosticsReport` and `diagnose_event_log(EventLog, active_owner_epoch=...)`; aggregate only event kind, task state, checkpoint count, sequence range/gaps and bounded reasons. Return frozen/detached data.
- **Acceptance:** read-only diagnosis never creates/mutates log/state/lifecycle; stale owner events fail closed; malformed/inconsistent transitions produce deterministic degraded/blocked status; sequence gaps are reported without inventing events; raw payload/reasons/secrets are never exported; query/replay remains bounded and deterministic; no CLI/orchestrator/provider/network/process integration.
- **Status:** implemented + independently verified (`21 focused`, `825 full`, final review CLOSED / E4 UNBLOCKED).

## E4 — Supervisor facade event diagnostics

- **Files:** `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_supervisor_event_diagnostics.py`.
- **Depends:** E3/E3R closed.
- **Implementation:** add `FleetSupervisor.diagnose_events(event_log, active_owner_epoch=None, limit=...)` as a thin read-only facade over `diagnose_event_log`.
- **Acceptance:** returns the same bounded immutable report; never increments dispatch count or mutates event log, lifecycle, checkpoint or STATE; owner/limit errors propagate fail-closed; no CLI/provider/network/process integration.
- **Status:** implemented + independently verified (`6 focused`, `831 full`, final review CLOSED / E5 unblocked).

- G1: E1 RED tests exist before implementation.
- G2: E1 focused + full verification and fresh-eyes review.
