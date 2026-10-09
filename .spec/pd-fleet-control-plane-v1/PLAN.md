# PLAN.md — pd-fleet-control-plane-v1

Workspace (visual control plane): mission modules + live per-agent activity + swarm view;
steering designed, not built. FleetPlan v1-compatible; machine manifest in `plan.yaml`.

## Wave 0 — Registration (09/10)

- [x] T-000 · orchestrator · Intake: SPEC/CONTEXT/PLAN/RESEARCH + plan.yaml, from the owner vision (vault `control-plane-workspace.md`) + omp Agent Hub delta (ROADMAP refs). Evidence: this registration commit.
- [x] **G1 — SPEC approval (owner: Vitor)** — ✅ 09/10 (owner: "vamos atuar" — waves 1+ liberadas).

## Wave 1 — Contract + read-only surface

- [x] T-101 · coder · Activity event contract v1 ✅ 09/10 (`ACTIVITY-CONTRACT.md` + `fixtures/activity-events.example.jsonl`; parse+keys ✓; diff ✓; pytest formal em T-103) · deps: G1 · paths: `.spec/pd-fleet-control-plane-v1/`, `docs/` · acceptance: R1 — documented + deterministic fixtures.
- [ ] T-102 · coder · Read-only swarm surface (fleet tab: per-agent cards — heartbeat, last action, paths; real sources; explicit empty) · deps: T-101 · paths: `scripts/`, `.spec/pd-studio/` · acceptance: R2 — renders real data, no fabricated fields · validation: sync + Board bindings verified.
- [ ] T-103 · test-engineer · Anti-fabrication + determinism tests for collector/surface · deps: T-102 · paths: `tests/` · validation: focused pytest.
- [ ] **G2 — Read-only surface acceptance (owner: Vitor)** — pending.

## Wave 2 — Hermes-native activity source (local spike)

- [ ] T-201 · coder · Emit R1 events from Hermes sessions/bridge into observer transport (local, redacted, no network) · deps: T-101, G2 · paths: `scripts/pd_fleet/` · acceptance: R3 — local end-to-end emission with redaction · validation: spike log + tests.
- [ ] T-203 · coder · Laya advisory slots for activity routing (event→sink, flush timing, notify/persist gates) — spike on real states; wire only if validated; sink allowlist + caps in code · deps: T-101, T-201 · paths: `scripts/pd_fleet/`, `.spec/pd-fleet-control-plane-v1/` · acceptance: slots validated on real states (agreement vs deterministic rule measured; zero wire) · validation: spike log + logged decisions (calibration dataset).
- [ ] T-202 · reviewer · Independent fresh-eyes review of W1–W2 incl. the Laya spike (evidence; no bypass) · deps: T-201, T-203.

## Wave 3 — Steering contract (design only)

- [ ] T-301 · orchestrator · Steering contract (steer/pause/kill/retry): commands, gates, audit, security model — design doc only; zero implementation · deps: G2 · paths: `.spec/pd-fleet-control-plane-v1/` · acceptance: R4 — reviewed contract; implementation boundary explicit.

## Wave 4 — Closeout

- [ ] T-401 · orchestrator · VERIFICATION.md (verified/deferred/blocked) + records (checkpoints, vault, ROADMAP ref) · deps: T-202, T-301.
- [ ] **G3 — Closeout (owner: orchestrator-isis)** — pending.
