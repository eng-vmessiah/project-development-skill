# Grounding executável — steering T-301

Execução de referência:

```text
/usr/bin/python3 .spec/pd-fleet-control-plane-v1/steering/probes/run_probes.py
TOTAL=6 PASS=5 FAIL=1
```

O exit code agregado foi `1`, intencionalmente, porque uma afirmação foi refutada.

| Afirmação (seção do contrato) | Probe | Saída real resumida | Veredito | O que o contrato precisa mudar |
|---|---|---|---|---|
| A allowlist atual é exatamente `{observation}`; ausência de gates nega por B1–B8; capability `steer.kill` em B7 é negada (§10 e §6). | `probes/probe_gate_allowlist.py` | `CAPABILITIES_V1=frozenset({'observation'})`; gates ausentes: `allowed=False`, `denied_by=('B1', ..., 'B8')`; `steer.kill`: `allowed=False`, `denied_by=('B7',)`. | CONFIRMED | Nenhuma mudança para esta afirmação. A prova cobre o gateway atual de oito gates, não o B9 ainda apenas desenhado. |
| `owner_epoch` obsoleto bloqueia reconcile com `stale_owner_epoch` (§3 regra 3 e §5). | `probes/probe_epoch_fencing.py` | Snapshot epoch `7`, active epoch `8`: `status='blocked'`, `reasons=('stale_owner_epoch',)`. | CONFIRMED | Nenhuma mudança para a afirmação sobre `reconcile_snapshot`. Não extrapolar isto como implementação de fencing de comandos de steering. |
| Estado desejado `paused` com liveness `alive` é diagnóstico honesto `degraded/pause_not_observed` (§5). | `probes/probe_pause_semantics.py` | `status='degraded'`, `reasons=('pause_not_observed',)`. | CONFIRMED | Nenhuma mudança. |
| `InterventionProposal.reason` usa o enum de handoff: `kill_now` é inválido e `retry` é aceito (§4). | `probes/probe_reason_enum.py` | `kill_now` levantou `SupervisionError: invalid intervention reason`; `retry` foi armazenado como `'retry'`. | CONFIRMED | Nenhuma mudança. |
| A canonicalização descrita produz chave estável, independente da ordem das chaves e sensível ao payload (§4). | `probes/probe_idempotency.py` | Original, repetição e chaves reordenadas: `d882c1d1...70e1d`; payload alterado: `3bd8e933...1ec8fa2`. | CONFIRMED | Nenhuma mudança na descrição do algoritmo. O contrato deve continuar deixando claro que esta é uma regra de design, pois não há envelope/sink de steering implementado. |
| A API pública do sandbox recusa metacaractere de shell e URL em argumentos, sem executar (§10; relacionado também ao limite local de §8). | `probes/probe_sandbox_refusal.py` | `value;uname` foi `rejected:argv_invalid`; `https://example.invalid/resource` foi `accepted`. `run()` não foi chamado. | REFUTED | Não afirmar recusa de URL em `argv`. Especificar com precisão: metacaracteres são recusados na allowlist; URL é recusada em valores de `env`, mas pode integrar um argv exato allowlisted. Se steering exigir proibição de URL em qualquer argumento, isso demanda validação adicional ainda não implementada. |

## O que isto NÃO prova

- Não prova que steering existe ou que algum verbo possa ser executado; os probes não criam action surface.
- Não prova B9, autorização T1–T3, lineage de comandos, sink, auditoria hash-chained, idempotência persistida nem observação posterior de efeitos; esses elementos são design.
- Não prova isolamento de rede do sandbox. O probe somente exercita validação de configuração e nunca chama `LocalSandboxRunner.run()`.
- Não prova resistência a concorrência, TOCTOU ou entradas hostis além dos casos concretos medidos.
- Não prova o repositório inteiro, testes gerais ou `pd validate --deep`; somente as seis afirmações solicitadas.
