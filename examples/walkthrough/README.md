# Walkthrough ponta-a-ponta (executavel)

Prova, num diretorio descartavel, que o ciclo do PD fecha **sem o autor**:

```
init -> SPEC/PLAN/CONTEXT -> plan.yaml com gate de revisao
     -> bloqueio honesto (o gate vale) -> gate humano com escopo amarrado
     -> execucao -> complete-task -> checkpoint -> VERIFICATION.md
     -> validate 13/13 -> verify
```

## Rodar

```bash
/usr/bin/python3 examples/walkthrough/run_walkthrough.py          # roda e limpa
/usr/bin/python3 examples/walkthrough/run_walkthrough.py --keep   # deixa .walkthrough/ para inspecao
```

Exit 0 = ciclo fechou. Qualquer passo falha com o comando, o stdout e o stderr na tela.

## O que ele prova (e como)

| passo | o que fica provado |
|---|---|
| `init` + documentos | o scaffold do `pd init` e suficiente para comecar; nada de arquivo escondido |
| `validate` antes do gate | o 12o check le o `plan.yaml`; e o `VERIFICATION.md` aparece como ausente (nao como aprovado) |
| `fleet-run` sem gate | uma wave com gate `review` **nao roda** — `blocked`, com `hint` e `gate_template` |
| gate de outro run | binding por `run` e por escopo (`plan_hash`/tasks/waves) recusa gate reaproveitado |
| gate valido | a task executa de fato e o `fleet_state` persiste `completed` |
| `complete-task` + `checkpoint` | o registro humano acompanha o estado da maquina |
| `VERIFICATION.md` + `[x]` | criterio so e marcado depois da evidencia |
| `validate` 13/13 + `verify` | os portoes finais fecham com o CLI sozinho |

## O que ele NAO prova

- **Dispatcher simulado.** O `fleet-run` usa o dispatcher local/default-deny; nao ha provider,
  rede, nem execucao externa. "completed" aqui significa "a task passou pelo ciclo", nao
  "um agente externo fez o trabalho".
- **Nada de merge, push ou release.** O walkthrough para em `verify`; publicar e decisao do dono.
- **Cockpit/Board.** A superficie visual nao e exercitada (o `--publish` escreve em
  `~/.hermes/boardstate-state/`, que nao existe numa maquina sem Hermes host).
- **Terceiro independente.** O script e reproduzivel por qualquer pessoa, mas esta execucao foi
  feita pelo autor. Prova de onboarding exige alguem de fora rodando e relatando onde travou —
  o script so remove a desculpa de "nao tem como reproduzir".

## Por que isso existe

Um review de produto (`.spec/reviews/produto-20261102.md`) apontou que o repo nao tinha nenhum
caminho ponta-a-ponta executavel: o unico exemplo (`examples/pd-fleet/run_local.py`) nao roda os
`validation_commands` do manifesto. Este script e a resposta minima: ele falha se o ciclo parar
de fechar, e cada passo tem o comando equivalente para quem quiser repetir na mao.
