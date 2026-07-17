# PD Fleet Orchestration — Implementation Plan

> **For Hermes:** execute with `subagent-driven-development`: fresh context per task, spec review before quality review, and explicit orchestrator state.

**Goal:** adicionar ao PD um núcleo determinístico para planejar, validar e coordenar tasks de subagents em waves, preservando o pipeline legado.

**Architecture:** `scripts/pd_fleet/` conterá modelos, validação, lifecycle, gates e adapters. `scripts/pd.py` fará apenas integração CLI/compatibilidade. O estado novo viverá em um bloco versionado `fleet_state`, separado de `tasks` legado. O primeiro runtime será local e simulado; nenhum provider externo será obrigatório.

**Tech Stack:** Python 3.12, stdlib + pytest; YAML opcional conforme suporte atual.

## Contract rules

- Cada task tem `id`, `wave`, `role`, `capabilities`, `objective`, `depends_on`, `parallel_group`, `allowed_paths`, `forbidden_paths`, `inputs`, `outputs`, `acceptance_criteria`, `validation_commands`, `blocked_when`, `retry_policy` e `owner`.
- Waves são sequenciais; tasks elegíveis na mesma wave somente são paralelas sem sobreposição de ownership.
- `allowed_paths` deve ser específico; diretórios amplos (`scripts/pd_fleet/`, `tests/`) não podem ser usados por duas tasks paralelas.
- O orchestrator é o único componente que agenda, muda lifecycle, libera gates e integra outputs.
- Cada task tem spec review e quality review antes de `completed`.
- Nenhum código começa antes de `G1 — Plan Grill` = PASS.

## Canonical waves

### Wave 0 — Intake e reconhecimento (concluída)

Artefatos: `RESEARCH.md`, baseline de testes e inventário do CLI/templates/estado.

**Gate G0:** contexto obrigatório lido e baseline registrado.

### Wave 1 — Design executável (concluída, revisada)

Artefatos: `SPEC.md`, `PLAN.md`, `CONTEXT.md`, `GRILL-001.md`.

**Gate G1:** grill adversarial do plano sem BLOCKER/HIGH aberto e sem decisão humana pendente.

### Wave 2 — Fundação de contratos (após G1, serial por ownership)

#### T1 — Modelos e normalização de fleet plan

- **Role:** coder; **capabilities:** python, schema-design
- **Depends:** [] após G1
- **Allowed paths:** `scripts/pd_fleet/models.py`, `tests/fleet/test_models.py`
- **Outputs:** modelos normalizados e schema versionado.
- **Acceptance:** contrato uniforme; IDs estáveis; estado default válido.

#### T2 — Validação de DAG e ownership

- **Role:** coder; **capabilities:** python, graph-algorithms
- **Depends:** [T1]
- **Allowed paths:** `scripts/pd_fleet/validation.py`, `tests/fleet/test_validation.py`
- **Outputs:** validação de IDs, dependências, ciclos, contracts e path ownership.
- **Acceptance:** casos válidos passam; ciclos, dependências ausentes, paths conflitantes e task incompleta falham com erro acionável.

#### T3 — Lifecycle, retry e gate policy

- **Role:** coder; **capabilities:** state-machines, testing
- **Depends:** [T1]
- **Allowed paths:** `scripts/pd_fleet/lifecycle.py`, `tests/fleet/test_lifecycle.py`
- **Outputs:** transições, retry policy, running órfão, gates e idempotência.
- **Acceptance:** transições inválidas rejeitadas; `failed` só retorna a `ready` por retry explícito; `completed` exige outputs/evidence.

#### T4 — Templates e manifests de exemplo

- **Role:** documentation; **capabilities:** markdown, yaml
- **Depends:** [T1]
- **Allowed paths:** `skills/pd/templates/fleet-task.yaml`, `skills/pd/templates/AGENT-REPORT.md`, `skills/pd/templates/FLEET-STATUS.md`, `examples/pd-fleet/plan.yaml`
- **Outputs:** templates alinhados ao schema.
- **Acceptance:** todos os campos obrigatórios e exemplo mínimo válido.

**Paralelismo da Wave 2:** T2 e T3 podem executar em paralelo após T1; T4 também pode executar em paralelo, pois possui ownership exclusivo. Nenhum desses tasks pode alterar `scripts/pd.py`.

### Wave 3 — Estado e inspeção (integração serial)

#### T5 — Estado `fleet_state` backward-compatible

- **Role:** coder; **capabilities:** python, migration
- **Depends:** [T2, T3]
- **Allowed paths:** `scripts/pd.py` somente nas funções de load/save, `scripts/pd_fleet/state.py`, `tests/fleet/test_state_migration.py`
- **Outputs:** round-trip JSON/MD, namespace versionado, preservação de campos desconhecidos.
- **Acceptance:** estados antigos somente MD, somente JSON, JSON parcial e tasks legadas continuam carregando.
- **Retry:** operações de escrita devem ser atômicas; preservar último estado válido e reports.

#### T6 — CLI fleet status e tasks elegíveis

