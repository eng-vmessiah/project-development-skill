# Prompt refinado — próxima sessão do caso PD Fleet

> **Artefato de continuação (T14).** Copie este arquivo como prompt de entrada para uma sessão nova. Ele é deliberadamente honesto: a suíte atual passa, mas a implementação ainda não satisfaz o protocolo completo. Não converter os findings abaixo em PASS por inferência.

## Goal

Completar e validar a primeira implementação executável de orquestração local do Project Development Skill (PD): transformar um goal em waves/tasks com contratos, DAG, ownership, lifecycle, retry, gates, evidências, estado persistente e resume determinístico, mantendo o fluxo legado compatível. O resultado deve ser demonstrável no exemplo `examples/pd-fleet/`, sem credenciais, rede ou despacho externo.

## Contexto obrigatório e baseline

Repositório: `project-development-skill`. Leia antes de editar:

- `README.md`, `ROADMAP.md`, `skills/pd/SKILL.md` e templates em `skills/pd/templates/`;
- `docs/PD-AS-IS-TO-BE.md`, `docs/PD-FLEET-ORCHESTRATION-PLAN.md` e este histórico (`docs/PD-FIRST-CASE-PROMPT.md`);
- `.spec/pd-fleet-orchestration/SPEC.md`, `PLAN.md`, `STATE.md`, `CONTEXT.md`, `GRILL-001.md` e `STATE.json`;
- `scripts/pd.py`, `scripts/pd_fleet/`, `examples/pd-fleet/` e `tests/fleet/`.

Baseline conhecido ao iniciar esta sessão: **272 testes passam**, porém isso não é evidência de cobertura dos requisitos R1–R18 nem autorização para declarar PASS. O estado real e os findings de T15/T16/T17 abaixo prevalecem sobre documentação otimista ou gates declarativos.

## R1–R18 — matriz de verdade a recuperar

Trate cada requisito como critério explícito, com teste e evidência. Marque `PASS`, `PARTIAL` ou `FAIL` somente após verificação fresca:

- **R1** — IDs estáveis para waves/tasks: modelo e validação aparentam existir; confirmar persistência e compatibilidade.
- **R2** — contrato completo por task (`role`, objetivo, dependências, paralelismo, paths, inputs, outputs, critérios, comandos): **PARTIAL** até inputs/blocked_when serem aplicados.
- **R3** — agentes por papel/capacidade sem runtime externo: modelo existe; fechar matching de role/capabilities (finding médio).
- **R4** — AgentReport completo (status, tentativa, agente, arquivos, comandos, evidências, riscos, blockers): **FAIL/PARTIAL** (H-05).
- **R5** — rejeitar IDs duplicados, dependências inexistentes e ciclos: validar com testes negativos.
- **R6** — rejeitar contrato mínimo/acceptance criteria ausentes: validar sem aceitar placeholders.
- **R7** — detectar conflito de ownership/paths em paralelo: validar tanto plano quanto execução.
- **R8** — calcular `ready` deterministicamente somente com dependências e gates satisfeitos: incluir blocked conditions reais.
- **R9** — lifecycle `pending`, `ready`, `running`, `blocked`, `failed`, `completed`, `skipped`: testar transições e rejeição de inválidas.
- **R10** — estender STATE sem quebrar legado: testar migração e leitura de estado antigo.
- **R11** — persistir waves/tasks/agentes/tentativas/blockers/gates/evidências: **PARTIAL** (H-04/H-05); provar escrita atômica e reload.
- **R12** — inspeção read-only de fleet/status/eligible tasks em texto e JSON: fechar CLI/dry-run (finding médio), sem mutação.
- **R13** — checkpoint/resume sem replay de concluídas: **FAIL/PARTIAL** enquanto persistência/resume forem opcionais (H-04).
- **R14** — review/grill/smoke/evidence como gates com status e evidência verificável: **FAIL/PARTIAL** enquanto gates declarativos/falsos passarem (H-03).
- **R15** — templates/documentação de task e AgentReport: template existe; tornar o contrato exigível e relatório completo.
- **R16** — exemplo local sem credenciais demonstrando paralelismo registrado: **PARTIAL** enquanto não houver caminho de `fleet-run` verificável (B-01).
- **R17** — estado com escrita atômica, evidências preservadas e recovery/rollback: testar crash/reload; não confundir arquivo gerado com garantia.
- **R18** — orchestrator local consumindo adapter e aplicando DAG/gates/ownership/lifecycle: **PARTIAL**; exige dispatch do fleet-run, retry, inputs/blocked_when e gates reais.

## Findings T15/T16/T17 (não ignorar)

