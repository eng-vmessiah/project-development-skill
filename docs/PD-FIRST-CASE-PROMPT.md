# Prompt final — Primeiro caso: transformar o PD em uma fleet de subagents

> Este é o prompt histórico de execução para iniciar a implementação em uma sessão nova, a partir da branch de planejamento. Ele assume que o executor deve ler o repositório antes de alterar qualquer arquivo.
>
> **Estado real (R3, 2026-07-17):** as remediações locais T1–T13, R1/R2 e matching de role/capabilities estão implementadas; a suíte atual tem **278 testes passando**. A evidência fresca está em [`.spec/pd-fleet-orchestration/VERIFICATION.md`](../.spec/pd-fleet-orchestration/VERIFICATION.md). Ainda assim, este documento não autoriza declarar PASS sem verification gate: R14/R18 permanecem PARTIAL por caveats documentados, `validation_commands` são declarativos, timestamps/paths podem variar na saída bruta e não há provider externo por default. O histórico T14/T15/T16/T17 abaixo é preservado deliberadamente.

## Papel

Você é o orchestrator principal desta missão. Coordene uma fleet de subagents com contexto fresco e responsabilidades delimitadas. Não implemente diretamente quando a tarefa puder ser delegada. Você é responsável por estado, dependências, integração, gates e evidências.

## Goal

Evoluir o Project Development Skill (PD) de um pipeline de fases com orientação textual de waves para um protocolo executável de orquestração de uma fleet de subagents, preservando compatibilidade com o fluxo simples existente.

O resultado deve permitir transformar um goal complexo em SPEC, PLAN, waves, DAG de tasks, contratos, atribuição de papéis, execução paralela segura, checkpoints, review/grill/smoke gates e prompt refinado de continuação.

## Contexto obrigatório

Leia primeiro:

- `README.md`
- `skills/pd/SKILL.md`
- `pd.yaml`
- `ROADMAP.md`
- `skills/subagent-driven-development/SKILL.md`
- `skills/plan/SKILL.md`
- `skills/writing-plans/SKILL.md`
- `skills/pd/templates/*`
- `scripts/pd`
- `tests/`

Considere também:

- `docs/PD-FLEET-ORCHESTRATION-PLAN.md`
- `docs/PD-AS-IS-TO-BE.md`

Não assuma que a documentação está correta sem verificar o código e os testes.

## Restrições

- Não quebrar o fluxo atual de features simples.
- Não introduzir um daemon distribuído como primeira implementação.
- Não permitir execução paralela sem validação de dependências e ownership de paths.
- Não criar abstrações sem uso demonstrável no primeiro caso.
- Manter adapters/runtime agnósticos sempre que possível.
- Não alegar conclusão sem executar testes/validações e registrar evidências.
- Perguntas não bloqueadoras devem ser resolvidas por uma decisão conservadora documentada.

## Método obrigatório

### Wave 0 — Reconhecimento
Use subagents de pesquisa em paralelo para mapear CLI, schemas, templates, testes e pontos de extensão. O orchestrator consolida antes de codar.

### Wave 1 — Design executável
Produza ou atualize SPEC/PLAN do próprio caso com:

- modelo de fleet e papéis;
- schema de wave/task/contract;
- estados e transições;
- regras de dependência e paralelismo;
- artefatos e evidências;
- compatibilidade e migração;
- critérios de aceitação testáveis.

Submeta o plano a um `grill` antes da implementação.

**Gate G1 obrigatório:** registre `gate_id`, owner, status, decisão e evidência no estado. Não inicie código enquanto houver `BLOCKER` ou `HIGH` aberto, ou decisão humana pendente.

### Wave 2 — Fundação
Implemente primeiro schemas, templates e validação determinística. Inclua testes para DAG, dependências inválidas, ciclos, paths conflitantes, transições inválidas e critérios ausentes.

### Wave 3 — Estado e inspeção
Adicione ao CLI a capacidade de inspecionar fleet, waves, tasks elegíveis, blockers e checkpoints/resume. O modo read-only deve ser útil antes de qualquer dispatcher.

### Wave 4 — Orquestração local e adapters mínimos
Implemente apenas a abstração necessária para representar despacho/relatório de subagent. Não acople o core a um provedor específico. Registre input, output, status, tentativa e evidência.

### Wave 5 — Gates e exemplo executável
Formalize review, grill, smoke test e evidence gate. Falhas devem interromper a progressão e apontar a task responsável. Execute o exemplo local da própria evolução do PD sem credenciais externas.

### Wave 6 — Review pós-código e prompt refinement
Execute spec compliance review, code quality review e adversarial grill. Em seguida crie o contrato/template de prompt refinement de entrada e saída. O prompt produzido deve conter goal, contexto, escopo, restrições, waves, dependências, critérios de aceitação e validação.

### Wave 7 — Smoke e evidence gate
Execute build, testes, CLI, migração, resume e o exemplo completo. Gere `VERIFICATION.md` com evidências frescas.

### Wave 8 — Closeout
Atualize estado, changelog e relatório. Salve o prompt refinado de continuação. Não faça merge automaticamente.

## Fleet inicial

Use estes papéis, sem multiplicar agentes desnecessariamente:

- `orchestrator`: coordena e atualiza estado;
- `researcher`: leitura e descoberta;
- `coder`: implementação delimitada;
- `analyst`: arquitetura e requisitos;
- `reviewer`: diff e contrato;
- `grill`: adversarial review;
- `smoke-tester`: execução do caminho crítico;
- `prompt-refiner`: prompt de entrada/saída.

## Critérios de aceitação

- [ ] O schema representa waves, tasks, dependências, papel, ownership, outputs e critérios.
- [ ] O validador rejeita ciclos, dependências inexistentes, task sem contrato e conflito de paths.
- [ ] O estado suporta `pending`, `ready`, `running`, `blocked`, `failed`, `completed` e `skipped`.
- [ ] Existe consulta determinística das tasks elegíveis.
- [ ] Há checkpoint/resume sem replay cego de tasks concluídas.
- [ ] Review, grill, smoke e evidence são gates representados por artefatos.
- [ ] O fluxo simples anterior continua funcionando.
- [ ] O exemplo da própria evolução do PD é executável e testado.
- [ ] A documentação explica As-Is, To-Be, migração, paralelismo e contratos.
- [ ] O prompt refinado final é salvo como artefato e pode iniciar uma nova sessão.
- [ ] O verification gate foi executado com comandos frescos, owner/decisão/evidência registrados; sem esse gate, o status permanece `PARTIAL`.

## Entrega final obrigatória

Retorne:

1. resumo arquitetural;
2. lista de arquivos alterados;
3. tasks executadas por wave e agente;
4. testes e comandos com resultado real;
5. blockers e riscos residuais;
6. decisões que exigem aprovação humana;
7. caminho do prompt final refinado;
8. recomendação objetiva para a próxima execução.

Não faça merge automaticamente. Pare com a branch pronta para review humano.
