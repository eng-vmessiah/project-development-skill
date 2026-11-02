# PLAN.md — pd-fleet-control-plane-v1

Workspace (visual control plane): mission modules + live per-agent activity + swarm view;
steering designed, not built. FleetPlan v1-compatible; machine manifest in `plan.yaml`.

## Wave 0 — Registration (09/10)

- [x] T-000 · orchestrator · Intake: SPEC/CONTEXT/PLAN/RESEARCH + plan.yaml, from the owner vision (vault `control-plane-workspace.md`) + omp Agent Hub delta (ROADMAP refs). Evidence: this registration commit.

## Wave 1 — Contract + read-only surface

- [x] **G1 — SPEC approval (owner: Vitor)** — ✅ 09/10 (owner: "vamos atuar"). Anexado à wave que o gate destrava, igual ao G2.
- [x] T-101 · coder · Activity event contract v1 ✅ 09/10 (`ACTIVITY-CONTRACT.md` + `fixtures/activity-events.example.jsonl`; parse+keys ✓; diff ✓; pytest formal em T-103) · deps: G1 · paths: `.spec/pd-fleet-control-plane-v1/`, `docs/` · acceptance: R1 — documented + deterministic fixtures.
- [x] T-102 · coder · Read-only swarm surface ✅ 09/10 (`swarm()` no collector → `swarm/agents.{md,json}`: monitor + kanban(ro) + pilot; vazio explícito; widgets `fleet-swarm-md`/`fleet-swarm-table` na aba fleet (v83) com bindings file verificados; payload `swarm-widgets.json`) · deps: T-101 · paths: `scripts/`, `.spec/pd-studio/` · acceptance: R2 — renders real data, no fabricated fields.
- [x] T-103 · test-engineer · Anti-fabrication + determinism tests ✅ 09/10 (`tests/test_control_plane_swarm.py` — 7 novos: vazio explícito, kanban ro, pilot counts, determinismo, shapes · focado: **21 passed**; guarda de contrato live em `.spec/…/tests/` (**2 passed**); determinismo do collector normalizado p/ o swarm) · deps: T-102 · paths: `tests/` · validation: focused pytest.
- [x] **G2 — Read-only surface acceptance (owner: Vitor)** — ✅ 09/10 (owner: "ok" — W2 destravada).

## Wave 2 — Hermes-native activity source (local spike)

- [x] T-201 · coder · Emit R1 events ✅ 09/10 (`scripts/pd_fleet/activity_emit.py`: state.db ro → bus `~/.hermes/activity/events.jsonl`; redação 0/0/0; watermark idempotente 21→0; collector agrega → Board mostra `hermes:desktop` running + `gateway:default`; 5 testes novos; focado **26 passed**; contrato §Local transport v1) · deps: T-101, G2 · paths: `scripts/pd_fleet/` · acceptance: R3 — local end-to-end emission with redaction.
- [x] T-203 · coder · Laya advisory spike ✅ 09/10 — Laya real (torch/multilingual), 21 eventos do bus: **sink 3/21 (14%)** · **notify 15/21 (71%)** (p≥0.5) · latência mediana ~262ms · **zero wire** · artefatos `spike-laya/{RESULTS.md,decisions.jsonl}` · veredito: **não wire** sem fine-tune/labels (zero-shot fraca confirmada); 5 testes (stub). · deps: T-101, T-201 · paths: `scripts/pd_fleet/`, `.spec/pd-fleet-control-plane-v1/` · acceptance: slots validated on real states (agreement vs deterministic rule measured; zero wire).
- [x] T-202 · reviewer · Independent fresh-eyes review of W1–W2 incl. the Laya spike (evidence; no bypass) ✅ 02/11 — verdict **APPROVED WITH RESERVATIONS** (no BLOCKER/HIGH); RISCO-1..4 + NIT-1..3 fixed, NIT-4 → T-401; dispositions in `CONTEXT.md` §T-202; delta re-executed: `pytest tests/ -q` 1434 passed, live `hermes:desktop` now `stale`. · deps: T-201, T-203.
- (futuro, pós-W2 — não é task desta missão) Lanes externas: (a) parsers tipo agent-trail spec (OpenCode primeiro) + (b) observação tipo Kitchen p/ lanes Codex/Claude (roles/todos) — RESEARCH#6/#7.

## Wave 3 — Steering contract + correção do coletor

- [x] T-301 · orchestrator · Steering contract ✅ 02/11 (`STEERING-CONTRACT.md`, 419 linhas: 5 verbos, tiers T0–T3 default-deny, envelope com idempotency key, fencing por `owner_epoch`, owned×attached, audit hash-chained, D-006/D-007) · grounding executável `steering/probes/` (**TOTAL=6 PASS=5 FAIL=1**, FAIL = refutação argv-URL por design) · review independente GLM-5.3-Flash **PASS_WITH_RESERVATIONS** (0 BLOCKER/1 HIGH/3 MEDIUM/2 LOW/1 NIT, todos dispostos) + delta no canvas pelo Vigia **PASS** (2 NITs fechados) · deps: G2 · paths: `.spec/pd-fleet-control-plane-v1/` · acceptance: R4 — reviewed contract; implementation boundary explicit.

- [x] T-402 · coder · Coletor conta `completed` como terminal ✅ 02/11 (a superfície publicada mostrava 6/9 com 7 tasks prontas: T-202 estava `completed` e o coletor só reconhecia `done`) — `scripts/plan_cockpit_sync.py` ganhou `_is_task_done`; teste `test_plan_yaml_counts_completed_as_terminal`; focado **15 passed**, suíte **1435 passed / 1 skipped**; coletor agora reporta **7/9** · deps: — · paths: `scripts/`, `tests/` · acceptance: número do painel = número do plan.yaml.

## Wave 4 — Closeout

- [x] T-401 · orchestrator · VERIFICATION.md + records ✅ 02/11 (`VERIFICATION.md` com verified/deferred/blocked/not-claimed e comando de reprodução em cada linha; `pd validate --deep` **11/11**, `pd verify` **all passed**; 11 checkpoints, vault W1–W3, `ROADMAP.md:141`) · deps: T-202, T-301.
- [x] **G3 — Closeout (owner: orchestrator-isis)** — ✅ 02/11. 10/10 tasks, 5/5 waves, G1–G3 approved; 6 itens deferred explícitos e 2 blocked externos (Maestri 0.28.2; publish aguardando o dono).
