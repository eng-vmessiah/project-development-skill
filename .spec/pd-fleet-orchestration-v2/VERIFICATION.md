# T2-18 — Verification e handoff

**Data da coleta:** 2026-07-17  
**Branch:** `feat/pd-fleet-orchestration-plan`  
**Commit observado:** `2b4f219 docs: plan fleet orchestration hardening v2`  
**Decisão:** **NOT READY / PARTIAL**. GRILL-001 permanece **PENDING**; não existe decisão humana `APPROVED` de G6.

Este documento separa evidência executada de planejamento e não transforma uma suíte verde em aprovação de release.

## Comandos e resultados frescos

| Comando copy-pasteável | Resultado observado | Classificação |
|---|---|---|
| `pytest -q -W error` | `577 passed`, exit `0` | Evidência de testes presentes; não PASS global |
| `python -m compileall scripts/pd_fleet` | exit `0` | Compilação dos módulos presentes |
| `git diff --check` | exit `0`, sem saída | Whitespace limpo |
| `python scripts/pd_fleet/v2_doc_paths.py /home/vitor/project/project-development-skill` | `{"repo_root":".","schema_version":"pd-fleet-doc-paths:v1","summary":{"documents":7,"status":"valid","violation_count":0},"violations":[]}`, exit `0` | Checker de paths/links válido |
| `pytest -q tests/fleet/test_v2_doc_paths.py` | `7 passed`, exit `0` | Checker/teste de contrato |
| `pytest -q tests/fleet/test_v2_run_store.py -k claim_use_commit` | `1 passed, 6 deselected`, exit `0` | Evidência focal TOCTOU |
| `pytest -q tests/fleet/test_run_store.py tests/fleet/test_v2_run_store.py` | `29 passed`, exit `0` | Testes direcionados do run store |
| `sha256sum artifacts/v2/M-04-toctou.json` | `1342844fb964393578344b5452f6d67f68d65fcabe87587f917c94effd85d45d` | SHA-256 bruto do arquivo do artefato disponível |

`git status --short --branch` foi coletado e mostrou a branch acima, com mudanças pré-existentes de T2-01…T2-17 em código, testes, documentação e `artifacts/`. O estado sujo não é apresentado como aprovação. Não houve commit ou push.

## Status rastreável T2-01…T2-17

| Tarefa | Estado de implementação observado | Evidência/gate | Decisão honesta |
|---|---|---|---|
| T2-01 | implementado/revisado | baseline fixture e testes; incluído na suíte | concluído localmente; não aprova G1/G6 |
| T2-02 | implementado/revisado | contratos/hash e testes V2 | evidência local; gate posterior |
| T2-03 | implementado/revisado | normalização e testes V2 | evidência local; gate posterior |
| T2-04 | implementado/revisado | run store; teste claim→use→commit e `M-04-toctou.json` | evidência focal disponível; G3 pendente |
| T2-05 | implementado/revisado | checkpoint/recovery e testes V2 | G3 pendente |
| T2-06 | implementado/revisado | AgentReport strict e testes V2 | G2/G3 pendente |
| T2-07 | implementado/revisado | ValidationExecutor e testes V2 | sem sandbox nativa; G4 pendente |
| T2-08 | implementado/revisado | provider disabled/default-deny e testes V2 | provider externo continua desabilitado; G4 pendente |
| T2-09 | implementado/revisado | reconciliation/orchestrator e testes V2 | G3 pendente |
| T2-10 | implementado/revisado | execução local/in-process e testes V2 | não é dispatch externo; G3/G4 pendente |
| T2-11 | implementado/revisado | observabilidade/redaction e testes V2 | G3 pendente |
| T2-12 | implementado/revisado | scheduler/leases e testes V2 | G5-pre pendente |
| T2-13 | implementado/revisado | executor bounded e testes V2 | repetição formal de 20 execuções/G5 pendente |
| T2-14 | implementado/revisado | integração ordering/concurrency e testes V2 | G5 pendente |
| T2-15 | implementado/revisado | CLI/compatibilidade e testes V2 | compatibilidade não substitui G6 |
| T2-16 | implementado/revisado | contrato/testes de human gate | aprovação humana e freshness final pendentes |
| T2-17 | implementado/revisado | docs, checker e `7 passed`; checker exit 0 | revisão final/handoff T2-18 ainda necessário |

