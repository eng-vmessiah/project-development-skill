# GRILL-001 — Grill pré-código V2 (adversarial/read-only)

**Data:** 2026-07-17
**Branch/commit observado:** `feat/pd-fleet-orchestration-plan` / `2b4f219`
**Escopo:** handoff documental e evidência local de T2-01…T2-17; nenhum provider, rede, dispatch externo, commit/push ou documento V1 foi usado.
**Status:** **PENDING** — GRILL-001 não substitui rerun formal nem decisão humana; G6 não está APPROVED.
**Regra de evidência:** suíte verde, checker válido e artefatos locais comprovam apenas os comandos indicados. Não convertem implementação parcial em PASS global.

## Baseline/checks executados

| Comando | Resultado observado | Evidência |
|---|---|---|
| `pytest -q -W error` | **577 passed** (exit 0) | execução fresca; inclui testes V1/V2 presentes |
| `git diff --check` | **PASS** (exit 0) | execução fresca |
| `python -m compileall scripts/pd_fleet` | **PASS** (exit 0) | execução fresca |
| `python scripts/pd_fleet/v2_doc_paths.py /home/vitor/project/project-development-skill` | **VALID**, `violation_count=0`, exit 0 | JSON determinístico; checker existente |
| `git status --short --branch` | **OBSERVADO**, branch `feat/pd-fleet-orchestration-plan`; working tree contém mudanças prévias de código/testes/docs e artifacts | status não é PASS de release |
| `git log -1 --oneline` | `2b4f219 docs: plan fleet orchestration hardening v2` | commit-base observado; sem commit nesta execução |
| `pytest -q tests/fleet/test_v2_doc_paths.py` | **7 passed** | checker/path contract |
| `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit` | **1 passed, 6 deselected** | evidência TOCTOU; artifact digest em VERIFICATION.md |

A suíte verde confirma apenas que os testes presentes passam; não é evidência suficiente para PASS global, segurança operacional ou aprovação humana. `e1cdb4e` e contagens 278/282/421 são referências históricas, não o estado corrente.

## Probes adversariais e resultado

Legenda: **CLOSED (design)** = ameaça coberta por contrato explícito; teste/implementação futura permanece pendente. **PENDING** = evidência prevista em tarefa/gate posterior, não blocker nesta fase. **MEDIUM residual** = evidência/operacionalização futura, sem lacuna de contrato HIGH/BLOCKER.

