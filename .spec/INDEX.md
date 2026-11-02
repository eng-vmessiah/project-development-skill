# .spec/ — índice das missões

Estado em 2026-11-02. Uma linha por missão; `arquivada/` guarda o histórico que não é mais fonte
de verdade. O que está aqui é **registro**, não compromisso: nada neste diretório autoriza
declarar PASS sem verification gate.

## Fonte de verdade atual

| missão | o que decide hoje | evidência |
|---|---|---|
| `pd-fleet-control-plane-v1` | contrato de atividade (`ACTIVITY-CONTRACT.md`), contrato de steering (design-only), 12º check do `validate --deep` | `VERIFICATION.md` (congelado no G3) + `POST-G3.md` (o que veio depois) |
| `plan-cockpit-v1` | coletor `scripts/plan_cockpit_sync.py` e o painel Mission Control | `VERIFICATION.md` |
| `b15b-gateway` | gateway Fleet V2 → Hermes; **ler a nota de status no topo** (a seam foi removida pelo update do host) | `VERIFICATION.md` (2026-10-05) |

`reviews/` guarda auditorias independentes (produto, docs×realidade, código). Review não é gate:
as decisões que ele gera viram incremento, com aprovação.

## Fechadas — histórico, não governam mais nada

| missão | substituída por | por que continua aqui |
|---|---|---|
| `archive/pd-fleet-orchestration` | `pd-fleet-orchestration-v2` | primeira geração do fleet; os números de teste dela (278) são baseline histórico |
| `pd-fleet-orchestration-v2` | `pd-fleet-control-plane-v1` | define o checker `v2_doc_paths`, ainda em uso |
| `pd-fleet-hermes-adapter-v0` | `pd-fleet-hermes-adapter-real-v1` | **não arquivar**: `contracts/` é lido por `scripts/pd_fleet/run_fake_vertical.py` e por `tests/fleet/test_v2_fake_adapter.py` |
| `pd-fleet-hermes-adapter-real-v1` | — | escopo aberto e nunca executado (0 tasks); fica como registro da intenção |
| `pd-fleet-hermes-gateway-fleet-v1` | `b15b-gateway` | decisão de gateway anterior |
| `pd-fleet-scope-alignment` | `pd-fleet-control-plane-v1` | alinhamento de escopo da fase anterior |
| `pd-fleet-supervisor-handoff` | `pd-fleet-control-plane-v1` | contrato de handoff do supervisor |
| `pd-fleet-lifecycle-events` | `pd-fleet-control-plane-v1` | eventos de lifecycle viraram `ACTIVITY-CONTRACT.md` |

## Design e pesquisa — sem execução, não são plano

`pd-studio`, `pilot-runs` e `cockpit-btg-benchmark-v1` são desenho/pesquisa, e `research/`
guarda input de discovery (omp/OMH/TTSR/advisor) que saiu do ROADMAP público. Não têm `STATE.json`,
`plan.yaml` nem `VERIFICATION.md`; não entram em `pd list` e não devem ser citados como
"implementado". Pesquisa (omp/OMH, benchmark BTG, TTSR) pertence a nota de vault, não a ROADMAP.
