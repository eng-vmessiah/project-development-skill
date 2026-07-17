# PD Fleet Orchestration V2 — Plano de implementação

**Estado atual (2026-07-17):** T2-01…T2-18 implementados localmente e documentados; a suíte fresca é `577 passed` com `-W error`, o checker offline retorna `valid`/`violation_count=0` e `M-04-toctou.json` possui digest verificado. Isso é evidência local, não aprovação de release: G1–G6 permanecem pendentes e a decisão continua **NOT READY / PARTIAL** até revisão humana explícita.

**Regra:** planning only até aprovação de `GRILL-001`; nenhuma tarefa abaixo deve ser iniciada com BLOCKER/HIGH. Cada tarefa é TDD: escrever teste falhando, implementar, verificar e registrar evidência. `Create` indica caminho ainda inexistente; caminhos não listados são proibidos.

## Gates e comandos globais

- **Canonical JSON/hash (normativo em todas as tarefas):** UTF-8 com `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`; remover timestamps de runtime, paths absolutos e secrets redigidos antes de serializar; SHA-256 lowercase hex sobre o domínio versionado `pd-fleet-plan:v2\0` + bytes canônicos. Reconciliation segue `load -> parse -> canonicalize -> hash -> compare plan_hash -> compare generation/run/checkpoint/lease/event sequence -> block on mismatch -> claim -> use -> commit`; mismatch/drift/stale bloqueia antes de mutar. Fixtures/golden e testes de drift são determinísticos.
- **G0 baseline histórico:** `278 passed` (estado anterior ao plano). A evidência corrente é `pytest -q -W error` → `577 passed`; contagens intermediárias são históricas e não substituem os gates.
- **G1 grill pré-código:** `GRILL-001.md` sem BLOCKER/HIGH + aprovação humana explícita.
- **G2 foundation:** `pytest -q tests/fleet` + `python -m compileall scripts/pd_fleet`.
- **G3 persistence:** testes de crash/replay/race passam.
- **G4 executor:** prova de default-deny; nenhum processo sem policy.
- **G5 parallel:** teste concorrente repetível, bounded e ordenado.
- **G6 release:** `pytest -q`, `git diff --check`, revisão docs e gate humano APPROVED.
- **Event ordering contract:** `sequence` é a ordem append-only de persistência/auditoria; `query("events")` ordena por `(ordering_key, sequence)`. A conclusão do scheduler não é contratualmente determinística.

## Regras de tarefa

`role/capabilities` define competência, não autorização. `allowed paths` é allowlist de edição; `forbidden paths` inclui código/docs V1, paths fora da lista, shell/provider/rede e todo arquivo compartilhado não listado. Failing tests são obrigatórios antes da implementação. Rollback significa remover apenas a mudança da tarefa e restaurar snapshot do store; nunca apagar evidência.

## Wave 0 — Baseline e reconciliação (serial)