| ID | Severidade | Evidência/estado observado | Correção exigida |
|---|---|---|---|
| B-01 | **BLOCKER** | Não existe um caminho/CLI `fleet-run` completo e verificável para executar o caso; o exemplo local isolado não prova o contrato operacional fim a fim. | Implementar/ligar o entrypoint local, com manifest, estado, reports, gates e exit code determinísticos; provar no comando de validação. |
| H-01 | **HIGH** | `retry_policy`/`max_attempts` e erros retryable aparecem no contrato, mas o orchestrator não aplica de modo comprovado retry, limite e backoff. | Fazer retry somente para erro permitido, registrar cada tentativa e falhar após o limite; testar erro transitório e não retryable. |
| H-02 | **HIGH** | `inputs` e `blocked_when` são aceitos/serializados, porém não são avaliados de forma efetiva antes de tornar uma task `ready`/executá-la. | Resolver inputs, avaliar condições de bloqueio e produzir blocker acionável; não executar task bloqueada. |
| H-03 | **HIGH** | O orchestrator pode aceitar gates declarativos/falsos (por exemplo, status `passed`) sem verificar evidência/critério produzido. | Gates devem ser avaliados por policy e evidência real; status fornecido pelo plano não substitui prova. Falha bloqueia progressão. |
| H-04 | **HIGH** | Persistência e resume são opcionais/insuficientes para o caminho principal; checkpoint em memória ou ausência de arquivo não garante retomada. | Persistir atomicamente antes/depois de transições, carregar checkpoint, retomar sem replay e preservar blockers/evidências; falha de persistência deve bloquear. |
| H-05 | **HIGH** | `AgentReport` não cobre consistentemente todos os campos exigidos (arquivos, comandos, resultados, evidências, riscos, blockers e handoff). | Tornar schema obrigatório, rejeitar relatório incompleto e emitir relatório auditável por tentativa/task. |
| M-01 | **MEDIUM** | Matching de agentes por `role`/`capabilities` não está demonstrado como restrição de atribuição. | Selecionar apenas agente elegível; ausência/mismatch deve bloquear, com evidência. |
| M-02 | **MEDIUM** | CLI de inspeção/dry-run não está comprovada como interface estável e read-only. | Expor JSON/texto determinístico, `--dry-run` sem lifecycle mutation e testes de saída/exit code. |
| M-03 | **MEDIUM** | Documentação e `VERIFICATION.md` não são consistentes quanto ao que foi realmente executado. | Atualizar apenas evidência fresca e declarar explicitamente comandos não executados; nunca usar texto como substituto de prova. |

## Blockers e regra de status

- **B-01 e H-01..H-05 permanecem abertos no início.** M-01..M-03 também precisam de plano, mas não podem ser escondidos por uma suíte verde.
- Enquanto qualquer `B-01` ou `H-01`–`H-05` estiver aberto, o status global é `BLOCKED`/`INCOMPLETE`; é proibido declarar `PASS`, “completo”, “pronto” ou equivalente.
- `272 passed` significa apenas que os testes existentes passaram. Exigir testes de regressão novos e evidência de comportamento para cada finding.
- Não fechar blocker por documentação, status declarado no YAML, mock sem asserção, ou gate sem evidência verificável.

## Escopo permitido e no external dispatch

Permitido nesta sessão: `scripts/pd.py`, `scripts/pd_fleet/`, `examples/pd-fleet/`, `tests/fleet/`, templates e documentação diretamente necessária ao caso; preservar compatibilidade, histórico e artefatos de estado. Antes de editar, verificar ownership e conflitos.

**No external dispatch:** usar somente adapter simulado/local determinístico. Não chamar Hermes, OpenCode, Claude, APIs, rede, credenciais, subprocesso de shell do adapter, daemon, multi-host ou serviço externo. Se uma capacidade exigir provider externo, registrar `BLOCKED` com evidência e não contornar o gate.

Não fazer merge, commit, reset destrutivo, apagar histórico ou alterar escopo sem decisão humana explícita.

## Contrato obrigatório de task

Toda task nova ou modificada deve registrar, em YAML/JSON e no estado: `id`, `wave`, `title`, `role`, `capabilities`, `objective`, `depends_on`, `parallel_group`, `allowed_paths`, `forbidden_paths`, `inputs`, `outputs` (com obrigatoriedade), `acceptance_criteria`, `validation_commands`, `blocked_when`, `owner`, `retry_policy` (`max_attempts`, `backoff_seconds`, `retryable_errors`) e `status`. IDs e paths devem ser estáveis; ownership paralelo não pode sobrepor.

Toda execução deve produzir um `AgentReport` completo por tentativa: task/wave/role/owner, status, objetivo, dependências, escopo, summary, critérios com evidência, outputs, files changed, comandos exatos e resultados, riscos, blockers, recomendação de retry, handoff e localização de evidência. Relatório incompleto é falha, não sucesso.

## Waves de remediação

