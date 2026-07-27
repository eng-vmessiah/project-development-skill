# PD Fleet Supervisor + Handoff

Feature adjacente ao `pd-fleet-orchestration`. Evolui o núcleo existente para observar MissionRuns/workers/orchestrator, reconciliar estado desejado vs observado e produzir handoffs verificáveis.

## Escopo desta feature

1. contratos puros de sinais de saúde e progresso;
2. diagnóstico read-only e reconciliation determinística;
3. `HandoffArtifact` bounded, redigido e retomável;
4. inspeção/relatório sem dispatch externo;
5. políticas de intervenção como propostas, não execução automática.

Fora do primeiro incremento: GraphQL server, live queries, provider real, daemon, restart automático, reassign automático, multi-host e actions destrutivas.
