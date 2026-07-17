# PD Fleet Orchestration V2 — Research

**Data da verificação:** 2026-07-17  
**Branch/commit:** `feat/pd-fleet-orchestration-plan` / `e1cdb4e`  
**Escopo:** planejamento apenas; nenhum código ou documento V1 é alterado.

## Estado atual verificado

- Baseline executado nesta revisão: `pytest -q` → **278 passed** (192 testes fleet conforme contexto do handoff).
- O domínio está em `scripts/pd_fleet/` com `models.py`, `validation.py`, `lifecycle.py`, `state.py`, `checkpoint.py`, `dispatch.py`, `orchestrator.py`, `contracts.py`, `gates.py` e `evidence.py`.
- `scripts/pd.py` continua sendo a integração CLI e preserva o comportamento legado; `scripts/pd` é wrapper.
- V1 já tem plano estruturado, lifecycle, gates, reports sanitizados e checkpoint injetável. O `FleetOrchestrator` valida antes de executar e aceita `max_parallel`, mas o loop atual despacha cada item sequencialmente (`for task_id in batch`); portanto **não há paralelismo real**.
- `TaskSpec.validation_commands` é uma lista declarativa. O domínio não deve interpretar isso como autorização para abrir shell.
- Reports são serializáveis/redigidos, mas o contrato V1 ainda permite semântica fraca: `outputs`, `tests`, `blockers`, `assumptions`, `decisions` e timestamps podem chegar vazios/default.
- Persistência/recovery aparece como hooks/checkpoints; falta um `FleetRunStore` independente do CLI, com ownership de run, atomicidade, idempotência e replay definidos.
- Saídas ainda podem refletir texto de executor/provider, timestamps e caminhos absolutos; falta uma representação normalizada, estável e independente de ambiente.
- Não há provider externo habilitado. Qualquer adapter futuro deve ser contrato default-deny, sem credenciais, rede ou dispatch implícitos.
- O gate de verificação humana permanece pendente/não aprovado; não deve ser descrito como PASS.
- V1 e legado devem ser preservados. Diretórios relevantes existentes: `tests/fleet/`, `examples/pd-fleet/`, `skills/pd/`, `docs/`, `ROADMAP.md`, `README.md`.

## Reconciliation matrix

| Área | V1 | Evidência | V2 decisão |
|---|---|---|---|
| Baseline/compatibilidade | **Verified** | 278 testes passam; CLI legado existente | Congelar baseline e adicionar testes sem mudar contratos legados |
| DAG/readiness/ownership | **Verified/partial** | `validation.py`, testes fleet | Reconciliation persistida e conflito considerando leases/runs |
| Deterministic output | **Partial** | ordenação existe, mas payload pode conter timestamp/path cru | Normalizar, ordenar, canonicalizar e redigir |
| FleetRunStore | **Partial/open** | hooks/checkpoint, acoplamento indireto | Store explícito, CLI como adapter fino |
| Checkpoint persistence | **Partial** | `checkpoint.py` e resume | atomic write, generation, checksum, recovery e idempotency |
| Validation commands | **Partial** | declarativos, sem executor seguro | executor separado, allowlist/sandbox opt-in; shell default deny |
| AgentReport | **Partial** | `TaskReport` com defaults permissivos | schema strict, completeness por status e rejeição de ambiguidade |
| Parallelism | **Open** | `max_parallel` apenas batching serial | só após ownership/persistência; executor bounded real e commit determinístico |
| Provider boundary | **Open** | dispatch local/injetável | contrato/adaptador externo não habilitado por padrão |
| Metrics/audit | **Partial** | evidence/hooks | eventos append-only, contadores sem segredos e correlation IDs |
| Human verification | **Open** | gate não aprovado | gate humano obrigatório, evidência e decisão persistidas |

## Findings e decisões

1. A fonte de verdade será um store de domínio por `run_id`; CLI apenas traduz comandos/saída.
2. O estado calculado deve ser reconstruível por eventos/checkpoints e reconciliado contra o plano atual antes de qualquer execução.
3. Ordem determinística é requisito de segurança operacional: IDs, waves, eventos, reports e JSON canônico usam ordenação explícita; wall-clock e paths absolutos não entram no contrato lógico.
4. `validation_commands` descreve intenção. Execução exige `ValidationExecutor` explícito, allowlist de comandos e sandbox aprovado; ausência de executor significa erro/skip explícito, nunca shell.
5. Provider externo é apenas protocolo/adaptador futuro, default-deny, sem rede/credencial/dispatch nesta V2.
6. Paralelismo real só será ligado depois de leases/ownership, commit atômico e testes de corrida; o modo local seguro continua disponível.
7. Report incompleto não pode completar task. Redação ocorre antes de persistir e antes de métricas.

## Não-objetivos

- Não reescrever `scripts/pd.py` nem quebrar `STATE.json`/`STATE.md` legados.
- Não executar comandos arbitrários, shell, scripts fornecidos pelo plano ou comandos remotos.
- Não habilitar Hermes/OpenCode/Claude ou outro provider externo, rede, credenciais ou daemon distribuído.
- Não criar scheduler distribuído, locks cross-host ou exactly-once impossível de provar.
- Não autoaprovar review, grill ou verificação humana; não declarar V2 PASS nesta fase.
- Não alterar código agora: este diretório contém somente o plano de implementação futura.

## Matriz auditável de findings V1 → V2

Esta matriz é o índice de auditoria obrigatório. `failing test exacto` nomeia o teste que deve falhar antes da implementação; `verification command/expected` é copy-pasteável; `evidence artifact` é o artefato a anexar ao handoff. Nenhum finding pode ser marcado fechado apenas por texto ou por uma suíte verde.

