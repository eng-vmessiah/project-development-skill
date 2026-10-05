# PLAN.md — plan-cockpit-v1

Cockpit-ready: every task declares `id · wave · role · depends_on · allowed_paths · acceptance · validation`
(FleetPlan v1-compatible; machine manifest in `plan.yaml`).

## Wave 0 — Intake ✅ (04/10)

- [x] T-000 · orchestrator · Intake + discovery (fleet machinery, docs, examples, executor templates). Evidence: this SPEC/CONTEXT + recon log.
- [x] **G1 — SPEC approval (owner: Vitor)** — ✅ aprovado 04/10 (SPEC aceito; waves 1+ liberadas).

## Wave 1 — Foundation (A)

- [x] T-101 · coder · `scripts/plan_cockpit_sync.py` aggregator ✅ 04/10 (7 features reais; determinismo ✓; G1/T-000 refletidos; py_compile ✓) · deps: G1 · paths: `scripts/`, `.spec/pd-studio/` · acceptance: R1 shape from real sources; empty ≠ fabricated · validation: `python3 scripts/plan_cockpit_sync.py --write` + fixtures.
- [x] T-102 · test-engineer · sync tests ✅ 04/10 (9 passed: fixtures→agregado, determinismo, anti-fabricação, corrupt-skip, pd_view, timeline desc; ruff ✓) · deps: T-101 · paths: `tests/` · validation: focused pytest.

## Wave 2 — Mission Control (A)

- [x] T-201 · orchestrator · Board tab `mc` ✅ 04/10 (5 widgets, v57 · dados reais · reconstruída pós-reset do app · payloads reproduzíveis via `--widgets` → `mc-widgets.json`) · deps: T-101 · validation: `boardstate_workspace_get` + bindings verified.
- [x] T-202 · coder · adopt `pd` feeding ✅ 04/10 (feedings reais desde 23:12: `complete-task` ×5 + 7 checkpoints; docs: `docs/PLAN-COCKPIT.md` + skill `plan-cockpit`) · deps: G1 · validation: `pd list --json` shows this feature with real data.
- [x] T-203 · coder · automatic refresh ✅ 04/10 (cron `f9203296553a` a cada 30m · no_agent · silent-on-success · deliver local · wrapper `~/.hermes/scripts/plan_cockpit_publish.sh`; test-run manual ✓) · deps: T-101 · validation: cron fires + JSON fresh.
- [x] T-204 · orchestrator · mission selector no `mc` ✅ 04/10 (action-form + `mc/mission.md`/`mission.json` ao vivo · 3 widgets (v65) · troca testada plan-yaml→legada→volta · 13/13 tests) · deps: T-201 · validation: seleção no painel → detalhe atualizado.

## Wave 3 — Skill + docs (A)

- [x] T-301 · orchestrator · skill `plan-cockpit` ✅ 04/10 (skill criada + `docs/PLAN-COCKPIT.md` + vault `plan-cockpit.md`; lint fixes: author/When-to-Use/pointer) · deps: T-101, T-201 · validation: skill_view + standard reviewed.

## Wave 4 — Real fleet pilot (B)

- [x] T-401 · coder · wire real adapter ✅ 04/10 (thin runner `run_hermes_pilot.py`: profile READY + envelope + exact-argv allowlist + smoke fail-closed ✓ 3 tasks; live atrás de `--live --authorized` (G2); 6/6 tests) · deps: T-101 · paths: `scripts/pd_fleet/` · validation: dry-run with fake adapter + template smoke (no real dispatch).
- [x] T-402 · orchestrator · pilot plan ✅ 04/10 (PILOT-PLAN.md: 3 invocações flash ≈ centavos, caps declarados, output `.spec/pilot-runs/hermes`; **G2 aprovado pelo owner** — "autorizado") · deps: T-401 · validation: plan validated + cost declared.
- [ ] T-403 · coder · pilot RUN (3 tasks via pinned hermes runtime) · deps: T-402 + G2 · validation: reports/evidence/gates/summary + cockpit presence.
- [ ] T-404 · reviewer · pilot review (real evidence vs claims; limits) · deps: T-403.

## Wave 5 — Closeout

- [ ] T-501 · orchestrator · VERIFICATION.md + records (diary/caminho/vault) + final Board + `pd` closeout (real complete-task calls).
