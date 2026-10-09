# Context — pd-fleet-control-plane-v1

## Source of truth

- Owner vision (09/10/2026): vault `Projects/project-development-skill/control-plane-workspace.md`.
- Repo input: `ROADMAP.md` -> "Fleet harness research inputs — oh-my-pi (omp)" (+ Mapping).
- Existing machinery: `scripts/pd_fleet/` (supervisor/observer, read-only increment);
  `scripts/plan_cockpit_sync.py` (collector + mc widgets); `docs/PLAN-COCKPIT.md`; board
  connector / tool-mode pattern (commit `fc6e618`); war-room / Swarm Kanban (frontend track).
- State: `.spec/pd-fleet-control-plane-v1/`.

## Decisions

- D-001 — The workspace view is a **surface over real state**, not a new source of truth.
  Sources: fleet run_store/observer events, kanban heartbeat, machine monitor, plan.yaml/STATE.
  Golden rule: never fabricate telemetry.
- D-002 — **Read-only first.** Supervisor remains control-plane, not executor; v1 ships zero
  action surface. Steering is contracted (R4) but implemented only under separate
  authorization (default-deny).
- D-003 — **Cross-runtime activity contract** (R1) is the new core piece; fidelity is
  progressive and labeled per source (native Hermes = high; external lanes = partial).
- D-004 — Visual surfaces: extend `mc`/`fleet` Board tabs first (live bindings proven);
  war-room is the later full-swarm canvas. No parallel dashboard platform.
- D-005 — omp/oh-my-pi is UX/feature reference only (roster/cost/time, live transcript,
  steer/revive/kill, `agent://` addressing); not installed, not integrated, not authoritative.

## Status labels

`implemented`, `verified`, `deferred`, `blocked` are distinct; without human gate approval the
state is `NOT READY/PARTIAL`, never PASS.
