# PD Fleet Orchestration — Plano de Evolução

**Status:** implementação local verificada parcialmente; aguardando verification gate humano
**Branch de planejamento:** `feat/pd-fleet-orchestration-plan`
**Objetivo:** evoluir o PD de um pipeline orientado a fases para um sistema de planejamento e execução coordenada por uma fleet de subagents.

## 1. Visão

O PD continuará sendo o guardrail de desenvolvimento — `spec + plan antes de code` e conclusão baseada em evidências — mas passará a modelar explicitamente:

- waves de execução;
- tasks com contratos verificáveis;
- dependências e caminhos críticos;
- paralelismo seguro;
- papéis de agentes;
- gates de review, grill e smoke test;
- retomada após checkpoint ou falha;
- refinamento do prompt antes e depois da execução.

O resultado não é um conjunto de agentes autônomos editando o mesmo repositório sem coordenação. É uma execução supervisionada, com estado persistente, escopo de arquivos e evidências.

## 2. Princípios não negociáveis

1. **No spec + plan, no code.**
2. **O orchestrator coordena; não implementa por acidente.**
3. **Cada task tem um contrato e um output verificável.**
4. **Paralelismo só ocorre quando dependências e escopos não conflitam.**
5. **Waves são sequenciais; tasks independentes dentro da wave podem ser paralelas.**
6. **Review e validação são gates, não sugestões.**
7. **Nenhuma conclusão sem comando executado e evidência fresca.**
8. **Falha e bloqueio são estados explícitos, nunca silêncio.**
9. **O estado persistido é a fonte de verdade entre contextos.**
10. **Humano aprova decisões irreversíveis, escopo ambíguo e merge final.**

## 3. Modelo operacional final

```text
Goal bruto
  ↓
Prompt Refinement (entrada)
  ↓
Discovery + SPEC
  ↓
Plan Compiler (waves, DAG, contracts)
  ↓
Plan Grill / aprovação
  ↓
Orchestrator
  ├── Researcher(s)
  ├── Coder(s)
  ├── Analyst / Reviewer(s)
  ├── Test / Smoke Tester(s)
  └── Prompt Refiner (saída)
  ↓
Evidence Gate
  ↓
Relatório + próximo prompt / merge
```

## 4. Papéis da fleet

| Papel | Responsabilidade | Pode editar código? |
|---|---|---:|
| `orchestrator` | agenda waves, verifica dependências, atualiza estado, replaneja | não por padrão |
| `researcher` | investiga repo, docs, APIs e alternativas | não |
| `analyst` | revisa requisitos, arquitetura, riscos e completude | não |
| `coder` | implementa uma task delimitada | sim, somente no escopo |
| `test-engineer` | cria/ajusta testes e executa suíte relevante | sim, testes |
| `reviewer` | revisa diff contra contrato e critérios de aceitação | não |
| `grill` | procura falhas, premissas ocultas, gaps e complexidade desnecessária | não |
| `smoke-tester` | executa o caminho crítico em ambiente real | não por padrão |
| `prompt-refiner` | transforma goal, plano e feedback em prompt executável | não |

O monitor é uma função do orchestrator, não um agente com autoridade ilimitada: observa cada transição e pode pausar, bloquear ou solicitar replanejamento.

## 5. Contrato de task

Cada task deverá conter, no mínimo:

```yaml
id: T-001
wave: 1
title: Nome curto
role: coder
objective: Resultado observável
depends_on: []
parallel_group: foundation
allowed_paths: []
forbidden_paths: []
inputs: []
outputs: []
acceptance_criteria: []
validation_commands: []
blocked_when: []
capabilities: []
owner: orchestrator
retry_policy:
  max_attempts: 2
  retryable_errors: []
status: pending
```

O relatório de execução deverá registrar `status`, arquivos alterados, comandos executados, resultados, riscos e blockers.

## 6. Waves e gates (taxonomia canônica)

### Wave 0 — Reconhecimento
Ler contexto obrigatório, pesquisar CLI/estado/templates/testes e registrar baseline.

**Gate G0:** pesquisa concluída e baseline verificável.

### Wave 1 — Design executável
Produzir SPEC, PLAN, DAG, contracts, estratégia de rollback e matriz de cobertura.

**Gate G1:** grill do plano PASS, owner registrado e nenhum BLOCKER/HIGH aberto.

### Wave 2 — Fundação
Implementar modelos, validação de DAG/ownership, lifecycle, gates e templates.

**Regra:** tasks paralelas só com ownership não sobreposto e contrato completo.

### Wave 3 — Estado e inspeção
Integrar `fleet_state` backward-compatible, status, tasks elegíveis e checkpoint/resume.

