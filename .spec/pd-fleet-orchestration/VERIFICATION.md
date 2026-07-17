# PD Fleet Orchestration — Verification (R3)

**Data da verificação:** 2026-07-17
**Escopo:** remediações T1–T13, R1/R2 e matching de papel/capabilities.
**Gate:** este documento registra evidência executada; ele não substitui aprovação humana nem autoriza um `PASS` global sem o verification gate.

## Resultado resumido

- Suíte completa: **278 passed** (`python -m pytest -q`, 0.83 s).
- Suíte de fleet/regressão: **166 passed** (`tests/fleet` selecionados, 0.23 s).
- Exemplo local `run_local.py`: executado com sucesso; produziu contratos, resultados T-001/T-002/T-003, reports, evidências, gates e summary.
- O caminho CLI `fleet-run` foi exercitado em normal, `--dry-run` e `--resume`. Com o manifesto versionado, G1 está `pending`; portanto o comportamento fail-closed observado é `blocked` (T-001/T-002 completed; T-003 blocked). Isso é evidência de gate aplicado, não um PASS do caso completo.
- **Status desta verificação: PARTIAL / aguardando aprovação do verification gate.** Não há claim de PASS global.

## Comandos e resultados reais

Todos os comandos abaixo foram executados a partir da raiz do repositório, salvo o smoke CLI que usa um diretório temporário para não mutar o checkout.

```text
$ python -m pytest -q
278 passed in 0.83s

$ python -m pytest -q tests/fleet/test_orchestrator.py tests/fleet/test_resume.py \
    tests/fleet/test_contracts.py tests/fleet/test_gates.py tests/fleet/test_evidence.py \
    tests/fleet/test_dispatch.py tests/fleet/test_cli_inspection.py tests/fleet/test_example_e2e.py
166 passed in 0.23s

$ python examples/pd-fleet/run_local.py \
    --plan examples/pd-fleet/plan.yaml --output /tmp/pd-fleet-r3
exit 0
arquivos produzidos: contracts.json, evidence.json, gates.json, reports.json,
results/T-001.json, results/T-002.json, results/T-003.json, summary.json
resultado dos três tasks: completed

$ python scripts/pd.py fleet-run --feature demo --plan <tmp>/fleet.yaml --json
exit 1; status=blocked; completed=[T-001,T-002]; blocked=[T-003]
statuses: T-001=completed, T-002=completed, T-003=blocked

$ python scripts/pd.py fleet-run --feature demo --plan <tmp>/fleet.yaml --dry-run --json
exit 1; status=dry_run; nenhum task executado/mutado; T-001/T-002=pending; T-003=blocked

$ python scripts/pd.py fleet-run --feature demo --plan <tmp>/fleet.yaml --resume --json
exit 1; status=blocked; T-001/T-002 permaneceram completed; T-003 permaneceu blocked

$ python -m pytest -q tests/fleet/test_cli_inspection.py
3 passed

$ git diff --check
sem saída (exit 0)
```

Os caminhos `<tmp>` acima são deliberadamente abreviados: o smoke foi executado em diretório temporário, com `STATE.json` inicial e cópia local de `examples/pd-fleet/plan.yaml`.

## Evidência por comportamento

| Área | Evidência reproduzível | Resultado |
|---|---|---|
| Testes e compatibilidade | `python -m pytest -q` | PASS — 278 testes |
| Fleet-run local | `python examples/pd-fleet/run_local.py ...` | PASS — três tasks completed, sem credenciais |
| Normal/dry-run/resume | três comandos CLI acima | PASS do comportamento fail-closed/read-only; caso CLI com G1 pending fica BLOCKED por desenho |
| Checkpoint roundtrip | `tests/fleet/test_orchestrator.py`, `test_resume.py` | PASS — snapshot serializa/carrega e não repete completed |
| Read-only/mtime | `tests/fleet/test_cli_inspection.py::test_json_and_text_are_read_only` | PASS — bytes e `st_mtime_ns` de `STATE.*` inalterados |
| Default-deny, sem subprocesso/rede | `tests/fleet/test_dispatch.py`, `test_example_e2e.py`; implementação usa adapter local | PASS — exemplo não chama provider, shell, subprocess ou rede |
| Retry/limites | `tests/fleet/test_resume.py`, testes de lifecycle/orchestrator | PASS — retryable, limite e retry explícito; não-retryable rejeitado |
| Inputs/blocked_when/gates | `tests/fleet/test_validation.py`, `test_orchestrator.py`, `test_gates.py`, smoke CLI | PASS — dependência/gate bloqueia; progressão não ocorre silenciosamente |
| Output sanitization | `tests/fleet/test_evidence.py`, `test_orchestrator.py` | PASS — exceções/saídas são sanitizadas e referências resolvidas |
| Role/capability matching | `test_orchestrator.py::test_declared_agent_matching_role_and_capabilities_dispatches` e testes negativos | PASS — mismatch/owner ausente bloqueia antes do dispatch |