- **Role:** coder; **capabilities:** argparse, cli-testing
- **Depends:** [T5, T4]
- **Allowed paths:** `scripts/pd.py` somente parser/dispatch/output, `tests/fleet/test_cli_inspection.py`
- **Outputs:** comandos read-only `fleet-status` e `fleet-ready`, texto e `--json`.
- **Acceptance:** saída determinística; tasks elegíveis refletem DAG, gates e ownership; fluxo legado não muda.

#### T7 — Checkpoint/resume por task/wave

- **Role:** coder; **capabilities:** persistence, recovery
- **Depends:** [T5]
- **Allowed paths:** `scripts/pd_fleet/checkpoint.py`, `tests/fleet/test_resume.py`
- **Outputs:** checkpoint versionado, recuperação de `running` órfão e resume sem replay de completed.
- **Acceptance:** retry, crash/reload, bloqueio e evidências preservadas.

**Paralelismo da Wave 3:** T6 e T7 não compartilham arquivos e podem ser paralelos após T5.

### Wave 4 — Orquestração local de tasks (integração serial)

#### T8 — Protocolo de adapter

- **Role:** coder; **capabilities:** interfaces, python
- **Depends:** [T1, T3]
- **Allowed paths:** `scripts/pd_fleet/adapter.py`, `tests/fleet/test_adapter_contract.py`
- **Outputs:** interface provider-agnostic para start/complete/fail/timeout/cancel e report.
- **Acceptance:** contrato cobre input, output, status, attempt, evidence e erro.

#### T9 — `LocalDispatchAdapter` simulado

- **Role:** coder; **capabilities:** test-doubles
- **Depends:** [T8]
- **Allowed paths:** `scripts/pd_fleet/local_adapter.py`, `tests/fleet/test_local_adapter.py`
- **Outputs:** adapter sem credenciais, com sucesso, falha, timeout e output inválido simuláveis.
- **Acceptance:** cada resultado produz report serializável e não altera task fora do orchestrator.

#### T10 — `FleetOrchestrator`

- **Role:** coder; **capabilities:** orchestration, graph, state
- **Depends:** [T2, T3, T6, T7, T9]
- **Allowed paths:** `scripts/pd_fleet/orchestrator.py`, `tests/fleet/test_orchestrator.py`
- **Outputs:** `plan_ready`, `start`, `complete`, `fail`, `block`, `retry`, `resume`; seleção determinística e matching role/capability.
- **Acceptance:** executa duas tasks independentes sem conflito, respeita dependência, bloqueia gate/path conflict e persiste reports/lifecycle.

#### T11 — CLI dispatch dry-run

- **Role:** coder; **capabilities:** argparse, orchestration
- **Depends:** [T10]
- **Allowed paths:** `scripts/pd.py` somente parser/dispatch, `tests/fleet/test_cli_dispatch.py`
- **Outputs:** comando `fleet-run --dry-run` que mostra tasks elegíveis sem executar.
- **Acceptance:** dry-run não modifica estado; JSON contém wave, task, role e dependências.

### Wave 5 — Gates e exemplo executável

#### T12 — Gates review/grill/smoke/evidence

- **Role:** coder; **capabilities:** quality-gates
- **Depends:** [T3, T10]
- **Allowed paths:** `scripts/pd_fleet/gates.py`, `tests/fleet/test_gates.py`
- **Outputs:** gate schema com `gate_id`, `type`, `scope`, `status`, `owner`, `command`, `evidence`, `decision`, timestamps.
- **Acceptance:** gate falho bloqueia wave/task; mudança posterior reabre gate; evidence obrigatória para PASS.

#### T13 — Exemplo completo da própria evolução

- **Role:** coder; **capabilities:** documentation, integration-testing
- **Depends:** [T4, T10, T12]
- **Allowed paths:** `examples/pd-fleet/README.md`, `examples/pd-fleet/plan.yaml`, `examples/pd-fleet/reports/`, `tests/fleet/test_example.py`
- **Outputs:** goal, DAG, duas tasks paralelas simuladas, uma dependência, blocker e reports.
- **Acceptance:** executa localmente sem credenciais e demonstra seleção, dispatch, reports, gate e resume.

### Wave 6 — Reviews e prompt refinement (serial)

#### T15 — Spec compliance review

- **Role:** reviewer; **Depends:** [T11, T12, T13]
- **Allowed paths:** somente leitura
- **Output:** PASS ou gaps rastreáveis contra R1–R18.

#### T16 — Code quality review

- **Role:** reviewer; **Depends:** [T15]
- **Allowed paths:** somente leitura
- **Output:** APPROVED ou issues priorizadas.

#### T17 — Adversarial grill pós-código

- **Role:** grill; **Depends:** [T16]
- **Allowed paths:** somente leitura
- **Output:** blockers e riscos residuais.

#### T14 — Prompt refinement de entrada/saída

