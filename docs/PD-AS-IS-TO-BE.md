# PD — As-Is, To-Be e lacunas

## As-Is observado no repositório

O projeto já possui uma base sólida:

- skill `pd` como master orchestrator;
- pipeline de 8 fases: setup, brainstorming, planning, structure, coding, testing, validation e merge;
- princípio explícito de não codar antes de spec + plan;
- execução em waves e padrões supervisor-worker, pipeline, review loop e swarm;
- persistência em `.spec/<feature>/STATE.json` e `STATE.md`;
- CLI com `init`, `status`, `validate`, `checkpoint`, `verify`, `advance`, `complete-task`, `history`, `report` e `diff`;
- templates de `TASK.md`, `CHECKPOINT.md` e `STATUS.md`;
- suporte declarado a Hermes Agent, OpenCode e Claude Code;
- skills complementares de planejamento, testes, review, debugging e subagents;
- configuração de fases, arquivos obrigatórios, hooks e regras de validação em `pd.yaml`.

## Limitações atuais para uma fleet real

1. O plano descreve fases, mas não possui ainda um contrato formal de task com agent, paths, outputs e critérios.
2. Waves existem como orientação textual; falta um DAG validável e estados por task.
3. A configuração não modela papéis, capacidade, seleção de agente ou política de paralelismo.
4. O CLI acompanha progresso, mas não funciona ainda como scheduler/dispatcher.
5. Não há primeira classe para `ready`, `running`, `blocked`, `failed` e retries.
6. Checkpoints persistem contexto, mas resume granular de task/wave precisa ser especificado.
7. Review, grill e smoke test aparecem no pipeline, mas não como gates com artefatos e evidências padronizadas.
8. Não existe um fluxo explícito de prompt refinement antes do plano e após o grill.
9. Conflitos de paths, isolamento de worktree e ownership de arquivos precisam de contrato.
10. Compatibilidade entre plataformas é documentada, mas adapters/capabilities da fleet ainda não estão definidos.

## To-Be

O PD será um **compiler de goals em planos executáveis** e um **protocolo de coordenação**, não necessariamente um daemon único.

O sistema deverá:

- compilar goal em SPEC, PLAN, DAG e contracts;
- calcular tasks prontas e waves elegíveis;
- atribuir papel/agente de acordo com capacidades;
- executar tasks isoladas ou em paralelo com limites seguros;
- registrar outputs, evidências, blockers e tentativas;
- pausar em gates de decisão, review, grill e validação;
- retomar somente o que está pendente ou falhou;
- produzir um prompt final reutilizável para a próxima rodada.

## Estratégia de transição

A evolução deve ser incremental e compatível:

### M1 — Modelar
Schemas, templates, exemplos e validação. Nenhuma execução automática ainda.

### M2 — Observar
CLI mostra DAG, status, blockers e tasks elegíveis, sem despachar agentes.

### M3 — Coordenar
Dispatcher chama subagents conforme contratos e registra relatórios.

### M4 — Paralelizar com segurança
Isolamento, ownership de paths, limites de concorrência e resolução explícita de conflitos.

### M5 — Fechar o ciclo
Review/grill/smoke como gates; prompt refinement e métricas operacionais.

## Decisões recomendadas

- Começar com um orchestrator lógico, não com um novo serviço distribuído.
- Manter o PD como protocolo agnóstico de runtime; adapters cuidam de Hermes/OpenCode/Claude.
- Usar arquivos `.spec` como fonte de verdade e CLI como operador determinístico.
- Tratar subagent como executor descartável; estado e evidência pertencem ao projeto.
- Preferir paralelismo conservador e observável a máxima concorrência.
- Nunca permitir que o monitor esconda uma falha para “manter a operação andando”.