| ID | Probe adversarial | Resultado do rerun / contrato verificado | Severidade residual |
|---|---|---|---:|
| G-01 | Permutar campos/aliases, injetar timestamps/paths, alterar plano entre load e dispatch; verificar hash e drift | **CLOSED (design):** SPEC/CONTEXT/PLAN/PROMPT-NEXT fixam UTF-8, `json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`, saneamento pré-serialização de timestamps/runtime paths/secrets, SHA-256 lowercase hex, domínio `pd-fleet-plan:v2\\0` e sequência indivisível `load→parse→canonicalize→hash→compare plan_hash→compare generation/run/checkpoint/lease/event sequence→block→claim→use→commit`; mismatch bloqueia antes de mutação/readiness/dispatch. Golden/drift tests ficam para T2-02/T2-03/T2-09 e G2/G3. | CLOSED (contract); evidence G2/G3 pending |
| G-02 | Dois owners/threads tentam claim/commit da mesma task | **CLOSED (design):** owner, lease, generation e CAS estão definidos; T2-04/T2-12 nomeiam testes de corrida e claims bounded. | PENDING — G3/G5 |
| G-03 | Truncar snapshot/temp, checksum inválido e reiniciar; último snapshot válido/fsync/replay idempotente | **CLOSED (design + testes presentes):** atomic replace, checksum/generation, recovery e terminal sem replay estão cobertos pelos componentes/testes T2-04/T2-05. Revisão formal G3 ainda pendente. | MEDIUM — G3 pending |
| G-04 | Barrier prova overlap, contador mede bound em 20 repetições, timeout/cancelamento | **CLOSED (design):** PLAN reconhece o batching serial atual; paralelismo real só após ownership/G3 e T2-13 exige barrier, limite e ausência de workers ilimitados. | PENDING — G5 |
| G-05 | Randomizar conclusão; comparar bytes/events/reports/hashes e barriers de dependência | **CLOSED (design):** ordenação canônica de IDs/resultados/events/reports e bufferização/commit ordenado estão fixadas em CONTEXT/SPEC/PLAN T2-14. | PENDING — G5 |
| G-06 | `;`, `&&`, glob, traversal, cwd/env inválidos, timeout/output excedidos e sandbox ausente | **CLOSED (design):** caminho default é declarativo; executor opt-in exige argv sem shell, allowlist exata, root/cwd/env/limits e sandbox; capability ausente falha fechado sem fallback. | PENDING — G4 |
| G-07 | Ausência de config/credential e fake network tenta provider/fallback | **CLOSED (design):** protocolo/`DisabledProvider`, factory default-deny e proibição explícita de SDK/rede/credenciais/fallback em SPEC/PLAN/PROMPT-NEXT. | PENDING — G4 |
| G-08 | `AgentReport.completed` vazio/incoerente ou com failed/blocked sem motivo | **CLOSED (design):** completude semântica, motivos estruturados e `reject_unknown_fields=True` estão normativos em SPEC/PLAN T2-06. | PENDING — G2 |
| G-09 | Persistir URL/token/bearer, `/home`, `/mnt`, symlink/traversal em output/audit | **CLOSED (design + testes presentes):** redaction, paths relativos e rejeição de traversal/symlink estão implementados em normalizer/observability T2-03/T2-11; revisão formal G3 ainda pendente. | MEDIUM — G3 pending |
| G-10 | Gate pending/ownerless/identity vazia, digest stale/artifact alterado; tentar release | **CLOSED (design):** gate exige owner, identity string auditável, APPROVED, escopo/hash, digest e freshness; mudança reabre. **Não existe aprovação humana nem autorização G6 para T2-01 nesta revisão**; a decisão persistida de release continua exigida em T2-16/G6. | PENDING — G6 |
| G-11 | Regressão V1; carregar `STATE.json`/`STATE.md` sem bloco V2 e preservar desconhecidos | **CLOSED (baseline/design):** a contagem histórica de 278 não é fresca; a verificação corrente é 577 passed. SPEC exige API aditiva, CLI/imports/estado legado preservados e namespace V2 separado. | PENDING — G2/G6 compatibility |
| G-12 | Crash após efeito simulado antes do commit; resume não repete terminal | **CLOSED (design):** attempt/idempotent commit e no-replay estão programados em T2-05/T2-10; evidência ainda não exigida para G1. | MEDIUM — G3 pending |
| G-13 | Claim→use; renovar lease/avançar generation; commit com tokens stale e comparar tudo antes/depois | **CLOSED (design):** SPEC define tokens imutáveis capturados no claim, CAS simultâneo generation+lease e rejeição antes da mutação; T2-04 nomeia teste que afirma state/snapshot/events/evidence intactos. | PENDING — G3 |
| G-14 | Policy/allowlist/cwd/env/timeout/output/sandbox inválidos | **CLOSED (design + testes presentes):** expected fail-closed é explícito e coberto por ValidationExecutor/testes; sandbox ausente continua falha fechada. | PENDING — G4 |
| G-15 | Campo desconhecido em AgentReport | **CLOSED (design + teste presente):** `reject_unknown_fields=True` por default; erro estável e nada persistido. | PENDING — G2 |
| G-16 | Identity/owner/digest/freshness inválidos ou artifact alterado | **CLOSED (design):** contrato do gate exige esses campos e reabre em mudança; identity é registro literal, não alegação de autenticação criptográfica. | PENDING — G6 |
| G-17 | Tasks com `allowed_paths` sobrepostos, traversal/symlink e forbidden paths; checker com ownership incorreto | **CLOSED (contract + execução):** checker existente e `7 passed`; paths exatos, ownership/capabilities, stdlib-only/offline/read-only, root explícito, V1 forbidden, links/âncoras e saída/exit codes determinísticos foram verificados. | CLOSED (contract); evidence G2/G6 pending |
| G-18 | Mesma entrada com permutações, Unicode, NaN, relógio/path/segredo variáveis; bytes/digest | **CLOSED (design):** parâmetros normativos, `allow_nan=False`, remoção pré-hash e SHA-256/domain versionado cobrem determinismo e rejeição de NaN/Infinity. | PENDING — G2 |
| G-19 | Alterar plano/generation/checkpoint/lease/event sequence após load/hash e tentar readiness/claim/commit | **CLOSED (design):** reconciliation formal exige todos os compares e bloqueio fail-closed antes de readiness/dispatch/mutação; CAS cobre tokens claim→use→commit. | PENDING — G3 |
| G-20 | Checker em root inválido, ownership/Create errado, V1 forbidden, link quebrado/traversal e execuções idênticas | **CLOSED (contract + execução):** checker/testes presentes verificam JSON determinístico, `repo_root` relativizado, schema/violations/summary e exits `0/1/2`; execução corrente exit `0`, sem violações. | PENDING — G6 |

