# B15B — Review Packet (B15b.0)

**Objeto do review:** `B15B-DECISION-MATRIX.md` (seções A/B/C) + `B15B-PLAN.md` v0.3 (contexto).
**Modo:** read-only. Nada implementado; nenhuma ativação; canário B15a.2 (TUI) segue como estava.

## Perguntas ao reviewer

1. **Completude:** as 11 decisões (A1–A11) cobrem integralmente os 7 itens do G4 §10 + os 4 do G4-CLOSURE §7? Alguma decisão está fora do corpus-fonte (valor inventado) ou faltando?
2. **Composite-deny (B):** a matriz cobre os 8 gates do blocker #3 (plugin allow-list, flag, seam, caller, sessão server-resolved, associação, capability, lifecycle) sem furos — hot-reload, malformed config, chamadas diretas e "herança" indevida entre camadas?
3. **Wire mapping (C):** respeita o G1 §3 (um vocabulário autoritativo, sem alias silencioso, colisão proibida, erro/versão por camada, default-off, seleção pelo Hermes owner)?
4. **Honestidade:** algo apresentado como verificado/aprovado indevidamente? (Status deve ser draft; propostas ≠ normativas; live = `NOT_READY_HERMES_SEAM`.)
5. **Gate G-0:** o que falta para o gate fechar (review sem BLOCKER/HIGH + sign-offs)?

## Fora de escopo

- Implementação (B15b.1+), ativação, edição do checkout Hermes, validação live.
- Re-litigar decisões já aprovadas no corpus (ex.: Option B como direção; sem wildcard v1) — apontar apenas se houver contradição real.

## Fontes

`B15B-PLAN.md` · `B15B-DECISION-MATRIX.md` · `G1-CONTRACT.md` · `G4-AUTH-LIFECYCLE.md` · `G4-CLOSURE.md` · `G4-SECURITY.md` · `B15A-EXECUTION-PLANS.md` (Reconciliation) · `B15-TUI-SEAM.md` · `transport-wave-parked.md`.