### T2-01 — Congelar baseline e matriz V1/V2
- **Objective:** registrar estado real, hashes e reconciliação sem declarar PASS.
- **Exact files:** `.spec/pd-fleet-orchestration-v2/RESEARCH.md`, `.spec/pd-fleet-orchestration-v2/CONTEXT.md` (existem); `tests/fleet/test_v2_baseline.py` (Create); `scripts/pd_fleet/v2_doc_paths.py` e `tests/fleet/test_v2_doc_paths.py` pertencem exclusivamente a T2-17 e já estão implementados.
- **Dependencies:** [] (checker/path contract is defined before T2-17; no implementation authorized in T2-01) | **Role/capabilities:** reviewer, pytest, git, threat-model, docs/path-contract, stdlib/offline path and link analysis.
- **Allowed paths:** todos os exact files acima. **Forbidden:** código V1, `.spec/pd-fleet-orchestration/*` (V1), outros testes/código, commits/push.
- **Failing tests:** teste que fixa `pytest` count/hash e rejeita alegação PASS sem gate.
- **Implementation:** capturar baseline reproduzível e matriz verified/partial/open/superseded.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_baseline.py` → exit 0; baseline/hash e ausência de PASS sem gate passam.
- **Verification:** `pytest -q`; `git status --short`; `git show -s --format=%H`.
- **Acceptance:** baseline 278 passed ou mudança explicada; tabela rastreável.
- **Rollback:** remover teste/atualização V2 mantendo V1.
- **Gate:** G0 registrado; G1 ainda pendente.

### T2-02 — Contrato canônico e reconciliation matrix executável
- **Objective:** definir schema/hash e casos de drift, stale run e replay.
- **Exact files:** `scripts/pd_fleet/contracts.py` (existe; alteração futura), `tests/fleet/test_v2_contracts.py` (Create).
- **Dependencies:** T2-01 | **Role/capabilities:** domain engineer, schema, hashing.
- **Allowed paths:** esses dois. **Forbidden:** CLI, provider, executor.
- **Failing tests:** alias equivalence, unknown schema, hash estável e drift bloqueado.
- **Implementation:** contrato versionado, canonical serialization e diagnostics determinísticos.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_contracts.py` → exit 0; hash canônico, aliases, unknown fields e drift-blocking passam.
- **Verification:** `pytest -q tests/fleet/test_v2_contracts.py`.
- **Acceptance:** mesma entrada produz mesmo hash/JSON; mismatch nunca executa.
- **Rollback:** retirar contrato V2 sem tocar contratos V1.
- **Gate:** G1 obrigatório antes de código de produção.

## Wave 1 — Modelo e estado (serial por persistência)

