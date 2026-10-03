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

## Limitações históricas para uma fleet real

> **Nota de direção (escopo atual):** Os itens abaixo preservam o diagnóstico histórico de uma
> possível Fleet mais ampla; não são um compromisso de habilitar um runtime de produção. O alvo
> desta etapa é a correção e a verificação de um protocolo Fleet local/simulado. Hermes continua
> sendo o host de runtime e Gateway. Em um follow-up separado, o Fleet poderá se conectar ao
> Gateway como cliente/bridge para observar sessões iniciadas pelo usuário; uma execução
> Fleet-owned continua sendo uma etapa posterior e explicitamente autorizada.

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

## To-Be — alvo local atual

O PD será um **compiler de goals em planos executáveis** e um **protocolo de coordenação local**,
não um daemon, scheduler ou serviço de produção. O PD Core mantém a decisão e o workflow; o PD
Fleet é uma extensão opcional para coordenação simulada/local.

O sistema deverá:

- compilar goal em SPEC, PLAN, DAG e contracts;
- calcular tasks prontas e waves elegíveis;
- atribuir papel/agente de acordo com capacidades;
- executar tasks isoladas ou em paralelo localmente, com limites seguros e ownership explícito;
- registrar outputs, evidências, blockers e tentativas;
- pausar em gates de decisão, review, grill e validação;
- retomar somente o que está pendente ou falhou;
- produzir um prompt final reutilizável para a próxima rodada, sem ativar dispatch externo.

O sucesso desta etapa é um run local reproduzível, sem provider, rede, credencial, cron ou
execução live. OMH permanece apenas como material de referência/aprendizagem, sem instalação,
adapter ou sincronização de estado.

### Follow-up separado — Hermes Gateway Fleet Bridge

Futuramente, e somente mediante escopo e aprovação próprios, um `HermesGatewayFleetBridge` poderá
consumir eventos JSON-RPC/WebSocket do Gateway e associar sessões Hermes ao estado do Fleet. O
primeiro modo é `user_owned_session`, read-only; `fleet_owned_task` e operações como execute,
cancel, handoff e cleanup exigem contrato e autorização separados. Esse trabalho não faz parte
do objetivo local atual e não implica provider live, cron, sandbox de produção ou integração OMH.

## Estratégia de transição

A evolução deve ser incremental e compatível:

### M1 — Modelar
Schemas, templates, exemplos e validação. Nenhuma execução automática ainda.

### M2 — Observar
CLI mostra DAG, status, blockers e tasks elegíveis, sem despachar agentes.

### M3 — Coordenar localmente
Um coordenador local/simulado aplica contratos e registra relatórios; não há ativação de
provider, rede ou dispatch externo.

### M4 — Paralelizar localmente com segurança
Isolamento, ownership de paths, limites de concorrência e resolução explícita de conflitos.

### M5 — Fechar o ciclo local
Review/grill/smoke como gates locais; prompt refinement e evidências do projeto. Métricas
operacionais e runtime ficam fora deste escopo.

## Decisões recomendadas

- Começar com um orchestrator lógico, não com um novo serviço distribuído.
- Manter o PD como protocolo agnóstico de runtime; adapters de Hermes/OpenCode/Claude são seams
  opcionais e não são ativados pelo Fleet local.
- O `pd` deve funcionar em modo `pd-only`, sem Fleet e sem Hermes. O Fleet deve funcionar em
  modo `fleet-local`, sem Hermes, rede, credenciais ou provider externo. Hermes é apenas um
  runtime adapter opcional, selecionado por capability e sujeito a gates próprios. Ver
  [`PD-FLEET-RUNTIME-ADAPTERS.md`](PD-FLEET-RUNTIME-ADAPTERS.md).
- O `.spec` é a fonte de verdade do workflow PD: intenção, contratos, gates e decisões de desenvolvimento. O Fleet mantém apenas o estado da execução local — tasks, leases, lifecycle, reports, checkpoints e eventos — e não pode substituir uma decisão, gate ou aprovação do PD. O runtime adapter mantém o estado concreto de sua sessão/execução; nenhum estado de runtime ou Fleet, isoladamente, autoriza merge, release, deploy ou mudança de escopo.
- Preferir paralelismo conservador e observável a máxima concorrência.
- Nunca permitir que o monitor esconda uma falha para “manter a operação andando”.