“Implementado/revisado” significa que os caminhos e testes estão presentes no working tree observado e passam no comando global; não significa que todos os gates operacionais, revisão de segurança/concurrency ou aprovação humana foram concedidos.

## Gates e decisão

- **G0:** evidência de suíte atual disponível; a contagem histórica `278` permanece apenas como baseline anterior documentado. A coleta atual é `577`.
- **G1:** **PENDING** — GRILL-001 precisa de rerun formal e decisão humana; não registrar `PASS`.
- **G2:** **PENDING/não demonstrado como gate formal** — testes presentes passam, mas o handoff não autoaprova o gate.
- **G3:** **PENDING** — persistência/recovery/TOCTOU requer revisão formal.
- **G4:** **PENDING** — executor permanece default-deny; ausência de sandbox nativa é residual explícito.
- **G5:** **PENDING** — paralelismo bounded/ordering requer evidência repetível e revisão de concorrência.
- **G6:** **PENDING** — owner, identity literal auditável, decisão `APPROVED`, escopo/hash, digest e freshness humanos ainda não foram registrados.

## Residuais e limites conhecidos

1. O hook/integração shell legada continua existindo para V1; T2-18 não o remove nem o trata como autorização do executor V2.
2. Não há sandbox nativa disponível/atestada neste handoff. O executor opt-in deve falhar fechado; não há fallback para shell ou execução sem sandbox.
3. Provider externo, rede, credenciais e dispatch externo continuam desabilitados.
4. A suíte e o checker não constituem revisão humana, autenticação criptográfica ou aprovação de release.
5. A árvore contém mudanças de ondas anteriores; a classificação de arquivos deve ser revista antes de merge/release.

## Artefatos e digests

- `artifacts/v2/M-04-toctou.json` — digest canônico declarado `1e75c1e7bf9d55ae7083ed484d571a283b38afa49228a83e33ae4626ba3fefdf`; SHA-256 bruto do arquivo `1342844fb964393578344b5452f6d67f68d65fcabe87587f917c94effd85d45d`.
- O checker produz saída sem violações e sem paths absolutos no JSON. Nenhum digest de evidência global/G6 foi inventado.

## Rollback e próximo passo humano

Rollback seguro: desabilitar a entrada/feature V2, preservar snapshots, eventos e artefatos, e continuar usando a compatibilidade V1; não apagar estado para mascarar drift. Para release, um revisor humano deve repetir os comandos acima sobre o estado final, revisar residuais/artifacts, registrar `owner`, `identity`, escopo, digest, janela de freshness e decisão explícita. Até então, o estado obrigatório é **NOT READY / PARTIAL**.

## Evidência fresca G1 — 2026-07-28 02:22 UTC

- Artefato: `artifacts/v2/G1-fresh-verification.json`.
- Branch/commit observados: `feat/pd-fleet-lifecycle-events` / `3036786`.
- `python -m pytest -q tests/fleet/test_v2*.py` → **401 passed**, exit `0`.
- `python -m pytest -q` → **921 passed**, exit `0`.
- `python -m compileall -q scripts tests` → exit `0`.
- `git diff --check` → exit `0`, após a coleta final.
- `python scripts/pd_fleet/v2_doc_paths.py .` → 7 documentos, 0 violações, exit `0`.
- Validação independente do artefato → `G1_ARTIFACT_VALID`.
- SHA-256 bruto atual do artefato: `04ae0076e543bdb9c80926c6aae2883b6b6b15b8d20e56ec1af13ef0554e6430`.

**Classificação:** evidência local fresca, **NOT READY / PARTIAL**. Esta coleta não fecha GRILL-001, G2–G5 ou G6 e não constitui aprovação humana/release PASS.

## GRILL-001 — 2026-07-28 — BLOCKED