### T2-03 — Normalização e output determinístico
- **Objective:** eliminar variação de ordem, relógio e path absoluto.
- **Exact files:** `scripts/pd_fleet/models.py` (existe), `tests/fleet/test_v2_normalization.py` (Create).
- **Dependencies:** T2-02 | **Role/capabilities:** Python, serialization, redaction.
- **Allowed paths:** esses paths. **Forbidden:** CLI/docs V1.
- **Failing tests:** permutações equivalentes, timestamps injetados, Windows/WSL paths e redaction.
- **Implementation:** canonical sort, relative path policy, stable null/default policy.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_normalization.py` → exit 0; permutações, relógio injetado, redaction e JSON estável passam.
- **Verification:** `pytest -q tests/fleet/test_v2_normalization.py`.
- **Acceptance:** golden JSON byte-identical; nenhum `/mnt/`, home ou segredo cru.
- **Rollback:** revert normalizer e manter parser V1.
- **Gate:** G2 parcial após revisão de golden fixtures.

### T2-04 — FleetRunStore e ownership de run
- **Objective:** desacoplar persistência do CLI e centralizar transitions/leases.
- **Exact files:** `scripts/pd_fleet/run_store.py` (Create), `tests/fleet/test_run_store.py` (Create).
- **Dependencies:** T2-03 | **Role/capabilities:** persistence, atomicity, concurrency.
- **Allowed paths:** esses paths. **Forbidden:** `scripts/pd.py`, provider, rede.
- **Failing tests:** owner mismatch, CAS generation, duplicate commit, lease expiry e concurrent writers; `tests/fleet/test_v2_run_store.py::test_claim_use_commit_rejects_stale_generation_or_lease_without_corruption` prova explicitamente claim→use→commit, rejeição de generation/lease stale e snapshot/state intactos.
- **Implementation:** API create/load/claim/renew/commit/append/query; lock/atomic replace local. `claim` retorna generation+lease token, `use` exige o token e `commit` faz CAS atômico dos dois; stale falha fechado antes de qualquer mutação.
- **Commands / Expected results:** `pytest -q tests/fleet/test_run_store.py tests/fleet/test_v2_run_store.py` → exit 0; ownership, CAS, lease, duplicate commit, ordenação canônica de eventos e TOCTOU stale passam sem mutar state.
- **Verification:** `pytest -q tests/fleet/test_run_store.py tests/fleet/test_v2_run_store.py`; focused evidence `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit`.
- **Acceptance:** único owner commita; crash preserva último snapshot válido.
- **Rollback:** excluir novo store/testes, sem tocar state V1.
- **Gate:** G3.

### T2-05 — Checkpoint persistence/recovery
- **Objective:** tornar checkpoint durable, verificável e replay-safe.
- **Exact files:** `scripts/pd_fleet/checkpoint.py` (existe), `tests/fleet/test_v2_checkpoint.py` (Create).
- **Dependencies:** T2-04 | **Role/capabilities:** recovery, filesystem, fault injection.
- **Allowed paths:** esses paths. **Forbidden:** comandos externos.
- **Failing tests:** truncation, checksum, temp leftovers, old schema, completed não reexecutado.
- **Implementation:** generation/checksum/atomic temp+replace/fsync e recovery explícito.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_checkpoint.py` → exit 0; truncation, checksum, atomic recovery and no-replay cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_checkpoint.py`.
- **Acceptance:** reload idempotente e evidência intacta.
- **Rollback:** restaurar checkpoint V1; manter fixtures fora do runtime.
- **Gate:** G3 passa apenas com fault injection.

## Wave 2 — Contracts e validação segura (pode paralelizar após Wave 1, ownership exclusivo)

### T2-06 — AgentReport strict/completeness
- **Objective:** rejeitar reports semanticamente insuficientes.
- **Exact files:** `scripts/pd_fleet/contracts.py`, `tests/fleet/test_v2_agent_report.py` (Create).
- **Dependencies:** T2-03 | **Role/capabilities:** schema, validation, redaction.
- **Allowed paths:** esses paths. **Forbidden:** executor/provider.
- **Failing tests:** missing output/evidence/decision, status mismatch, invalid attempts/timestamps, blocker absence; `tests/fleet/test_v2_agent_report.py::test_unknown_fields_rejected_by_default` cobre a policy `reject_unknown_fields=True`.
- **Implementation:** strict constructors, completeness predicates, stable schema errors and redaction-before-store. Campos desconhecidos são rejeitados por default; preservação, se futura, exige versão/policy explícita.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_agent_report.py` → exit 0; completeness, status, redaction and reject-unknown-fields cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_agent_report.py`.
- **Acceptance:** somente report completo pode terminal `completed`.
- **Rollback:** manter `TaskReport` V1 e retirar adapter V2.
- **Gate:** G2.

### T2-07 — ValidationExecutor default-deny
- **Objective:** separar declaração de execução segura.
- **Exact files:** `scripts/pd_fleet/validation_executor.py` (Create), `tests/fleet/test_v2_validation_executor.py` (Create).
- **Dependencies:** T2-03 | **Role/capabilities:** application security, subprocess sandbox.
- **Allowed paths:** esses paths. **Forbidden:** `scripts/pd.py`, shell global, rede.
- **Failing tests:** default deny, shell metacharacters, non-allowlisted argv, traversal, timeout/output limit e `test_default_deny_and_fail_closed_without_sandbox`.
- **Implementation:** implementação local/in-process sem shell por default; policy explícita `allowlist/root/cwd/env/timeout/output_limits/sandbox_capability`; API aceita somente argv estruturado. Sem capability de sandbox, executor opt-in falha fechado (sem fallback); modo declarativo nunca executa.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_validation_executor.py -k 'deny or allowlist or traversal or timeout or output or sandbox'` → exit 0; unsafe/default-deny and sandbox-fail-closed cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_validation_executor.py`; `python -m compileall scripts/pd_fleet`.
- **Acceptance:** sem policy nenhum processo; com policy somente comandos exatos e sandboxados.
- **Rollback:** remover executor e deixar validação declarativa.
- **Gate:** G4, security review obrigatório.

### T2-08 — Adapter/provider boundary default-deny
- **Objective:** fixar protocolo futuro sem habilitar provider externo.
- **Exact files:** `scripts/pd_fleet/provider.py` (Create), `tests/fleet/test_v2_provider_boundary.py` (Create).
- **Dependencies:** T2-06 | **Role/capabilities:** API design, security, adapters.
- **Allowed paths:** esses paths. **Forbidden:** SDKs, secrets, sockets, network, dispatch real.
- **Failing tests:** factory default disabled, capability mismatch, credential/network injection rejected.
- **Implementation:** `ProviderAdapter` protocol + `DisabledProvider`; explicit policy and audit reason.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_provider_boundary.py` → exit 0; disabled factory, capability mismatch and network/credential rejection cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_provider_boundary.py`.
- **Acceptance:** import/protocol existe; nenhuma chamada externa possível no default.
- **Rollback:** retirar protocolo/adaptador sem mudar `dispatch.py` V1.
- **Gate:** G4.

## Wave 3 — Orchestrator seguro (serial até integração)

### T2-09 — Reconciliation no orchestrator
- **Objective:** impedir execução sobre estado driftado/stale.
- **Exact files:** `scripts/pd_fleet/orchestrator.py` (existe), `tests/fleet/test_v2_reconciliation.py` (Create).
- **Dependencies:** T2-04,T2-05,T2-06 | **Role/capabilities:** orchestration, state machines.
- **Allowed paths:** esses paths. **Forbidden:** CLI/provider.
- **Failing tests:** plan hash drift, stale lease, orphaned running, duplicate event, missing checkpoint.
- **Implementation:** `reconcile()` antes de readiness/dispatch; fail closed e eventos de diagnóstico.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_reconciliation.py` → exit 0; drift, stale lease, orphan, duplicate-event and missing-checkpoint cases block before dispatch.
- **Verification:** `pytest -q tests/fleet/test_v2_reconciliation.py`.
- **Acceptance:** zero dispatch antes de reconciliation válida.
- **Rollback:** desabilitar somente entrypoint V2; conservar resume V1.
- **Gate:** G3.

