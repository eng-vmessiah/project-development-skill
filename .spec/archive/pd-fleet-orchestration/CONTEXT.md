# PD Fleet Orchestration — Implementation Context

**Phase:** Wave 1 — Design executável
**Date:** 2026-07-16
**Status:** `planning — G1 PASS; Wave 2 unlocked`

## Decisions

- **Arquitetura:** módulo `scripts/pd_fleet/` separado do CLI monolítico; integração gradual em `scripts/pd.py`.
- **Persistência:** `STATE.json` continua fonte estruturada; `STATE.md` continua visão humana e compatibilidade.
- **Execução inicial:** local/determinística, com adapter simulado; nenhum provider externo.
- **Paralelismo:** somente por DAG + ownership de paths + contrato completo.
- **Orchestrator:** coordena, calcula elegibilidade e registra estado; não implementa tasks diretamente.
- **Task identity:** IDs estáveis são obrigatórios para retry, resume, reports e dependências.
- **Compatibilidade:** campos novos são opcionais ao carregar estados legados.
- **CLI:** novos comandos devem ter saída humana e `--json`; comportamento legado permanece.

## Lifecycle

```text
pending → ready → running → completed
                    ├──────→ failed → ready (retry explícito)
                    ├──────→ blocked
pending ────────────┴──────→ skipped (decisão registrada)
```

`ready` exige dependências completed/skipped permitidas, gates liberados e inputs presentes. `running` exige tentativa e agente registrados. `completed` exige outputs e evidência. `blocked` exige motivo acionável. `skipped` exige decisão/razão.

## Parallelism policy

Tasks com paths de escrita sobrepostos não entram no mesmo grupo paralelo. Paths de leitura podem ser compartilhados. A integração de branches/worktrees é responsabilidade do orchestrator em uma etapa serial; não há merge implícito entre workers.

## Open questions deliberately deferred

- Qual adapter oficial será usado para Hermes/OpenCode/Claude? (fora do primeiro incremento)
- Deve o scheduler suportar concorrência configurável por projeto? (primeiro usar limite conservador)
- Como persistir logs volumosos? (primeiro guardar referências/resumos, não streams completos)

## Gates

- `G0` — reconhecimento e baseline: PASS (`49 passed`).
- `G1` — plan grill: **PASS** após revalidação adversarial; owner `grill`; evidências: `GRILL-001.md`, SPEC/PLAN revisados, `pytest -q` → 49 passed e `git diff --check` sem saída.
- Nenhuma task de código inicia sem `G1 = passed`.

## Blockers

- Revalidar G1 após as correções do plano; enquanto isso, Wave 2 está bloqueada.
