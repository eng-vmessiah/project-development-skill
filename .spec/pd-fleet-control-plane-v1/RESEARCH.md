# RESEARCH.md — pd-fleet-control-plane-v1

## Inputs

1. **Owner vision (09/10/2026)** — vault `control-plane-workspace.md`: workspace visual =
   plan modules (waves/tasks/gates) + swarm vivo (heartbeat/acao/arquivos por agente) +
   steering (gated). "ISIS/fleet e pra ser um workspace."
2. **oh-my-pi / omp — Agent Hub delta** (UX/feature ruler; repo ROADMAP section): roster with
   status/cost/time per worker · live transcript · steer/revive/kill without aborting the
   parent · `agent://<id>/<path>` typed yields · worktree isolation (pi-iso) · TTSR stream
   rules · advisor model. Not installed/integrated; pin-versions caveat.
3. **Existing components inventory**: `mc` tab (8 widgets, live file bindings) · `fleet` tab
   (B15a.2 canary) · observer wire/canary (B15, read-only) · kanban heartbeat ·
   machine-monitoring (jsonl + widget) · war-room (Swarm Kanban) · board connector tool-mode
   (buttons run syncs by click, `fc6e618`).
4. **Constraints**: PLAN-COCKPIT golden rule (never fabricate; empty != invented); Supervisor
   read-only increment ("Supervisor e control-plane, nao executor"); default-deny; actions
   require separate authorization.

## Gap (what is actually new)

- Standardized cross-runtime **activity event** (the missing seam) + its display.
- Per-agent live fidelity beyond run-level status (current: runs/checkpoints; wanted:
  action/file/heartbeat).
- Steering: absent by design; contract first, implementation later (separate scope).
