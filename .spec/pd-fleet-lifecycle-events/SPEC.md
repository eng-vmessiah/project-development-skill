# Spec — PD Fleet Lifecycle Events

## Goal

Criar uma fronteira local e determinística para registrar eventos de lifecycle/checkpoint sem acoplar o evento ao CLI ou a provider execution.

## Requirements

- R1 — Evento possui schema version, run/task identity, kind, ordering_key, sequence e payload.
- R2 — Envelope é JSON-safe, redacted, bounded e rejeita NaN/Infinity, prompt/CoT, secrets, PIDs, handles e paths absolutos.
- R3 — `sequence` representa ordem append-only/auditoria; `ordering_key` representa ordenação lógica consultável; conclusão do scheduler não é declarada determinística.
- R4 — Append é atômico, idempotente para a mesma identidade/conteúdo e fail-closed para colisão/conflicting replay.
- R5 — Replay e query são read-only, determinísticos e não mutam eventos retornados nem o log.
- R6 — Ownership/run epoch é validado quando fornecido; evento stale/mismatched é rejeitado.
- R7 — Limites de payload e quantidade protegem contra memória/arquivo ilimitados.
- R8 — A API permanece separada de `STATE`, `CheckpointV2Store`, CLI e providers nesta fatia.

## Non-goals

- event broker/distributed stream;
- worker observer, retry/reassign/restart;
- alteração do orchestrator;
- GraphQL/SSE/subscriptions;
- provider/network/subprocess.
