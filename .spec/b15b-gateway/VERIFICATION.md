# VERIFICATION — b15b-gateway (B15b)

**Status:** final · 2026-10-05 · Feature `b15b-gateway` (12 tasks / 7 waves / gates G-0→G-3).
**Regra-mãe honrada:** `local_verified` **nunca** substitui `NOT_READY_HERMES_SEAM`; buckets de evidência separados (contract/fake/TUI/seam/live).

## Verified (com evidência)

| Fase | Entregável | Evidência |
|---|---|---|
| B15b.0 | Decisões A1–A11 + composite-deny (B1–B8) + mapping TUI↔bridge | `B15B-DECISION-MATRIX.md`/`B15B-REVIEW-PACKET.md`; reviews PASS; **G-0/G-1 approved**; commits `b914ec0`/`15106a1` |
| B15b.1 | Seam read-only (observer registry default-off) | Série `patches/b15b-seam/` (base `dc50153faf`); **replay tree idêntico `39dd54e4be…`**; 7/7; **0 call sites**; review PASS + re-check |
| B15b.2 (a) | Auth + associação local | `gateway_auth.py`; 22+1 fixtures G4 §9; review PASS (LOW fixes aplicados) |
| B15b.2 (b) | Composite-deny + redaction | `gateway_deny.py`/`gateway_redaction.py`; 23 fixtures nomeadas G-2; MEDIUM-1 fechado (re-check PASS) |
| **G-2** | Allowlist/denylist de redação | `B15B-REDACTION-ALLOWLIST.md` **aprovado pelo owner** ("sim"); v0.2 review PASS |
| B15b.3 | Subscription v1 (ordering/ack/TTLs/gaps) | `gateway_subscription.py`; 17 fixtures; MEDIUM-1/2 fechados (re-check PASS) |
| B15b.4 | Replay/rollback + crash matrix | Ensaio do rollback **PASS** (ambiente controlado; live intocado); review PASS; matriz 8/8 |
| **B15b.5 LIVE** | Instalação + validação live | Checkout vivo `966a079d9c`; sanidade **7/7**; restart stop/verify/start/verify (**~3s downtime**); **default-off vivo OK** (env real); serve intocado (MainPID 1534474); `B15B-LIVE-EVIDENCE.md` + `.log` |
| Suíte local | Regressão | `tests/fleet/` **1351 passed / 0 errors** (inclui fix do harness pytest/nose-compat) |

## G4 live closure (o que este slice FECHOU vs o que segue ABERTO)

**Fechado live:** instalação do seam sem efeito (default-off provado no processo real) · estabilidade do gateway pós-restart (procedimento ensaiado e executado) · rollback pronto e ensaiado · canário B15a.2 preservado (serve intocado) · uniformidade fail-closed provada em camada local (fake).

**Aberto (NOT_READY_HERMES_SEAM permanece):** publisher de eventos live (não existe) · wiring TUI↔bridge end-to-end · replay operacional pós-restart do gateway · crash injection real · rotação de chave (A8) · global/multi-sessão (deferido por design) · medição de timing-budget externo (propriedade do gateway live futuro).

## Deferred / Blocked (explícitos)

- **Deferred:** publisher/wiring live; A8 rotação; multi-sessão; SIGKILL real; retenção/tombstone com store durável (notas NIT-1 do T-301).
- **Blocked:** nada bloqueado. **Quirk documentado:** stop do gateway ⇒ exit 1 no SIGTERM ⇒ unit `failed` pós-stop (stop rc=0; start recupera) — pré-existente, sem impacto funcional.

## Estado final

- **Repo PD:** `main` com toda a linha B15b (commits `b914ec0` → `41f943f`/`dd97e28`); feature 12/12; gates G-0/G-1/G-2/**G-3 approved**.
- **Checkout vivo:** `966a079d9c` (seam **instalada, inert**); rollback documentado (`dc50153faf` + restart).
- **Painel:** Mission Control reflete o fechamento (refresh pós-feedings).
- **Review independente final:** dispatchado no closeout (T-602).
