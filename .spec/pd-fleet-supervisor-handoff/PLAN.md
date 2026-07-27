# PD Fleet Supervisor + Handoff — Implementation Plan

**Goal:** implementar contratos locais, observação read-only, reconciliation e handoff bounded sobre o PD Fleet existente.
**Architecture:** novos módulos em `scripts/pd_fleet/`; integração mínima e sem provider/rede.

## Contract rules

- Orchestrator continua único scheduler/lifecycle owner.
- Observer não muta snapshot.
- Supervisor produz propostas idempotentes; não executa ações fortes neste plano.
- Uma task possui uma única ownership epoch ativa.
- Cada tarefa registra arquivos, testes, evidência e bloqueios.
- Dependentes de task falha permanecem bloqueados.

## Wave 0 — Reconciliation gate

- [x] S0-01 — Auditar código/estado existente e preservar feature anterior.
- [x] S0-02 — Registrar SPEC, RESEARCH, CONTEXT e DECISIONS.
- [x] S0-03 — Validar spec/plan e criar checkpoint inicial; CLI deep validation atual: 10/11, bloqueado somente pela ausência de teste antes do RED.

## Wave 1 — Pure contracts (TDD)

### S1 — Health signals
- **Files:** `scripts/pd_fleet/supervision.py`, `tests/fleet/test_supervision.py`
- **Depends:** S0-03
- **Acceptance:** sinais liveness/readiness/progress/health bounded, tipos inválidos rejeitados, snapshot imutável.
- **Status:** implemented + focused GREEN (`2 passed`).

### S2 — Diagnostics and reconciliation
- **Files:** `scripts/pd_fleet/supervision.py`, `tests/fleet/test_supervision.py`
- **Depends:** S1
- **Acceptance:** diagnóstico determinístico; liveness sem progress não vira failed; eventos duplicados não duplicam proposta; estado inválido bloqueia fail-closed.
- **Status:** implemented + focused GREEN (`3 passed` in supervision slice).

### S3 — Handoff artifact
- **Files:** `scripts/pd_fleet/handoff.py`, `tests/fleet/test_handoff.py`
- **Depends:** S1
- **Acceptance:** artifact bounded/redacted, lineage preservada, próxima ação e evidências obrigatórias, campos proibidos rejeitados ou removidos, serialização estável.
- **Status:** implemented + focused GREEN (`2 passed`).

### S4 — Ownership epoch
- **Files:** `scripts/pd_fleet/handoff.py`, `tests/fleet/test_handoff.py`
- **Depends:** S3
- **Acceptance:** lane antiga não pode assumir task após epoch avançar; handoff novo é idempotente.
- **Status:** implemented + focused GREEN (`3 passed` in handoff slice).

## Wave 2 — Read-only integration

### S5 — Supervisor facade
- **Files:** `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_supervisor.py`
- **Depends:** S2, S4
- **Acceptance:** combina observer/reconciler/handoff sem dispatch/rede/processos e produz report/proposals bounded.
- **Status:** implemented + focused GREEN (`2 passed`).

## Wave 2A — Contract hardening before CLI

### S5A — Redaction, bounds and immutable artifacts
- **Files:** `scripts/pd_fleet/handoff.py`, `scripts/pd_fleet/supervision.py`, focused tests.
- **Depends:** S5; blocked until fresh-eyes review findings B1/H2/M1/M2 are resolved.
- **Acceptance:** every persisted textual field is sanitized/rejected through the canonical redaction policy; secrets, URLs, embedded absolute paths, PIDs and native handles cannot survive serialization; numeric inputs are finite and bounded; returned artifacts/reports cannot be mutated through nested mappings; adversarial tests cover hostile text and NaN/Infinity.
- **Status:** implemented + independently verified (`19 focused`, `720 full` at S5A boundary).

### S5B — Lineage, ownership and intervention contracts
- **Files:** `scripts/pd_fleet/handoff.py`, `scripts/pd_fleet/supervision.py`, `scripts/pd_fleet/supervisor.py`, focused tests.
- **Depends:** S5A; fresh-eyes findings B2/H1/H3/H4/H5/M3/M4 remediated.
- **Acceptance:** lineage explicitly represents Mission → MissionRun → Lane → Attempt → Session; handoff identity validates mission/run/task/lane/attempt/session/epoch; reason and `InterventionProposal` are typed, bounded and deterministic; diagnosis covers the complete required taxonomy; replay/collision/stale-owner cases fail closed.
- **Status:** implemented + independently verified (`24 focused`, `725 full` at S5B boundary).

