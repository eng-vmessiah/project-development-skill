# PD Fleet Orchestration — Plano de Evolução

**Status:** plano histórico de evolução; o objetivo vigente é verificação local/simulada, sem
runtime live ou produção
**Branch de planejamento:** `feat/pd-fleet-orchestration-plan`
**Objetivo histórico:** evoluir o PD de um pipeline orientado a fases para um sistema de
planejamento e coordenação por uma fleet de subagents. A direção vigente restringe a execução
ao protocolo local/simulado.

## 0. Direção vigente e limites

Este documento preserva o histórico do plano e de suas remediações, mas não deve ser lido como
declaração de runtime ativo. **PD** continua sendo o compiler/workflow e a camada de decisão;
**PD Fleet** é uma extensão opcional de coordenação local; **Hermes Runtime/Gateway** hospeda
sessões, `delegate_task`, cron, providers, ferramentas, capabilities e os eventos/transportes
consumidos pelos clientes; **OMH** é somente referência/aprendizagem.
O objetivo local atual é planejar, validar, reivindicar, executar de forma simulada/local,
reconciliar e reportar tasks sem rede, credenciais, provider externo, cron, deployment ou
dispatch live. Não há claim de produção, sandbox de produção, worker pool ou operação multi-host.

O `HermesGatewayFleetBridge` — Gateway Hermes → Fleet events/state — é o follow-up de integração
atual. Primeiro cobre sessões `user_owned_session` de modo read-only; uma sessão
`fleet_owned_task` e o envelope Fleet → execução Hermes são uma etapa posterior, separada e
explicitamente autorizada. Isso não é uma implementação presente nem autorização para ativar
runtime Hermes ou integração OMH.

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
Orchestrator local
  ├── Researcher(s)
  ├── Coder(s)
  ├── Analyst / Reviewer(s)
  ├── Test / Smoke Tester(s)
  └── Prompt Refiner (saída local)
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
| `smoke-tester` | executa o caminho crítico em ambiente local/simulado | não por padrão |
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
Integrar o seam de protocolo, um adapter local/simulado e `FleetOrchestrator` com seleção, dispatch
local e reports. Esta wave deve funcionar sem Hermes instalado. A integração com o Hermes Gateway
permanece no follow-up opcional `.spec/pd-fleet-hermes-gateway-fleet-v1/` e não é pré-requisito
para fechar o Fleet local.

**Gate:** pelo menos duas tasks independentes e uma dependente executadas localmente.

### Wave 5 — Gates e exemplo
Formalizar review/grill/smoke/evidence e demonstrar o próprio PD como exemplo executável.

### Wave 6 — Review pós-código e prompt refinement
Reviewer, analyst e grill verificam requisitos, diff, segurança, regressões, premissas e complexidade. O prompt-refiner incorpora os findings em um prompt reutilizável.

**Gate:** zero blocker aberto ou decisão humana explícita.

### Wave 7 — Smoke local e evidence gate
Executar build, inicialização, caminho crítico local/simulado e testes mínimos. Gerar
`VERIFICATION.md` com evidências, sem inferir disponibilidade de produção.

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

## Authority and state boundaries

The `.spec` control plane is authoritative for PD intent, task contracts, development gates, acceptance, and human delivery decisions. Fleet state is authoritative for generic coordination: task lifecycle, leases, checkpoints, reports, event reconciliation, and session/task association when an adapter provides that capability. PD Core and Fleet local must not require Hermes. A runtime adapter is selected explicitly (`none`, `local`, `hermes`, or future adapters) and exposes capabilities rather than assumptions. Hermes runtime state is authoritative only for Hermes-backed sessions, tools, providers, capabilities, and runtime events. The dashboard is a sibling Gateway client, not a Fleet dependency. Fleet or runtime state cannot substitute for a PD decision, approve a merge, change scope, or declare release readiness.

The term **scheduler** in Fleet means deterministic ready-set calculation and local claim coordination inside an already-created run. It does not mean a persistent service, cron, worker daemon, or production scheduler; those remain outside Fleet and cron remains a Hermes responsibility.

## 8. Estado persistente

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
6. Definir e testar a interface capability-based de runtime adapters, incluindo adapter `local` sem Hermes.
7. Adicionar dispatcher/adapters para execução por subagents.
8. Adicionar isolamento de execução e detecção de conflitos.
9. Implementar gates de review, grill e smoke/evidence.
10. Implementar Prompt Refinement de entrada e saída.
11. Atualizar skill `pd`, exemplos, testes e documentação; registrar Hermes/OpenCode/Claude como adapters opcionais sem ativar adapters de runtime por default.
12. Tratar a integração Hermes em trilha opcional de plugin/adapter `pd-fleet-hermes`: B15a TUI local por sessão, depois B15b Gateway/API de mensagens. O plugin não contém o Fleet Core.

## 10. Critérios de sucesso

- Um goal complexo gera um plano reproduzível com DAG e waves.
- Tasks paralelas não compartilham escrita sem contrato explícito.
- Uma sessão nova consegue retomar pelo estado persistido.
- Falhas são localizadas e reexecutáveis sem replay cego.
- Review, grill e smoke test produzem evidência auditável.
- O primeiro caso — a própria evolução do PD — é executável localmente pelo prompt final deste
  branch.
- O comportamento antigo de pipeline simples permanece compatível.

## 11. Fora de escopo inicial

- Inferência autônoma ilimitada de novos agentes.
- Cron, scheduler de produção, providers live, deployment e integração runtime do OMH.
- Deploy automático em produção.
- Merge automático sem gate humano.
- Orquestração distribuída multi-host.
- Dependência de um único provedor/modelo.
- Métricas sofisticadas antes de existir um fluxo funcional.

## 12. Remediações R3 e verification gate (registro histórico)

As remediações T1–T13, R1/R2 e matching de `role`/`capabilities` foram registradas como parte
do caminho local histórico. A evidência então registrada está em
[`.spec/pd-fleet-orchestration/VERIFICATION.md`](../.spec/pd-fleet-orchestration/VERIFICATION.md):
a suíte completa registra 278 testes passando, o exemplo local é executável sem provider externo
e o CLI `fleet-run` foi exercitado em normal, `--dry-run` e `--resume`. Esses registros não
constituem evidência de produção ou de runtime live.

O estado documental é deliberadamente **PARTIAL até o verification gate**. Nenhum gate declarativo, número de testes ou smoke local autoriza declarar PASS global sem comando executado, evidência fresca, owner e decisão registrados. Em particular, `validation_commands` permanecem declarativos; a saída JSON bruta pode variar em timestamps/paths; e provider externo não é habilitado por default.

O histórico de planejamento e de findings anteriores permanece preservado nos artefatos existentes. Após qualquer remediação, reexecutar a suíte e o smoke, atualizar `VERIFICATION.md` e somente então registrar a decisão humana de closeout.
