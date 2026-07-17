# GRILL-001 — Grill pré-código V2

**Status:** PENDING; este grill não aprova implementação. Regra absoluta: se existir qualquer `BLOCKER` ou `HIGH` aberto, não iniciar T2-02 nem qualquer código.

## Ameaças e probes

| ID | Ameaça | Severidade | Probe obrigatório | Blocker se |
|---|---|---:|---|---|
| G-01 | drift de plano/checkpoint executa task errada | BLOCKER | alterar plan hash, generation e arquivo no meio de load | houver dispatch antes de reconcile |
| G-02 | dois owners commitem a mesma task | BLOCKER | duas threads/processos simulados com CAS/lease | ambos obtêm lease ou ambos completam |
| G-03 | escrita parcial perde evidência | BLOCKER | truncar temp/snapshot e reiniciar | store não recupera último válido |
| G-04 | `max_parallel` continua serial ou explode workers | HIGH | barrier + contador sob 20 repetições | não houver overlap real ou exceder bound |
| G-05 | ordem depende do timing | HIGH | randomized completion order, comparar bytes/events | hashes/ordem divergem |
| G-06 | validation command vira shell arbitrário | BLOCKER | `;`, `&&`, glob, traversal, env injection, timeout | qualquer execução sem allowlist+sandbox |
| G-07 | provider externo é ativado por fallback | BLOCKER | ausência de config/credential e fake network | factory tentar rede/SDK |
| G-08 | AgentReport “completed” vazio | HIGH | omitir outputs, evidence, tests, decision | aceitação terminal permissiva |
| G-09 | segredo/path absoluto em output/audit | HIGH | URL, bearer, token, `/home`, `/mnt` e symlink | valor cru persistido/emitido |
| G-10 | gate humano bypassável | BLOCKER | gate pending, identidade ausente, artifact hash alterado | run liberado sem APPROVED válido |
| G-11 | regressão V1/legado | HIGH | suíte completa e estados JSON/MD antigos | qualquer teste legado falha |
| G-12 | replay duplica efeitos | HIGH | crash após side effect simulado antes de commit | completed é reexecutado sem idempotency key |

## Decisões que precisam estar fechadas antes do código

1. Formato canônico de `run_id`, `plan_hash`, generation, event sequence e owner.
2. Semântica de lease/timeout e política para orphaned run.
3. Allowlist de validação e sandbox disponível no ambiente suportado; caso contrário, somente declarativo.
4. Política de unknown fields e campos mínimos por status de AgentReport.
5. Limite de workers, cancelamento e ordem de commit.
6. Human gate exige owner, identity string auditável, decision, evidence digest e freshness; autenticação criptográfica/identity provider são futuros e out-of-scope.

## Blockers esperados

- Não existir store local atômico testável.
- Não ser possível provar que comandos/provider/rede estão default-deny.
- Não haver teste de corrida e output determinístico.
- Qualquer proposta que trate batching serial como paralelismo real.
- Qualquer tentativa de editar V1, commit/push ou despachar externo neste ciclo.

## Probes adicionais obrigatórios da review

| ID | Probe | Expected fail-closed result |
|---|---|---|
| G-13 TOCTOU | executar claim→use, renovar lease/generation, tentar commit e comparar snapshot/hash antes/depois | commit rejeitado; state, eventos e evidência inalterados |
| G-14 executor | policy ausente, allowlist errada, metacaracteres, cwd/env inválidos, timeout/output excedidos e sandbox capability ausente | zero shell/processo fora da policy; sandbox indisponível não faz fallback |
| G-15 report schema | adicionar campo desconhecido a AgentReport | rejeição determinística por `reject_unknown_fields=True`, nada persistido |
| G-16 human gate | identity vazia, owner ausente, decision sem digest, digest stale e artifact alterado | gate bloqueia/reabre; identity é somente string registrada, sem claim criptográfico |

A matriz de `RESEARCH.md` é a fonte de rastreio para cada probe, teste e artefato. O reviewer deve executar também `pytest -q`, `git diff --check` e `python -m compileall scripts/pd_fleet`; qualquer ausência de evidência permanece OPEN. Os probes/evidências residuais (incluindo G-13…G-16) só serão executados durante a implementação V2; nesta fase permanecem PENDING/OPEN e não podem ser classificados como PASS.
## Resultado e regra de parada

O reviewer deve preencher cada probe com comando, resultado, evidência e severidade residual. `BLOCKER` ou `HIGH` aberto ⇒ **STOP/NO-GO**, criar correção/decisão e repetir o grill. Somente zero BLOCKER/HIGH, todos os invariantes aceitos e aprovação humana explícita ⇒ **GO para T2-02**. Ausência de evidência não equivale a PASS.