## Verificação por área solicitada

| Área | Resultado G1 documental | Gate de implementação |
|---|---|---|
| Hash/reconciliation | **CLOSED — sem BLOCKER/HIGH de design**; canonicalização, domínio SHA-256 e ordem/bloqueio formalizados | G2/G3 |
| Checker ownership/path contract | **CLOSED — sem BLOCKER/HIGH de design**; paths exatos, ownership, allowlists, forbidden V1, links, output e exits formalizados | T2-17/T2-18, G6 |
| TOCTOU | **CLOSED — sem BLOCKER/HIGH de design**; claim/use/commit com tokens e CAS antes de mutação | T2-04, G3 |
| Store/checkpoint | **CLOSED — contrato suficiente** para owner/CAS/atomicity/checksum/recovery/no-replay | T2-04/T2-05, G3 |
| Executor | **CLOSED — default-deny/fail-closed especificado** | T2-07, G4 |
| Reports/audit | **CLOSED — schema strict/completeness/redaction/unknown-fields especificados** | T2-06/T2-11, G2/G3 |
| Parallelism/ordering | **CLOSED — boundedness, leases, barriers e commit determinístico agendados**; batching serial atual não é falsamente tratado como PASS | T2-12/T2-14, G5 |
| Provider boundary | **CLOSED — disabled/default-deny, sem rede/credenciais/fallback** | T2-08/T2-10, G4 |
| Human gate | **CLOSED — owner/identity/decision/digest/freshness e re-open especificados**; eventual aprovação G1 não equivale a release G6 | T2-16, G6 |
| Compatibility | **CLOSED — baseline histórico 278 e preservação V1 explicitadas; verificação corrente 577** | T2-15, G6 |

## Blockers reais

Os dois blockers HIGH anteriores estão concretamente fechados **pelos contratos documentais**, sem constituir aprovação humana ou autorização G6:

1. **B-HIGH-01 (G-01): RESOLVIDO POR CONTRATO.** Os cinco documentos V2 fixam serialização canônica exata, saneamento pré-hash, SHA-256/domain versionado, reconciliação completa, bloqueio fail-closed e testes determinísticos/drift-stale agendados.
2. **B-HIGH-02 (G-17): RESOLVIDO POR CONTRATO.** Os cinco documentos V2 fixam os paths exatos do checker e teste, ownership/capabilities, stdlib/offline/read-only, root/inputs, regras Create/Exact/Allowed e ownership, V1 forbidden, links/âncoras, output determinístico e exit codes.

**Resultado do rerun:** não foi identificado novo `BLOCKER` ou `HIGH` de design em hash/reconciliation, checker ownership/path contract, TOCTOU, store, executor, reports, parallelism, provider boundary, human gate ou compatibilidade. Ausência de implementação/evidência foi classificada como **PENDING** somente onde o PLAN agenda explicitamente G2-G6/T2 posteriores; não foi usada para inventar PASS de implementação.

## Decisão de handoff

**GRILL-001: PENDING. G1/G2/G3/G4/G5/G6: PENDING ou não demonstrados neste handoff.** A execução atual não é rerun formal autorizado nem decisão humana. Não há `G6 APPROVED`, `PASS` global ou autorização de release.

## Escopo/diff desta execução

Esta etapa atualiza o pacote documental V2 permitido (GRILL-001, PROMPT-NEXT, RESEARCH e VERIFICATION). O working tree já continha mudanças de código/testes/docs/artifacts de T2-01…T2-17; elas não foram revertidas nem ampliadas por este handoff. Não houve commit/push, rede, provider ou subprocesso derivado do plano.
