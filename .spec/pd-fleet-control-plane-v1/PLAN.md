# PLAN.md — pd-fleet-control-plane-v1

Workspace (visual control plane): mission modules + live per-agent activity + swarm view;
steering designed, not built. FleetPlan v1-compatible; machine manifest in `plan.yaml`.

## Wave 0 — Registration (09/10)

- [x] T-000 · orchestrator · Intake: SPEC/CONTEXT/PLAN/RESEARCH + plan.yaml, from the owner vision (vault `control-plane-workspace.md`) + omp Agent Hub delta (ROADMAP refs). Evidence: this registration commit.
- [x] **G1 — SPEC approval (owner: Vitor)** — ✅ 09/10 (owner: "vamos atuar" — waves 1+ liberadas).

## Wave 1 — Contract + read-only surface

- [x] T-101 · coder · Activity event contract v1 ✅ 09/10 (`ACTIVITY-CONTRACT.md` + `fixtures/activity-events.example.jsonl`; parse+keys ✓; diff ✓; pytest formal em T-103) · deps: G1 · paths: `.spec/pd-fleet-control-plane-v1/`, `docs/` · acceptance: R1 — documented + deterministic fixtures.
- [x] T-102 · coder · Read-only swarm surface ✅ 09/10 (`swarm()` no collector → `swarm/agents.{md,json}`: monitor + kanban(ro) + pilot; vazio explícito; widgets `fleet-swarm-md`/`fleet-swarm-table` na aba fleet (v83) com bindings file verificados; payload `swarm-widgets.json`) · deps: T-101 · paths: `scripts/`, `.spec/pd-studio/` · acceptance: R2 — renders real data, no fabricated fields.
- [x] T-103 · test-engineer · Anti-fabrication + determinism tests ✅ 09/10 (`tests/test_control_plane_swarm.py` — 7 novos: vazio explícito, kanban ro, pilot counts, determinismo, shapes · focado: **21 passed**; guarda de contrato live em `.spec/…/tests/` (**2 passed**); determinismo do collector normalizado p/ o swarm) · deps: T-102 · paths: `tests/` · validation: focused pytest.
- [x] **G2 — Read-only surface acceptance (owner: Vitor)** — ✅ 09/10 (owner: "ok" — W2 destravada).

## Wave 2 — Hermes-native activity source (local spike)

- [x] T-201 · coder · Emit R1 events ✅ 09/10 (`scripts/pd_fleet/activity_emit.py`: state.db ro → bus `~/.hermes/activity/events.jsonl`; redação 0/0/0; watermark idempotente 21→0; collector agrega → Board mostra `hermes:desktop` running + `gateway:default`; 5 testes novos; focado **26 passed**; contrato §Local transport v1) · deps: T-101, G2 · paths: `scripts/pd_fleet/` · acceptance: R3 — local end-to-end emission with redaction.
- [x] T-203 · coder · Laya advisory spike ✅ 09/10 — Laya real (torch/multilingual), 21 eventos do bus: **sink 3/21 (14%)** · **notify 15/21 (71%)** (p≥0.5) · latência mediana ~262ms · **zero wire** · artefatos `spike-laya/{RESULTS.md,decisions.jsonl}` · veredito: **não wire** sem fine-tune/labels (zero-shot fraca confirmada); 5 testes (stub). · deps: T-101, T-201 · paths: `scripts/pd_fleet/`, `.spec/pd-fleet-control-plane-v1/` · acceptance: slots validated on real states (agreement vs deterministic rule measured; zero wire).
- [ ] T-202 · reviewer · Independent fresh-eyes review of W1–W2 incl. the Laya spike (evidence; no bypass) · deps: T-201, T-203.

## Wave 3 — Steering contract (design only)

- [ ] T-301 · orchestrator · Steering contract (steer/pause/kill/retry): commands, gates, audit, security model — design doc only; zero implementation · deps: G2 · paths: `.spec/pd-fleet-control-plane-v1/` · acceptance: R4 — reviewed contract; implementation boundary explicit.

## Wave 4 — Closeout

- [ ] T-401 · orchestrator · VERIFICATION.md (verified/deferred/blocked) + records (checkpoints, vault, ROADMAP ref) · deps: T-202, T-301.
- [ ] **G3 — Closeout (owner: orchestrator-isis)** — pending.
