# PLAN.md — plan-cockpit-v1

Cockpit-ready: every task declares `id · wave · role · depends_on · allowed_paths · acceptance · validation`
(FleetPlan v1-compatible; machine manifest in `plan.yaml`).

## Wave 0 — Intake ✅ (04/10)

- [x] T-000 · orchestrator · Intake + discovery (fleet machinery, docs, examples, executor templates). Evidence: this SPEC/CONTEXT + recon log.
- [ ] **G1 — SPEC approval (owner: Vitor)** — blocks waves 1+.

## Wave 1 — Foundation (A)

- [ ] T-101 · coder · `scripts/plan_cockpit_sync.py` aggregator · deps: G1 · paths: `scripts/`, `.spec/pd-studio/` · acceptance: R1 shape from real sources; empty ≠ fabricated · validation: `python3 scripts/plan_cockpit_sync.py --write` + fixtures.
- [ ] T-102 · test-engineer · sync tests (fake features + fake pd json → expected aggregate; determinism; anti-fabrication) · deps: T-101 · paths: `tests/` · validation: focused pytest.

## Wave 2 — Mission Control (A)

- [ ] T-201 · orchestrator · Board tab `mc` (tab + widgets) with real `plan-cockpit.json` data · deps: T-101 · validation: `boardstate_workspace_get` + bindings verified.
- [ ] T-202 · coder · adopt `pd` feeding in the workflow (docs + this feature: real checkpoints per gate) · deps: G1 · validation: `pd list --json` shows this feature with real data.

## Wave 3 — Skill + docs (A)

- [ ] T-301 · orchestrator · skill `plan-cockpit` (create) + repo docs + vault · deps: T-101, T-201 · validation: skill_view + standard reviewed.

## Wave 4 — Real fleet pilot (B)

- [ ] T-401 · coder · wire the real runtime adapter into the `pd fleet-run` path (spike fallback: thin runner using the existing adapter classes, documented) · deps: T-101 · paths: `scripts/pd_fleet/` · validation: dry-run with fake adapter + template smoke (no real dispatch).
- [ ] T-402 · orchestrator · pilot plan (FleetPlan + cost caps + output dir) + **G2 — owner authorization for live dispatch** · deps: T-401 · validation: plan validated + cost declared.
- [ ] T-403 · coder · pilot RUN (3 tasks via pinned hermes runtime) · deps: T-402 + G2 · validation: reports/evidence/gates/summary + cockpit presence.
- [ ] T-404 · reviewer · pilot review (real evidence vs claims; limits) · deps: T-403.

## Wave 5 — Closeout

- [ ] T-501 · orchestrator · VERIFICATION.md + records (diary/caminho/vault) + final Board + `pd` closeout (real complete-task calls).
