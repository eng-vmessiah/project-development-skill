# PD Fleet Orchestration V2 — Research

**Data da verificação:** 2026-07-17  
**Branch/commit:** `feat/pd-fleet-orchestration-plan` / `2b4f219`
**Escopo:** baseline T2-01 e testes de contrato; nenhum runtime ou documento V1 é alterado.

## Estado atual verificado

- Baseline histórico do handoff anterior: `pytest -q` → **282 passed** (a contagem anterior de 278 é preservada como referência histórica). Verificação corrente deste T2-18: `pytest -q -W error` → **577 passed**, exit 0.
- O domínio V2 observado inclui `models.py`, `validation.py`, `lifecycle.py`, `state.py`, `checkpoint.py`, `dispatch.py`, `orchestrator.py`, `contracts.py`, `gates.py`, `evidence.py`, `run_store.py`, `validation_executor.py`, `provider.py`, `observability.py`, `scheduler.py`, `parallel.py` e `v2_doc_paths.py`, além dos testes correspondentes.
- `scripts/pd.py` continua sendo a integração CLI e preserva o comportamento legado; `scripts/pd` é wrapper.
- O `FleetOrchestrator` e os componentes V2 estão presentes e testados; o modo seguro local/in-process é o único habilitado neste handoff. Qualquer claim de paralelismo/release depende dos gates formais.
- `TaskSpec.validation_commands` continua sendo declarativo; não autoriza shell.
- Existe `FleetRunStore` independente do CLI, com testes de ownership/CAS/recovery/TOCTOU; a evidência de teste não substitui aprovação G3.
- Normalização, reports strict e redaction possuem implementação/testes presentes; a revisão de segurança e os gates permanecem necessários.
- Não há provider externo habilitado. Qualquer adapter futuro deve ser contrato default-deny, sem credenciais, rede ou dispatch implícitos.
- O gate de verificação humana permanece pendente/não aprovado; não deve ser descrito como PASS.
- V1 e legado devem ser preservados. Diretórios relevantes existentes: `tests/fleet/`, `examples/pd-fleet/`, `skills/pd/`, `docs/`, `ROADMAP.md`, `README.md`.

## Reconciliation matrix

| Área | V1 | Evidência | V2 decisão |
|---|---|---|---|
| Baseline/compatibilidade | **Verified** | 278 testes passam no baseline histórico; CLI legado existente; verificação corrente: 577 passed | Congelar baseline e adicionar testes sem mudar contratos legados |
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

## Evidência intermediária/histórica — T2-04 (2026-07-17)

- Artifact nomeado: `artifacts/v2/M-04-toctou.json`.
- `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit` → **1 passed**.
- `pytest -q tests/fleet/test_run_store.py tests/fleet/test_v2_run_store.py` → **29 passed**.
- O teste nomeado prova claim→use, renovação que invalida o token antigo, rejeição de commit stale e invariância de state, bytes/digest do snapshot, events e reports.
- Em execução intermediária anterior, `pytest -q` → **421 passed**; essa contagem **não é fresca** e não deve ser usada como estado corrente. `python -m compileall -q scripts tests` e `git diff --check` → **pass** nessa execução intermediária.
- Escopo: somente documentação V2, teste de evidência e artifact; `scripts/pd_fleet/run_store.py` não foi alterado.

## Evidência fresca — T2-01 (2026-07-17)

- `pytest -q tests/fleet/test_v2_baseline.py` → **4 passed**.
- O teste captura branch e commit com `subprocess.run` usando argv (sem shell), `check=True`, e rejeita valores vazios, multilinha ou fora do conjunto seguro de identificadores.
- O contrato local rejeita claim global `PASS` sem gate explícito `approved` e `evidence_digest`; ausência/pending não é aprovação.
- A classificação V1→V2 está congelada no teste como `verified`, `partial`, `open` ou `superseded`; o baseline atual contém itens `open` e não contém status `PASS`.
- Verificação corrente T2-18: `pytest -q -W error` → **577 passed**; `python -m compileall scripts/pd_fleet`, `git diff --check` e `python scripts/pd_fleet/v2_doc_paths.py /home/vitor/project/project-development-skill` → exit 0. Checker: `violation_count=0`.
- Status honesto: T2-01…T2-17 têm caminhos/testes presentes no working tree e evidência local, mas gates G1…G6 e decisão humana final continuam pendentes. Consulte `VERIFICATION.md` para tabela determinística, residuais e rollback.

