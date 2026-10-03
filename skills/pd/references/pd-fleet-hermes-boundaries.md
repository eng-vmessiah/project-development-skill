# PD/Fleet/Hermes boundary reference

## Canonical ownership

| Layer | Answers | Owns |
|---|---|---|
| PD Core | What should be built and how is it accepted? | goal, discovery, SPEC, PLAN, project gates, acceptance, human decisions, `.spec` artifacts |
| Fleet | How is a plan's task execution coordinated and evidenced? | task contracts, DAG/waves, eligibility, leases, attempts, checkpoints, reports, events, reconciliation |
| Hermes | How is an agent actually run? | session, model/provider, credentials, tools, capability grants, sandbox/backend, `delegate_task`, cron, gateway |
| OMH | What workflow patterns are worth learning? | reference only; no authority, store, scheduler, provider, or completion status |

## Source-of-truth rules

- PD `.spec` is authoritative for development intention, scope, acceptance, and product decisions.
- Fleet run state is authoritative for execution lifecycle, attempts, leases, reports, and evidence reconciliation.
- Hermes is authoritative for the live agent session and effective runtime capabilities.
- A subagent's textual summary is evidence input, never completion authority.
- OMH must not create a competing task/status/store model in the active runtime.

## Correct Hermes integration

The integration belongs at the Hermes host boundary, not inside the pure Fleet library:

```text
Fleet: claim task and issue bounded execution envelope
  -> Hermes adapter: call delegate_task
  -> Hermes: return subagent summary/result
  -> adapter: normalize to AgentReport
  -> Fleet: validate task/run/attempt/lease/evidence
  -> Fleet: commit or mark failed/blocked
```

`delegate_task` is suitable for bounded synchronous subwork. It is not a durable queue, scheduler, distributed worker pool, or substitute for Fleet persistence. If the parent is interrupted, the child lifecycle is not a promise of durable completion; recovery must be explicit and evidence-based.

## Cron and sandbox decisions

Cron and external triggers belong to Hermes. Fleet may receive a `run_id`, but should not own time scheduling, messaging delivery, webhooks, or gateway lifecycle.

A production sandbox is not required for simulated/offline Fleet execution or for delegation performed by Hermes under Hermes-owned runtime policy. It becomes a release prerequisite when Fleet directly starts subprocesses, executes validation commands, runs untrusted code, or grants shell/network/provider capabilities. A local process runner with argv allowlisting and timeouts is defense in depth, not host isolation.

## Scope classification

### Keep in PD Core

- discovery, SPEC, PLAN, phases, acceptance criteria;
- product/development gates and human approval;
- project `.spec` state and verification interpretation;
- prompt refinement as a project artifact.

### Keep in Fleet

- versioned task/wave/report contracts;
- DAG validation and ready-task calculation;
- lifecycle, retries, leases, fencing, checkpoints;
- event log, reconciliation, evidence binding;
- executor interface and simulation adapter.

### Keep behind runtime adapters

- Hermes/Codex/OpenCode/Claude translation;
- provider-specific output parsing;
- command construction;
- provider readiness and capability mapping.

### Do not add to Fleet by default

- cron/autopilot;
- a second memory or state system;
- direct credentials/auth discovery;
- provider/model selection authority;
- a daemon or distributed worker platform;
- direct execution without an injected trusted runner.

## Naming guidance

Prefer `TaskDispatcher` for Fleet coordination and `RuntimeAdapter` for concrete execution translation. Avoid using a generic `Dispatcher` for both. Keep `TaskSpec` (PD/Fleet contract), `RuntimeTaskEnvelope` (authorized execution request), and `RuntimeResult` (normalized runtime output) distinct.