1. **Reconhecimento e baseline:** reproduzir 272 testes, ler estado, localizar entrypoints e escrever matriz R1–R18/findings. Gate: baseline reproduzível.
2. **Contratos e seleção:** tornar inputs, blocked_when, role/capabilities, outputs e AgentReport obrigatórios; adicionar testes negativos. Gate: nenhum contrato incompleto aceito.
3. **Execução local e retry:** entregar `fleet-run`/entrypoint local sem providers; aplicar retry/backoff/limites e registrar tentativas. Gate: cenário sucesso, erro retryable e erro definitivo.
4. **Estado e resume:** persistir atomicamente transitions/reports/evidence/blockers; interromper e retomar sem replay. Gate: teste de crash/reload e prova de arquivo.
5. **Gates reais e CLI:** validar review/grill/smoke/evidence por evidência, implementar inspeção/dry-run read-only e exit codes. Gate: gate falso falha e não avança.
6. **Exemplo completo:** executar duas tasks independentes e uma dependente via manifest local, com outputs e blockers reproduzíveis. Gate: B-01 fechado por comando real.
7. **Review, grill e evidence:** spec-compliance, code-quality e adversarial grill; atualizar matriz, `VERIFICATION.md` e findings sem apagar histórico. Gate: cada finding fechado com teste/evidência ou decisão humana.
8. **Closeout honesto:** gerar prompt de continuação/estado; se houver blocker, entregar `INCOMPLETE/BLOCKED` e próximo passo, nunca PASS.

## Dependências e paralelismo

Waves são sequenciais. Tasks só podem ser paralelas se dependências concluídas, role/capability resolvida, inputs disponíveis, `blocked_when` falso, gates da wave aprovados, paths de escrita disjuntos e fixture compartilhada segura. O orchestrator deve ordenar deterministicamente e bloquear conflitos; não assumir que a ordem da lista resolve dependências.

## Acceptance criteria

- [ ] R1–R18 têm status e evidência fresca, sem claims não verificadas.
- [ ] B-01 e H-01..H-05 têm regressão, implementação e evidência; ou permanecem explicitamente `OPEN`.
- [ ] `fleet-run` local reproduzível executa o manifest completo sem dispatch externo.
- [ ] Retry, inputs, blocked_when, matching e AgentReport são aplicados, não apenas armazenados.
- [ ] Gates falsos/declarativos não avançam a execução; gates reais deixam evidência auditável.
- [ ] STATE/checkpoint/resume são persistentes, atômicos e não repetem tasks concluídas.
- [ ] CLI texto/JSON e dry-run são determinísticos e read-only.
- [ ] Compatibilidade do fluxo legado permanece verde.
- [ ] `VERIFICATION.md` distingue comandos executados de comandos apenas planejados.
- [ ] Nenhum PASS global enquanto B-01/H-01..H-05 estiver aberto.

## Validation commands (executar e registrar saída real)

A partir da raiz:

```bash
python -m pytest -q
python -m pytest -q tests/fleet
python examples/pd-fleet/run_local.py --plan examples/pd-fleet/plan.yaml --output /tmp/pd-fleet-output
python -m pytest -q tests/fleet/test_orchestrator.py tests/fleet/test_resume.py tests/fleet/test_contracts.py tests/fleet/test_gates.py tests/fleet/test_evidence.py
python scripts/pd.py --help
python scripts/pd.py validate --help
```

Adicionar e executar comandos específicos para: retry até `max_attempts`, input ausente, `blocked_when`, role/capability incompatível, gate sem evidência, crash/reload/resume e dry-run. Inspecionar os JSON/relatórios gerados e `git diff --check`. Não declarar que um comando foi executado se apenas foi listado.

## Checkpoints, resume e handoff

Antes/depois de cada wave, salvar checkpoint persistente contendo commit/base (sem criar commit), wave/task lifecycle, tentativas, reports, gates, blockers, evidências e próximo conjunto elegível. Ao retomar, validar schema e inputs novamente, preservar evidência anterior, não reexecutar `completed` e marcar divergências como blocker. Ao fim, deixar um handoff com comandos executados, resultados, arquivos e decisão necessária.

## Review / grill / evidence gates

- **Review:** conferir cada diff contra contrato, allowed/forbidden paths e R1–R18.
- **Grill:** tentar gates falsos, relatório incompleto, retry infinito, input ausente, role incompatível, path conflitante, estado corrompido e resume com replay.
- **Smoke:** executar o caminho `fleet-run` completo e consultar status/eligible/dry-run.
- **Evidence gate:** cada PASS de task/gate aponta para saída, arquivo ou teste reproduzível; placeholder e status declarado não contam.
- Qualquer falha pausa a wave, identifica responsável e registra blocker; não mascarar com `skipped` ou PASS global.

## Entrega da sessão

Retornar resumo arquitetural, arquivos alterados, tasks por wave/agente, comandos e resultados reais, matriz R1–R18, findings abertos/fechados, blockers/riscos, decisões humanas, checkpoint/handoff e recomendação objetiva. Sem commit e sem merge automático.
