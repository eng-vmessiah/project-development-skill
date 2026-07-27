# Decisions — Supervisor + Handoff

## D-001 — Control loop antes de GraphQL

**Decisão:** implementar observer/reconciliation e contratos de evento primeiro.
**Motivo:** GraphQL é transporte/interface; não resolve durable state, replay, idempotência ou policy.

## D-002 — Read-only antes de autocorreção

**Decisão:** o primeiro slice gera diagnósticos e propostas, sem restart/reassign/dispatch.
**Motivo:** reduz falso positivo e permite calibrar sinais com evidência real.

## D-003 — Handoff como artefato formal

**Decisão:** troca de agente deve usar `HandoffArtifact`, não dump da sessão.
**Motivo:** bounded, auditável, redigido e retomável.

## D-004 — Ownership por epoch

**Decisão:** uma task tem no máximo uma lane/attempt ativa; escrita com epoch antigo é rejeitada.
**Motivo:** evitar execução dupla após retry, fallback ou handoff.

## D-005 — Supervisor externo a si mesmo

**Decisão:** disponibilidade do supervisor será responsabilidade futura de s6/systemd/Docker/scheduler, não do próprio LLM.

## D-006 — GraphQL como adapter futuro, não como núcleo

**Decisão:** não implementar GraphQL nesta fase. O domínio permanecerá transport-neutral, com `.spec`/estado persistido como fonte de verdade e CLI read-only como primeiro consumidor. GraphQL poderá ser adicionado posteriormente como adapter de leitura — e, se necessário, de comandos explicitamente idempotentes — somente após existir UI ou múltiplos consumidores com necessidade comprovada de consultas agregadas ou atualizações em tempo real.

**Motivo:** GraphQL pode reduzir round-trips e permitir payloads sob medida, mas não resolve ownership, lifecycle, leases, handoff, retry, gates, replay ou evidência. Introduzi-lo agora aumentaria a superfície operacional antes de o protocolo local estar estabilizado.

**Guardrails:** nenhum resolver poderá acessar `STATE` diretamente, decidir ownership, despachar agentes ou alterar o lifecycle fora dos contratos do Fleet Supervisor. Qualquer adapter futuro deverá reutilizar a mesma interface de consulta do CLI e permanecer default-deny para mutações.

## D-007 — Hardening antes de exposição via CLI

**Decisão:** a revisão independente bloqueia S6 até que redaction, lineage, ownership, diagnóstico, imutabilidade e persistência local tenham contratos verificáveis.
**Motivo:** um CLI read-only ainda pode expor segredos, paths, prompt integral ou estado de ownership incorreto. Expor uma fachada incompleta cristalizaria um contrato inseguro.

**Escopo da remediação:** permanecer local/in-process e sem alterar o `STATE` legado; persistência de handoff, quando implementada, usará uma fronteira própria, atômica e idempotente.
