# SPEC.md — pd-fleet-control-plane-v1

## Problem

The Fleet/Mission Control surface today is read-only and scattered: the `mc` tab renders
mission modules (features/tasks/timeline/plan) and the `fleet` tab shows the B15a.2 canary,
but there is no single workspace view that shows, per worker, LIVE state — heartbeat,
current action, files being touched — nor a swarm view of several agents, nor any steering.
Intent (`.spec`) and execution surfaces are not connected into one operational picture.

## Goal

Turn the PD Fleet control plane into a **visual workspace** over real state: mission modules
(waves/tasks/gates) + live per-agent activity (heartbeat · action · paths) + swarm view +
a *designed* (not implemented) steering contract. Read-only first; every pixel derived from
real sources; never fabricate telemetry.

## Requirements (checkable)

R1. **Activity event contract v1** — one cross-runtime event schema
    (`{agent_id, run_id, ts, kind: tool|file|status|heartbeat, action, paths[], status}`),
    redaction rules, example fixtures; documented in this mission + `docs/`.
R2. **Read-only swarm surface** — Board surface rendering per-agent cards (heartbeat · last
    action · files/paths · status) + mission modules, from REAL sources (fleet
    run_store/observer events, kanban heartbeat, machine monitor, plan.yaml/STATE); missing
    data → explicit empty (PLAN-COCKPIT golden rule). Local only.
R3. **Hermes-native activity source (local spike)** — emit R1 events from Hermes
    sessions/bridge into the observer transport, redacted, no network; progressive fidelity
    for external lanes (tail/RPC) documented, not implemented.
R4. **Steering contract (design only)** — steer/pause/kill/retry contract, security model,
    audit trail; explicit boundary: implementation is a separate scope requiring its own
    authorization. Zero action surface in v1.
R5. **Tests** — anti-fabrication (empty when source missing), determinism, contract fixtures;
    `pd validate --deep` green; no regressions on touched canons.
R6. **Records** — VERIFICATION.md (verified/deferred/blocked), checkpoints via `pd`, vault
    updates (`control-plane-workspace.md`), ROADMAP cross-refs.

## Constraints

- Local/simulated only: no network, no provider activation, no live dispatch, no deployment.
- Default-deny; read-only before actions; deterministic policies; redaction before persist.
- Never fabricate telemetry (empty != invented).
- Fidelity is explicit per source (native Hermes = high; external = partial; unknown = labeled).

## Non-goals (v1)

- Implementing steering/actions; external-lane adapters; production sandbox; HA/multi-host;
  a parallel dashboard platform (this extends the Board/war-room, not replaces them).

## Success criteria

- [x] Swarm surface renders real per-agent activity for at least one live local mission, no fabricated fields. *(T-102/T-103 — `swarm/agents.md` 10 rows, missing source = `sem fonte`; VERIFICATION.md#r2.)*
- [x] Activity contract documented + fixtures passing. *(T-101/T-103 — `ACTIVITY-CONTRACT.md`, `docs/ACTIVITY-EVENTS.md`, fixtures; VERIFICATION.md#r1.)*
- [x] Hermes-native spike emits redacted events end-to-end (local). *(T-201 — 21 events on `~/.hermes/activity/events.jsonl`, watermark idempotent; VERIFICATION.md#r3.)*
- [x] Steering contract reviewed; zero action surface shipped in v1. *(T-301 — GLM `PASS_WITH_RESERVATIONS` + Vigia delta `PASS`; `CAPABILITIES_V1` still `{observation}`; VERIFICATION.md#r4.)*
- [x] `pd validate --deep` green; VERIFICATION.md with explicit deferred items. *(T-401 — 11/11 at closeout; 12/12 after the `plan.yaml` check landed post-G3 — see `POST-G3.md`, since `VERIFICATION.md` is frozen at the approved state.)*