1. A fonte de verdade será um store de domínio por `run_id`; CLI apenas traduz comandos/saída.
2. O estado calculado deve ser reconstruível por eventos/checkpoints e reconciliado contra o plano atual antes de qualquer execução.
3. Ordem determinística é requisito de segurança operacional: IDs, waves, reports e JSON canônico usam ordenação explícita. Em eventos, `sequence` é a ordem append-only de persistência/auditoria e `query("events")` ordena por `(ordering_key, sequence)`; a conclusão do scheduler não é uma ordem determinística contratada. Wall-clock e paths absolutos não entram no contrato lógico.
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
| B-01 | R3, R7, R12 | T2-10,T2-15 | `tests/fleet/test_v2_local_execution.py::test_local_fleet_run_end_to_end` | `pytest -q tests/fleet/test_v2_local_execution.py -k end_to_end` → 1 passed, sem provider/rede | `artifacts/v2/B-01-local-run.json` + stdout/exit-code (**planejado; não presente**) |
| H-01 | R3, R6, R8 | T2-10 | `tests/fleet/test_v2_local_execution.py::test_retry_policy_records_attempts_and_backoff` | `pytest -q tests/fleet/test_v2_local_execution.py -k retry_policy` → retryable repete até limite; não-retryable não repete | `artifacts/v2/H-01-retry.json` (**planejado; não presente**) |
| H-02 | R1, R8 | T2-09 | `tests/fleet/test_v2_reconciliation.py::test_inputs_and_blocked_when_gate_readiness` | `pytest -q tests/fleet/test_v2_reconciliation.py -k blocked_when` → task bloqueada não é dispatchada | `artifacts/v2/H-02-readiness.json` (**planejado; não presente**) |
| H-03 | R10, R11 | T2-11,T2-16 | `tests/fleet/test_v2_human_gate.py::test_gate_requires_policy_evidence_not_declared_status` | `pytest -q tests/fleet/test_v2_human_gate.py -k declared_status` → gate falso rejeitado | `artifacts/v2/H-03-gate-evidence.json` (**planejado; não presente**) |
| H-04 | R4 | T2-05 | `tests/fleet/test_v2_checkpoint.py::test_crash_reload_resume_without_replay` | `pytest -q tests/fleet/test_v2_checkpoint.py -k crash_reload` → último snapshot válido carrega e concluída não reexecuta | `artifacts/v2/H-04-recovery.json` (**planejado; não presente**) |
| H-05 | R6, R10 | T2-06 | `tests/fleet/test_v2_agent_report.py::test_report_requires_auditable_fields` | `pytest -q tests/fleet/test_v2_agent_report.py -k auditable_fields` → report incompleto rejeitado | `artifacts/v2/H-05-agent-report.json` (**planejado; não presente**) |
| M-01 | R1, R7 | T2-02 | `tests/fleet/test_v2_contracts.py::test_role_capability_mismatch_blocks_assignment` | `pytest -q tests/fleet/test_v2_contracts.py -k capability_mismatch` → mismatch bloqueia | `artifacts/v2/M-01-assignment.json` (**planejado; não presente**) |
| M-02 | R12 | T2-15 | `tests/fleet/test_v2_cli.py::test_inspect_and_dry_run_are_read_only` | `pytest -q tests/fleet/test_v2_cli.py -k dry_run` → JSON determinístico, state/hash inalterados | `artifacts/v2/M-02-cli.json` (**planejado; não presente**) |
| M-03 | R10, R12 | T2-18 | `tests/fleet/test_v2_doc_paths.py::test_verification_labels_planned_vs_executed` | `pytest -q tests/fleet/test_v2_doc_paths.py -k planned` → evidência planejada não é apresentada como executada | `artifacts/v2/M-03-doc-evidence.json` (**planejado; não presente**) |
| M-04 (gap adicional: TOCTOU) | R1, R3, R7 | T2-04,T2-12,T2-14 | `tests/fleet/test_v2_run_store.py::test_claim_use_commit_rejects_stale_generation_or_lease_without_corruption` | `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit` → commit stale rejeitado e snapshot/state/hash permanecem inalterados | `artifacts/v2/M-04-toctou.json` |
| gap adicional: executor seguro | R5 | T2-07 | `tests/fleet/test_v2_validation_executor.py::test_default_deny_and_fail_closed_without_sandbox` | `pytest -q tests/fleet/test_v2_validation_executor.py` → sem policy/sandbox nenhum processo; argv não-shell, allowlist, cwd/env/timeout/output limits testados | `artifacts/v2/gap-validation-executor.json` (**planejado; não presente**) |
| gap adicional: unknown AgentReport fields | R6 | T2-06 | `tests/fleet/test_v2_agent_report.py::test_unknown_fields_rejected_by_default` | `pytest -q tests/fleet/test_v2_agent_report.py -k unknown_fields` → campo desconhecido rejeitado (policy strict default) | `artifacts/v2/gap-report-unknown-fields.json` (**planejado; não presente**) |
| gap adicional: human freshness/identity | R11 | T2-16 | `tests/fleet/test_v2_human_gate.py::test_identity_decision_digest_and_freshness_are_required` | `pytest -q tests/fleet/test_v2_human_gate.py -k freshness` → identity/owner string + decision + digest + timestamps válidos; stale/ownerless rejeitados | `artifacts/v2/gap-human-gate.json` (**planejado; não presente**) |

