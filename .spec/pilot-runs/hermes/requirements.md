# Requisitos — exemplo de fleet (piloto PD Fleet, T-001)

Documento curto e honesto que descreve o que o exemplo de fleet precisa entregar.
Escopo: exemplo de referência usado no piloto; não é o produto final.

## Objetivo

Demonstrar, em uma execução fictícia de fleet, que um agente consegue:

1. Receber uma missão com tarefas identificadas (ex.: `pd-fleet T-001`).
2. Executar uma tarefa por vez, com escopo explícito (o que criar, onde criar).
3. Produzir um artefato verificável no diretório de trabalho.

## Requisitos funcionais

- R1. Entrada: missão com id, objetivo e critérios de aceite da tarefa.
- R2. Escopo fechado: a ação de cada tarefa é declarada antes da execução (sem descobrir o escopo durante a execução).
- R3. Saída verificável: artefato persistido em disco, no caminho indicado pela tarefa.
- R4. Rastreabilidade: o artefato cita a missão e a tarefa que o originou.
- R5. Conclusão honesta: declarar concluído, dívida ou bloqueio — sem fabricar resultado.

## Requisitos não funcionais

- N1. Simplicidade: um arquivo por tarefa, sem dependências externas.
- N2. Revisabilidade: conteúdo curto o bastante para revisão humana em uma leitura.
- N3. Idempotência: reexecutar a tarefa reescreve o mesmo artefato, sem efeitos colaterais.

## Critério de aceite

Os requisitos do exemplo estão documentados neste arquivo, em formato revisável,
e cobrem entrada, escopo, saída, rastreabilidade e declaração honesta de status.

## Fora de escopo

- Execução real de agentes externos, custo de API, integração com o Hermes vivo.
- Definição de missões ou tarefas além do exemplo do piloto.

## Status

Concluído — artefato de exemplo para o piloto T-001, sujeito a revisão.