### S5C — Handoff persistence boundary
- **Files:** `scripts/pd_fleet/handoff.py`, `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_handoff_persistence.py`.
- **Depends:** S5B.
- **Acceptance:** handoff can be stored and loaded through an explicit local boundary without mutating legacy STATE; writes are atomic/idempotent; evidence and status survive reload; stale or mismatched artifacts are rejected; no dispatch, network or provider is introduced.
- **Status:** implemented + independently verified (`30 focused including persistence`, `731 full` at S5C boundary).

### S5D — Exposure and concurrency hardening
- **Files:** `scripts/pd_fleet/handoff.py`, `scripts/pd_fleet/supervision.py`, `scripts/pd_fleet/supervisor.py`, focused tests.
- **Depends:** S5C; post-remediation findings resolved.
- **Acceptance:** all serialized identifiers and safety metadata are constrained/redacted; artifact evidence and diagnosis/proposal collections are bounded; health snapshots/reports expose complete lineage; report nested types are validated; local handoff persistence uses a lock/CAS boundary and read-only loads have no directory-creation side effect; adversarial concurrent-write and unsafe-identifier tests fail closed.
- **Status:** implemented + independently verified (`30 focused`, `731 full`, deep validation `11/11`).

### S5E — Report immutability micro-fix
- **Files:** `scripts/pd_fleet/supervisor.py`, `tests/fleet/test_supervisor.py`.
- **Depends:** S5D.
- **Acceptance:** nested report lineage is detached and immutable; source/report mutations cannot change serialized output.
- **Status:** implemented + independently verified (`3 focused`, `732 full`).

### S6 — CLI inspection
- **Files:** `scripts/pd.py` somente parser/output, `tests/fleet/test_cli_supervisor.py`
- **Depends:** S5E
- **Acceptance:** `fleet-supervisor-status` e `fleet-handoff-preview` em texto/JSON read-only, sem alterar STATE.
- **Status:** implemented + independently verified (`39 focused`, `737 full`, compileall and diff check pass).

## Wave 3 — Review and evidence

### S7 — Contract/spec review
- **Depends:** S5, S6; leitura independente
- **Acceptance:** matriz R1–R12, gaps e riscos.

### S8 — Adversarial grill
- **Depends:** S7; leitura independente
- **Acceptance:** testar loops, falso positivo, replay, secret redaction, duplicate ownership e stale handoff.

### S8R — Adversarial remediation before closeout
- **Files:** `scripts/pd_fleet/handoff.py`, `scripts/pd.py`, focused adversarial tests.
- **Depends:** S8 grill.
- **Acceptance:** bounded iterators reject after `MAX_ITEMS + 1`; secret-like IDs reject `:` and `=` forms; supervisor CLI emits only a bounded/redacted known fleet projection without absolute plan paths; ancestral symlink components fail closed; focused adversarial tests and full verification pass.
- **Status:** implemented + independently verified (`48 focused`, `749 full`, deep validation `11/11`).

### S9 — Fresh verification/closeout
- **Depends:** S8R
- **Acceptance:** suíte completa, CLI read-only, diff check, verification report; sem claim de provider/live operation.

## Deferred waves

- GraphQL query/subscription/SSE adapter, condicionado a UI ou múltiplos consumidores com necessidade comprovada; quando priorizado, será somente adapter sobre a interface de consulta do supervisor, não parte do domínio.
- durable event stream/broker.
- automatic retry/reassign/restart.
- external supervisor process and deployment.
- semantic LLM diagnosis.

## Verification commands

```bash
python -m pytest -q tests/fleet/test_supervision.py tests/fleet/test_handoff.py tests/fleet/test_supervisor.py
python -m pytest -q
python scripts/pd.py validate --deep --json -f pd-fleet-supervisor-handoff
python -m compileall scripts/pd_fleet
git diff --check
```
