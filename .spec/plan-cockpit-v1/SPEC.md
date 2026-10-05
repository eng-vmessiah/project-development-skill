# SPEC.md — plan-cockpit-v1

## Problem

The real PD state (phases, gates, waves, tasks, roles, KPIs, timeline) and the
execution machinery (Fleet) have no single machine-readable view:

- `pd list --json` is stale: features worked manually show phase 0 / 0 tasks / 0 checkpoints;
- real progress lives scattered across STATE.md prose, `b15a2-caminho.md`, commits, docs;
- the Board (pd-studio) covers only B15a.2, curated by hand;
- the Fleet (FleetPlan / scheduler / run_store / supervisor) is implemented but has
  never executed a real plan end-to-end.

## Goal

Close the **plan → execution → tracking** loop: a canonical aggregate derived from real
sources (`plan-cockpit.json`) + a Mission Control render on the Board + the habit of
feeding the process machine (`pd`) + one **real-execution pilot** via `pd fleet-run`
with a real runtime adapter (Hermes CLI), proving the loop end-to-end.

## Requirements (checkable)

R1. `scripts/plan_cockpit_sync.py` generates `.spec/pd-studio/plan-cockpit.json`, 100%
    derived from real sources (`pd` CLI `--json`, `.spec/*/STATE.json`, PLAN.md, fleet
    run_store/supervisor state, git, checkpoints). No data → explicit empty (rule:
    never fabricate telemetry). Shape: `meta`, `features[]` (phase, status, source,
    gates, waves/tasks with role+wave+status, KPIs: done/total, checkpoints, cycle
    time, blockers), `timeline[]`, `fleet_runs[]`.
R2. Feed the `pd`: every new PD feature records real transitions (`pd checkpoint`,
    `complete-task`, `advance`). Legacy features stay labeled `source: state-md`
    (no fabricated backfill).
R3. **Mission Control** tab (`mc`) on the Board: Overview + Features + Tasks + Timeline +
    Fleet runs, static bindings from `plan-cockpit.json` (pd-studio pattern; documented
    refresh).
R4. Skill **`plan-cockpit`**: cockpit-ready plan standard (FleetPlan-compatible task
    contracts), sync/refresh procedure, layout rules, pitfalls.
R5. **Real fleet pilot**: `examples/pd-fleet/plan.yaml` executed via `pd fleet-run` with
    the REAL runtime adapter (`hermes chat -q … --safe-mode --max-turns 1`, pinned
    cheap provider/model), explicit output dir; evidence = reports/gates/summary +
    presence in `plan-cockpit.json` + MC tab. **Its own authorization gate (G2) before
    live dispatch** (cost + external effect).
R6. Tests: sync unit tests (fixtures → expected aggregate; anti-fabrication;
    determinism), controlled smoke for the real adapter path, `pd validate --deep`
    green, no regression on relevant canons.
R7. Docs: repo `docs/` + vault (`plan-cockpit.md`; update `pd-studio.md`).

## Non-goals (v1)

- continuous/automatic live dispatch (the pilot is ONE authorized controlled run);
- opencode/claude adapters (templates exist; out of pilot scope);
- backfilling legacy feature history;
- KPIs beyond what real artifacts can derive (no invented metrics).

## Constraints

- PD Core stays Hermes-independent (decision `fleet_core_standalone_hermes_thin_plugin`);
  the pilot uses the adapter as a separate layer.
- `dispatch: live` requires its own gate/authorization (runtime-adapters doc) — the
  pilot opens THAT gate for ONE run, with declared cost cap (invocations × pinned model).
- No new credentials; no external effects beyond the pilot's explicit output dir.

## Success criteria

- [ ] `plan_cockpit.json` reproducible (two runs → same content except timestamps) and
      consistent with sources.
- [ ] MC tab renders real data (B15a.2 + other features with honest state).
- [ ] Pilot: full run of 3 tasks via the real runtime; reports+evidence+gates persisted;
      visible in the cockpit.
- [ ] `pd validate --deep` green; sync tests green; zero regression.
- [ ] Skill `plan-cockpit` installed and used (self-hosted: this feature itself fed via `pd`).