### Invariantes dos gaps adicionais

- **TOCTOU:** a API é explicitamente `claim → use → commit`; `claim` captura `generation` e lease, `use` só opera com esses tokens, e `commit` faz CAS dos dois. Generation ou lease stale rejeita atomicamente, sem alterar state, snapshot, eventos ou evidência.
- **ValidationExecutor:** a implementação local/in-process é default e não usa shell. Execução de argv só é possível com allowlist exata, `cwd` contido no root, ambiente explícito/mínimo, timeout e limites de stdout/stderr; `sandbox_capability` é uma capability observável. Se sandbox requerida não estiver disponível, falha fechado (não faz fallback para shell ou execução sem sandbox).
- **AgentReport:** unknown fields são **rejeitados por default** (policy `reject_unknown_fields=True`); qualquer futura política de preservação exigirá versionamento e teste próprio.
- **Human gate:** registra `identity: str`, `decision`, `evidence_digest`, `created_at`, `updated_at` e `freshness_window`. Rejeita evidência fora da janela ou decisão sem owner/identity. Identity é apenas string registrada (não simula autenticação criptográfica); autenticação real é out-of-scope/futura.

## Evidência fresca G1 — 2026-07-28

A coleta atual confirmou, no workspace corrente, 401 testes V2 e 921 testes totais passando, além de compileall, diff-check e checker de paths com zero violações. O pacote `artifacts/v2/G1-fresh-verification.json` foi validado independentemente e não contém paths absolutos, segredos ou claim de aprovação.

A evidência é local e fresca, mas o status permanece **NOT READY / PARTIAL**: GRILL-001, G2–G5 e a decisão humana G6 continuam pendentes.

## GRILL-001 — 2026-07-28 — BLOCKED

A revisão adversarial independente encontrou **6 HIGH, 6 MEDIUM e 2 LOW**. Os principais blockers são: execução de binary controlado por `PATH` na readiness probe sem sandbox capability; ausência de `use` imediatamente antes do adapter; corrida entre `ready_ids()` e `claim_many()`; bypass de `HumanVerificationGate` por `GateResult`; falta de comparação de `scope`/`run` no gate; e leakage de assignments de segredo em metadata de provider.

Artefato: `artifacts/v2/GRILL-001-findings.json`. A classificação formal é **BLOCKED_NOT_READY**. A suíte verde não reduz esses findings nem concede G1/G6.


## GRILL-H01 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `9f90221414024b62b3bef2e0a7804efa13b6158f`.
- `LocalRuntimeReadinessProbe` agora falha fechado antes de `PATH`/subprocess quando não recebe runner explícito.
- Runner injetado continua bounded e suportado.
- Artefato: `artifacts/v2/GRILL-001-H01-resolution.json`.
- Review independente: PASS; 94 testes focados.
- O relatório histórico GRILL-001 permanece BLOCKED pelos outros cinco HIGH.

