# Context — Supervisor + Handoff

## Source of truth

- Código: `scripts/pd_fleet/`
- Contratos existentes: `models.py`, `lifecycle.py`, `orchestrator.py`, `state.py`, `checkpoint.py`, `contracts.py`
- Testes: `tests/fleet/`
- Estado desta feature: `.spec/pd-fleet-supervisor-handoff/`

## Decisions

- Supervisor é control-plane, não executor.
- Observer é read-only no primeiro incremento.
- LLM pode interpretar e recomendar, mas políticas de segurança são determinísticas.
- HandoffManager pertence ao Supervisor como componente explícito.
- Lane permanece estável entre retries/fallbacks; Attempt/Session podem mudar.
- `owner_epoch`/generation impede execução dupla.
- `HandoffArtifact` nunca transporta prompts, chain-of-thought, credenciais, PIDs, paths absolutos ou handles Hermes.
- GraphQL fica deferred; o contrato precisa ser útil por CLI/testes antes de qualquer API.

## Status labels

`implemented`, `verified`, `deferred`, `blocked` são distintos.
