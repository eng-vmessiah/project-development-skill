# PLAN — b15b-gateway (Gateway de mensagens/API)

Plano: `B15B-PLAN.md` v0.3 (aprovado pelo owner em 05/10) · Decisões: `B15B-DECISION-MATRIX.md`.

## Wave 0 — Init
- [x] T-000 · orchestrator · feature init + plano cockpit-ready (FleetPlan v1 validado).

## Wave 1 — B15b.0: contratos & decisões (gate G-0)
- [x] T-101 · decision matrix — 11 decisões congeladas (`B15B-DECISION-MATRIX.md` §A).
- [x] T-102 · matriz composite-deny (8 gates, all-gates-pass) — §B.
- [x] T-103 · wire vocabulary mapping (proposta; seleção pelo Hermes owner) — §C.
- **Gate G-0: review independente sem BLOCKER/HIGH + sign-offs (owner/security) — PENDENTE.**

## Wave 2 — B15b.1: host seam read-only (gate G-1 = autorização de edição do checkout)
- [ ] T-201 · contrato do seam (publisher + principal resolution) ANTES de qualquer patch.
- [ ] T-202 · série replayable em `patches/` + fixtures default-off/absent/disabled + golden non-Fleet + 0 call sites.

## Wave 3 — B15b.2: auth + associação (gate G-2 = aprovação da allowlist de redação)
- [ ] T-301 · issuance/consume internal-only + state machine + store durável + idempotência (fixtures locais).
- [ ] T-302 · fixtures composite-deny/redaction nomeadas.

## Wave 4 — B15b.3: subscription v1
- [ ] T-401 · associação explícita + ordering/ack + heartbeat/TTLs + gap explícito.

## Wave 5 — B15b.4: replay/rollback operacional
- [ ] T-501 · epochs/boundaries + crash points + rollback do `isis-gateway.service` ensaiado.

## Wave 6 — B15b.5: validação live + closeout (gate G-3 = autorização live)
- [ ] T-601 · live validation (slice separadamente autorizado; downtime declarado ~10–20 min).
- [ ] T-602 · closeout: evidence buckets separados + G4 live closure + review final.

**Regras:** nada toca o checkout Hermes antes de G-1; nada ativa antes do slice próprio; `local_verified` nunca substitui `NOT_READY_HERMES_SEAM`.
