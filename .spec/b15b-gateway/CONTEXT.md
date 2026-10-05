# CONTEXT — b15b-gateway

## Decisions

- 2026-10-05 · Plano B15B v0.3 **aprovado pelo owner (Vitor)**. Ciclo de review: v0.1 `PASS_WITH_BLOCKERS` → v0.2 `PASS` (sem BLOCKER/HIGH).
- Escopo: Gateway de mensagens/API (caller autenticado Discord/Telegram/API; associação durable; replay/rollback do `isis-gateway.service`). Decisões G4 §10 + G4-CLOSURE §7 propostas em `B15B-DECISION-MATRIX.md` (sign-off pendente — gate G-0).
- Precondição satisfeita: B15a aprovado localmente (fases 1–3; canário live desde 04/10 22:41; canônica com delta zero). Readiness live segue `NOT_READY_HERMES_SEAM`.
- Gate G-0 = review independente sem BLOCKER/HIGH + sign-offs (owner/security/Hermes-owner roles — §D da matriz).
- Regras herdadas: nunca fabricar telemetria/estado; buckets de evidência separados (contract/fake/TUI/live); default-off até autorização própria por slice.
- Feature registrada no cockpit (padrão plan-cockpit); feedings no `pd` a cada transição.
- 2026-10-05 · Autorizações do owner ("autorizado"): **sign-off A1–A11 + mapping C** (§D da matriz) e **G-1 — edição do checkout Hermes** (série replayable, sem instalação). Wave 2 inicia somente após o G-0 fechar (review independente em curso).
- 2026-10-05 · **G-0 approved** (B15b.0 review `PASS_WITH_BLOCKERS` → fixes → `PASS`). Wave 1 fechada.
- 2026-10-05 · **T-201 CLOSED** — seam contract v0.3 (`PASS`; bounds congelados). **T-202 CLOSED + review `PASS`** — série `patches/b15b-seam/` (base `dc50153faf`; replay provado tree idêntico; 0 call sites; 7/7 fixtures). Wave 2 fechada.
- 2026-10-05 · **G-2 APPROVED** (owner) — allowlist/denylist de redação + 23 fixtures congeladas (`B15B-REDACTION-ALLOWLIST.md`). Wave 3 desbloqueada.
- 2026-10-05 · **T-301 entregue** — auth + associação local (`scripts/pd_fleet/gateway_auth.py`: tickets §1, consume atômico single-writer §4, idempotência §5, uniformidade externa §6, state machine §3; **22 fixtures G4 §9 verdes**). Review independente a dispatchar.