## Matriz R1–R18

`PASS` nesta tabela significa que há teste/evidência fresca para o comportamento local. Não significa provider externo, execução distribuída ou aprovação humana.

| Req. | Status | Evidência / limite honesto |
|---|---|---|
| R1 | PASS | IDs estáveis, serialização e validação de modelo/testes. |
| R2 | PASS | Contrato inclui role, DAG, paths, inputs, outputs, critérios, blocked_when e retry; aplicado no fluxo local. `validation_commands` continuam declarativos. |
| R3 | PASS | Agente elegível exige role e capabilities; mismatch bloqueia antes do dispatch. |
| R4 | PASS | AgentReport/evidence com status, tentativa, agente, outputs, comandos/referências, riscos e blockers cobertos pelos testes. |
| R5 | PASS | IDs duplicados, dependência inexistente e ciclos rejeitados. |
| R6 | PASS | Campos mínimos, outputs e acceptance criteria ausentes rejeitados. |
| R7 | PASS | Ownership/allowed paths sobrepostos são detectados e não paralelizam. |
| R8 | PASS | Elegibilidade é determinística e respeita dependências, inputs, blocked_when e gates. |
| R9 | PASS | Lifecycle completo e transições inválidas cobertos. |
| R10 | PASS | Estado legado é normalizado sem perder compatibilidade. |
| R11 | PASS | Waves/tasks/agentes/tentativas/blockers/gates/evidências são representados e recarregáveis no estado fleet. |
| R12 | PASS | Inspeção texto/JSON e dry-run não mutam estado; mtime testado. |
| R13 | PASS | Checkpoint roundtrip/resume exclui tasks completed; crash/orphan e retry têm cobertura. |
| R14 | PARTIAL | Gates locais reais/fail-closed são testados, mas comandos de validação do manifesto não são executados pelo runtime; por isso não se afirma evidência completa de acceptance gate. |
| R15 | PASS | Templates, contratos e documentação de task/report existem e são exercitados. |
| R16 | PASS | `run_local.py` reproduz o exemplo completo com três tasks e outputs, sem provider externo. |
| R17 | PASS | Persistência/checkpoint e preservação de evidências têm roundtrip e testes de recovery; execução distribuída não é coberta. |
| R18 | PARTIAL | Orchestrator local aplica DAG, gates, ownership, lifecycle, retry e matching; integração com provider externo permanece fora do default e não foi reivindicada. |

## Caveats remanescentes

1. `validation_commands` são **declarativos**: são armazenados/transportados no contrato, mas o caminho local não executa comandos arbitrários. Não tratar sua presença como resultado de validação.
2. A saída JSON bruta do CLI contém timestamps e paths absolutos do plano; execuções podem diferir nesses campos. A semântica/status é determinística, mas não se promete igualdade byte a byte da saída bruta.
3. Por default não há provider externo: o dispatcher é local/simulado e default-deny. Hermes/OpenCode/Claude, rede, credenciais, shell/subprocesso e multi-host não foram testados nem habilitados.
4. O manifesto de exemplo deixa G1 `pending`; o CLI `fleet-run` corretamente bloqueia T-003. O exemplo `run_local.py` constrói evidência local de preflight e completa as três tasks. Esses caminhos não devem ser confundidos.

## Próximos passos

- Aprovar/registrar o verification gate humano com owner, decisão e evidência.
- Definir uma política segura para executar (ou explicitamente não executar) `validation_commands`, mantendo default-deny.
- Fixar um formato de comparação sem timestamps/paths para determinismo de saída, ou documentar normalização oficial.
- Se necessário, adicionar adapter/provider externo atrás de capability explícita, sandbox e gate humano; manter o caminho local como baseline.
- Reexecutar a suíte completa e este smoke após qualquer alteração, atualizando esta matriz sem apagar o histórico.
