# Research — Supervisor + Handoff

## Evidência externa

- Kubernetes Controllers: desired state vs observed state e reconciliation loop — https://kubernetes.io/docs/concepts/architecture/controller/
- Erlang/OTP Supervisors: árvores de supervisão, políticas de restart e limites — https://www.erlang.org/doc/system/sup_princ
- Temporal failure detection/heartbeats: liveness, timeout e recuperação durável — https://docs.temporal.io/encyclopedia/detecting-activity-failures
- GraphQL subscriptions: atualização em tempo real, mas sem histórico durável por si só — https://spec.graphql.org/October2021/#sec-Subscriptions
- GraphQL over SSE/live queries: transporte/atualização não substituem event log — https://github.com/enisdenjo/graphql-sse e https://github.com/graphql/graphql-wg/blob/main/rfcs/GraphQLLiveQueries.md

## Conclusões

1. O padrão central é control loop/reconciliation, não “um LLM conversando com workers”.
2. Heartbeat prova liveness, não progresso.
3. GraphQL deve ser camada de leitura/comando; estado/eventos são a verdade operacional.
4. Supervisor não pode ser o único mecanismo que mantém a si próprio vivo.
5. Handoff é um artefato bounded e versionado, distinto de retry/fallback/replan.

## Estado local auditado

O repositório já tem `FleetOrchestrator`, `TaskLifecycle`, `fleet_state`, reconciliation V2, checkpoints, gates e reports. O gap é a camada semântica residente/read-only para diagnóstico, propostas e handoff. O feature anterior fica preservado como histórico; esta feature reutiliza seus contratos.
