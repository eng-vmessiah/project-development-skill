# PD Fleet Orchestration — Specification

**Date:** 2026-07-16
**Status:** `approved — G1 PASS after adversarial grill revalidation`
**Feature:** `pd-fleet-orchestration`

## Problem Statement

O PD já descreve waves e subagents, mas seu estado e CLI só representam fases e uma lista de tarefas concluídas. Isso impede planejar e acompanhar uma fleet de subagents de forma determinística: não há DAG de dependências, ownership de paths, estados operacionais, blockers, evidências ou consulta de tasks elegíveis.

## Goal

Evoluir o núcleo do PD para representar e validar planos orientados a tasks executadas por subagents, mantendo compatibilidade com features legadas e sem acoplar o core a um provedor específico.

## Requirements

### Modelagem

- [ ] R1 — Representar waves e tasks com IDs estáveis.
- [ ] R2 — Cada task deve registrar role, objetivo, dependências, grupo de paralelismo, paths permitidos/proibidos, inputs, outputs, critérios e comandos de validação.
- [ ] R3 — Representar agentes por papel/capacidade sem exigir runtime externo.
- [ ] R4 — Registrar relatório de execução com status, tentativa, agente, arquivos, comandos, evidências, riscos e blockers.

### Validação e coordenação

- [ ] R5 — Rejeitar IDs duplicados, dependências inexistentes e ciclos.
- [ ] R6 — Rejeitar tasks sem contrato mínimo ou critérios de aceitação.
- [ ] R7 — Detectar conflito de ownership/paths entre tasks que pretendem rodar em paralelo.
- [ ] R8 — Calcular deterministicamente tasks `ready` quando dependências e gates estiverem satisfeitos.
- [ ] R9 — Validar transições de lifecycle: `pending`, `ready`, `running`, `blocked`, `failed`, `completed`, `skipped`.

### Estado e CLI

- [ ] R10 — Estender STATE.json/STATE.md sem quebrar estados legados.
- [ ] R11 — Persistir waves, tasks, agentes, tentativas, blockers, gates e evidências.
- [ ] R12 — Expor inspeção read-only de fleet/status/tasks elegíveis em JSON e texto.
- [ ] R13 — Permitir checkpoint/resume sem reexecutar tasks concluídas.

### Gates e prompt

- [ ] R14 — Representar review, grill, smoke e evidence como gates com status e evidência.
- [ ] R15 — Criar templates/documentação para prompt de task e relatório de subagent.
- [ ] R16 — Criar um exemplo local, sem credenciais externas, demonstrando tasks paralelas simuladas/registradas.
- [ ] R17 — Persistir estado com escrita atômica, preservando evidências e permitindo rollback/recovery.
- [ ] R18 — Implementar um orchestrator local que consuma o adapter, aplique DAG/gates/ownership e atualize lifecycle.

## Non-Functional Requirements

- Compatível com Python 3.12 e dependências atuais.
- Core agnóstico de Hermes Agent, OpenCode e Claude Code.
- Saídas JSON determinísticas e estáveis.
- Erros acionáveis, sem falhas silenciosas.
- Backward compatible com os 49 testes existentes e features com estado legado.

## Proposed Approaches

### A — Expandir tudo em `scripts/pd.py`

- **Prós:** mudança rápida e poucos arquivos.
- **Contras:** aumenta acoplamento, dificulta testes e torna o CLI um monólito.

### B — Criar domínio modular de fleet e integrar gradualmente ao CLI (recomendado)

- **Prós:** validação pura e testável; compatibilidade preservada; adapters futuros ficam isolados.
- **Contras:** mais arquivos e uma pequena camada de integração.

### C — Criar daemon/scheduler distribuído imediatamente

- **Prós:** caminho direto para execução remota.
- **Contras:** escopo excessivo, dependências operacionais e impossível validar o protocolo sem estabilizar o modelo.

## Recommended Approach

Escolher **B**. Primeiro implementar contratos, validação e coordenação local/read-only; depois adicionar dispatcher/adapters. O próprio PD continua sendo a fonte de verdade e o subagent permanece executor descartável.

## Success Criteria

- [ ] `pd init` continua funcionando para features simples.
- [ ] Um PLAN estruturado consegue produzir DAG e tasks elegíveis.
- [ ] Ciclos, dependências inválidas e conflitos de paths são rejeitados.
- [ ] O estado pode ser salvo, carregado e retomado por task.
- [ ] Review/grill/smoke/evidence podem bloquear progressão sem apagar contexto.
- [ ] Existem testes unitários e de CLI para todos os requisitos implementados.
- [ ] Existe exemplo executável sem credenciais externas.

## Constraints and Decisions

- Não alterar comportamento legado sem teste de compatibilidade.
- Não despachar agentes reais no primeiro incremento.
- Não permitir que tasks paralelas tenham paths de escrita sobrepostos.
- Não fazer merge automático.
- A aprovação humana continua obrigatória após o grill e antes do merge.