## GRILL-H02 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `b2fb44ae2c4a4a0a1522544c15f675df89d26293`.
- Provider metadata agora rejeita assignments explícitos de credencial e formas `Bearer` antes de redaction/immutable storage, inclusive em nested/list values.
- Lookalikes inertes continuam aceitos; redaction de chave/path/URL foi preservada.
- Artefato: `artifacts/v2/GRILL-001-H02-resolution.json`.
- Review independente: PASS; 121 testes focados e 939 totais.
- O relatório histórico GRILL-001 permanece BLOCKED pelos HIGH restantes.

## GRILL-H03 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `44b4b75524c618198f3ea1ef8746864996701b5a`.
- Orchestrator V2 agora executa `store.use(run_id, task_id, original_token, owner)` imediatamente antes do adapter. Lease stale/expired/replaced bloqueia antes do efeito.
- Compatibilidade de aridade usa signature binding; não há retry após `TypeError` interno do adapter.
- Artefato: `artifacts/v2/GRILL-001-H03-resolution.json`.
- Review independente: PASS; 62 focados e 942 totais.
- O relatório histórico GRILL-001 permanece BLOCKED pelos HIGH restantes.

## GRILL-H04 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `719dac51156fea0f4462103afc08e7ccd18dd66a`.
- `LeaseScheduler` recalcula a dependency barrier no snapshot locked de `claim_many`; stale candidates não são leaseados e candidates newly-ready podem ser selecionados.
- Toda a plan é validada antes de readiness/status filtering; containers/elements malformed falham com `SchedulerError` sem mutation, inclusive em tarefas terminais.
- Artefato: `artifacts/v2/GRILL-001-H04-resolution.json`.
- Review independente: PASS; 126 focados. Full rerun parent: 952 passed.
- O relatório histórico GRILL-001 permanece BLOCKED pelos HIGH restantes.

## GRILL-H05 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `6c34aca3362828b6352cab95243c8f8b41515990`.
- Gates de governança `review`/`grill` agora exigem `HumanVerificationGate`; `GateResult` estrutural não autoriza. Gates automáticos `smoke_test`/`evidence` mantêm policy evaluation.
- Artefato: `artifacts/v2/GRILL-001-H05-resolution.json`.
- Review independente: PASS; 32 focados e 956 totais.
- H06 permanece aberto para binding de `scope/run`; o relatório histórico GRILL-001 continua BLOCKED.

## GRILL-H06 — resolução local

- Status: **RESOLVED_LOCALLY** no commit `d3b2c78faa2385151ee67ef736a26071f56423d3`.
- `HumanVerificationGate` agora exige binding ao `run_id` atual e ao escopo canônico do plano (`schema_version`, `plan_hash`, tasks e waves). Comparação é estrutural e ordena elementos de forma determinística.
- Call sites reais (`ready_tasks`, `_ready_ids` e wave stall) usam o contexto corrente; gates automáticos permanecem inalterados.
- Artefato: `artifacts/v2/GRILL-001-H06-resolution.json`.
- Review independente: PASS; 22 focados e 959 totais.
- Identidade continua sendo metadata auditável, não autenticação criptográfica.

## GRILL-001 — rerun consolidado atual

- **Data do rerun:** 2026-07-28.
- **Commit:** `5e3f9fa`; **branch:** `feat/pd-fleet-lifecycle-events`.
- H01…H06: **RESOLVED_LOCALLY** com artefatos individuais.
- Review independente consolidado: **não encontrou novo BLOCKER/HIGH**.
- Residuais ativos: M01–M06 e L01–L02 (observability `repr`, cwd não pinned por descriptor, lease expirado ocupando path, expiry antes do lock, parsers permissivos, evidence sem provenance/freshness, timestamps implícitos e policy keys desconhecidas).
- Evidência fresca: security/executor/provider **107 passed**; persistence/scheduler/concurrency **47 passed**; governance/contracts/reports **147 passed**; full **959 passed**; compileall, doc checker (7/0) e diff-check passaram.
- `artifacts/v2/G1-fresh-verification.json` é histórico e stale (`commit 3036786`, contagens antigas); não é usado como evidência corrente.
- Artefato corrente: `artifacts/v2/GRILL-001-rerun-current.json`.
- **Decisão:** **NOT_READY_PARTIAL**. Não há aprovação humana G1/G6, autorização de merge/provider/release ou PASS global.
