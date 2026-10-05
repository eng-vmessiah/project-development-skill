# CONTEXT — b15b-gateway

- 2026-10-05 · Plano B15B v0.3 **aprovado pelo owner (Vitor)**. Ciclo de review: v0.1 `PASS_WITH_BLOCKERS` → v0.2 `PASS` (sem BLOCKER/HIGH).
- Escopo: Gateway de mensagens/API (caller autenticado Discord/Telegram/API; associação durable; replay/rollback do `isis-gateway.service`). Decisões G4 §10 + G4-CLOSURE §7 propostas em `B15B-DECISION-MATRIX.md` (sign-off pendente — gate G-0).
- Precondição satisfeita: B15a aprovado localmente (fases 1–3; canário live desde 04/10 22:41; canônica com delta zero). Readiness live segue `NOT_READY_HERMES_SEAM`.
- Gate G-0 = review independente sem BLOCKER/HIGH + sign-offs (owner/security/Hermes-owner roles — §D da matriz).
- Regras herdadas: nunca fabricar telemetria/estado; buckets de evidência separados (contract/fake/TUI/live); default-off até autorização própria por slice.
- Feature registrada no cockpit (padrão plan-cockpit); feedings no `pd` a cada transição.