- **Role:** prompt-refiner; **capabilities:** prompt-design
- **Depends:** [T17]
- **Allowed paths:** `docs/PD-FIRST-CASE-PROMPT.md`, `examples/pd-fleet/PROMPT-NEXT.md`
- **Outputs:** prompt reutilizável com goal, contexto, escopo, contracts, waves, dependências, critérios e validação.
- **Acceptance:** todos os caminhos referenciados existem e o prompt pode iniciar uma nova sessão.

### Wave 7 — Smoke/evidence gate

#### T18 — Smoke test e VERIFICATION.md

- **Role:** smoke-tester; **Depends:** [T14]
- **Allowed paths:** `.spec/pd-fleet-orchestration/VERIFICATION.md`, `examples/pd-fleet/`
- **Output:** evidência fresca de CLI, exemplo, migração e suíte completa.
- **Acceptance:** todos os comandos obrigatórios executados; sem regressão.

### Wave 8 — Closeout

#### T19 — Documentação e roadmap

- **Role:** documentation; **Depends:** [T18]
- **Allowed paths:** `skills/pd/SKILL.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`
- **Output:** docs sincronizados com comportamento real.

#### T20 — Relatório final e commit para review humano

- **Role:** orchestrator; **Depends:** [T19]
- **Allowed paths:** artifacts da feature; sem merge/push
- **Output:** relatório por wave/agent, diff limpo, riscos e decisões humanas.

## State and gate contracts

`fleet_state` deve conter `schema_version`, `agents`, `waves`, `tasks`, `gates`, `reports`, `attempts`, `blockers`, `evidence` e `updated_at`. O campo legado `tasks` no nível raiz permanece lista de strings concluídas.

### Gate contract

Todo gate, inclusive `G0` e `G1`, usa o mesmo contrato persistido:

```yaml
gate_id: G1
kind: plan_grill
scope: feature
owner: grill
status: pending
required_evidence: []
evidence: []
decision: null
blockers: []
created_at: null
updated_at: null
```

`PASS` exige evidência não vazia, `owner`, decisão e zero blocker crítico. O orchestrator não libera a próxima wave enquanto o gate requerido não estiver `passed`. Qualquer mudança em artefato dentro do escopo reabre o gate.

### Retry and recovery policy

A política inicial é determinística: `max_attempts: 2`, sem backoff no adapter local, retry apenas para erros declarados como retryable, e nenhuma repetição automática após `blocked`. Um task `running` sem `heartbeat` por 5 minutos ou sem report final na recuperação vira `failed` com `orphaned_run`; o retry precisa ser explícito. Tasks `completed` são idempotentes e nunca são reexecutadas no resume.

### Atomic state protocol

O estado estruturado será salvo em arquivo temporário no mesmo diretório, validado como JSON, substituído via rename atômico e só então refletido em `STATE.md`. O último JSON válido fica preservado como backup/version. Se a operação falhar, o estado anterior e os reports permanecem recuperáveis; nenhuma evidência é apagada.

### Task readiness rule

Uma task só pode ser `ready` se todos os campos do contrato estiverem presentes, suas dependências estiverem `completed`/`skipped` permitido, o gate da wave estiver `passed`, capabilities forem atendidas, inputs existirem e o ownership não conflitar com tasks `running`.

Lifecycle permitido:

```text
pending → ready → running → completed
                    ├──────→ failed → ready (retry explícito)
                    ├──────→ blocked
pending ────────────┴──────→ skipped (decisão registrada)
```

Um `running` sem heartbeat/finish em recuperação vira `failed` com motivo `orphaned_run`; nunca é considerado completed automaticamente.

## Requirements coverage matrix

| Requirement | Implementação | Teste | Evidência |
|---|---|---|---|
| R1-R4 | T1, T8-T10 | models/adapter/orchestrator | pytest + reports |
| R5-R9 | T2-T3 | validation/lifecycle/orchestrator | pytest |
| R10-R13 | T5-T7 | migration/CLI/resume | pytest + JSON |
| R14 | T12 | gates | gate reports |
| R15 | T4, T14 | template/example | artifact review |
| R16 | T13 | example | smoke output |
| R17 — atomicidade/rollback | T5, T7 | state recovery | VERIFICATION.md |
| R18 — orchestrator real | T10-T11 | integration dispatch | reports |

## Verification commands

```bash
pytest -q
python3 scripts/pd.py --help
python3 scripts/pd.py list --json
python3 scripts/pd.py fleet-status --json -f pd-fleet-orchestration
python3 scripts/pd.py fleet-ready --json -f pd-fleet-orchestration
python3 scripts/pd.py fleet-run --dry-run --json -f pd-fleet-orchestration
python3 scripts/pd.py validate --deep --json -f pd-fleet-orchestration
python3 scripts/pd.py verify --json -f pd-fleet-orchestration
python3 -m compileall scripts/
git diff --check
```

## Exit criteria

- G1 e todos os gates posteriores passam.
- R1–R18 cobertos por implementação, teste e evidência.
- 49 testes legados continuam passando.
- Pelo menos duas tasks independentes e uma dependente são orquestradas pelo adapter simulado.
- Estado legado continua carregando sem migração destrutiva.
- Nenhum BLOCKER/HIGH aberto no grill final.
- Nenhum merge automático.
