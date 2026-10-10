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

5. **Laya — decision layer for activity routing** (owner idea, 09/10/2026) — vault
   `Projects/isis/laya-uso-por-projeto.md` (slot "roteamento de escrita/log"): typed slots
   (choice/score/noul) for event->sink, flush timing, and notify/persist gates. Advisory only:
   sink allowlist + caps stay in code; features precomputed; fail-open; validate slots on real
   states BEFORE wiring (weak zero-shot). Local, ~93ms warm CPU, zero egress; tooling live
   (`laya_decide`, plugin laya v1.2.0; skill `decision-model-integration`).

6. **Agenttrail (sodiumsun/agenttrail) — local observability for coding agents** (09/10/2026;
   754 stars, MIT, npm `agenttrail` 0.2.0 + `agenttrail-kitchen` 0.1.0-alpha.3): two views —
   **Map** (`PLAN.md` + file changes + optional Claude hooks; component progress) and
   **Kitchen** (3D roles-as-chefs view: native todos as tickets, role contributions, deliveries;
   127.0.0.1-only, allowlisted fields, ~/.agenttrail). Observes Codex CLI + Claude Code logs
   (Cursor hooks pending; Windows unverified). Patterns worth adopting: **role vs session-count
   separation** ("chefs are responsibilities, not necessarily processes"), native-todo ingestion
   as tasks, evidence discipline (delivered = todo reported complete != deployed; "progress
   unknown" when no plan), labeled example-vs-live mode, and its lightweight PLAN.md convention
   (stable `{ids}`, `files:` globs -> components, `by:` agents). Candidate to TRY standalone on
   our Codex/Claude lanes; alpha quality, month-quiet repo (last push 2026-09-09).

7. **agent-trail/agent-trail (session-interchange spec — found while searching the above)**
   (draft 0.1.0, Apache-2.0; stalled since 2026-07-12, single contributor, CLI unpublished):
   borrow the **adapters (OpenCode / Claude Code / Pi / Codex session stores)**, the
   **live-capture protocol** (`stream.state: open|closed` + `<pending>` hash -> finalize), the
   **two-tier content_hash + fork/redacted lineage**, and **writer-strict vs reader-tolerant
   conformance (R0-R2/W)** for our contract consumers and the external-lane seam.
   Vendor patterns, not the package.

## Gap (what is actually new)

- Standardized cross-runtime **activity event** (the missing seam) + its display.
- Per-agent live fidelity beyond run-level status (current: runs/checkpoints; wanted:
  action/file/heartbeat).
- Steering: absent by design; contract first, implementation later (separate scope).