| finding | V2-R | task T2 | failing test exacto | verification command/expected | evidence artifact |
|---|---|---|---|---|---|
| B-01 | R3, R7, R12 | T2-10,T2-15 | `tests/fleet/test_v2_local_execution.py::test_local_fleet_run_end_to_end` | `pytest -q tests/fleet/test_v2_local_execution.py -k end_to_end` → 1 passed, sem provider/rede | `artifacts/v2/B-01-local-run.json` + stdout/exit-code |
| H-01 | R3, R6, R8 | T2-10 | `tests/fleet/test_v2_local_execution.py::test_retry_policy_records_attempts_and_backoff` | `pytest -q tests/fleet/test_v2_local_execution.py -k retry_policy` → retryable repete até limite; não-retryable não repete | `artifacts/v2/H-01-retry.json` |
| H-02 | R1, R8 | T2-09 | `tests/fleet/test_v2_reconciliation.py::test_inputs_and_blocked_when_gate_readiness` | `pytest -q tests/fleet/test_v2_reconciliation.py -k blocked_when` → task bloqueada não é dispatchada | `artifacts/v2/H-02-readiness.json` |
| H-03 | R10, R11 | T2-11,T2-16 | `tests/fleet/test_v2_human_gate.py::test_gate_requires_policy_evidence_not_declared_status` | `pytest -q tests/fleet/test_v2_human_gate.py -k declared_status` → gate falso rejeitado | `artifacts/v2/H-03-gate-evidence.json` |
| H-04 | R4 | T2-05 | `tests/fleet/test_v2_checkpoint.py::test_crash_reload_resume_without_replay` | `pytest -q tests/fleet/test_v2_checkpoint.py -k crash_reload` → último snapshot válido carrega e concluída não reexecuta | `artifacts/v2/H-04-recovery.json` |
| H-05 | R6, R10 | T2-06 | `tests/fleet/test_v2_agent_report.py::test_report_requires_auditable_fields` | `pytest -q tests/fleet/test_v2_agent_report.py -k auditable_fields` → report incompleto rejeitado | `artifacts/v2/H-05-agent-report.json` |
| M-01 | R1, R7 | T2-02 | `tests/fleet/test_v2_contracts.py::test_role_capability_mismatch_blocks_assignment` | `pytest -q tests/fleet/test_v2_contracts.py -k capability_mismatch` → mismatch bloqueia | `artifacts/v2/M-01-assignment.json` |
| M-02 | R12 | T2-15 | `tests/fleet/test_v2_cli.py::test_inspect_and_dry_run_are_read_only` | `pytest -q tests/fleet/test_v2_cli.py -k dry_run` → JSON determinístico, state/hash inalterados | `artifacts/v2/M-02-cli.json` |
| M-03 | R10, R12 | T2-18 | `tests/fleet/test_v2_doc_paths.py::test_verification_labels_planned_vs_executed` | `pytest -q tests/fleet/test_v2_doc_paths.py -k planned` → evidência planejada não é apresentada como executada | `artifacts/v2/M-03-doc-evidence.json` |
| M-04 (gap adicional: TOCTOU) | R1, R3, R7 | T2-04,T2-12,T2-14 | `tests/fleet/test_v2_run_store.py::test_claim_use_commit_rejects_stale_generation_or_lease_without_corruption` | `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit` → commit stale rejeitado e snapshot/state/hash permanecem inalterados | `artifacts/v2/M-04-toctou.json` |
| gap adicional: executor seguro | R5 | T2-07 | `tests/fleet/test_v2_validation_executor.py::test_default_deny_and_fail_closed_without_sandbox` | `pytest -q tests/fleet/test_v2_validation_executor.py` → sem policy/sandbox nenhum processo; argv não-shell, allowlist, cwd/env/timeout/output limits testados | `artifacts/v2/gap-validation-executor.json` |
| gap adicional: unknown AgentReport fields | R6 | T2-06 | `tests/fleet/test_v2_agent_report.py::test_unknown_fields_rejected_by_default` | `pytest -q tests/fleet/test_v2_agent_report.py -k unknown_fields` → campo desconhecido rejeitado (policy strict default) | `artifacts/v2/gap-report-unknown-fields.json` |
| gap adicional: human freshness/identity | R11 | T2-16 | `tests/fleet/test_v2_human_gate.py::test_identity_decision_digest_and_freshness_are_required` | `pytest -q tests/fleet/test_v2_human_gate.py -k freshness` → identity/owner string + decision + digest + timestamps válidos; stale/ownerless rejeitados | `artifacts/v2/gap-human-gate.json` |

### Invariantes dos gaps adicionais

- **TOCTOU:** a API é explicitamente `claim → use → commit`; `claim` captura `generation` e lease, `use` só opera com esses tokens, e `commit` faz CAS dos dois. Generation ou lease stale rejeita atomicamente, sem alterar state, snapshot, eventos ou evidência.
- **ValidationExecutor:** a implementação local/in-process é default e não usa shell. Execução de argv só é possível com allowlist exata, `cwd` contido no root, ambiente explícito/mínimo, timeout e limites de stdout/stderr; `sandbox_capability` é uma capability observável. Se sandbox requerida não estiver disponível, falha fechado (não faz fallback para shell ou execução sem sandbox).
- **AgentReport:** unknown fields são **rejeitados por default** (policy `reject_unknown_fields=True`); qualquer futura política de preservação exigirá versionamento e teste próprio.
- **Human gate:** registra `identity: str`, `decision`, `evidence_digest`, `created_at`, `updated_at` e `freshness_window`. Rejeita evidência fora da janela ou decisão sem owner/identity. Identity é apenas string registrada (não simula autenticação criptográfica); autenticação real é out-of-scope/futura.
