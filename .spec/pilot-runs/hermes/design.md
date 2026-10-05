# design.md — T-002 (piloto PD Fleet)

## Objetivo
Definir a estrutura técnica do artefato dependente da tarefa T-002.

## Escopo
Artefato é um documento de desenho (este arquivo). NÃO inclui: código,
banco de dados, integração externa ou automação. É um piloto: o artefato
é deliberadamente mínimo.

## Interfaces
- Entrada: especificação da tarefa (objetivo + critérios) fornecida pelo
  runner.
- Saída: este arquivo `design.md` no diretório atual.
- Consumidor: revisão/verificação do piloto; leitura humana ou por script.

## Limites
- Sem dependências externas, rede ou credenciais.
- Sem efeitos fora do diretório de execução.
- Não define comportamento de runtime: apenas descreve a forma do artefato.
- Não substitui spec de produto; cobre só a fatia necessária ao piloto.

## Critério de aceite
O desenho identifica interfaces (entrada/saída/consumidor) e limites do
artefato final — conforme seções acima.
