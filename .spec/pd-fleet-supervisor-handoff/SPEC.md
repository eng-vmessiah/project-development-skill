# PD Fleet Supervisor + Handoff — Specification

**Date:** 2026-07-27
**Status:** `approved — user authorized registration and execution`
**Feature:** `pd-fleet-supervisor-handoff`

## Problem Statement

O PD já consegue modelar e executar localmente uma fleet, mas ainda não possui uma camada explícita que observe continuamente liveness, readiness, progresso, health, bloqueios e continuidade entre agentes. Sem essa camada, um worker pode estar vivo porém semanticamente travado, o orchestrator pode ficar órfão e a troca de agente depende de contexto informal.

## Goal

Adicionar uma camada local-first de **Observer + Mission Supervisor + Handoff Manager**, separada do executor: observar sinais, comparar estado desejado/observado, produzir diagnóstico e materializar handoffs bounded sem criar dupla execução.

## Requirements

- [ ] R1 — Representar sinais separados de `liveness`, `readiness`, `progress` e `health`.
- [ ] R2 — Diagnosticar `healthy`, `slow`, `suspected`, `blocked`, `degraded`, `failed` e `needs_human_intervention` sem mutar o snapshot.
- [ ] R3 — Reconciliar estado desejado vs observado de forma determinística, idempotente e fail-closed.
- [ ] R4 — Distinguir retry, fallback, handoff e replan.
- [ ] R5 — Representar ownership/epoch para impedir dois workers ativos na mesma task.
- [ ] R6 — Gerar `HandoffArtifact` bounded com resumo, concluído, restante, decisões, riscos, evidências e próxima ação.
- [ ] R7 — Rejeitar/omitir prompt completo, chain-of-thought, credenciais, PIDs, handles nativos e paths absolutos desnecessários.
- [ ] R8 — Preservar lineage Mission → MissionRun → Lane → Attempt → Session.
- [ ] R9 — Permitir que o supervisor produza `InterventionProposal` sem executar ação externa no primeiro incremento.
- [ ] R10 — Manter compatibilidade com `FleetOrchestrator`, lifecycle e `fleet_state` existentes.
- [ ] R11 — Expor relatório read-only determinístico para futura UI/GraphQL.
- [ ] R12 — Registrar evidência e estado de handoff para retomada após morte/restart do worker.

## Non-goals

- GraphQL como mecanismo de supervisão;
- subscriptions/live queries obrigatórias;
- broker distribuído;
- reinício automático de processos;
- execução de comandos declarativos sem gate;
- provider/model específico;
- supervisor LLM como autoridade única;
- alteração automática de DAG;
- merge, push ou deploy.

## Architecture

```text
Mission desired state
  → MissionRun / task DAG / snapshots
  → Observer (signals + diagnostics)
  → Supervisor/Reconciler (policy + proposals)
  → Orchestrator (schedules work)
  → Lane → Attempt → Session → Worker
  → HandoffManager (bounded continuation artifact)
```

GraphQL, quando vier, será uma interface para query/subscription/mutation idempotente. A fonte operacional será estado persistido + eventos versionados + reconciliação periódica.

## Success Criteria

- [ ] Snapshot saudável produz diagnóstico sem proposta indevida.
- [ ] Worker vivo sem progresso é diagnosticado como suspeito/degradado, não morto automaticamente.
- [ ] Evento duplicado/reconciliação repetida não cria intervenção duplicada.
- [ ] Handoff não contém segredos, prompt integral, chain-of-thought ou identificadores operacionais perigosos.
- [ ] Worker novo pode retomar a partir do handoff e de evidências referenciadas.
- [ ] Ownership epoch rejeita escrita de lane antiga.
- [ ] Primeiro incremento não abre processos, rede, GraphQL ou provider.
- [ ] Testes legados continuam passando.

## Constraints

- Python 3.12 + stdlib/pytest;
- usar `scripts/pd_fleet/`;
- não modificar o contrato legado sem teste;
- nenhuma task paralela escreve nos mesmos paths;
- toda intervenção forte exige gate humano futuro;
- estados `blocked` não são retryáveis automaticamente.
