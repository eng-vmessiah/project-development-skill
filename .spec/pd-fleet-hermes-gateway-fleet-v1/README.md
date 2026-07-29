# PD Fleet → Hermes Gateway Fleet Bridge v1 — Discovery Scope

**Status:** `g0_hold_global_fleet_surface_unconfirmed`
**Parent evidence:** `pd-fleet-hermes-adapter-v0` — `passed_local_fake_only` / `NOT_READY_RUNTIME`
**Supersedes:** `pd-fleet-hermes-adapter-real-v1` as the current integration direction
**Scope authorization:** discovery/design only
**External effects:** disabled

## Purpose

Define and reconcile a real integration boundary between the Hermes Gateway and PD Fleet. The target is not the Hermes dashboard: Fleet is a first-class Gateway client/bridge that can become aware of user-owned Hermes sessions and later coordinate explicitly Fleet-owned tasks.

## Product direction

```text
User starts Hermes
  → Hermes Runtime / Session
  → Hermes Gateway (JSON-RPC/WebSocket/events)
  → Fleet Gateway Bridge
  → PD Fleet
  → PD Core decisions and gates
```

The dashboard and desktop app remain sibling Gateway clients. Fleet must not depend on their UI, React code, routes, or presentation state.

## Authority boundaries

- **Hermes Runtime/Gateway:** concrete sessions, providers, models, tools, capabilities, runtime state, and Gateway event delivery.
- **Fleet:** coordination state, session/task association, task lifecycle, leases, checkpoints, reconciliation, and reports.
- **PD Core:** goal, SPEC, PLAN, DAG, acceptance, gates, human decisions, merge/release decisions.
- **Dashboard:** presentation client only; never a Fleet dependency or source of truth.

## Operating modes

### `user_owned_session`

The user starts Hermes in the terminal or another Hermes surface. Fleet observes through the Gateway and records bounded metadata. Initial controls are read-only: discover, observe, heartbeat, attach metadata, and detach.

### `fleet_owned_task`

A later, separately authorized mode where Fleet associates a task with a Hermes session and may use explicit prepare/execute/cancel/handoff/cleanup operations. The v0 adapter contract remains relevant here, but it must not be imposed on every interactive user session.

## Explicit non-goals for this scope

- no dashboard integration;
- no direct `delegate_task` or private Hermes internals;
- no ACP implementation as the Fleet contract;
- no provider/model activation;
- no credentials, network exposure, cron, subprocess, or production sandbox changes;
- no live dispatch or prompt injection;
- no direct dependency on Hermes `state.db` schema;
- no production worker pool, HA, deployment, or release claim;
- no automatic cancellation or destructive control of user-owned sessions.

## Discovery exit condition

A reviewed design packet exists with:

1. actual Hermes Gateway surface and event evidence;
2. explicit Gateway → Fleet bridge contract;
3. user-owned versus Fleet-owned ownership rules;
4. event cursor, replay, reconnect, and stale-session semantics;
5. bounded metadata, redaction, capability, and authorization boundaries;
6. injected Gateway/Fleet test and local observer strategy;
7. G0–G8 evidence, risks, open questions, and a separate implementation authorization proposal.

Discovery exit is not implementation approval. Runtime code, provider access, credentials, network, live dispatch, and destructive control require a new explicit authorization.