### Wave 4 — Orquestração local
Integrar protocolo de adapter, adapter simulado e `FleetOrchestrator` com seleção, dispatch e reports.

**Gate:** pelo menos duas tasks independentes e uma dependente executadas localmente.

### Wave 5 — Gates e exemplo
Formalizar review/grill/smoke/evidence e demonstrar o próprio PD como exemplo executável.

### Wave 6 — Review pós-código e prompt refinement
Reviewer, analyst e grill verificam requisitos, diff, segurança, regressões, premissas e complexidade. O prompt-refiner incorpora os findings em um prompt reutilizável.

**Gate:** zero blocker aberto ou decisão humana explícita.

### Wave 7 — Smoke e evidence gate
Executar build, inicialização, caminho crítico e testes mínimos. Gerar `VERIFICATION.md` com evidências.

### Wave 8 — Closeout
Atualizar estado, changelog e relatório. Merge somente após aprovação humana.

## 7. Dependências e paralelismo

Uma task pode rodar em paralelo somente se:

- todas as dependências estiverem concluídas;
- os paths de escrita não se sobrepuserem;
- não depender de uma decisão ainda aberta;
- o contrato de entrada estiver disponível;
- o ambiente/fixture compartilhado não gerar corrida.

O orchestrator deverá identificar automaticamente o conjunto elegível e pausar a wave se houver conflito. O plano deve distinguir dependência real de mera ordem conveniente.

## 8. Estado persistente

A implementação deverá estender o estado atual do PD sem quebrar compatibilidade:

- `STATE.json`: estado de execução, waves, tasks, agentes, tentativas, blockers e evidências;
- `STATE.md`: visão humana resumida;
- `PLAN.md`: plano legível e contratos;
- `VERIFICATION.md`: evidências de validação;
- `CHECKPOINT.md`: retomada entre contextos.

Estados mínimos de task: `pending`, `ready`, `running`, `blocked`, `failed`, `completed`, `skipped`.

Transições inválidas devem ser rejeitadas pelo CLI/validador.

## 9. Ordem de implementação

1. Definir schema de waves/tasks/dependências e validar YAML/JSON.
2. Criar templates de task, wave, agent report e fleet status.
3. Implementar validação de DAG, paths, critérios e transições.
4. Adicionar comandos CLI read-only para visualizar fleet e tasks elegíveis.
5. Adicionar checkpoints e resume por task/wave.
6. Adicionar dispatcher/adapters para execução por subagents.
7. Adicionar isolamento de execução e detecção de conflitos.
8. Implementar gates de review, grill e smoke/evidence.
9. Implementar Prompt Refinement de entrada e saída.
10. Atualizar skill `pd`, exemplos, testes, documentação e compatibilidade Hermes/OpenCode/Claude.

## 10. Critérios de sucesso

- Um goal complexo gera um plano reproduzível com DAG e waves.
- Tasks paralelas não compartilham escrita sem contrato explícito.
- Uma sessão nova consegue retomar pelo estado persistido.
- Falhas são localizadas e reexecutáveis sem replay cego.
- Review, grill e smoke test produzem evidência auditável.
- O primeiro caso — a própria evolução do PD — é executável pelo prompt final deste branch.
- O comportamento antigo de pipeline simples permanece compatível.

## 11. Fora de escopo inicial

- Inferência autônoma ilimitada de novos agentes.
- Deploy automático em produção.
- Merge automático sem gate humano.
- Orquestração distribuída multi-host.
- Dependência de um único provedor/modelo.
- Métricas sofisticadas antes de existir um fluxo funcional.

## 12. Remediações R3 e verification gate

As remediações T1–T13, R1/R2 e matching de `role`/`capabilities` foram incorporadas ao caminho local. A evidência atual está em [`.spec/pd-fleet-orchestration/VERIFICATION.md`](../.spec/pd-fleet-orchestration/VERIFICATION.md): a suíte completa registra 278 testes passando, o exemplo local é executável sem provider externo e o CLI `fleet-run` foi exercitado em normal, `--dry-run` e `--resume`.

O estado documental é deliberadamente **PARTIAL até o verification gate**. Nenhum gate declarativo, número de testes ou smoke local autoriza declarar PASS global sem comando executado, evidência fresca, owner e decisão registrados. Em particular, `validation_commands` permanecem declarativos; a saída JSON bruta pode variar em timestamps/paths; e provider externo não é habilitado por default.

O histórico de planejamento e de findings anteriores permanece preservado nos artefatos existentes. Após qualquer remediação, reexecutar a suíte e o smoke, atualizar `VERIFICATION.md` e somente então registrar a decisão humana de closeout.
