# PD Fleet Orchestration V2 — Specification

**Status:** Draft para implementação após `GRILL-001` e aprovação humana. Não é PASS.

## Goal e compatibilidade

Entregar coordenação local segura e determinística, com store desacoplado do CLI, reconciliação, reports estritos e paralelismo bounded comprovável. Python 3.12/stdlib + pytest; V1 e comportamento legado permanecem compatíveis.

## Requirements V2

- **V2-R1 Baseline/reconciliation:** antes de mutar/executar, carregar plano canônico, calcular `plan_hash`, comparar generation/run/checkpoints/leases/events e bloquear divergências não reconciliáveis.
- **V2-R2 Normalized deterministic output:** normalizar tipos/aliases/IDs, ordenar coleções e resultados, remover timestamps não determinísticos e relativizar/redigir paths; JSON canônico deve ser byte-estável para mesma entrada.
- **V2-R3 FleetRunStore:** prover API de create/load/transition/lease/append-event/commit/report/query independente de CLI, com owner e compare-and-swap.
- **V2-R4 Checkpoint persistence:** snapshots versionados, escrita atômica, checksum/generation, recovery de arquivo parcial e resume idempotente sem replay de terminal.
- **V2-R5 Safe validation executor:** manter comandos declarativos sem execução; executor opt-in aceita apenas allowlist explícita, argv sem shell, root/sandbox, timeout, ambiente mínimo, output limitado/redigido; default deny.
- **V2-R6 AgentReport strict/completeness:** schema rejeita tipos/status incoerentes; `completed` requer outputs/evidência/testes/decisão; `failed/blocked` exige motivo; unknown fields são tratados por política explícita.
- **V2-R7 True bounded parallelism:** executar tarefas independentes em workers bounded após leases/ownership persistidos; `max_parallel` não pode produzir processos ilimitados nem corrida de commit.
- **V2-R8 Deterministic ordering/concurrency:** seleção, commit, eventos, reports e saída são ordenados por chaves canônicas, independentemente da ordem de conclusão; dependências/gates continuam barreiras.
- **V2-R9 Provider boundary default-deny:** definir protocolo/adaptador capability-based para futuro provider; factory não habilita externo, rede ou credenciais sem policy explícita e gate humano.
- **V2-R10 Metrics/audit:** registrar contadores/latências/resultados e trilha append-only com correlation/run/task IDs, sem conteúdo secreto, path absoluto ou payload não redigido.
- **V2-R11 Human verification gate:** gate final exige owner, identity string auditável, decision, evidence digest e freshness no contexto do run, além de zero BLOCKER/HIGH; ausência ou mudança reabre/bloqueia. Autenticação criptográfica ou identity provider são futuros/out-of-scope.
- **V2-R12 Docs/roadmap/compatibilidade:** documentar contratos, migração, threat model e uso local; preservar V1, adicionar testes de regressão e não alegar PASS sem evidência.

## Critérios de segurança

- Sem `shell=True`, `os.system`, interpolação de comando, rede ou credencial no caminho default.
- Allowlist compara argv/padrão aprovado, não substring; sandbox e timeout são obrigatórios quando executor opt-in.
- Path traversal, symlink escape, glob amplo e ownership ambíguo falham fechado.
- Persistência não perde evidência; crash entre prepare/commit deixa snapshot anterior válido.
- Logs/reports/metrics redigem URL, token, senha, bearer, assignment sensível e paths absolutos.
- Race, stale lease, checksum/hash mismatch e report incompleto bloqueiam, nunca “best effort completed”.

## Critérios de compatibilidade

- `pytest -q` mantém baseline 278+ testes passando.
- Imports e CLI V1 (`pd init`, load/save, estado legado) mantêm resultados anteriores.
- `STATE.json`/`STATE.md` legados carregam sem exigir fleet_state; migração não destrói campos desconhecidos.
- API nova é aditiva e o modo local/simulado é default; `fleet-run` sem executor externo não dispara efeitos.
- JSON novo é versionado e não altera o formato legado fora do namespace V2.

## Critério de sucesso

Todos V2-R1…R12 cobertos por testes/evidência, `git diff --check` limpo, grill sem BLOCKER/HIGH e gate humano explicitamente `APPROVED`. Até lá, status é PARTIAL/OPEN.

## Contratos de gaps obrigatórios

### TOCTOU claim→use→commit
`claim(run_id, task_id)` captura `generation` e `lease_id/expiry`; `use` recebe esses tokens imutáveis; `commit` exige CAS simultâneo de generation e lease. Qualquer token stale é rejeitado antes da mutação. O teste deve tirar snapshot/hash do state, provocar renovação/commit concorrente entre use e commit, provar rejeição e afirmar que state, snapshot, eventos e evidência permanecem inalterados.

### ValidationExecutor
O caminho default é local/in-process e declarativo: `validation_commands` nunca abre shell. O executor opt-in recebe argv estruturado e policy com allowlist exata, root e `cwd` contidos, `env` explícito/mínimo, timeout e limites separados de stdout/stderr (com redaction antes de persistir). `sandbox_capability` deve ser reportada; quando sandbox requerida estiver indisponível, o resultado é erro fail-closed, sem fallback para shell ou execução sem isolamento. Testes cobrem default-deny, argv/metacaracteres, allowlist, traversal, cwd/env, timeout, output limit e capability ausente.

### AgentReport unknown fields
A policy V2 é `reject_unknown_fields=True` por default: qualquer campo fora do schema é erro estável e não é persistido. Preservação de campos desconhecidos é out-of-scope nesta versão e só pode ser introduzida com versionamento e teste de compatibilidade.

### Human verification gate
A decisão registra `identity` como string literal auditável (não prova de autenticação), `owner`, `decision`, `evidence_digest`, `created_at`, `updated_at` e `freshness_window`. O gate rejeita decisão sem owner/identity, digest ausente ou evidência stale, e reabre quando o artifact digest muda. Autenticação criptográfica real é out-of-scope/futura; não deve ser simulada por este contrato.