### T2-10 — Local safe execution path e report commit
- **Objective:** executar apenas adapter local/in-process e commitar report estrito.
- **Exact files:** `scripts/pd_fleet/dispatch.py` (existe), `scripts/pd_fleet/orchestrator.py`, `tests/fleet/test_v2_local_execution.py` (Create).
- **Dependencies:** T2-07,T2-08,T2-09 | **Role/capabilities:** orchestration, TDD.
- **Allowed paths:** esses paths. **Forbidden:** shell/provider externo.
- **Failing tests:** no external side effect, incomplete report rejected, idempotent commit, retry explicit.
- **Implementation:** adapter local simulado, result normalization, store commit único por attempt.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_local_execution.py` → exit 0; local-only execution, strict report commit and idempotency cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_local_execution.py`.
- **Acceptance:** local safe funciona; `completed` só com report válido.
- **Rollback:** voltar ao `Dispatcher` simulado V1.
- **Gate:** G3 + G4.

### T2-11 — Métricas, audit e redaction
- **Objective:** observabilidade útil sem exfiltração.
- **Exact files:** `scripts/pd_fleet/observability.py` (Create), `tests/fleet/test_v2_observability.py` (Create).
- **Dependencies:** T2-06,T2-09 | **Role/capabilities:** monitoring, privacy.
- **Allowed paths:** esses paths. **Forbidden:** telemetry/network sinks.
- **Failing tests:** ordered events, counters, correlation IDs, secret/path/URL redaction.
- **Implementation:** in-process sink append-only, monotonic sequence, bounded fields, deterministic export.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_observability.py` → exit 0; ordered audit, counters, IDs and secret/path/URL redaction pass.
- **Verification:** `pytest -q tests/fleet/test_v2_observability.py`.
- **Acceptance:** auditoria reconstruível localmente; payload sensível ausente.
- **Rollback:** no-op sink, sem remover reports persistidos.
- **Gate:** G3.

## Wave 4 — Paralelismo real (serial, somente após G3)

### T2-12 — Lease/ownership scheduler
- **Objective:** preparar execução concorrente sem corrida.
- **Exact files:** `scripts/pd_fleet/scheduler.py` (Create), `tests/fleet/test_v2_scheduler.py` (Create).
- **Dependencies:** T2-04,T2-09 | **Role/capabilities:** concurrency, locking, DAG.
- **Allowed paths:** esses paths. **Forbidden:** executor/provider/CLI.
- **Failing tests:** no duplicate claim, bounded claims, overlap rejection, stale lease recovery.
- **Implementation:** select sorted ready IDs, atomically claim leases, release/renew and deterministic capacity.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_scheduler.py` → exit 0; exclusive claims, bounded capacity, overlap rejection and stale-lease recovery pass.
- **Verification:** `pytest -q tests/fleet/test_v2_scheduler.py`.
- **Acceptance:** dois workers não obtêm mesma task; capacity nunca excede limit.
- **Rollback:** scheduler fica em modo serial read-only.
- **Gate:** G5-pre.

