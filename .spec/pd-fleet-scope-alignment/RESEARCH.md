# GRILL-001 — Reclassificação no escopo PD/Fleet

## Propósito e limites

Esta matriz reclassifica, para o escopo de `.spec/pd-fleet-scope-alignment`, **todos os findings** registrados em `artifacts/v2/GRILL-001-findings.json`. O JSON histórico não foi alterado.

As classificações possíveis são:

- **retain-local** — correção/verificação de protocolo local ou simulado do PD Fleet permanece no plano atual.
- **defer-runtime** — preocupação dependente de runtime/host Hermes, sandbox forte, providers, deployment ou operação; fica fora desta execução.
- **superseded-by-scope** — premissa ou expectativa substituída explicitamente pelo novo boundary, sem apagar o finding histórico.
- **evidence-later** — não abre trabalho novo nesta tarefa; requer evidência posterior, ou registra um finding já resolvido localmente sem declarar encerramento global.

A classificação nova **não declara GRILL PASS, produção, G6_APPROVED ou readiness de runtime**. A decisão histórica permanece `BLOCKED_NOT_READY`; os números e severidades históricos abaixo são apenas referência.

## Referência histórica preservada

Fonte: `artifacts/v2/GRILL-001-findings.json` (`schema_version: pd-fleet-grill-001:v1`, `scope: local_adversarial_review`).

- Contagens históricas: **HIGH 6, MEDIUM 6, LOW 2**.
- Decisão histórica: **`BLOCKED_NOT_READY`**.
- Notas históricas: os findings eram blockers para a progressão formal G1/G2-G6; nenhuma aprovação humana ou release PASS era implícita.
- O contexto de escopo registra **H01–H03 como `resolved_locally`** e **H04–H06 como abertos**. `resolved_locally` é estado histórico/contextual, não uma das quatro classificações desta matriz.

## Matriz de reclassificação

| ID | Severidade | Título histórico (JSON) | Classificação nova | Estado/decisão no escopo atual | Justificativa honesta |
|---|---|---|---|---|---|
| GRILL-H01 | HIGH | Local readiness probe executes PATH-controlled binaries without sandbox capability | **defer-runtime** | `resolved_locally` no contexto; não é alvo de produção nesta execução | Sandbox forte e execução de provider ficam fora do boundary local; o finding continua referência de risco runtime e não é convertido em claim de sandbox seguro. |
| GRILL-H02 | HIGH | Provider metadata redaction misses free-form secret assignments | **defer-runtime** | `resolved_locally` no contexto; providers live/credenciais permanecem desabilitados | A questão é tratada como preocupação de provider/runtime. Não há evidência nova aqui para afirmar cobertura além do estado histórico. |
| GRILL-H03 | HIGH | Orchestrator does not fence lease immediately before adapter execution | **evidence-later** | `resolved_locally` no contexto; não reabre trabalho de H03 em S0.4 | O finding histórico é preservado como resolvido localmente. Qualquer confirmação adicional depende de evidência posterior; esta matriz não declara fechamento de GRILL nem prontidão de produção. |
| GRILL-H04 | HIGH | Dependency readiness has a ready_ids to claim_many TOCTOU race | **retain-local** | Trabalho local aberto; Task H04 | É uma falha de protocolo Fleet local: a dependência deve ser revalidada no caminho bloqueado de claim, entre observação de readiness e lease. |
| GRILL-H05 | HIGH | Ordinary GateResult can bypass HumanVerificationGate | **retain-local** | Trabalho local aberto; Task H05 | É uma falha de admissão/autorização do protocolo local: operação que exige humano não pode aceitar `GateResult` comum como substituto de `HumanVerificationGate`. |
| GRILL-H06 | HIGH | HumanVerificationGate stored scope and run are not checked against operation | **retain-local** | Trabalho local aberto; Task H06 | É uma falha de autorização local: `expected run` e escopo canônico da operação precisam ser exigidos e mismatch deve falhar fechado. |
| GRILL-M01 | MEDIUM | Observability serializes arbitrary objects through repr | **retain-local** | Trabalho local de robustez; sem evidência nova registrada nesta tarefa | Serialização/projeção de observabilidade pertence ao Fleet local e pode invocar `repr` controlado pelo objeto; permanece correção local, sem inventar resultado de teste. |
| GRILL-M02 | MEDIUM | Sandbox cwd is path-validated but not descriptor-pinned | **defer-runtime** | Fora do alvo atual; sem claim de sandbox forte | Pinagem de diretório contra atores hostis é requisito de sandbox/runtime. O escopo explicitamente não promete sandbox de produção nem trata `LocalSandboxRunner` como tal. |
| GRILL-M03 | MEDIUM | Expired leases remain in scheduler path occupancy | **retain-local** | Trabalho local de consistência do scheduler; sem evidência nova registrada nesta tarefa | Ocupação de paths e expiração de leases são responsabilidades do Fleet local; o finding permanece uma questão de correção do protocolo, embora não seja H04/H05/H06. |
| GRILL-M04 | MEDIUM | Single-task claim computes expiry before acquiring store lock | **retain-local** | Trabalho local de consistência de claim; sem evidência nova registrada nesta tarefa | Momento de cálculo de expiry e fencing sob lock pertencem ao contrato local de persistência/lease. Não há comando ou evidência nesta tarefa para marcar como resolvido. |
| GRILL-M05 | MEDIUM | Legacy parsers silently discard unknown fields | **retain-local** | Trabalho local de contrato/validação; sem evidência nova registrada nesta tarefa | Parsing de contratos Fleet e rejeição/extensão de campos desconhecidos são responsabilidades locais e permanecem relevantes para entradas determinísticas e seguras. |
| GRILL-M06 | MEDIUM | Evidence record can be accepted without execution provenance or freshness | **retain-local** | Trabalho local de evidência/gates; sem evidência nova registrada nesta tarefa | Proveniência, escopo e freshness usados na autorização local são parte do contrato de evidência e complementam H06; não se afirma que a lacuna foi corrigida. |
| GRILL-L01 | LOW | Missing evidence timestamp uses wall clock and breaks deterministic serialization | **retain-local** | Melhoria local de determinismo; sem evidência nova registrada nesta tarefa | Timestamp e serialização determinística de evidência são comportamento local do Fleet e não dependem de providers live ou deployment. |
| GRILL-L02 | LOW | GatePolicy accepts unknown requirement keys silently | **retain-local** | Melhoria local de validação; sem evidência nova registrada nesta tarefa | Validação de chaves de política é contrato local de gates; permanece no escopo de robustez, sem alegar correção já verificada. |

## Resultado da triagem

- **retain-local:** H04, H05, H06, M01, M03, M04, M05, M06, L01, L02.
- **defer-runtime:** H01, H02, M02.
- **superseded-by-scope:** nenhum finding do JSON é apagado ou reinterpretado como inexistente; nenhum dos 14 títulos é, por si só, uma implementação OMH/live/deployment a ser declarada superseded. As expectativas de sandbox forte, providers live, deployment e runtime operacional são tratadas como **defer-runtime** pelo novo boundary.
- **evidence-later:** H03, por já constar como `resolved_locally` no contexto e não ser reaberto por S0.4; confirmação posterior continua necessária para qualquer conclusão mais ampla.

Esta triagem é uma decisão de escopo para o plano. Ela não substitui testes, revisão independente, parse do artefato histórico, verificação de diff ou a futura decisão `LOCAL_VERIFIED`/`PARTIAL` prevista pelo plano.