- Review independente: **6 HIGH, 6 MEDIUM, 2 LOW**.
- Artefato: `artifacts/v2/GRILL-001-findings.json`.
- Findings HIGH reproduzidos ou confirmados por inspeção: PATH-controlled readiness execution, human-gate scope/run bypass, provider free-form secret leakage, missing use fence, dependency readiness TOCTOU e GateResult substituindo HumanVerificationGate.
- **Decisão:** GRILL-001 não passa. O status permanece **NOT READY / PARTIAL**; não existe aprovação humana G6.

Próxima fatia recomendada: corrigir os seis HIGH com testes red-first e revisão independente antes de reabrir qualquer gate formal.


## Atualização GRILL-H01 — 2026-07-28

- HIGH-01 resolvido localmente no commit `9f90221414024b62b3bef2e0a7804efa13b6158f`.
- Teste RED reproduziu execução de binary controlado por `PATH`; correção retorna `denied/trusted_runner_required` antes de descoberta ou subprocesso.
- Review independente: PASS; 94 testes focados.
- Artefato: `artifacts/v2/GRILL-001-H01-resolution.json`.
- **Status global:** permanece **BLOCKED_NOT_READY**; HIGH-02…HIGH-06 continuam abertos.

## Atualização GRILL-H02 — 2026-07-28

- HIGH-02 resolvido localmente no commit `b2fb44ae2c4a4a0a1522544c15f675df89d26293`.
- Testes RED reproduziram bypasses `private-key`/`Bearer` assignment; H02R fechou esses casos e preservou lookalikes inertes.
- Review independente: PASS; 121 focados, 939 totais.
- Artefato: `artifacts/v2/GRILL-001-H02-resolution.json`.
- **Status global:** permanece **BLOCKED_NOT_READY**; HIGH-03…HIGH-06 continuam abertos.

## Atualização GRILL-H03 — 2026-07-28

- HIGH-03 resolvido localmente no commit `44b4b75524c618198f3ea1ef8746864996701b5a`.
- RED reproduziu ausência de fencing e execução com lease stale; GREEN adicionou `store.use` antes do adapter e eliminou retry duplicado por `TypeError`.
- Review independente: PASS; 62 focados, 942 totais.
- Artefato: `artifacts/v2/GRILL-001-H03-resolution.json`.
- **Status global:** permanece **BLOCKED_NOT_READY**; HIGH-04…HIGH-06 continuam abertos.

## Atualização GRILL-H04 — 2026-07-28

- HIGH-04 resolvido localmente no commit `719dac51156fea0f4462103afc08e7ccd18dd66a`.
- H04R/H04R2 fecharam TypeError não controlado e bypass em tarefas terminais malformed.
- Review independente: PASS; full rerun: 952 passed.
- Artefato: `artifacts/v2/GRILL-001-H04-resolution.json`.
- **Status global:** permanece **BLOCKED_NOT_READY**; HIGH-05 e HIGH-06 continuam abertos.

## Atualização GRILL-H05 — 2026-07-28

- HIGH-05 resolvido localmente no commit `6c34aca3362828b6352cab95243c8f8b41515990`.
- RED reproduziu autorização por `GateResult` estrutural; GREEN exige human gate explícito e atualizou o exemplo local.
- Review independente: PASS; full rerun: 956 passed.
- Artefato: `artifacts/v2/GRILL-001-H05-resolution.json`.
- **Status global:** permanece **BLOCKED_NOT_READY**; HIGH-06 continua aberto.

## Atualização GRILL-H06 — 2026-07-28

- HIGH-06 resolvido localmente no commit `d3b2c78faa2385151ee67ef736a26071f56423d3`.
- Wrong-run, wrong-scope, missing-context, aliases, extra keys e type pollution falham fechado.
- Review independente: PASS; full independente: 959 passed. Uma execução parent teve falha intermitente fora do escopo no validation executor; rerun isolado passou.
- Artefato: `artifacts/v2/GRILL-001-H06-resolution.json`.
- **Status global:** HIGH-01…HIGH-06 resolvidos localmente, mas GRILL-001/G1–G6 continuam **BLOCKED_NOT_READY** até decisão humana formal.