### T2-13 — Bounded parallel executor
- **Objective:** substituir batching serial por concorrência real controlada.
- **Exact files:** `scripts/pd_fleet/parallel.py` (Create), `tests/fleet/test_v2_parallel.py` (Create).
- **Dependencies:** T2-10,T2-12 | **Role/capabilities:** Python concurrency, fault testing.
- **Allowed paths:** esses paths. **Forbidden:** `scripts/pd.py`, shell/provider.
- **Failing tests:** barrier proves overlap, max workers, exception/timeout, cancellation, no unbounded threads.
- **Implementation:** executor in-process bounded; results buffered by task ID; no worker mutates store directly.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_parallel.py` → exit 0; overlap, worker bound, timeout/exception and cancellation cases pass.
- **Verification:** `pytest -q tests/fleet/test_v2_parallel.py` (repetir 20x).
- **Acceptance:** overlap mensurável e bounded; falhas são reports, não crashes silenciosos.
- **Rollback:** feature flag off e adapter serial local.
- **Gate:** G5 somente após evidência repetível.

### T2-14 — Ordering/concurrency integration
- **Objective:** integrar scheduler+executor+store com commits determinísticos.
- **Exact files:** `scripts/pd_fleet/orchestrator.py`, `tests/fleet/test_v2_concurrency_integration.py` (Create).
- **Dependencies:** T2-11,T2-13 | **Role/capabilities:** integration, determinism.
- **Allowed paths:** esses paths. **Forbidden:** V1 docs/code fora deles.
- **Failing tests:** randomized completion order gives identical JSON/events; dependency barriers and max_parallel.
- **Implementation:** reconcile→claim→run→sort results→CAS commit→next wave; deterministic cancellation.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_concurrency_integration.py` → exit 0; randomized completion yields identical ordered JSON/events and respects barriers.
- **Verification:** `pytest -q tests/fleet/test_v2_concurrency_integration.py`; 20 repeated runs.
- **Acceptance:** output/hash iguais sob schedules distintos; no overlap/duplicate commit.
- **Rollback:** disable parallel mode, retain persisted run format.
- **Gate:** G5.

## Wave 5 — CLI, docs, roadmap e gates (serial)

