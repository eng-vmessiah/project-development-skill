# POST-G3.md — incrementos posteriores ao closeout

`VERIFICATION.md` desta missão está congelado no estado em que G3 foi aprovado (`5a8f27e`): 11/11,
com o item deferido #5 aberto. Ele **não** é editado depois do gate — um artefato de verificação que
muda após a aprovação reconstrói o problema que o PD existe para evitar. Trabalho feito depois disso
vive aqui, separado e datado.

## 02/11 — manifest check no CLI + migração de status

Origem: review de produto apontou o item como "anti-evidência estrutural"; a correção foi separar o
registro novo do artefato congelado, não reescrevê-lo.

### O que mudou

1. **`pd validate --deep` ganhou o 12º check** (`plan.yaml manifest`): o manifesto precisa carregar no
   modelo `FleetPlan`, todo status de task/wave precisa estar em `LifecycleState`, e toda referência
   task→wave / wave→task / wave→gate precisa resolver. Era o buraco que deixou o drift de `done`
   viver semanas sem ninguém ver.
2. **45 linhas migradas de `done` para `completed`** nos três manifestos (b15b-gateway 19,
   pd-fleet-control-plane-v1 7, plan-cockpit-v1 19). `done` não existe no `LifecycleState`, e é por
   isso que `pd fleet-run` recusava checkpoint com esse status.

### Evidência (executada)

| o que | comando | resultado |
|---|---|---|
| check novo | `/usr/bin/python3 scripts/pd.py validate --deep -f pd-fleet-control-plane-v1` | **12/12** (11 + manifest) |
| testes do check | `pytest tests/test_pd.py -q` | **52 passed** (3 casos novos: drift rejeitado, canônico aceito, wave inexistente) |
| suíte inteira | `pytest tests/ -q` | **1438 passed, 1 skipped** |
| modelo aceita os três | `FleetPlan.from_dict` em cada `plan.yaml` | sem status fora do enum |

### Efeito colateral declarado

`b15b-gateway` e `plan-cockpit-v1` passam a marcar **11/12** (falham só em
`Test files — 0 non-empty test file(s)`), onde antes liam 11/11. O denominador mudou porque o check
passou a existir; não é regressão de código.

### O que o item #5 de `VERIFICATION.md` continua dizendo

Ele registra o estado do closeout — e estava certo quando foi escrito. A frase "a manifest check
belongs in the CLI" foi cumprida aqui, não lá.

## 2026-11-02 (2) — 13º check: `STATE.json loads`

O review de código (`codigo-20261102.md`, D4) reproduziu `phase: 99` no `STATE.json`: `pd status`
morria com `IndexError` enquanto `pd validate --deep` imprimia "All checks passed". O check de
`STATE.md parseable` era `_add(..., True, "Loaded successfully")` incondicional.

- `PDState._load_from_json` valida `phase` contra as fases configuradas (não confia no fallback).
- `pd validate --deep` relê o `STATE.json` cru e reprova com `STATE.json loads` + motivo.
- O check de `STATE.md` passou a exigir o header `## Phase` de fato (antes era sempre verdadeiro).
- Total: **13/13** na missão. Suíte: 1447 passed / 1 skipped.
