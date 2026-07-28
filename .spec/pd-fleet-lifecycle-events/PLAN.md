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

## E5 — CLI read-only event diagnostics

- **Files:** `scripts/pd.py`, shell completion blocks, `tests/fleet/test_cli_event_diagnostics.py`.
- **Depends:** E4 closed.
- **Implementation:** add `fleet-supervisor-events --store --run-id --owner-epoch --limit`; instantiate `EventLog` + `FleetSupervisor.diagnose_events`; output stable bounded text or exact sorted JSON report.
- **Acceptance:** command is independent of feature discovery and never opens `PDState`; missing log is `unknown` without mkdir; invalid owner/limit exits fail-closed; event bytes/mtime unchanged; old commands and completions remain compatible; no write/provider/network/process.
- **Status:** implemented + independently verified (`6 focused`, `837 full`, final review CLOSED / E6 unblocked; fish runtime parser unavailable because `fish` is not installed).

## E6 — RunStore/EventLog reconciliation

- **Files:** `scripts/pd_fleet/run_event_reconciliation.py`, `tests/fleet/test_run_event_reconciliation.py`.
- **Depends:** E5 closed.
- **Decision:** do not create a second index. `FleetRunStore` already persists snapshot, `event_sequence`, events, checksum, lock and generation/CAS.
- **Implementation:** read-only `RunEventReconciliationReport` comparing an existing `FleetRunStore` snapshot with `EventLog`: run identity, owner/generation, snapshot status, event sequence, last event sequence, bounded mismatch reasons. Accept existing store/log instances; never instantiate a missing store or write either source.
- **Acceptance:** missing artifacts fail closed without mkdir; matching empty/valid sources report consistent; sequence/status/owner divergence reports deterministic degraded reasons without exporting raw payload; bytes/mtime of both sources unchanged; bounded detached JSON-safe report; no new persistence, broker, provider, network or process.
- **Status:** implemented + independently verified (`13 focused`, `850 full`, final review CLOSED / E7 unblocked).

## E7 — Supervisor reconciliation view

- **Files:** `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_supervisor_reconciliation.py`.
- **Depends:** E6/E6R closed.
- **Implementation:** add `FleetSupervisor.reconcile_events(store, event_log, run_id, limit=...)` as a thin read-only facade over `reconcile_run_events`.
- **Acceptance:** exact report equivalence; no mutation/dispatch/STATE/filesystem writes; existing source instances only; invalid/missing/corrupt inputs fail closed; no raw payload/owner export; bounded immutable deterministic result.
- **Status:** implemented + independently verified (`6 focused`, `856 full`, final review CLOSED / E8 unblocked).

## E8 — CLI read-only reconciliation

- **Files:** `scripts/pd.py`, shell completion blocks, `tests/fleet/test_cli_reconciliation.py`.
- **Depends:** E7A closed.
- **Implementation:** add `fleet-supervisor-reconcile --store --events --run-id --owner-epoch --limit [--json]`; construct existing source handles, invoke `FleetSupervisor.reconcile_events`, emit stable bounded text or sorted JSON.
- **Acceptance:** no feature discovery/PDState; missing source distinction preserved; no mkdir/write/provider/network/process; source bytes/mtime unchanged; old commands/completions compatible; invalid path/id/epoch/limit fail closed; no raw payload/owner export.
- **Status:** implemented + independently verified (`11 focused`, `867 full`, final review CLOSED / E9 unblocked; fish runtime parser unavailable because `fish` is not installed).

## E9 — Readiness view composition

- **Files:** `scripts/pd_fleet/readiness.py`, `tests/fleet/test_readiness.py`.
- **Depends:** E8/E8R closed.
- **Implementation:** compose already-calculated `SupervisorReport`, `EventDiagnosticsReport` and `RunEventReconciliationReport` into frozen `ReadinessView`; no filesystem/provider/state reads inside the compositor.
- **Acceptance:** deterministic precedence (`blocked`/failed diagnosis > degraded source > unknown > ready); bounded fixed reason codes only; no proposals/payloads/owners/raw details; missing components are explicit; input reports remain immutable; detached JSON-safe output; no dispatch/provider/network/process.
- **Status:** implemented + independently verified (`35 focused`, `902 full`, final review CLOSED / E10 unblocked).

## E10 — Supervisor readiness facade

- **Files:** `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_supervisor_readiness.py`.
- **Depends:** E9/E9R closed.
- **Implementation:** add `FleetSupervisor.readiness_view(...)` as a thin pure delegation to `compose_readiness`.
- **Acceptance:** exact report equivalence; no dispatch/state/filesystem writes; no provider/network/process; invalid report types fail closed; no payload/owner/proposal leakage.
- **Status:** implemented + independently verified (`10 focused`, `912 full`, final review CLOSED / E11 unblocked).