### T2-15 — CLI adapter e compatibilidade
- **Objective:** expor V2 read/run-local sem acoplar store à CLI.
- **Exact files:** `scripts/pd.py` (existe), `tests/fleet/test_v2_cli.py` (Create), `tests/test_pd.py` (existe; somente regressão/addição).
- **Dependencies:** T2-14 | **Role/capabilities:** CLI, compatibility.
- **Allowed paths:** parser/adapter V2 e testes. **Forbidden:** alterar semântica legada/V1 docs.
- **Failing tests:** legacy unchanged, JSON canonical, dry-run no mutation, external provider denied.
- **Implementation:** comandos finos que chamam store/orchestrator; mensagens não incluem abs paths.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_cli.py tests/test_pd.py` → exit 0; V1 regression, V2 dry-run/canonical output and provider denial pass.
- **Verification:** `pytest -q tests/fleet/test_v2_cli.py tests/test_pd.py`.
- **Acceptance:** legado passa; V2 local é explícito e seguro.
- **Rollback:** retirar subcommands V2, sem reverter store.
- **Gate:** G6-pre.

### T2-16 — Human verification gate
- **Objective:** impedir release automático sem decisão humana.
- **Exact files:** `scripts/pd_fleet/gates.py` (existe), `tests/fleet/test_v2_human_gate.py` (Create).
- **Dependencies:** T2-11,T2-14 | **Role/capabilities:** governance, security.
- **Allowed paths:** esses paths. **Forbidden:** autoapprove, provider, merge/push.
- **Failing tests:** missing identity/evidence/decision, stale evidence, BLOCKER/HIGH, artifact change reopens; `test_identity_decision_digest_and_freshness_are_required` cobre ownerless decision e freshness window.
- **Implementation:** typed decision registra `identity: str`, owner/decision, escopo, `evidence_digest`, `created_at`, `updated_at` e `freshness_window`; rejeita digest stale ou decisão sem owner/identity. Identity é registro, não autenticação criptográfica; autenticação real futura é out-of-scope.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_human_gate.py` → exit 0; owner/identity/decision/digest/freshness, stale reopen and severity blocking pass.
- **Verification:** `pytest -q tests/fleet/test_v2_human_gate.py`.
- **Acceptance:** only explicit APPROVED releases; pending is blocking.
- **Rollback:** gate remains pending; no bypass flag.
- **Gate:** G6 human approval required.

### T2-17 — Docs, examples e roadmap
- **Objective:** document safe local mode, opt-in executor/provider boundaries and operational recovery.
- **Exact files:** `.spec/pd-fleet-orchestration-v2/SPEC.md`, `.spec/pd-fleet-orchestration-v2/CONTEXT.md`, `README.md`, `ROADMAP.md`, `docs/ARCHITECTURE.md`, `examples/pd-fleet/README.md`, `scripts/pd_fleet/v2_doc_paths.py` (implementado; checker stdlib-only/offline), `tests/fleet/test_v2_doc_paths.py` (implementado).
- **Dependencies:** T2-01 (contrato, ownership e matriz de referências), T2-15 (compatibilidade/CLI), T2-16 (contrato do human gate), T2-02…T2-14 (reviews e resultados a documentar); **Role/capabilities:** documentação, roadmap, verificação determinística de paths/links, Python stdlib/offline, pytest; smoke `pytest -q` e checker devem estar disponíveis antes do handoff.
- **Allowed paths:** exact files acima, incluindo `scripts/pd_fleet/v2_doc_paths.py` e `tests/fleet/test_v2_doc_paths.py`. **Forbidden:** `.spec/pd-fleet-orchestration/*`, qualquer outro código/teste, rede, commits/push.
- **Failing tests:** histórico TDD já encerrado em `tests/fleet/test_v2_doc_paths.py`, cobrindo root explícito, referências Create/Exact/Allowed, ownership/tarefa correta, V1 forbidden, links/âncoras, JSON determinístico e exits 0/1/2.
- **Implementation:** examples sem credenciais, threat model, migration/rollback and roadmap statuses PARTIAL/OPEN.
- **Commands / Expected results:** `pytest -q tests/fleet/test_v2_doc_paths.py` → exit 0; `python scripts/pd_fleet/v2_doc_paths.py <repo-root>` → exit 0 e JSON determinístico sem violações. Evidência fresca registrada em `VERIFICATION.md`.
- **Verification:** `pytest -q tests/fleet/test_v2_doc_paths.py`; `python scripts/pd_fleet/v2_doc_paths.py <repo-root>`; `git diff --check`.
- **Acceptance:** nenhuma promessa de provider/parallel PASS; todos limites claros.
- **Rollback:** reverter somente docs V2/roadmap edits.
- **Gate:** G6-pre.

