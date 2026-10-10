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

6. **agent-trail — open interchange format for coding-agent sessions** (reference, 09/10/2026;
   github.com/agent-trail/agent-trail): draft spec (Apache-2.0) + Bun tooling for session JSONL
   trails; adapters already parse **OpenCode, Claude Code, Pi (omp upstream), Codex** session
   stores. Borrow: (a) **adapters = the external-lane path** for real activity rows (fidelity
   upgrade over raw tail; OpenCode adapter reads file + sqlite sessions); (b) **live-capture
   protocol** (`stream.state: open|closed` + `<pending>` hash -> finalize); (c) **two-tier
   content_hash** + `redacted_from`/`fork_from` lineage tiers; (d) **writer-strict vs
   reader-tolerant conformance (R0-R2/W)** for our contract consumers; (e) redaction as a
   lineage-producing pipeline. Do NOT depend on it: repo stalled since 2026-07-12, single
   contributor, 0 stars, CLI unpublished (npm) — vendor patterns, not the package.

## Gap (what is actually new)

- Standardized cross-runtime **activity event** (the missing seam) + its display.
- Per-agent live fidelity beyond run-level status (current: runs/checkpoints; wanted:
  action/file/heartbeat).
- Steering: absent by design; contract first, implementation later (separate scope).
