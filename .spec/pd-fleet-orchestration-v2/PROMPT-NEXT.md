# PROMPT-NEXT — Execução PD Fleet Orchestration V2

Você é o executor da V2 no repositório `/home/vitor/project/project-development-skill`, branch `feat/pd-fleet-orchestration-plan`, commit-base `e1cdb4e`. Trabalhe em português. **Não faça dispatch externo, não use provider, não altere docs V1, não faça commit/push e não execute comandos arbitrários do plano.**

## Contexto e status real

Leia antes de agir: `.spec/pd-fleet-orchestration-v2/RESEARCH.md`, `CONTEXT.md`, `SPEC.md`, `PLAN.md`, `GRILL-001.md`. V1 está em `.spec/pd-fleet-orchestration/` e deve ser preservado. Baseline verificado: `pytest -q` = **278 passed**. A review encontrou batching serial apesar de `max_parallel`, validation_commands apenas declarativos, output não totalmente canônico, falta de FleetRunStore independente do CLI, AgentReport permissivo, provider externo inexistente (por decisão default-deny) e gate humano não aprovado. Não chame isso de PASS.

## Pré-condições e gates

1. Rode `git status --short --branch`, `git log -1 --oneline`, `pytest -q` e `git diff --check`.
2. Leia o grill. Se houver BLOCKER/HIGH, pare: não implemente.
3. Exija aprovação humana explícita para G1. Sem ela, apenas refine documentação/testes de plano.
4. Após cada wave, execute seu gate; falha bloqueia a próxima e preserva evidência.
5. Antes do handoff: `pytest -q`, `python -m compileall scripts/pd_fleet`, `git diff --check`, checker de caminhos documentado no plano e `git status --short`.

## Contratos obrigatórios

- Store único: `run_id`, `plan_hash`, generation, owner/lease, CAS, snapshots atômicos, events append-only e replay idempotente.
- Reconciliation precede readiness e qualquer dispatch.
- JSON/report/eventos normalizados e ordenados; timestamps e paths absolutos não participam do output lógico; redaction antes de persistir.
- `AgentReport.completed` exige outputs requeridos, evidence/tests, decisão e timestamps; failed/blocked exige motivo estruturado.
- Validation é declarativa por default. Executor só via allowlist exata + argv sem shell + root/sandbox + timeout + ambiente mínimo + output limitado. Sem policy: zero subprocessos.
- Provider é somente protocolo/adaptador disabled; sem rede, credenciais, SDK ou fallback.
- Paralelismo real somente após persistência/ownership: workers bounded, leases, sem mutação no worker, resultados bufferizados e commit por ordem canônica.
- Gate humano final exige `owner`, identity string auditável, decision APPROVED, escopo/hash, evidence digest e freshness; BLOCKER/HIGH ou mudança reabre. Autenticação criptográfica/identity provider são futuros e out-of-scope.

## Waves e tarefas

Execute exatamente as waves de `PLAN.md`, tarefas pequenas T2-01…T2-18: baseline/reconciliation; canonical model; FleetRunStore; checkpoints; strict AgentReport; executor seguro; provider boundary; reconciliation/orchestration; audit/metrics; leases; bounded parallelism; deterministic integration; CLI compatibility; human gate; docs/roadmap; evidence/handoff. Respeite para cada tarefa objective, exact files, dependencies, role/capabilities, allowed/forbidden paths, failing tests, implementation, verification, acceptance, rollback e gate. Não crie arquivos fora das allowlists; caminhos inexistentes marcados `Create` podem ser criados somente na tarefa correspondente.

## Política de implementação

O modo aprovado agora é local/in-process e simulado. Não habilite shell, rede ou provider para “fazer os testes passarem”. Se sandbox real não estiver disponível, mantenha executor declarativo e registre a limitação. Paralelismo só pode ser ligado depois de G3 e G5; feature flag default-off até evidência repetível. Compatibilidade legada tem precedência sobre conveniência V2.

## Handoff

Entregue relatório por tarefa/wave com testes falhos iniciais, implementação, comandos/resultados, evidência, riscos residuais, rollback e decisão de gate. Estado final sem aprovação humana deve ser `NOT READY/PARTIAL`, nunca PASS. Modifique somente `.spec/pd-fleet-orchestration-v2/` nesta sessão de planejamento.

## Critérios adicionais não negociáveis da review

- Use a matriz auditável em `RESEARCH.md`: todo finding B-01, H-01…H-05, M-01…M-04 e gap adicional precisa de V2-R, T2, failing test exacto, comando/expected e evidence artifact.
- Cada T2-01…T2-18 deve manter `Commands / Expected results` separado de `Verification`, com comando copy-pasteável e expected explícito.
- TOCTOU só fecha com teste claim→use→commit que rejeite generation/lease stale e prove state não corrompido.
- ValidationExecutor é local sem shell por default; allowlist, cwd/env, timeout/output limits e sandbox capability são explícitos; sandbox indisponível falha fechado. Unknown AgentReport fields são rejeitados por default e testados.
- Human gate registra identity string, owner, decision, evidence digest, created_at/updated_at e freshness window; stale/ownerless rejeita. Não alegar autenticação criptográfica: é out-of-scope/futura.
- Antes do handoff execute e registre: `pytest -q`, `git diff --check`, `python -m compileall scripts/pd_fleet` e o checker de paths; ausência de evidência mantém `NOT READY/PARTIAL`.