### T2-18 — Evidence pack, final review e handoff humano
- **Objective:** produzir evidência completa e fechar plano sem implementar/commitar.
- **Exact files:** `.spec/pd-fleet-orchestration-v2/GRILL-001.md`, `.spec/pd-fleet-orchestration-v2/PROMPT-NEXT.md`, `.spec/pd-fleet-orchestration-v2/RESEARCH.md` e `.spec/pd-fleet-orchestration-v2/VERIFICATION.md` (implementados; evidence pack atual).
- **Dependencies:** T2-01…T2-17, incluindo contrato e implementação/testes de `scripts/pd_fleet/v2_doc_paths.py` e `tests/fleet/test_v2_doc_paths.py` em T2-17 | **Role/capabilities:** release reviewer, evidence, human gate, docs/path checker, pytest, git diff.
- **Allowed paths:** `.spec/pd-fleet-orchestration-v2/GRILL-001.md`, `.spec/pd-fleet-orchestration-v2/PROMPT-NEXT.md`, `.spec/pd-fleet-orchestration-v2/RESEARCH.md`, `.spec/pd-fleet-orchestration-v2/VERIFICATION.md` (Create), `scripts/pd_fleet/v2_doc_paths.py`, `tests/fleet/test_v2_doc_paths.py`. **Forbidden:** código V1, outros paths, V1 docs, commit/push, external dispatch.
- **Failing tests:** `git diff --check`; full pytest; `python scripts/pd_fleet/v2_doc_paths.py <repo-root>`; path-reference checker; review matrix sem PASS indevido.
- **Implementation:** reunir comandos/outputs frescos, riscos residuais, decisão humana e rollback; atualizar prompt reutilizável. O pacote atual registra `NOT READY / PARTIAL`; nenhuma decisão humana `APPROVED` foi inventada.
- **Commands / Expected results:** `pytest -q && git diff --check && python scripts/pd_fleet/v2_doc_paths.py <repo-root>` → exit 0; a suíte, whitespace e checker passam, e GRILL-001 continua PENDING até rerun formal.
- **Verification:** `pytest -q`; `git diff --check`; `python scripts/pd_fleet/v2_doc_paths.py <repo-root>`; `git status --short`; `git diff --stat -- .spec/pd-fleet-orchestration-v2`.
- **Acceptance:** somente artefatos V2 modificados, diff whitespace limpo, todos gates explicitamente evidenciados; aprovação humana registrada fora do agente.
- **Rollback:** remover diretório V2 inteiro restaura exatamente a branch original.
- **Gate:** G6 final; sem APPROVED, status permanece NOT READY.

## Matriz de cobertura

| Requirement | Tasks | Gate |
|---|---|---|
| R1–R2 | T2-01…03 | G2/G3 |
| R3–R4 | T2-04…06,T2-09 | G3 |
| R5 | T2-07 | G4 |
| R6 | T2-06 | G2 |
| R7–R8 | T2-12…14 | G5 |
| R9 | T2-08 | G4 |
| R10 | T2-11 | G3 |
| R11 | T2-16 | G6 |
| R12 | T2-15,T2-17,T2-18 | G6 |

## Rollback global

Desabilitar feature flag V2 e continuar lendo V1; preservar snapshots/events; nunca apagar estado para “corrigir” drift. Em falha de qualquer gate, parar a wave, registrar blocker e solicitar revisão humana.
